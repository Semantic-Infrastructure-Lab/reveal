"""BACK-1726: a dead pool worker costs only the files it took down, and says so.

Three pools still handed their work out with ``executor.map``: imports://'s per-file
extraction (``ImportsAdapter._extract_files``), I002's import-graph Pass B
(``_collect_raw_imports``) and ``utils.parallel.grep_files``. Once a worker dies the
pool is broken: ``map`` raises BrokenProcessPool for the rest, so imports:// and
grep_files lost the whole run, and I002 swallowed it at debug level and re-ran every
file serially in the parent, the culprit included. They now go through
``utils.parallel.submit_each`` with per-future handling, like check and stats://
(BACK-1717/1718).

Two ways to break a pool: a fake executor that fails the second item and refuses the
rest at submit time (deterministic, every platform), and a real worker that calls
``os._exit`` on one file, which only a forked worker can be made to do from here.
A dead worker fails every pending future, so the tests assert bounds, not exact counts.
"""
import logging
import multiprocessing
import os
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest

from conftest import needs_forked_workers
from reveal.adapters import imports as imports_adapter
from reveal.rules.imports import I002 as i002
from reveal.utils import parallel

N_FILES = 6
DYING = 'm2.py'
SUBMIT_BROKEN = "A child process terminated abruptly, the process pool is not usable anymore"
FUTURE_BROKEN = "A process in the process pool was terminated abruptly while the future was running or pending."


class _BreaksOnSubmit:
    """Runs the first item in-process, fails the second like a dead worker, then refuses
    every later submission the way a broken ProcessPoolExecutor does. ``map`` behaves
    like a broken pool's: the first result, then BrokenProcessPool."""

    def __init__(self, *args, **kwargs):
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        self.calls += 1
        if self.calls > 2:
            raise BrokenProcessPool(SUBMIT_BROKEN)
        future = Future()
        if self.calls == 1:
            future.set_result(fn(*args))
        else:
            future.set_exception(BrokenProcessPool(FUTURE_BROKEN))
        return future

    def map(self, fn, *iterables, chunksize=1):
        for i, args in enumerate(zip(*iterables)):
            if i:
                raise BrokenProcessPool(FUTURE_BROKEN)
            yield fn(*args)


class _Healthy(_BreaksOnSubmit):
    def submit(self, fn, *args):
        future = Future()
        future.set_result(fn(*args))
        return future

    def map(self, fn, *iterables, chunksize=1):
        return [fn(*args) for args in zip(*iterables)]


class _CannotStart:
    def __init__(self, *args, **kwargs):
        raise OSError("[Errno 38] Function not implemented (no sem_open)")


def _tree(tmp_path, n=N_FILES):
    root = tmp_path / 'tree'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="probe"\n', encoding='utf-8')
    for i in range(n):
        (root / f'm{i}.py').write_text(f'import os\nVALUE_{i} = os.sep\n', encoding='utf-8')
    return root.resolve()


@pytest.fixture
def pools(monkeypatch):
    """Every pool in this module runs with 2 workers on a 6-file tree."""
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '2')
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.setattr(imports_adapter, '_PARALLEL_MIN_FILES', 1)
    monkeypatch.setattr(i002, '_GRAPH_PARALLEL_MIN_FILES', 1)
    i002._graph_cache.clear()
    yield monkeypatch
    i002._graph_cache.clear()


def _imports_run(root):
    adapter = imports_adapter.ImportsAdapter(resource=str(root))
    result = adapter.get_structure()
    return adapter, result


# ------------------------------------------------------------- imports://

def test_imports_reports_files_the_broken_pool_refused_and_keeps_the_run(tmp_path, pools):
    root = _tree(tmp_path)
    pools.setattr('concurrent.futures.ProcessPoolExecutor', _BreaksOnSubmit)
    adapter, result = _imports_run(root)
    analysis = adapter.analysis
    assert len(analysis.scanned_files) == N_FILES, 'every file is still in the scan'
    lost = {fp.name for fp in analysis.files_failed}
    assert 1 <= len(lost) <= N_FILES - 1  # the first chunk ran
    meta = result['metadata']
    assert meta['files_failed_count'] == len(lost)
    reasons = [d['parse']['reason'] for d in meta['extraction_diagnostics'].values()]
    assert reasons and all('BrokenProcessPool' in r for r in reasons)
    warnings = adapter.integrity_warnings(root)
    assert [w['type'] for w in warnings] == ['worker_lost'] and warnings[0]['count'] == len(lost)


