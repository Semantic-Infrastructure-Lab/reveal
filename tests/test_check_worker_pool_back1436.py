"""BACK-1436: `reveal check`'s directory pool honors REVEAL_MAX_WORKERS.

BACK-1004 taught stats:// the override; check's own pool (cli/file_checker.py) kept a
hardcoded ``min(4, cpu_count, len(files))``, so ``REVEAL_MAX_WORKERS=1`` still forked
4 workers -- no genuine serial baseline for profiling, and check-path tests stacked a
pool on pytest-xdist's workers despite conftest's suite-wide REVEAL_MAX_WORKERS=1
(BACK-1449). Both check renders (text streams, JSON maps) share one worker count.
"""

import os
from concurrent.futures import ProcessPoolExecutor as RealExecutor
from unittest.mock import patch

import pytest

from reveal.cli import file_checker
from reveal.utils.parallel import pool_worker_count


def _tree(tmp_path, n=6):
    """n Python files, with findings, enough to take the parallel path (>= 4)."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "t"\n', encoding="utf-8")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    for i in range(n - 1):
        (pkg / f"m{i}.py").write_text(
            f"import os\n\n\ndef f{i}():\n    try:\n        return {i}\n    except:\n        return 0\n",
            encoding="utf-8",
        )
    return sorted(pkg.glob("*.py"))


class _PoolSpy:
    """Records each ProcessPoolExecutor the check module builds; runs it for real."""

    def __init__(self):
        self.max_workers = []

    def __call__(self, *args, **kwargs):
        self.max_workers.append(kwargs.get("max_workers"))
        return RealExecutor(*args, **kwargs)


def _run_json(files, root):
    return file_checker._check_files_json(files, root, None, None)


def _run_text(files, root, capsys):
    result = file_checker._check_files_text(files, root, None, None, collect_json=True)
    return result, capsys.readouterr().out


class TestPoolWorkerCount:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("REVEAL_MAX_WORKERS", raising=False)
        assert pool_worker_count(3) == 3

    def test_override_wins(self, monkeypatch):
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "5")
        assert pool_worker_count(2) == 5

    def test_override_floor_is_one(self, monkeypatch):
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "0")
        assert pool_worker_count(4) == 1

    def test_invalid_override_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "lots")
        assert pool_worker_count(4) == 4


class TestCheckHonorsMaxWorkers:
    @pytest.mark.parametrize("render", ["json", "text"])
    def test_one_worker_runs_serially_without_a_pool(self, tmp_path, monkeypatch, capsys, render):
        files = _tree(tmp_path)
        assert len(files) >= file_checker._PARALLEL_THRESHOLD
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "1")
        spy = _PoolSpy()
        with patch.object(file_checker, "ProcessPoolExecutor", side_effect=spy):
            if render == "json":
                total, *_ = _run_json(files, tmp_path)
            else:
                (total, *_), _out = _run_text(files, tmp_path, capsys)
        assert spy.max_workers == [], "REVEAL_MAX_WORKERS=1 must not start a pool"
        assert total > 0

    @pytest.mark.parametrize("render", ["json", "text"])
    def test_override_sets_pool_size(self, tmp_path, monkeypatch, capsys, render):
        # 5 is above the old hardcoded cap of 4, so it can only come from the env var.
        files = _tree(tmp_path)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "5")
        spy = _PoolSpy()
        with patch.object(file_checker, "ProcessPoolExecutor", side_effect=spy):
            if render == "json":
                _run_json(files, tmp_path)
            else:
                _run_text(files, tmp_path, capsys)
        assert spy.max_workers == [5]

    def test_override_is_capped_at_file_count(self, tmp_path, monkeypatch):
        files = _tree(tmp_path)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "64")
        spy = _PoolSpy()
        with patch.object(file_checker, "ProcessPoolExecutor", side_effect=spy):
            _run_json(files, tmp_path)
        assert spy.max_workers == [len(files)]

    def test_unset_keeps_the_default_pool_size(self, tmp_path, monkeypatch):
        """Negative control: with no override the pool is what it always was."""
        files = _tree(tmp_path)
        monkeypatch.delenv("REVEAL_MAX_WORKERS", raising=False)
        spy = _PoolSpy()
        with patch.object(file_checker, "ProcessPoolExecutor", side_effect=spy):
            _run_json(files, tmp_path)
        assert spy.max_workers == [min(4, os.cpu_count() or 4, len(files))]

    def test_few_files_stay_serial_whatever_the_override(self, tmp_path, monkeypatch):
        """Negative control: below _PARALLEL_THRESHOLD there is never a pool."""
        files = _tree(tmp_path, n=3)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "8")
        spy = _PoolSpy()
        with patch.object(file_checker, "ProcessPoolExecutor", side_effect=spy):
            _run_json(files, tmp_path)
        assert spy.max_workers == []


class TestSerialEqualsParallel:
    def test_json_results_identical(self, tmp_path, monkeypatch):
        files = _tree(tmp_path, n=8)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "1")
        serial = _run_json(files, tmp_path)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "3")
        parallel = _run_json(files, tmp_path)
        assert serial[0] > 0
        assert serial == parallel

    def test_text_output_identical(self, tmp_path, monkeypatch, capsys):
        files = _tree(tmp_path, n=8)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "1")
        serial = _run_text(files, tmp_path, capsys)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "3")
        parallel = _run_text(files, tmp_path, capsys)
        assert "Found" in serial[1]
        assert serial == parallel
