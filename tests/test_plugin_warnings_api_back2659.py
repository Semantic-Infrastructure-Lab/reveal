"""DiscoveryNotes: what a once-per-process discovery met reaches every invocation (BACK-2659)."""
import logging

from reveal.utils.invocation_log import log_scope
from reveal.utils.plugin_warnings import DiscoveryNotes, plugin_warning

LOGGER = logging.getLogger('reveal.test_plugin_notes')


def _entry():
    return plugin_warning('plugin_load_failed', 'plugin p.py did not load', path='p.py', kind='analyzer',
                          reason='ImportError: x')


def test_entry_shape():
    assert _entry() == {'type': 'plugin_warning', 'code': 'plugin_load_failed', 'message': 'plugin p.py did not load',
                        'path': 'p.py', 'kind': 'analyzer', 'reason': 'ImportError: x'}


def test_note_records_inside_an_invocation_and_logs_nothing(caplog):
    notes = DiscoveryNotes(LOGGER)
    with caplog.at_level(logging.WARNING), log_scope(to_stderr=False) as log:
        notes.note(_entry(), logging.WARNING, 'failed %s', 'p.py')
    assert list(log.warnings.values()) == [_entry()]
    assert caplog.records == []


def test_note_logs_outside_an_invocation(caplog):
    with caplog.at_level(logging.WARNING):
        DiscoveryNotes(LOGGER).note(_entry(), logging.WARNING, 'failed %s', 'p.py')
    assert caplog.messages == ['failed p.py']


def test_replay_reaches_each_later_invocation_once():
    notes = DiscoveryNotes(LOGGER)
    with log_scope(to_stderr=False):
        notes.note(_entry(), logging.WARNING, 'failed')
    for _ in range(2):
        with log_scope(to_stderr=False) as log:
            notes.replay()
            notes.replay()
        assert list(log.warnings.values()) == [_entry()]


def test_clear_forgets_the_previous_discovery():
    notes = DiscoveryNotes(LOGGER)
    with log_scope(to_stderr=False):
        notes.note(_entry(), logging.WARNING, 'failed')
    notes.clear()
    with log_scope(to_stderr=False) as log:
        notes.replay()
    assert log.warnings == {}


def test_failure_cause_keeps_an_oserror_path_out_and_matches_failure_of():
    from reveal.utils.causes import failure_cause
    from reveal.utils.path_utils import failure_of
    error = PermissionError(13, 'Permission denied', 'secret/abs/dir')
    assert failure_cause(error) == 'PermissionError: Permission denied' == failure_of(error).cause
    assert failure_cause(ImportError('boom')) == 'ImportError: boom' == failure_of(ImportError('boom')).cause
    assert failure_cause(OSError('no strerror')) == 'OSError: no strerror'