def test_imports_negative_control_a_healthy_pool_fails_nothing(tmp_path, pools):
    root = _tree(tmp_path)
    pools.setattr('concurrent.futures.ProcessPoolExecutor', _Healthy)
    adapter, result = _imports_run(root)
    assert adapter.analysis.files_failed == []
    assert result['metadata']['files_failed_count'] == 0
    assert len(adapter.analysis.symbols_by_file) == N_FILES


# ------------------------------------------------------------------ I002

def _counting_extract(pools):
    calls = []
    real = i002._extract_imports_for_file

    def counted(fp_str):
        calls.append(Path(fp_str).name)
        return real(fp_str)
    pools.setattr(i002, '_extract_imports_for_file', counted)
    return calls


def test_i002_reports_files_the_broken_pool_refused_without_a_serial_rerun(tmp_path, pools, caplog):
    root = _tree(tmp_path)
    pools.setattr('concurrent.futures.ProcessPoolExecutor', _BreaksOnSubmit)
    calls = _counting_extract(pools)
    with caplog.at_level(logging.WARNING, logger=i002.logger.name):
        imports, failed, _lost, skipped = i002.I002()._collect_raw_imports(root)
    assert skipped is None
    assert len(calls) == 1, f'only the in-process first item ran; nothing re-ran in the parent: {calls}'
    assert 1 <= len(failed) <= N_FILES - 1
    assert {Path(f).name for f in failed} == {f'm{i}.py' for i in range(N_FILES)} - set(calls)
    assert 'lost to a dead import-extraction worker' in caplog.text
    assert 'BrokenProcessPool' in caplog.text


def test_i002_scan_disclosure_names_the_lost_files(tmp_path, pools):
    root = _tree(tmp_path)
    pools.setattr('concurrent.futures.ProcessPoolExecutor', _BreaksOnSubmit)
    i002.I002()._build_import_graph(root)
    disclosures = i002.get_scan_disclosures()
    assert any('circular-dependency results may be incomplete' in d for d in disclosures), disclosures


def test_i002_pool_that_cannot_start_runs_serially_and_says_so(tmp_path, pools, caplog):
    """The serial fallback stays for a pool that never runs, and it is a warning now."""
    root = _tree(tmp_path)
    pools.setattr('concurrent.futures.ProcessPoolExecutor', _CannotStart)
    calls = _counting_extract(pools)
    with caplog.at_level(logging.WARNING, logger=i002.logger.name):
        imports, failed, _lost, _ = i002.I002()._collect_raw_imports(root)
    assert sorted(calls) == sorted(f'm{i}.py' for i in range(N_FILES))
    assert failed == []
    assert len(imports) == N_FILES
    assert 'extracting the rest serially' in caplog.text


def test_i002_negative_control_a_healthy_pool_fails_nothing(tmp_path, pools, caplog):
    root = _tree(tmp_path)
    pools.setattr('concurrent.futures.ProcessPoolExecutor', _Healthy)
    with caplog.at_level(logging.WARNING, logger=i002.logger.name):
        imports, failed, _lost, _ = i002.I002()._collect_raw_imports(root)
    assert failed == [] and len(imports) == N_FILES
    assert 'lost to a dead' not in caplog.text and 'serially' not in caplog.text


# ------------------------------------------------------------ grep_files

def _grep_tree(tmp_path, n=10):
    files = []
    for i in range(n):
        path = tmp_path / f'g{i}.txt'
        path.write_text('needle here\n' if i != 3 else 'nothing\n', encoding='utf-8')
        files.append(path)
    return files


