"""BACK-1681: a file lost to a dead pool worker is an errored file, not a vanished one.

If a worker is killed (OOM, native crash) the pool breaks (BrokenProcessPool) and every
pending future fails. The text path used to log each file once on stderr and drop it from the
report: files_errored 0, exit 1 instead of 3. A lost file now arrives as a ``status: error``
result, so the report counts it, the exit is 3, and the disclosure is the report's own line.
"""

import multiprocessing
import os
import sys
from pathlib import Path

import pytest

from reveal.cli import file_checker
from reveal.cli.defaults import _default_args
from reveal.cli.file_checker import handle_recursive_check

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX pool semantics")

# The dying worker is injected by patching the module the pool's workers inherit, which only
# a forked worker does. Python 3.14 (Linux: forkserver) and macOS (spawn) do not default to fork.
needs_forked_workers = pytest.mark.skipif(
    multiprocessing.get_context().get_start_method() != "fork",
    reason="the default pool does not fork, so the patched worker never reaches it",
)

DYING = "m2.py"


def _tree(tmp_path, n=6):
    for i in range(n):
        (tmp_path / f"m{i}.py").write_text(
            "def f():\n    try:\n        return 1\n    except:\n        return 0\n", encoding="utf-8")
    return sorted(tmp_path.glob("*.py"))


def _killer(real, victim):
    def check(file_path, *args, **kwargs):
        if Path(file_path).name == victim:
            os._exit(1)
        return real(file_path, *args, **kwargs)
    return check


@pytest.fixture
def two_workers(monkeypatch):
    monkeypatch.setenv("REVEAL_MAX_WORKERS", "2")


@needs_forked_workers
def test_text_path_counts_every_file_when_a_worker_dies(tmp_path, monkeypatch, two_workers):
    files = _tree(tmp_path)
    monkeypatch.setattr(file_checker, "check_and_collect_file",
                        _killer(file_checker.check_and_collect_file, DYING))
    report = file_checker._check_text(files, tmp_path, ["B001"], None)
    assert sorted(b.checked.relative for b in report.blocks) == sorted(f.name for f in files)
    assert report.tally.files_errored >= 1
    dead = next(b.checked for b in report.blocks if b.checked.relative == DYING)
    assert dead.state == "error"
    assert "BrokenProcessPool" in dead.status["detail"]


@needs_forked_workers
def test_cli_exits_3_and_discloses_the_lost_file_once(tmp_path, monkeypatch, capsys, caplog, two_workers):
    _tree(tmp_path)
    monkeypatch.setattr(file_checker, "check_and_collect_file",
                        _killer(file_checker.check_and_collect_file, DYING))
    with pytest.raises(SystemExit) as exc:
        handle_recursive_check(tmp_path, _default_args(format="text", select="B001"))
    assert exc.value.code == 3
    captured = capsys.readouterr()
    assert captured.out.count(f"{DYING}: ") == 1 and "could not be checked" in captured.out
    assert DYING not in captured.err and not any(DYING in r.getMessage() for r in caplog.records)


def test_negative_control_no_death_is_unchanged(tmp_path, two_workers, capsys):
    """Same tree, no dying worker: nothing errored, exit 1 (issues found)."""
    _tree(tmp_path)
    with pytest.raises(SystemExit) as exc:
        handle_recursive_check(tmp_path, _default_args(format="text", select="B001"))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "could not be checked" not in out


def test_a_pool_that_cannot_start_falls_back_to_serial(tmp_path, monkeypatch, two_workers):
    """The fallback around the generator is real: the pool failing to build still checks every file."""
    files = _tree(tmp_path)

    def broken(*a, **k):
        raise OSError("no pool for you")
    monkeypatch.setattr(file_checker, "ProcessPoolExecutor", broken)
    report = file_checker._check_text(files, tmp_path, ["B001"], None)
    assert report.tally.files_errored == 0
    assert report.tally.files_with_issues == len(files)
