"""The per-invocation log lives below the CLI (BACK-2659): code at any layer records into it."""
from reveal.cli.invocation import Invocation, invocation_scope, noted_retirements, retirement_note
from reveal.utils.invocation_log import answer_is_json, current_log, invocation_warnings, log_scope, record_warning


def test_no_log_outside_an_invocation():
    assert current_log() is None


def test_scope_opens_a_log_and_restores_the_previous_one():
    with log_scope(to_stderr=False) as outer:
        assert current_log() is outer and outer.to_stderr is False
        with log_scope() as inner:  # a request inside another joins it (an MCP call's invocation)
            assert current_log() is inner is outer
        assert current_log() is outer
    assert current_log() is None


def test_a_warning_is_recorded_once_and_printed_once_unless_a_json_answer_carried_it(capsys):
    entry = {'type': 'config_warning', 'code': 'c', 'message': 'm'}
    assert record_warning(entry) is False  # outside an invocation the caller logs it
    with log_scope():
        assert record_warning(entry) and record_warning(dict(entry))
    assert capsys.readouterr().err == 'warning: m\n'
    with log_scope():
        record_warning(entry)
        answer_is_json(True)
        assert invocation_warnings() == [entry]
    assert capsys.readouterr().err == ''
    with log_scope(to_stderr=False):
        record_warning(entry)
    assert capsys.readouterr().err == ''


def test_invocation_scope_records_retirements_in_that_log():
    with invocation_scope(Invocation.parse(['reveal', '.']), retirements_to_stderr=False):
        log = current_log()
        assert log is not None and log.to_stderr is False
        retirement_note('flag:--calls')
        assert list(log.noted) == ['flag:--calls'] == list(noted_retirements())
    assert current_log() is None and noted_retirements() == {}


def _record_in_worker(item):
    record_warning({'type': 'config_warning', 'code': 'c', 'message': f'from worker {item}'})
    return item * 2


def test_submit_each_hands_a_worker_warning_to_the_submitting_invocation():
    """A worker records into a log of its own and never prints; the parent's log gets the entry
    before the caller's Future resolves (BACK-2659)."""
    from concurrent.futures import ThreadPoolExecutor
    from reveal.utils.parallel import submit_each
    with log_scope(to_stderr=False) as log, ThreadPoolExecutor(max_workers=2) as pool:
        futures = submit_each(pool, _record_in_worker, [1, 2, 2])
        assert [future.result() for future in futures] == [2, 4, 4]
        assert sorted(entry['message'] for entry in log.warnings.values()) == ['from worker 1', 'from worker 2']


class _InlineExecutor:
    """An executor that runs each task in the caller, as several tests' fakes do."""

    def submit(self, fn, *args):
        from concurrent.futures import Future
        future = Future()
        future.set_result(fn(*args))
        return future


def test_a_task_run_in_the_caller_leaves_no_log_behind():
    """A task outside any invocation records into a log of its own for that task only: a log left
    on the thread would swallow every later invocation's notes (each would join it)."""
    from reveal.utils.parallel import submit_each
    assert [f.result() for f in submit_each(_InlineExecutor(), _record_in_worker, [3])] == [6]
    assert current_log() is None


def test_json_answer_running_follows_the_answer_format():
    from argparse import Namespace
    from reveal.cli.global_flags import apply_global_flags
    from reveal.utils.invocation_log import json_answer_running
    assert json_answer_running() is False  # no invocation
    with log_scope(to_stderr=False):
        apply_global_flags(Namespace(format='json'))
        assert json_answer_running() is True
        apply_global_flags(Namespace(format='text'))
        assert json_answer_running() is False


def _format_in_worker(item):
    from reveal.utils.invocation_log import json_answer_running
    return json_answer_running()


def test_a_pool_task_runs_in_the_submitting_invocations_answer_format():
    from concurrent.futures import ThreadPoolExecutor
    from reveal.utils.parallel import submit_each
    for is_json in (True, False):
        with log_scope(to_stderr=False), ThreadPoolExecutor(max_workers=2) as pool:
            answer_is_json(is_json)
            assert [f.result() for f in submit_each(pool, _format_in_worker, [1, 2])] == [is_json, is_json]
    with log_scope(to_stderr=False) as log:  # a task run in the caller leaves the caller's format as it was
        answer_is_json(True)
        submit_each(_InlineExecutor(), _format_in_worker, [1])
        assert log.json_answer is True
