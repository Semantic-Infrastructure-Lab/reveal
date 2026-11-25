"""The server-only diagnostic of a failed answer names its entries' messages, never the repr of a list (BACK-2786)."""
from reveal.cli.routing.uri import _answer_diagnostic


def test_warnings_are_named_by_their_messages():
    result = {'meta': {'errors': [], 'warnings': [{'type': 'worker_lost', 'message': 'a worker died: 2 files'},
                                                  {'type': 'scan_capped'}]}}
    assert _answer_diagnostic(result) == 'a worker died: 2 files; scan_capped'


def test_errors_come_before_warnings_and_the_error_before_both():
    meta = {'errors': [{'code': 'adapter_error', 'message': 'boom'}], 'warnings': [{'type': 'x', 'message': 'w'}]}
    assert _answer_diagnostic({'meta': meta}) == 'boom'
    assert _answer_diagnostic({'error': 'top', 'meta': meta}) == 'top'


def test_no_text_keeps_the_previous_and_a_new_one_is_appended():
    assert _answer_diagnostic({'meta': {'warnings': []}}, 'before') == 'before'
    assert _answer_diagnostic({'error': 'now'}, 'before') == 'before\nnow'
    assert '[{' not in (_answer_diagnostic({'meta': {'warnings': [{'type': 'analysis_failed', 'message': 'm'}]}}) or '')