def test_grep_files_reports_files_the_broken_pool_refused(tmp_path, monkeypatch, caplog):
    files = _grep_tree(tmp_path)
    monkeypatch.setattr(parallel, 'ProcessPoolExecutor', _BreaksOnSubmit)
    with caplog.at_level(logging.WARNING, logger=parallel.logger.name):
        found = parallel.grep_files(files, 'needle')
    assert found == [files[0]], 'the one scanned file matches; lost files are not matches'
    assert 'not scanned, a pool worker died' in caplog.text
    assert '9 file(s)' in caplog.text


def test_grep_files_negative_control_a_healthy_pool(tmp_path, monkeypatch, caplog):
    files = _grep_tree(tmp_path)
    monkeypatch.setattr(parallel, 'ProcessPoolExecutor', _Healthy)
    with caplog.at_level(logging.WARNING, logger=parallel.logger.name):
        found = parallel.grep_files(files, 'needle')
    assert found == [f for i, f in enumerate(files) if i != 3]
    assert 'not scanned' not in caplog.text


# ------------------------------------------------- a real worker that dies
# The stand-in workers are module-level so a pool can pickle them by name, and call
# the real worker captured here (the module attribute is the patched stand-in).

_REAL_I002_EXTRACT = i002._extract_imports_for_file
_REAL_IMPORTS_EXTRACT = imports_adapter._extract_one_file
_REAL_SCAN_ONE = parallel._scan_one


def _dies_on_one(path, name=DYING):
    """Ends the pool worker that reaches *name*, like a parser crashing the interpreter."""
    if Path(path).name == name and multiprocessing.parent_process() is not None:
        os._exit(1)


def _i002_extract_dying(fp_str):
    _dies_on_one(fp_str)
    return _REAL_I002_EXTRACT(fp_str)


def _imports_extract_dying(fp_str, want_structure):
    _dies_on_one(fp_str)
    return _REAL_IMPORTS_EXTRACT(fp_str, want_structure)


def _scan_dying(args):
    _dies_on_one(args[0], name='g2.txt')
    return _REAL_SCAN_ONE(args)


@needs_forked_workers
def test_i002_real_dying_worker_costs_only_lost_files(tmp_path, pools, caplog):
    root = _tree(tmp_path)
    pools.setattr(i002, '_extract_imports_for_file', _i002_extract_dying)
    with caplog.at_level(logging.WARNING, logger=i002.logger.name):
        imports, failed, _lost, _ = i002.I002()._collect_raw_imports(root)
    lost = {Path(f).name for f in failed}
    assert DYING in lost and len(lost) <= N_FILES
    assert 'lost to a dead import-extraction worker' in caplog.text
    assert 'BrokenProcessPool' in caplog.text
    assert 'serially' not in caplog.text


@needs_forked_workers
def test_imports_real_dying_worker_costs_only_lost_files(tmp_path, pools):
    root = _tree(tmp_path)
    pools.setattr(imports_adapter, '_extract_one_file', _imports_extract_dying)
    adapter, result = _imports_run(root)
    lost = {fp.name for fp in adapter.analysis.files_failed}
    assert DYING in lost and len(lost) <= N_FILES
    assert len(adapter.analysis.scanned_files) == N_FILES
    assert result['metadata']['files_failed_count'] == len(lost)
    reasons = [d['parse']['reason'] for d in result['metadata']['extraction_diagnostics'].values()]
    assert reasons and all('BrokenProcessPool' in r for r in reasons)


@needs_forked_workers
def test_grep_files_real_dying_worker_costs_only_lost_files(tmp_path, monkeypatch, caplog):
    files = _grep_tree(tmp_path)
    monkeypatch.setattr(parallel, '_scan_one', _scan_dying)
    with caplog.at_level(logging.WARNING, logger=parallel.logger.name):
        found = parallel.grep_files(files, 'needle', workers=2)
    assert files[2] not in found and files[3] not in found
    assert set(found) <= set(files)
    assert 'not scanned, a pool worker died (BrokenProcessPool' in caplog.text
