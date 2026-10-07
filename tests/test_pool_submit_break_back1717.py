"""BACK-1717/1718: a worker that dies while files are still being handed to the pool.

Once a worker dies the pool is broken and every later ``submit`` raises BrokenProcessPool.
When that happened mid-submission, the exception escaped the submit loop: check's
``_results_in_sorted_order`` fell back to re-checking every file serially in the parent (the
culprit included, exit 1, nothing errored), and stats:// lost the whole run. It only shows on a
fast-dying worker (macOS runners under fork, CI run 37560151769), so these tests break the
pool at submit time with a fake executor instead of racing a real one.
"""

from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool

import pytest

from reveal.adapters.stats.adapter import _pool_results
from reveal.cli import file_checker

SUBMIT_BROKEN = "A child process terminated abruptly, the process pool is not usable anymore"
FUTURE_BROKEN = "A process in the process pool was terminated abruptly while the future was running or pending."


class _BreaksOnSubmit:
    """Runs the first submission in-process, fails the second like a dead worker, then refuses
    every later submission the way a broken ProcessPoolExecutor does."""

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


def _tree(tmp_path, n=6):
    for i in range(n):
        (tmp_path / f"m{i}.py").write_text(
            "def f():\n    try:\n        return 1\n    except:\n        return 0\n", encoding="utf-8")
    return sorted(tmp_path.glob("*.py"))


def test_submit_each_gives_every_item_a_future():
    from reveal.utils.parallel import submit_each
    futures = submit_each(_BreaksOnSubmit(), lambda x: x * 10, [1, 2, 3, 4])
    assert len(futures) == 4
    assert futures[0].result() == 10
    for refused in futures[2:]:
        with pytest.raises(BrokenProcessPool, match="not usable anymore"):
            refused.result()


def test_submit_each_negative_control_a_healthy_executor_is_untouched():
    from reveal.utils.parallel import submit_each

    class Healthy(_BreaksOnSubmit):
        def submit(self, fn, *args):
            future = Future()
            future.set_result(fn(*args))
            return future
    assert [f.result() for f in submit_each(Healthy(), lambda x: x + 1, [1, 2, 3])] == [2, 3, 4]


def test_check_reports_files_the_broken_pool_refused_as_errored(tmp_path, monkeypatch, caplog):
    files = _tree(tmp_path)
    monkeypatch.setenv("REVEAL_MAX_WORKERS", "2")
    monkeypatch.setattr(file_checker, "ProcessPoolExecutor", _BreaksOnSubmit)
    report = file_checker._check_text(files, tmp_path, ["B001"], None)
    assert sorted(b.checked.relative for b in report.blocks) == sorted(f.name for f in files)
    # one file checked, five lost with the pool; none re-run serially in the parent
    assert report.tally.files_errored == len(files) - 1
    assert "checking the rest serially" not in caplog.text


def test_stats_reports_files_the_broken_pool_refused_and_keeps_the_run(tmp_path):
    files = _tree(tmp_path, n=4)
    args = [(str(f), None, str(tmp_path)) for f in files]
    results = _pool_results(_BreaksOnSubmit(), args)
    assert len(results) == len(files)
    failed = [r for r in results if 'analysis_failed' in r]
    assert [r['path'] for r in failed] == [str(f) for f in files[1:]]
    assert all("BrokenProcessPool" in r['analysis_failed'] for r in failed)
