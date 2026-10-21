"""BACK-2109: ``calls://?callees=`` collects every file's structure on every query.

The callers index is kept across host requests (``_INDEX_CACHE``, validated against the tree
stamp), but ``find_callees`` (depth 1), ``walk_callees`` (depth >= 2, ``?root=``) and the
``&detail`` params/effects collected the structure of every file again for each query, and
structure collection is most of a warm query (gdscript 58-68%, java depth 1 ~90%, measured
contended). A long-lived host (MCP, ``reveal.api``) asking about the same tree twice paid it
twice. Counts here are deterministic: ``collect_structures`` calls and per-file analyses.
"""
import json
import os
import subprocess
import sys
import time

import pytest

from reveal import api, mcp_server
from reveal.adapters.ast import analysis
from reveal.adapters.calls import adapter as calls_adapter, index
from reveal.utils import gitignore, request_cache
from reveal.utils.exclusions import exclusion_scope

pytestmark = pytest.mark.component


def write(path, source, *, age=60):
    """Files modified at or after a request start are never stamped as current."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    stamp = time.time_ns() - age * 1_000_000_000
    os.utime(path, ns=(stamp, stamp))


def make_tree(root):
    write(root / 'app.py', 'from pkg.lib import other\n\ndef run():\n    helper()\n    other()\n\n'
                           'def helper():\n    leaf()\n    print(len([]))\n\ndef leaf():\n    pass\n')
    write(root / 'pkg' / 'lib.py', 'def other():\n    return sorted([2, 1])\n')
    write(root / 'pkg' / 'deep' / 'more.py', 'def run():\n    other_deep()\n\ndef other_deep():\n    pass\n')
    return root


@pytest.fixture(autouse=True)
def memo_only(monkeypatch):
    """The in-process caches alone: no structure disk cache, no stamps from other tests."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    request_cache._STAMPS.clear()
    yield
    request_cache._STAMPS.clear()


class Counts:
    def __init__(self):
        self.collections = []
        self.analyses = 0


@pytest.fixture
def counts(monkeypatch):
    """collect_structures calls through every module that calls it for a callee query, and
    per-file analyses (``analyze_file_outcome``, looked up at call time by the collector)."""
    seen = Counts()
    real_collect = analysis.collect_structures

    def collect(path, *args, **kwargs):
        seen.collections.append(os.path.basename(str(path)))
        return real_collect(path, *args, **kwargs)

    for module in (index, calls_adapter):
        monkeypatch.setattr(module, 'collect_structures', collect)
    real_analyze = analysis.analyze_file_outcome

    def analyze(*args, **kwargs):
        seen.analyses += 1
        return real_analyze(*args, **kwargs)

    monkeypatch.setattr(analysis, 'analyze_file_outcome', analyze)
    return seen


def query(root, suffix):
    return api.query(f'calls://{root.as_posix()}?{suffix}')


def dump(result):
    return json.dumps(result, sort_keys=True, default=str)


CALLEE_QUERIES = ('callees=run', 'callees=run&depth=2', 'callees=run&detail', 'callees=app.py:run',
                  'root=run&depth=3')


def test_repeated_callees_query_collects_once(tmp_path, counts):
    """The same ?callees= twice in one process, two host requests: one collection, three files analysed."""
    root = make_tree(tmp_path / 'one')
    first = query(root, 'callees=run')
    second = query(root, 'callees=run')
    assert dump(second) == dump(first)
    assert [m['function'] for m in first['matches']] == ['run', 'run']
    assert counts.collections == ['one'], counts.collections
    assert counts.analyses == 3


def test_depth_detail_file_filter_and_root_walk_share_one_collection(tmp_path, counts):
    """find_callees, walk_callees (depth >= 2, ?root=) and --detail read one stored artifact."""
    root = make_tree(tmp_path / 'shared')
    answers = [dump(query(root, suffix)) for suffix in CALLEE_QUERIES]
    assert counts.collections == ['shared'], counts.collections
    assert counts.analyses == 3
    assert [dump(query(root, suffix)) for suffix in CALLEE_QUERIES] == answers
    assert counts.collections == ['shared'], counts.collections


# ------------------------------------------------------------- controls

def test_a_different_root_misses(tmp_path, counts):
    """Negative control: another root is another collection."""
    one = make_tree(tmp_path / 'one')
    two = make_tree(tmp_path / 'two')
    query(one, 'callees=run')
    query(two, 'callees=run')
    assert counts.collections == ['one', 'two'], counts.collections
    assert counts.analyses == 6


# ------------------------------------------------- answers equal the cache-off answer
#
# The positive control is the same query with the cache switched off (no host request is seen,
# so nothing is read or stored). Every query of CALLEE_QUERIES is compared as sorted JSON,
# answer and meta diagnostics together, cold, warm and after each edit.

@pytest.fixture
def cache_off(monkeypatch):
    def answers(root, suffixes=CALLEE_QUERIES):
        with monkeypatch.context() as patch:
            patch.setattr(index, 'in_host_request', lambda: False)
            return [dump(query(root, suffix)) for suffix in suffixes]
    return answers


