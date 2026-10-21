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
import time

import pytest

from reveal import api
from reveal.adapters.ast import analysis
from reveal.adapters.calls import adapter as calls_adapter, index
from reveal.utils import request_cache

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
