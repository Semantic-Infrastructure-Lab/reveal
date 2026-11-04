"""BACK-2156: a process pool the platform cannot start costs the import build nothing.

``extraction.extract_files`` raised whatever ``ProcessPoolExecutor`` raised where no pool can run
(no ``sem_open``, a sandbox without fork/spawn), so imports:// failed the whole build. I002 had its
own extraction with a serial fallback for that case; now that I002 builds through the analysis
service, the fallback lives in the one owner: the files the pool did not deliver are extracted in
this process, and a warning says so. A worker that dies inside a running pool is still a lost
file, never a serial re-run (BACK-1726, negative control below).
"""
import logging
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool

import pytest

from reveal.adapters import imports as imports_adapter
from reveal.analyzers.imports import extraction as import_extraction

N_FILES = 6


class _CannotStart:
    def __init__(self, *args, **kwargs):
        raise OSError("[Errno 38] Function not implemented (no sem_open)")


class _FailsOnSecondSubmit:
    """The first chunk runs in-process; then submitting raises the way a pool that cannot
    spawn its workers does (the error escapes ``submit``, it is not a BrokenProcessPool)."""

    def __init__(self, *args, **kwargs):
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        self.calls += 1
        if self.calls > 1:
            raise OSError("[Errno 11] Resource temporarily unavailable")
        future = Future()
        future.set_result(fn(*args))
        return future


class _BreaksOnSubmit(_FailsOnSecondSubmit):
    def submit(self, fn, *args):
        self.calls += 1
        if self.calls > 2:
            raise BrokenProcessPool('the process pool is not usable anymore')
        future = Future()
        if self.calls == 1:
            future.set_result(fn(*args))
        else:
            future.set_exception(BrokenProcessPool('terminated abruptly'))
        return future


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '2')
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.setattr(import_extraction, '_PARALLEL_MIN_FILES', 1)
    root = tmp_path / 'tree'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="probe"\n', encoding='utf-8')
    for i in range(N_FILES):
        (root / f'm{i}.py').write_text(f'import os\nVALUE_{i} = os.sep\n', encoding='utf-8')
    return root.resolve()


def _build(root):
    adapter = imports_adapter.ImportsAdapter(resource=str(root))
    adapter.get_structure()
    return adapter.analysis


@pytest.mark.parametrize('executor', [_CannotStart, _FailsOnSecondSubmit])
def test_a_pool_that_cannot_run_extracts_serially_and_says_so(tree, monkeypatch, caplog, executor):
    monkeypatch.setattr('concurrent.futures.ProcessPoolExecutor', executor)
    with caplog.at_level(logging.WARNING, logger='reveal.analyzers.imports.extraction'):
        analysis = _build(tree)
    assert analysis.files_failed == []
    assert sorted(fp.name for fp in analysis.symbols_by_file) == [f'm{i}.py' for i in range(N_FILES)]
    assert 'extracting the rest serially' in caplog.text
    assert 'OSError' in caplog.text


def test_a_worker_that_dies_is_still_a_lost_file_not_a_serial_rerun(tree, monkeypatch, caplog):
    monkeypatch.setattr('concurrent.futures.ProcessPoolExecutor', _BreaksOnSubmit)
    with caplog.at_level(logging.WARNING, logger='reveal.analyzers.imports.extraction'):
        analysis = _build(tree)
    assert 1 <= len(analysis.files_lost) <= N_FILES - 1
    assert 'serially' not in caplog.text
