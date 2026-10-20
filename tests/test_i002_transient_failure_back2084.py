"""BACK-2084: I002 never keeps an unreadable file or a lost worker as the tree's graph.

BACK-2083 stopped the imports caches from storing a failure the file's content did not
cause; I002's own graph caches still did. ``chmod 000 b.py`` on an a.py <-> b.py cycle,
``reveal check --select I002`` (0 issues, b.py's edges unseen), ``chmod 644``: every later
run still reported 0, because ``chmod`` moves only ctime and the ``import_graph_v4`` disk
entry is keyed on mtime and size. A long-lived host kept the same graph in ``_graph_cache``
across requests, since its tree stamp is stat-based too. A genuine syntax error of
unchanged content is still cached in both layers: the same bytes fail the same way.
"""

import json
import os
import time
from pathlib import Path

import pytest

from conftest import _clear_module_caches, _run_reveal_direct
from reveal import base as reveal_base
from reveal import mcp_server
from reveal.rules.imports import I002 as i002
from reveal.utils import request_cache

pytestmark = [pytest.mark.integration, pytest.mark.disk_cache]

POSIX_CHMOD = pytest.mark.skipif(os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                                 reason='chmod 000 does not deny a read on Windows or to root')


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """proj/{a.py: import b, b.py: import a}; the cache dir lives beside it, outside the tree."""
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="p"\n', encoding='utf-8')
    (root / 'a.py').write_text('import b\n', encoding='utf-8')
    (root / 'b.py').write_text('import a\n', encoding='utf-8')
    _clear_module_caches()
    yield root.resolve()
    _clear_module_caches()


@pytest.fixture
def deny(monkeypatch):
    """Paths whose read raises PermissionError, the way an unreadable file does."""
    denied = set()
    real = reveal_base.FileAnalyzer._read_file

    def read(self):
        if Path(self.path).resolve() in denied:
            raise PermissionError(13, 'Permission denied', str(self.path))
        return real(self)

    # Reaches extraction under every start method: I002 extracts serially below
    # _GRAPH_PARALLEL_MIN_FILES and the suite sets REVEAL_MAX_WORKERS=1.
    monkeypatch.setattr(reveal_base.FileAnalyzer, '_read_file', read)  # noqa: V036 reviewed: serial
    return denied


@pytest.fixture
def builds(monkeypatch):
    """Graph builds from extraction, i.e. misses of both I002 graph caches."""
    calls = []
    real = i002.I002._collect_raw_imports

    def counting(self, directory, **kwargs):
        calls.append(directory)
        return real(self, directory, **kwargs)

    monkeypatch.setattr(i002.I002, '_collect_raw_imports', counting)
    return calls


def _check(root):
    """(total I002 issues, scan disclosures) of one CLI run, then forget every in-process
    cache, so the next run is a fresh process that only the disk cache can answer."""
    result = _run_reveal_direct('check', root, '--select', 'I002', '--format', 'json')
    _clear_module_caches()
    summary = json.loads(result.stdout)['summary']
    return summary['total_issues'], summary['scan_disclosures']


def _age(root):
    """Files modified at or after a request start are never stamped as current."""
    aged = time.time_ns() - 10_000_000_000
    for path in root.rglob('*'):
        os.utime(path, ns=(aged, aged))


def _host_check(root):
    return mcp_server.reveal_check(str(root), select='I002').count('[I002]')


# ------------------------------------------------------------- disk cache, through the CLI

@POSIX_CHMOD
def test_recovered_chmod_is_seen_on_the_next_run(proj):
    """The reported reproduction as written: chmod 000, run, chmod 644, run."""
    target = proj / 'b.py'
    os.chmod(target, 0)
    try:
        issues, disclosures = _check(proj)
        assert issues == 0 and disclosures, 'fixture: the unreadable b.py hides the cycle and says so'
    finally:
        os.chmod(target, 0o644)
    assert _check(proj) == (2, []), 'the unreadable run was served again after b.py became readable'


