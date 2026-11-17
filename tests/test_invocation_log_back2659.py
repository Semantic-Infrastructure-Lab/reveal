"""The per-invocation log lives below the CLI (BACK-2659): code at any layer records into it."""
from reveal.cli.invocation import Invocation, invocation_scope, noted_retirements, retirement_note
from reveal.utils.invocation_log import current_log, log_scope


def test_no_log_outside_an_invocation():
    assert current_log() is None


def test_scope_opens_a_log_and_restores_the_previous_one():
    with log_scope(to_stderr=False) as outer:
        assert current_log() is outer and outer.to_stderr is False
        with log_scope() as inner:
            assert current_log() is inner and inner is not outer
        assert current_log() is outer
    assert current_log() is None


def test_invocation_scope_records_retirements_in_that_log():
    with invocation_scope(Invocation.parse(['reveal', '.']), retirements_to_stderr=False):
        log = current_log()
        assert log is not None and log.to_stderr is False
        retirement_note('flag:--calls')
        assert list(log.noted) == ['flag:--calls'] == list(noted_retirements())
    assert current_log() is None and noted_retirements() == {}