def answers(root, suffixes=CALLEE_QUERIES):
    return [dump(query(root, suffix)) for suffix in suffixes]


def append(path, text):
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(text)


def matched(answer):
    return sorted((os.path.basename(m['file']), m['function'], tuple(m['calls'])) for m in json.loads(answer)['matches'])


def test_cache_off_cold_and_warm_answers_are_byte_equal(tmp_path, counts, cache_off):
    root = make_tree(tmp_path / 'eq')
    off = cache_off(root)
    assert len(counts.collections) == len(CALLEE_QUERIES)
    counts.collections.clear()
    cold = answers(root)
    warm = answers(root)
    assert cold == off and warm == off
    assert counts.collections == ['eq'], counts.collections


def test_in_place_edit_is_seen(tmp_path, counts, cache_off):
    """BACK-2093 R5 for callees: an append deep in the tree moves no directory mtime."""
    root = make_tree(tmp_path / 'r5')
    assert answers(root) == cache_off(root)
    append(root / 'pkg' / 'deep' / 'more.py', '\ndef added():\n    other_deep()\n\ndef run2():\n    added()\n')
    after = answers(root)
    assert after == cache_off(root)
    assert ('more.py', 'run', ('other_deep',)) in matched(after[0])
    assert dump(query(root, 'callees=run2')) == cache_off(root, ('callees=run2',))[0]
    assert matched(dump(query(root, 'callees=run2'))) == [('more.py', 'run2', ('added',))]


def test_new_file_two_levels_down_is_seen(tmp_path, cache_off):
    """BACK-2093 R13 for callees: a new file in pkg/deep/deeper moves only that directory's mtime."""
    root = make_tree(tmp_path / 'r13')
    (root / 'pkg' / 'deep' / 'deeper').mkdir()
    first = answers(root)
    assert first == cache_off(root)
    (root / 'pkg' / 'deep' / 'deeper' / 'new.py').write_text('def run():\n    brand_new()\n', encoding='utf-8')
    after = answers(root)
    assert after == cache_off(root) and after != first
    assert ('new.py', 'run', ('brand_new',)) in matched(after[0])


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX permission bits: chmod 000 does not deny reads on Windows')
@pytest.mark.skipif(hasattr(os, 'geteuid') and os.geteuid() == 0, reason='root reads a mode-000 file')
def test_unreadable_file_is_returned_never_stored(tmp_path, counts, cache_off):
    """chmod moves only ctime, so no tree stamp sees the file become readable again (BACK-2093 rule)."""
    root = make_tree(tmp_path / 'perm')
    lib = root / 'pkg' / 'lib.py'
    lib.chmod(0)
    try:
        failed = answers(root, ('callees=other',))
        assert 'PermissionError' in failed[0]
        assert failed == cache_off(root, ('callees=other',))
        assert 'perm' not in [os.path.basename(key) for key in index._CALLEE_CACHE]
    finally:
        lib.chmod(0o644)
    healed = answers(root, ('callees=other',))
    assert healed == cache_off(root, ('callees=other',))
    assert matched(healed[0]) == [('lib.py', 'other', ())]
    assert 'PermissionError' not in healed[0]


def _git_tree(root):
    make_tree(root)
    subprocess.run(['git', 'init', '-q', str(root)], check=True, timeout=60)
    write(root / '.gitignore', 'ign/\n')
    write(root / 'ign' / 'gen.py', 'def run():\n    generated()\n')
    return root


def test_gitignore_switch_and_gitignore_edit(tmp_path, counts, cache_off):
    root = _git_tree(tmp_path / 'gi')
    off_switch = ('callees=run&respect_gitignore=false',)
    default = answers(root, ('callees=run',))
    without = answers(root, off_switch)
    assert default == cache_off(root, ('callees=run',))
    assert without == cache_off(root, off_switch)
    assert 'gen.py' not in default[0] and 'gen.py' in without[0]
    # Each switch is its own scope; a repeat of each reads its own source.
    assert answers(root, ('callees=run',)) == default and answers(root, off_switch) == without
    # An edit to an ignored file: the stamp (default switch) cannot see it, so a source
    # collected with the switch off must not outlive its request (the BACK-2118 rule).
    append(root / 'ign' / 'gen.py', '\ndef run3():\n    more()\n')
    assert answers(root, ('callees=run3&respect_gitignore=false',)) == cache_off(
        root, ('callees=run3&respect_gitignore=false',))
    write(root / 'ign' / 'gen.py', 'def run():\n    regenerated()\n', age=120)
    assert answers(root, off_switch) == cache_off(root, off_switch)
    assert 'regenerated' in answers(root, off_switch)[0]
    # Toggling the ignore rule itself. gitignore's own rule memo outlives a request (BACK-2117,
    # open): the cache-off control is stale without this clear too, so it is cleared here.
    write(root / '.gitignore', '# nothing ignored\n', age=30)
    gitignore.clear_cache()
    toggled = answers(root, ('callees=run',))
    assert toggled == cache_off(root, ('callees=run',))
    assert 'gen.py' in toggled[0]


