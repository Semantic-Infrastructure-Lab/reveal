"""BACK-2093 R7: a long-lived host never keeps a callers index built while a file was unreadable.

``chmod 000 other.py``, an MCP ``calls://...?target=helper`` request ("1 file(s) could not
be analyzed completely (PermissionError)"), ``chmod 644``, a second request: it still said
so, because the validated callers index survives a request while the tree stamp (path,
mtime, size) is unchanged and ``chmod`` moves only ctime. An index whose skipped files
failed for an environmental reason (an ``OSError``, a lost worker) is returned but never
stored, as the imports caches do since BACK-2083. A failure the content causes may stay.
"""

import os
import time
from pathlib import Path

import pytest

from reveal import base as reveal_base
from reveal import mcp_server
from reveal.adapters.ast import analysis
from reveal.adapters.calls import index
from reveal.utils import request_cache

pytestmark = pytest.mark.component

POSIX_CHMOD = pytest.mark.skipif(os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                                 reason='chmod 000 does not deny a read on Windows or to root')
SKIPPED = 'could not be analyzed'


def write(path, source):
    """Aged, so the first request's index is stamped as current (BACK-1825)."""
    path.write_text(source, encoding='utf-8')
    stamp = time.time_ns() - 60_000_000_000
    os.utime(path, ns=(stamp, stamp))


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    request_cache._STAMPS.clear()
    root = tmp_path / 'r7'
    root.mkdir()
    write(root / 'lib.py', 'def helper():\n    pass\n')
    write(root / 'use.py', 'from lib import helper\n\ndef a():\n    helper()\n')
    write(root / 'other.py', 'from lib import helper\n\ndef b():\n    helper()\n')
    yield root
    request_cache._STAMPS.clear()


@pytest.fixture
def builds(monkeypatch):
    """Callers-index builds (every miss reaches _cache_callers_index)."""
    calls = []
    real = index._cache_callers_index

    def counting(dir_str, *args, **kwargs):
        calls.append(dir_str)
        return real(dir_str, *args, **kwargs)

    monkeypatch.setattr(index, '_cache_callers_index', counting)
    return calls


def request(root):
    return mcp_server.reveal_query(f'calls://{root.as_posix()}?target=helper')


def fail_one(monkeypatch, name, cause):
    """*name*'s structure analysis fails with *cause* ("ErrorType: message")."""
    real = analysis.analyze_file_outcome

    def outcome(file_path, *args, **kwargs):
        if Path(file_path).name == name:
            return None, cause
        return real(file_path, *args, **kwargs)

    monkeypatch.setattr(analysis, 'analyze_file_outcome', outcome)


@POSIX_CHMOD
def test_recovered_chmod_is_seen_by_the_next_request(tree, builds):
    """The reported reproduction as written."""
    os.chmod(tree / 'other.py', 0)
    try:
        assert SKIPPED in request(tree)
    finally:
        os.chmod(tree / 'other.py', 0o644)
    second = request(tree)
    assert SKIPPED not in second and ' b' in second, second
    assert len(builds) == 2


def test_recovered_read_is_seen_by_the_next_request(tree, builds, monkeypatch):
    real = reveal_base.FileAnalyzer._read_file

    def read(self):
        if Path(self.path).name == 'other.py':
            raise PermissionError(13, 'Permission denied', str(self.path))
        return real(self)

    with monkeypatch.context() as denied:
        # calls:// collects structures serially in this process.
        denied.setattr(reveal_base.FileAnalyzer, '_read_file', read)  # noqa: V036 reviewed: serial
        assert SKIPPED in request(tree)
    second = request(tree)
    assert SKIPPED not in second and ' b' in second, second
    assert len(builds) == 2, 'the index built while other.py was unreadable was kept'


def test_a_lost_worker_is_not_stored(tree, builds, monkeypatch):
    with monkeypatch.context() as lost:
        fail_one(lost, 'other.py', 'BrokenProcessPool: A process in the process pool was terminated abruptly')
        assert SKIPPED in request(tree)
    assert SKIPPED not in request(tree)
    assert len(builds) == 2


# ------------------------------------------------------------- negative controls

def test_a_failure_the_content_causes_is_still_stored(tree, builds, monkeypatch):
    """Same bytes, same failure: the second request reuses the index (counted builds)."""
    fail_one(monkeypatch, 'other.py', 'RecursionError: maximum recursion depth exceeded')
    first = request(tree)
    assert SKIPPED in first
    # Only the cold build echoes the per-file "Failed to analyze" stderr line; the answer
    # and its analysis_failed disclosure are the same.
    assert request(tree) == first.split('\n[stderr: ')[0]
    assert len(builds) == 1, builds


def test_a_clean_tree_still_reuses_the_index(tree, builds):
    first = request(tree)
    assert SKIPPED not in first and ' a' in first and ' b' in first
    assert request(tree) == first
    assert len(builds) == 1, builds
