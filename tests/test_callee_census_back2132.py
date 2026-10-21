"""BACK-2132: every ``?callees=`` answer walked the tree again for its language census.

``confidence.build_meta`` counts the files of each language (``language_census``) to weight the
answer's confidence, pick the dispatch vocabulary and name an unmeasured language (W-CALLS-10).
BACK-2109 keeps the callee collection per root across host requests, validated by the tree stamp,
but the census walk still ran on every query: 31-34% of a warm gdscript depth-1 query, 12% dart,
8% java (contended). The census is a function of the same files and scope the stored source was
collected under, so it is carried on that source. Counts here are deterministic: census walks.

What must not change: the answer and its diagnostics, byte for byte, against the cache-off answer.
A census that lost input (an unreadable directory) or saw nothing (a hidden tree, whose
``scope_hidden`` warning counts entries a tree stamp does not cover) is never carried.
"""
import json
import os
import subprocess
import sys
import time

import pytest

from reveal import api
from reveal.adapters.calls import confidence, index
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
    write(root / 'web' / 'view.js', 'function run() { render(); }\nfunction render() {}\n')
    return root


@pytest.fixture(autouse=True)
def memo_only(monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    request_cache._STAMPS.clear()
    yield
    request_cache._STAMPS.clear()


@pytest.fixture
def walks(monkeypatch):
    """Roots of every census walk ``language_census`` starts."""
    seen = []
    real = confidence.census_for_path

    def counting(path, *args, **kwargs):
        seen.append(os.path.basename(str(path)))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(confidence, 'census_for_path', counting)
    return seen


def query(root, suffix):
    return api.query(f'calls://{root.as_posix()}?{suffix}')


def dump(result):
    return json.dumps(result, sort_keys=True, default=str)


SHAPES = ('callees=run', 'callees=run&depth=2', 'callees=run&depth=3&detail', 'callees=app.py:run',
          'callees=run&builtins=true')


@pytest.fixture
def cache_off(monkeypatch):
    def answers(root, suffixes=SHAPES):
        with monkeypatch.context() as patch:
            patch.setattr(index, 'in_host_request', lambda: False)
            return [dump(query(root, suffix)) for suffix in suffixes]
    return answers


def answers(root, suffixes=SHAPES):
    return [dump(query(root, suffix)) for suffix in suffixes]


def test_a_repeated_callees_query_walks_for_its_census_once(tmp_path, walks):
    """Every query shape of one root: one census walk, whatever the number of queries."""
    root = make_tree(tmp_path / 'once')
    first = answers(root)
    assert walks == ['once'], walks
    assert answers(root) == first
    assert walks == ['once'], walks


def test_outside_a_host_request_every_query_walks(tmp_path, walks, monkeypatch):
    """Nothing revalidates a source outside a host request, so none carries a census."""
    root = make_tree(tmp_path / 'outside')
    monkeypatch.setattr(index, 'in_host_request', lambda: False)
    query(root, 'callees=run')
    query(root, 'callees=run')
    assert walks == ['outside'] * 2, walks


def test_other_modes_keep_their_own_census(tmp_path, walks):
    """Negative control: callers and uncalled hold no stored source; each still counts languages."""
    root = make_tree(tmp_path / 'modes')
    query(root, 'callers=leaf')
    query(root, 'callers=leaf')
    query(root, 'uncalled')
    assert walks == ['modes'] * 3, walks


def test_a_different_root_is_a_different_census(tmp_path, walks):
    one, two = make_tree(tmp_path / 'one'), make_tree(tmp_path / 'two')
    query(one, 'callees=run')
    query(two, 'callees=run')
    assert walks == ['one', 'two'], walks


def test_a_file_target_counts_its_own_file(tmp_path, walks, cache_off):
    """calls://dir/app.py?callees=run reads the directory's source but its census is the file's."""
    root = make_tree(tmp_path / 'file')
    query(root, 'callees=run')
    target = root / 'app.py'
    one = [dump(query(target, suffix)) for suffix in SHAPES]
    assert one == cache_off(target)
    assert [dump(query(target, suffix)) for suffix in SHAPES] == one
    meta = json.loads(one[0])['meta']
    assert meta['confidence'] == confidence.build_meta(str(target))['confidence']


# ---------------------------------------------------- answers and diagnostics stay byte-equal

def test_cold_and_warm_equal_cache_off_for_each_language_mix(tmp_path, cache_off):
    """Meta carries the census: weighted confidence, the dominant language's vocabulary, and for an
    unmeasured language (elixir) a null confidence naming it (W-CALLS-10)."""
    plain = make_tree(tmp_path / 'plain')
    unmeasured = make_tree(tmp_path / 'unmeasured')
    write(unmeasured / 'lib.ex', 'defmodule A do\n  def run do\n    b()\n  end\nend\n')
    single = tmp_path / 'single'
    write(single / 'm.py', 'def run():\n    x()\n')
    for root in (plain, unmeasured, single):
        off = cache_off(root)
        assert answers(root) == off, root
        assert answers(root) == off, root
    assert '"W-CALLS-10"' in answers(unmeasured, ('callees=run',))[0]
    assert '"W-CALLS-10"' not in answers(plain, ('callees=run',))[0]


def test_an_edit_that_adds_a_language_moves_the_confidence(tmp_path, cache_off):
    root = make_tree(tmp_path / 'edit')
    before = answers(root)
    assert before == cache_off(root)
    write(root / 'extra.ex', 'defmodule B do\n  def go do\n    c()\n  end\nend\n')
    after = answers(root)
    assert after == cache_off(root) and after != before
    assert '"W-CALLS-10"' in after[0]
    (root / 'extra.ex').unlink()
    assert answers(root) == before == cache_off(root)


def test_new_file_two_levels_down_is_counted(tmp_path, cache_off):
    root = make_tree(tmp_path / 'deep')
    (root / 'pkg' / 'deep' / 'deeper').mkdir()
    first = answers(root)
    assert first == cache_off(root)
    write(root / 'pkg' / 'deep' / 'deeper' / 'new.ex', 'defmodule C do\nend\n')
    after = answers(root)
    assert after == cache_off(root) and after != first


def test_exclusion_scope_is_part_of_the_carried_census(tmp_path, cache_off):
    root = make_tree(tmp_path / 'ex')
    full = answers(root)
    with exclusion_scope(root, ['web']):
        narrowed = answers(root)
        assert narrowed == cache_off(root)
    assert narrowed != full
    assert answers(root) == full == cache_off(root)


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX permission bits')
@pytest.mark.skipif(hasattr(os, 'geteuid') and os.geteuid() == 0, reason='root lists a mode-000 directory')
def test_an_unreadable_directory_is_reported_by_every_query_and_heals(tmp_path, walks, cache_off):
    """BACK-2093 rule: a directory the census could not list is a loss the answer must name, every
    time, and never one a stored census hides. Unreadable before the first query and after a warm one."""
    root = make_tree(tmp_path / 'perm')
    web = root / 'web'
    web.chmod(0)
    try:
        for _ in range(2):
            got = answers(root)
            assert got == cache_off(root)
            assert 'PermissionError' in got[0]
    finally:
        web.chmod(0o755)
    healed = answers(root)
    assert healed == cache_off(root) and 'PermissionError' not in healed[0]
    warm = answers(root)
    assert warm == healed
    web.chmod(0)
    try:
        lost = answers(root)
        assert lost == cache_off(root)
        assert 'PermissionError' in lost[0]
    finally:
        web.chmod(0o755)
    assert answers(root) == healed


def test_a_fully_hidden_tree_keeps_its_scope_hidden_warning(tmp_path, cache_off):
    """Nothing left to analyze: the warning counts entries the walk hid, which the stamp cannot see
    change. That census is never carried; the warning comes from a live walk every time."""
    root = tmp_path / 'hidden'
    subprocess.run(['git', 'init', '-q', str(root)], check=True, timeout=60)
    write(root / '.gitignore', 'src/\n')
    write(root / 'src' / 'a.py', 'def run():\n    x()\n')
    first = answers(root, ('callees=run',))
    assert first == cache_off(root, ('callees=run',))
    assert 'scope_hidden' in first[0]
    write(root / '.gitignore', 'src/\nbuild/\nout/\n', age=30)
    (root / 'build').mkdir()
    write(root / 'build' / 'b.py', 'def go():\n    y()\n')
    gitignore.clear_cache()
    second = answers(root, ('callees=run',))
    assert second == cache_off(root, ('callees=run',))
    assert 'scope_hidden' in second[0] and second != first


def test_a_census_that_lost_input_is_not_carried(tmp_path, walks, monkeypatch):
    """The census walk itself could not list a directory the collection could (a race, a mount):
    that failure reaches this answer and every later one, never a carried census without it."""
    root = make_tree(tmp_path / 'lost')
    real = confidence.census_for_path
    error = PermissionError(13, 'Permission denied', str(root / 'web'))

    def failing(path, *args, on_error=None, **kwargs):
        on_error(error)
        return real(path, *args, on_error=on_error, **kwargs)

    monkeypatch.setattr(confidence, 'census_for_path', failing)
    first, second = answers(root, ('callees=run', 'callees=run'))
    assert first == second
    assert 'Permission denied' in first