def test_exclusion_scope_is_part_of_the_stored_scope(tmp_path, counts, cache_off):
    root = make_tree(tmp_path / 'ex')
    full = answers(root)
    with exclusion_scope(root, ['pkg/deep']):
        narrowed = answers(root)
        assert narrowed == cache_off(root)
        assert answers(root) == narrowed
    assert narrowed != full
    assert all('more.py' not in answer for answer in narrowed)
    assert answers(root) == full == cache_off(root)
    # Two scopes, two collections (the cache-off runs collect for themselves).
    assert counts.collections.count('ex') == 2 + 2 * len(CALLEE_QUERIES)


def test_edit_inside_one_request_is_seen_by_the_next(tmp_path, counts, cache_off):
    """A source stored by a request during which its tree changed is never stamped, so the
    next request rebuilds it. Within the request it is reused (one request, one view)."""
    root = make_tree(tmp_path / 'inreq')
    with request_cache.host_request():
        before = answers(root, ('callees=leaf',))
        write(root / 'app.py', 'def leaf():\n    changed()\n', age=0)
        assert answers(root, ('callees=leaf',)) == before
    after = answers(root, ('callees=leaf',))
    assert after == cache_off(root, ('callees=leaf',)) and after != before
    assert matched(after[0]) == [('app.py', 'leaf', ('changed',))]


def test_outside_a_host_request_nothing_is_read_or_stored(tmp_path, counts):
    root = make_tree(tmp_path / 'outside')
    assert not request_cache.in_host_request()
    direct = index.find_callees(str(root), 'leaf')
    assert index._CALLEE_CACHE == {}
    query(root, 'callees=leaf')                       # stored by a host request
    assert len(index._CALLEE_CACHE) == 1
    write(root / 'app.py', 'def leaf():\n    edited()\n')
    edited = index.find_callees(str(root), 'leaf')    # not read: no request revalidated it
    assert [m['calls'] for m in direct['matches']] == [[]]
    assert [m['calls'] for m in edited['matches']] == [['edited']]
    assert counts.collections == ['outside'] * 3


def test_lru_evicts_the_least_recent_root(tmp_path, counts, cache_off):
    roots = [make_tree(tmp_path / f'lru{i}') for i in range(index._CALLEE_CACHE_MAX + 1)]
    first = [answers(root, ('callees=run',)) for root in roots]
    assert len(index._CALLEE_CACHE) == index._CALLEE_CACHE_MAX
    assert str(roots[0]) not in index._CALLEE_CACHE and str(roots[-1]) in index._CALLEE_CACHE
    counts.collections.clear()
    assert answers(roots[0], ('callees=run',)) == first[0] == cache_off(roots[0], ('callees=run',))
    assert counts.collections == ['lru0', 'lru0']    # the miss, then the cache-off control
    assert str(roots[1]) not in index._CALLEE_CACHE  # now the least recent


def test_a_third_scope_drops_the_oldest_of_a_root(tmp_path, counts):
    root = make_tree(tmp_path / 'scopes')
    query(root, 'callees=run')
    with exclusion_scope(root, ['pkg']):
        query(root, 'callees=run')
    with exclusion_scope(root, ['pkg/deep']):
        query(root, 'callees=run')
    sources = index._CALLEE_CACHE[str(root)]
    assert len(sources) == index._CALLEE_SCOPES_MAX
    assert [source.scope.exclusions[1] for source in sources] == [('pkg',), ('pkg/deep',)]


def test_a_relative_root_follows_the_working_directory(tmp_path, monkeypatch, cache_off):
    """Two trees whose tree stamps are equal (same relative paths, sizes and mtimes): the
    relative root `proj` names a different tree once the working directory moves."""
    for side, callee in (('a', 'aaa'), ('b', 'bbb')):
        write(tmp_path / side / 'proj' / 'm.py', f'def run():\n    {callee}()\n', age=90)
    stamp = os.stat(tmp_path / 'a' / 'proj' / 'm.py').st_mtime_ns
    os.utime(tmp_path / 'b' / 'proj' / 'm.py', ns=(stamp, stamp))
    seen = []
    for side in ('a', 'b', 'a'):
        monkeypatch.chdir(tmp_path / side)
        answer = dump(api.query('calls://proj?callees=run'))
        with monkeypatch.context() as patch:
            patch.setattr(index, 'in_host_request', lambda: False)
            assert answer == dump(api.query('calls://proj?callees=run'))
        seen.append(json.loads(answer)['matches'][0]['calls'])
    assert seen == [['aaa'], ['bbb'], ['aaa']]


def test_mcp_repeats_read_the_stored_source(tmp_path, counts):
    """Sibling host: MCP tools run as host requests too."""
    root = make_tree(tmp_path / 'mcp')
    first = mcp_server.reveal_query(f'calls://{root.as_posix()}?callees=run&depth=2')
    assert mcp_server.reveal_query(f'calls://{root.as_posix()}?callees=run&depth=2') == first
    assert counts.collections == ['mcp']
