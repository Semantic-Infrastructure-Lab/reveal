"""BACK-2136: a failure that did not come from the file's content is never the file's answer.

BACK-2083 stopped the imports caches from storing an unreadable file or a lost worker. Two
other failures say nothing about the content either: the analyzer lookup raising (the
registry, not the file) and tree-sitter building no tree because its grammar could not be
loaded (``GrammarUnavailable``: the language pack's download or cache lock failed). Both were
caught as a parse failure and stored as the file's answer under its stat key: in the per-file
layer (``ImportsDiskCache``, in-process and on disk), in imports://'s ``adapter_import_graph``
and in I002's ``import_graph_v4`` and its request memo. Once the failure was gone, every
later request on the unchanged files still had no edges: ``depends://`` 0 modules, I002 "8
file(s) parsed with errors" (the contract harness's Windows CI failures, BACK-1647 note 4).

Each failure is still disclosed on the request that hit it; the next request reads the file
again. A syntax error of unchanged content stays cached and disclosed: the same bytes fail
the same way. An extractor that raises stays a content failure (BACK-2084).
"""

import json
import os
import shutil
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

from conftest import _clear_module_caches, _run_reveal_direct
from reveal import api, mcp_server
from reveal import base as reveal_base
from reveal import treesitter
from reveal.analyzers.imports import base as imports_base
from reveal.analyzers.imports import python as py_imports
from reveal.core import disk_cache
from reveal.core.treesitter_parse import GrammarUnavailable
from reveal.rules.imports import I002 as i002
from reveal.utils import request_cache

pytestmark = pytest.mark.integration

ONE_FILE_LOST = (2, 2)   # b.py's `import c` unseen: c.py loses its importer
HEALTHY = (3, 3)         # a -> b -> c -> a: three modules, three edges


@pytest.fixture(params=['disk_off', pytest.param('disk_on', marks=pytest.mark.disk_cache)])
def cache(request, tmp_path, monkeypatch):
    """The disk cache off (the in-process layer alone) or on (a scratch dir)."""
    if request.param == 'disk_on':
        monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
        monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    else:
        monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    return request.param