def test_recovered_read_is_seen_on_the_next_run(proj, deny, builds):
    deny.add(proj / 'b.py')
    assert _check(proj)[0] == 0
    deny.clear()
    assert _check(proj) == (2, [])
    assert len(builds) == 2, 'a graph holding an unreadable file was stored and served'


def test_lost_file_is_not_stored(proj, monkeypatch, builds):
    from test_pool_lost_files_back1726 import _BreaksOnSubmit
    for i in range(4):
        (proj / f'c{i}.py').write_text('import os\n', encoding='utf-8')
    with monkeypatch.context() as pool:
        pool.setenv('REVEAL_MAX_WORKERS', '2')
        pool.setattr(i002, '_GRAPH_PARALLEL_MIN_FILES', 1)
        pool.setattr('concurrent.futures.ProcessPoolExecutor', _BreaksOnSubmit)
        lost = i002.I002()._build_import_graph(proj).lost_files
        assert lost, 'fixture: the broken pool should lose at least one file'
    i002._graph_cache.clear()  # a fresh process
    graph = i002.I002()._build_import_graph(proj)
    assert graph.lost_files == [] and graph.failed_files == []
    assert len(builds) == 2, 'a graph with a file lost to a dead worker was stored and served'


# ------------------------------------------------------------- memo, in a long-lived host

def test_host_rebuilds_a_graph_built_while_a_file_was_unreadable(proj, deny, builds, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')  # the in-process memo alone
    request_cache._STAMPS.clear()
    _age(proj)
    deny.add(proj / 'b.py')
    assert _host_check(proj) == 0
    deny.clear()
    assert _host_check(proj) == 2, 'request 2 served the graph built while b.py was unreadable'
    assert len(builds) == 2


def test_request_reset_drops_a_graph_with_a_lost_file(proj, monkeypatch):
    from test_pool_lost_files_back1726 import _BreaksOnSubmit
    for i in range(4):
        (proj / f'c{i}.py').write_text('import os\n', encoding='utf-8')
    _age(proj)
    request_cache._STAMPS.clear()
    request_cache.reset_request_caches()
    started = request_cache.request_started_ns()
    with monkeypatch.context() as pool:
        pool.setenv('REVEAL_MAX_WORKERS', '2')
        pool.setattr(i002, '_GRAPH_PARALLEL_MIN_FILES', 1)
        pool.setattr('concurrent.futures.ProcessPoolExecutor', _BreaksOnSubmit)
        assert i002.I002()._build_import_graph(proj).lost_files
    request_cache.seal_request_caches(started)
    assert (i002.__name__, proj) in request_cache._STAMPS, 'fixture: the graph must be stamped as current'
    request_cache.reset_request_caches()
    assert proj not in i002._graph_cache, 'the next request kept a graph with a lost file'


# ------------------------------------------------------------- negative controls

def test_syntax_error_of_unchanged_content_stays_cached(proj, builds):
    """Content decides a syntax error: the graph is still read back from disk."""
    (proj / 'broken.py').write_text('import a\ndef f(\n    x = ( ( (\n', encoding='utf-8')
    cold = _check(proj)
    assert any('parsed with errors' in d for d in cold[1]), f'fixture: broken.py should fail to parse: {cold}'
    assert _check(proj) == cold
    assert len(builds) == 1, 'a genuine parse failure should still be served by the graph disk cache'


def test_unchanged_readable_tree_still_hits(proj, builds):
    assert _check(proj) == (2, [])
    assert _check(proj) == (2, [])
    assert len(builds) == 1


def test_host_keeps_a_graph_with_a_syntax_error_across_requests(proj, builds, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    (proj / 'broken.py').write_text('import a\ndef f(\n    x = ( ( (\n', encoding='utf-8')
    request_cache._STAMPS.clear()
    _age(proj)
    assert _host_check(proj) == 2
    assert _host_check(proj) == 2
    assert len(builds) == 1, 'a genuine parse failure should survive the request reset'
