"""BACK-2083: an environmental failure is not cached as the file's or the graph's answer.

A file that cannot be read (permission, I/O) or that a dead pool worker never parsed says
nothing about its content, and a later run can succeed without the file's mtime or size
changing (``chmod`` moves only ctime). Every imports cache keyed on stat kept such a
failure as the permanent answer: the per-file layer (``ImportsDiskCache``: in-process and
on disk) and the whole-graph layer (``adapter_import_graph``). A genuine parse failure of
unchanged content is still cached: the same bytes fail the same way.
"""

import json
import os
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest

from reveal.analyzers.imports import service as import_service

from reveal.analyzers.imports import extraction as import_extraction

from conftest import _MODULE_CACHES, _run_reveal_direct
from reveal import base as reveal_base
from reveal.adapters import imports as imports_adapter
from reveal.adapters.imports import ImportsAdapter
from reveal.analyzers.imports import generic, go, javascript, python as py_imports, rust, zig
from reveal.utils.request_cache import reset_request_caches

pytestmark = [pytest.mark.integration, pytest.mark.disk_cache]

_SINGLETON_MODULES = (py_imports, javascript, go, rust, zig, generic)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """r/{a.py: import bb, bb.py}; the cache dir lives beside it, outside the scanned tree."""
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    for module in _SINGLETON_MODULES:
        module._IMPORTS_CACHE.clear()
    root = tmp_path / 'r'
    root.mkdir()
    (root / 'a.py').write_text('import bb\n', encoding='utf-8')
    (root / 'bb.py').write_text('X = 1\n', encoding='utf-8')
    yield root
    for module in _SINGLETON_MODULES:
        module._IMPORTS_CACHE.clear()


@pytest.fixture
def deny(monkeypatch):
    """Paths whose read raises PermissionError, the way an unreadable file does."""
    denied = set()
    real = reveal_base.FileAnalyzer._read_file

    def read(self):
        if Path(self.path).resolve() in denied:
            raise PermissionError(13, 'Permission denied', str(self.path))
        return real(self)

    # Reaches extraction under every start method: its users extract serially (suite
    # REVEAL_MAX_WORKERS=1); the one test that sets 2 runs an in-process fake pool, not this.
    monkeypatch.setattr(reveal_base.FileAnalyzer, '_read_file', read)  # noqa: V036 reviewed: serial
    return denied


@pytest.fixture
def builds(monkeypatch):
    """How many times the graph was built from extraction, i.e. graph-cache misses."""
    calls = []
    original = import_service._process_extracted_files

    def counting(self, *args, **kwargs):
        calls.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(import_service, '_process_extracted_files', counting)
    return calls


def _fan_in(root):
    result = _run_reveal_direct(f'imports://{root}?rank=fan-in', '--format', 'json')
    data = json.loads(result.stdout)
    # D6 (BACK-1054): a file whose imports may be incomplete makes the answer incomplete: exit 3.
    assert result.returncode == (3 if data['metadata']['files_failed_count'] else 0), result.stderr
    return data['metadata']['files_failed_count'], {e['file']: e['fan_in'] for e in data['entries']}


HEALTHY = (0, {'bb.py': 1, 'a.py': 0})
DENIED = (1, {'a.py': 0, 'bb.py': 0})


def _extract(path):
    extractor = py_imports.PythonExtractor()
    modules = [stmt.module_name for stmt in extractor.extract_imports(path)]
    return modules, extractor.parse_failed


# ------------------------------------------------------------- through the CLI

def test_recovered_permission_is_seen_on_the_next_run(tree, deny):
    deny.add((tree / 'a.py').resolve())
    assert _fan_in(tree) == DENIED
    deny.clear()
    assert _fan_in(tree) == HEALTHY, 'the unreadable run was served again after the file became readable'


@pytest.mark.skipif(os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                    reason='chmod 000 does not deny a read on Windows or to root')
def test_recovered_chmod_is_seen_on_the_next_run(tree):
    """The reported reproduction as written: chmod 000, run, chmod 644, run."""
    target = tree / 'a.py'
    os.chmod(target, 0)
    try:
        assert _fan_in(tree) == DENIED
    finally:
        os.chmod(target, 0o644)
    assert _fan_in(tree) == HEALTHY