@pytest.fixture
def disk_on(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')


@pytest.fixture
def proj(tmp_path):
    """proj/{a.py: import b, b.py: import c, c.py: import a}, a project of its own."""
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="p"\n', encoding='utf-8')
    for name, target in (('a', 'b'), ('b', 'c'), ('c', 'a')):
        (root / f'{name}.py').write_text(f'import {target}\n', encoding='utf-8')
    _clear_module_caches()
    yield root.resolve()
    _clear_module_caches()


@pytest.fixture
def extractions(monkeypatch):
    """How many times each file's imports were extracted, i.e. per-file cache misses."""
    calls = Counter()
    real = py_imports.PythonExtractor._extract_imports_uncached

    def counting(self, file_path):
        calls[Path(file_path).name] += 1
        return real(self, file_path)

    monkeypatch.setattr(py_imports.PythonExtractor, '_extract_imports_uncached', counting)
    return calls


class _OneShot:
    """The next extraction of each armed path fails once, then the path works again."""

    def __init__(self):
        self.armed = set()
        self.fired = []

    def fires(self, path):
        resolved = Path(str(path)).resolve()
        if resolved in self.armed:
            self.armed.discard(resolved)
            self.fired.append(resolved.name)
            return True
        return False


@pytest.fixture
def lookup_fails(monkeypatch):
    """The analyzer lookup raises, as a registry that is mid-update or broken would."""
    shot = _OneShot()
    real = imports_base.get_analyzer

    def get_analyzer(path, *args, **kwargs):
        if shot.fires(path):
            raise RuntimeError('analyzer registry unavailable')
        return real(path, *args, **kwargs)

    monkeypatch.setattr(imports_base, 'get_analyzer', get_analyzer)
    return shot


@pytest.fixture
def grammar_fails(monkeypatch):
    """Tree-sitter has no grammar for this parse: the language pack's fetch or cache lock
    failed (its DownloadError and CacheLockError are not OSErrors)."""
    shot = _OneShot()
    real = treesitter.get_tree

    def get_tree(language, source, *, filename=None, **kwargs):
        if filename is not None and shot.fires(filename):
            raise GrammarUnavailable(language, RuntimeError('grammar cache is locked by another process'))
        return real(language, source, filename=filename, **kwargs)

    monkeypatch.setattr(treesitter, 'get_tree', get_tree)
    return shot


@pytest.fixture
def read_fails(monkeypatch):
    """The file's read raises PermissionError once (BACK-2083's case)."""
    shot = _OneShot()
    real = reveal_base.FileAnalyzer._read_file

    def read(self):
        if shot.fires(self.path):
            raise PermissionError(13, 'Permission denied', str(self.path))
        return real(self)

    # Extraction is serial here: the suite sets REVEAL_MAX_WORKERS=1.
    monkeypatch.setattr(reveal_base.FileAnalyzer, '_read_file', read)  # noqa: V036 reviewed: serial
    return shot


def _depends(root):
    """(modules, edges, warning) of one depends:// run in this process."""
    result = _run_reveal_direct(f'depends://{root}', '--format', 'json')
    data = json.loads(result.stdout)
    return data['total_modules'], data['metadata']['total_import_edges'], data.get('warning', '')


def _next_run(cache):
    """Between two runs: with the disk cache on, start the next one as a fresh process would,
    so only the disk layer can answer it; with it off, keep the in-process layer."""
    if cache == 'disk_on':
        _clear_module_caches()


def _forget_per_file_layers():
    """Empty both per-file layers, leaving every whole-graph cache in place."""
    _clear_module_caches()
    shutil.rmtree(disk_cache._namespace_dir(py_imports._IMPORTS_CACHE.namespace), ignore_errors=True)


def _age(root):
    """Files modified at or after a request start are never stamped as current."""
    aged = time.time_ns() - 10_000_000_000
    for path in root.rglob('*'):
        os.utime(path, ns=(aged, aged))


# ------------------------------------------------------------- depends://, per-file layers

@pytest.mark.parametrize('failure', ['lookup_fails', 'grammar_fails'])
def test_a_transient_failure_is_disclosed_then_read_again(proj, cache, extractions, failure, request):
    shot = request.getfixturevalue(failure)
    shot.armed.add(proj / 'b.py')
    *first, warning = _depends(proj)
    assert shot.fired == ['b.py'], 'fixture: the failure should hit b.py once'
    assert tuple(first) == ONE_FILE_LOST and '1 file(s) parsed with errors' in warning, (
        'the request that hit the failure must disclose the lost file, not read as a clean answer')
    _next_run(cache)
    *second, warning = _depends(proj)
    assert tuple(second) == HEALTHY and 'parsed with errors' not in warning, (
        f'{failure}: the failure was stored as b.py\'s answer and served again ({cache})')
    assert extractions == {'a.py': 1, 'b.py': 2, 'c.py': 1}, 'only the failed file is read again'


# ------------------------------------------------------------- whole-graph layers alone

def _fan_in(root):
    data = json.loads(_run_reveal_direct(f'imports://{root}?rank=fan-in', '--format', 'json').stdout)
    return data['metadata']['files_failed_count'], sum(entry['fan_in'] for entry in data['entries'])


def test_imports_graph_layer_does_not_store_a_transient_failure(proj, disk_on, lookup_fails):
    """adapter_import_graph (imports://, deps): with both per-file layers emptied, the
    whole-graph entry alone served the failure."""
    lookup_fails.armed.add(proj / 'b.py')
    assert _fan_in(proj) == (1, 2)
    _forget_per_file_layers()
    assert _fan_in(proj) == (0, 3), 'the graph built while b.py\'s analyzer lookup failed was stored'


@pytest.mark.parametrize('failure', ['lookup_fails', 'grammar_fails'])
def test_i002_graph_layer_does_not_store_a_transient_failure(proj, disk_on, failure, request):
    """import_graph_v4: with both per-file layers emptied, the I002 graph entry alone served
    the failure (the CI symptom: 'I002: 8 file(s) ... parsed with errors')."""
    shot = request.getfixturevalue(failure)
    shot.armed.add(proj / 'b.py')
    graph = i002.I002()._build_import_graph(proj)
    assert [path.name for path in graph.failed_files] == ['b.py']
    assert any('1 file(s)' in note and 'parsed with errors' in note for note in i002.get_scan_disclosures()), (
        'the build that hit the failure must disclose it')
    _forget_per_file_layers()
    graph = i002.I002()._build_import_graph(proj)
    assert (graph.failed_files, sum(len(deps) for deps in graph.dependencies.values())) == ([], 3), (
        f'{failure}: the I002 graph built while b.py failed was stored as the tree\'s graph')


# ------------------------------------------------------------- long-lived host (MCP)

def _in_thread(fn):
    out = {}
    worker = threading.Thread(target=lambda: out.setdefault('value', fn()))
    worker.start()
    worker.join()
    return out['value']


def test_host_requests_from_two_threads_read_the_file_again(proj, monkeypatch, lookup_fails):
    """I002's request memo is shared by every thread a host serves: a graph built while the
    lookup failed was stamped as current and kept for the next request (disk cache off)."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    request_cache._STAMPS.clear()
    _age(proj)
    lookup_fails.armed.add(proj / 'b.py')
    first = _in_thread(lambda: mcp_server.reveal_check(str(proj), select='I002'))
    assert first.count('[I002]') == 0 and 'parsed with errors' in first, first
    second = _in_thread(lambda: mcp_server.reveal_check(str(proj), select='I002'))
    assert second.count('[I002]') == 3, 'request 2 served the graph built while the lookup failed'


@pytest.mark.disk_cache
def test_host_depends_from_two_threads_reads_the_file_again(proj, disk_on, grammar_fails):
    grammar_fails.armed.add(proj / 'b.py')
    first = _in_thread(lambda: api.query(f'depends://{proj}'))
    assert (first['total_modules'], first['metadata']['total_import_edges']) == ONE_FILE_LOST
    second = _in_thread(lambda: api.query(f'depends://{proj}'))
    assert (second['total_modules'], second['metadata']['total_import_edges']) == HEALTHY, (
        'request 2 read the grammar failure back from the disk cache')


# ------------------------------------------------------------- negative controls

def test_syntax_error_stays_a_cached_disclosed_parse_failure(proj, cache, extractions):
    """Content decides a syntax error: the same bytes fail the same way, so it is still
    served from the cache, and still disclosed on every request."""
    (proj / 'c.py').write_text('import a\nx = (\n', encoding='utf-8')
    first = _depends(proj)
    assert first[:2] == HEALTHY and '1 file(s) parsed with errors' in first[2], (
        f'fixture: c.py should parse partially, keeping its import: {first}')
    _next_run(cache)
    assert _depends(proj) == first
    assert extractions['c.py'] == 1, 'a genuine parse failure should still be cached'


def test_unreadable_file_is_read_again(proj, cache, extractions, read_fails):
    """BACK-2083's case keeps working: an OSError is never stored either."""
    read_fails.armed.add(proj / 'b.py')
    assert _depends(proj)[:2] == ONE_FILE_LOST
    _next_run(cache)
    assert _depends(proj)[:2] == HEALTHY
    assert extractions['b.py'] == 2


@pytest.mark.disk_cache
def test_healthy_tree_answers_the_same_cold_warm_and_after_an_edit(proj, disk_on, monkeypatch):
    def run():
        return _run_reveal_direct(f'depends://{proj}', '--format', 'json').stdout

    def uncached():
        _clear_module_caches()
        with monkeypatch.context() as off:
            off.setenv('REVEAL_DISK_CACHE', '0')
            return run()

    cold = run()
    _clear_module_caches()
    warm = run()
    assert cold == warm == uncached()
    (proj / 'c.py').write_text('import a\nimport b\n', encoding='utf-8')
    _clear_module_caches()
    edited = run()
    assert edited == uncached() and edited != cold
