"""BACK-2093 R5, R13, R8: ``reveal.api.query`` serves calls indexes built before an edit.

The calls indexes (``_INDEX_CACHE``, ``_REFERENCE_CACHE``) are keyed on the mtimes of the
directory and its immediate child directories, so an in-place edit at any depth, or a
new file two directories down, leaves the key unchanged. A long-lived MCP host is fresh
anyway: every request resets the owner-registered caches under its request lock, and a
validated index survives only while the tree stamp (path, mtime, size of every walked
file) is unchanged. ``reveal.api.query`` took no such reset, so a library host calling it
twice in one process got the first answer back. The same sequence through
``mcp_server.reveal_query`` is the sibling control.
"""

import os
import time

import pytest

from reveal import api, mcp_server
from reveal.adapters.calls import index
from reveal.utils import request_cache

pytestmark = pytest.mark.component


def write(path, source, *, age=60):
    """Files modified at or after a request start are never stamped as current."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    stamp = time.time_ns() - age * 1_000_000_000
    os.utime(path, ns=(stamp, stamp))


def append(path, text):
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(text)


def api_callers(root):
    result = api.query(f'calls://{root.as_posix()}?target=helper')
    return sorted((os.path.basename(c['file']), c['caller']) for level in result['levels'] for c in level['callers'])


def api_uncalled(root):
    return sorted(entry['name'] for entry in api.query(f'calls://{root.as_posix()}?uncalled')['entries'])


@pytest.fixture(autouse=True)
def memo_only(monkeypatch):
    """The in-process indexes alone: no structure disk cache, no stamps from other tests."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    request_cache._STAMPS.clear()
    yield
    request_cache._STAMPS.clear()


@pytest.fixture
def builds(monkeypatch):
    """Callers-index builds (every miss stores through _cache_callers_index)."""
    calls = []
    real = index._cache_callers_index

    def counting(dir_str, *args, **kwargs):
        calls.append(dir_str)
        return real(dir_str, *args, **kwargs)

    monkeypatch.setattr(index, '_cache_callers_index', counting)
    return calls


@pytest.fixture
def r5(tmp_path):
    root = tmp_path / 'r5'
    write(root / 'pkg' / 'lib.py', 'def helper():\n    pass\n')
    write(root / 'pkg' / 'sub' / 'use.py', 'from pkg.lib import helper\n\ndef one():\n    helper()\n')
    return root


def test_in_place_edit_is_seen_by_the_next_query(r5):
    """R5: the directory mtimes do not move when a file deep in the tree is appended to."""
    assert api_callers(r5) == [('use.py', 'one')]
    append(r5 / 'pkg' / 'sub' / 'use.py', '\ndef added():\n    helper()\n')
    assert api_callers(r5) == [('use.py', 'added'), ('use.py', 'one')]


def test_new_file_two_levels_down_is_seen_by_the_next_query(tmp_path):
    """R13: a file created in pkg/deep/ moves only pkg/deep's mtime, which the key does not stat."""
    root = tmp_path / 'r13'
    write(root / 'lib.py', 'def helper():\n    pass\n')
    write(root / 'pkg' / 'mid.py', 'x = 1\n')
    (root / 'pkg' / 'deep').mkdir()
    assert api_callers(root) == []
    (root / 'pkg' / 'deep' / 'new.py').write_text(
        'from lib import helper\n\ndef deep_caller():\n    helper()\n', encoding='utf-8')
    assert api_callers(root) == [('new.py', 'deep_caller')]


def test_uncalled_sees_a_bare_reference_added_in_place(tmp_path):
    """R8: ``REGISTRY = [cb]`` is a use only _REFERENCE_CACHE records; clearing _INDEX_CACHE
    alone did not fix it."""
    root = tmp_path / 'r8'
    write(root / 'main.py', 'def cb():\n    return 1\n\ndef run():\n    return 2\n')
    assert api_uncalled(root) == ['cb', 'run']
    append(root / 'main.py', '\nREGISTRY = [cb]\n')
    assert api_uncalled(root) == ['run']


# ------------------------------------------------------------- controls

def test_mcp_sees_the_same_in_place_edit(r5):
    """Sibling path: the MCP request reset already makes this sequence fresh."""
    assert ' one' in mcp_server.reveal_query(f'calls://{r5.as_posix()}?target=helper')
    append(r5 / 'pkg' / 'sub' / 'use.py', '\ndef added():\n    helper()\n')
    assert ' added' in mcp_server.reveal_query(f'calls://{r5.as_posix()}?target=helper')


def test_unchanged_tree_reuses_the_index_across_queries(r5, builds):
    """Negative control: no edit, no rebuild (counted builds, not timing)."""
    first = api_callers(r5)
    assert api_callers(r5) == first == [('use.py', 'one')]
    assert api_uncalled(r5) == ['one']
    assert len(builds) == 1, builds


def test_a_query_inside_a_request_joins_it(tmp_path, builds):
    """Within one request the index is reused: a nested request neither resets nor seals,
    even for files too new to be stamped (no aging here)."""
    root = tmp_path / 'fresh'
    (root / 'pkg').mkdir(parents=True)
    (root / 'pkg' / 'lib.py').write_text('def helper():\n    pass\n\ndef one():\n    helper()\n', encoding='utf-8')
    with request_cache.host_request():
        assert api_callers(root) == [('lib.py', 'one')]
        assert api_callers(root) == [('lib.py', 'one')]
    assert len(builds) == 1, builds