def test_recovered_worker_loss_is_seen_on_the_next_run(tree, monkeypatch):
    """A file a dead pool worker never parsed is not stored as part of the graph."""
    from test_pool_lost_files_back1726 import _BreaksOnSubmit
    for i in range(4):
        (tree / f'c{i}.py').write_text('import bb\n', encoding='utf-8')
    with monkeypatch.context() as pool:
        pool.setenv('REVEAL_MAX_WORKERS', '2')
        pool.setattr(import_extraction, '_PARALLEL_MIN_FILES', 1)
        pool.setattr('concurrent.futures.ProcessPoolExecutor', _BreaksOnSubmit)
        failed, _ = _fan_in(tree)
        assert failed >= 1, 'fixture: the broken pool should lose at least one file'
    assert _fan_in(tree) == (0, {'bb.py': 5, 'a.py': 0, **{f'c{i}.py': 0 for i in range(4)}})


# ------------------------------------------------------------- each layer alone

def test_per_file_memory_layer_forgets_a_read_failure(tree, deny, monkeypatch):
    """R11: with the disk cache off, the in-process layer alone kept the failure."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    deny.add((tree / 'a.py').resolve())
    assert _extract(tree / 'a.py') == ([], True)
    deny.clear()
    assert _extract(tree / 'a.py') == (['bb'], False)


def test_per_file_disk_layer_forgets_a_read_failure(tree, deny):
    """A fresh process (in-process layer empty) must not read the failure back from disk."""
    deny.add((tree / 'a.py').resolve())
    assert _extract(tree / 'a.py') == ([], True)
    deny.clear()
    py_imports._IMPORTS_CACHE.clear()
    assert _extract(tree / 'a.py') == (['bb'], False)


def test_graph_layer_does_not_store_a_read_failure(tree, deny, builds):
    deny.add((tree / 'a.py').resolve())
    assert _fan_in(tree) == DENIED
    assert _fan_in(tree) == DENIED
    assert len(builds) == 2, 'a graph holding an unreadable file was stored and served'


def test_graph_layer_does_not_store_a_lost_file(tree, monkeypatch, builds):
    real = import_extraction.extract_files

    def one_lost(candidates, want_structure, inputs=None):
        for row in real(candidates, want_structure, inputs):
            if row[0].name == 'a.py':
                lost = BrokenProcessPool('A process in the process pool was terminated abruptly')
                row = (row[0], None, None, None, import_extraction.lost_extraction(lost), None, None)
            yield row

    with monkeypatch.context() as patched:
        patched.setattr(import_extraction, 'extract_files', one_lost)
        assert _fan_in(tree) == DENIED
    assert _fan_in(tree) == HEALTHY
    assert len(builds) == 2


# ------------------------------------------------------------- negative controls

def test_parse_failure_of_unchanged_content_stays_cached(tree, builds):
    """Content decides a syntax error: it is still served from both layers."""
    (tree / 'broken.py').write_text('def f(\n    x = ( ( (\n', encoding='utf-8')
    cold = _fan_in(tree)
    assert cold[0] == 1, 'fixture: broken.py should fail to parse'
    assert _fan_in(tree) == cold
    assert len(builds) == 1, 'a genuine parse failure should still be read from the graph cache'

    py_imports._IMPORTS_CACHE.clear()  # a fresh process: only the disk layer can answer
    extractor = py_imports.PythonExtractor()
    extractor._get_tree_analyzer = lambda *_a, **_k: pytest.fail('per-file disk miss: parse failure not stored')
    extractor.extract_imports(tree / 'broken.py')
    assert extractor.parse_failed


def test_clean_tree_still_hits_both_layers(tree, builds):
    assert _fan_in(tree) == HEALTHY
    assert _fan_in(tree) == HEALTHY
    assert len(builds) == 1


# ------------------------------------------------------------- request lifetime

def test_request_reset_empties_every_per_file_memory_layer(tree):
    for module in _SINGLETON_MODULES:
        module._IMPORTS_CACHE._mem_cache[('x', 0, 0)] = object()
    reset_request_caches()
    assert {m.__name__: len(m._IMPORTS_CACHE._mem_cache) for m in _SINGLETON_MODULES} == {
        m.__name__: 0 for m in _SINGLETON_MODULES}


def test_every_per_file_memory_layer_is_swept_between_tests():
    listed = set(_MODULE_CACHES)
    assert {(m.__name__, '_IMPORTS_CACHE') for m in _SINGLETON_MODULES} <= listed
