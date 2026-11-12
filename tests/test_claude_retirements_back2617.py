"""Legacy Claude query names retain answers and disclose their canonical replacements."""
import copy
import json

import pytest

from conftest import _run_reveal_in
from reveal import query
from reveal.cli.invocation import RETIREMENTS
from test_claude_source_evidence_back2617 import transcript


CASES = [
    ('summary', 'session/my-session?summary'),
    ('search', 'session/my-session?search=token'),
    ('contains', 'session/my-session/messages?contains=Fixed'),
    ('filter', 'sessions?filter=my-session'),
    ('tail', 'session/my-session?tail=2'),
    ('last', 'session/my-session?last'),
    ('full', 'session/my-session/exchanges?full'),
    ('raw', 'session/my-session/messages?raw'),
]


@pytest.mark.parametrize('name,resource', CASES)
def test_retirement_adds_exactly_one_notice_and_keeps_the_reader_answer(transcript, monkeypatch, name, resource):
    uri = 'claude://' + resource
    api_before = query(uri)
    key = 'param:claude.' + name
    with monkeypatch.context() as context:
        context.delitem(RETIREMENTS, key)
        baseline = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert baseline.returncode == 0 and baseline.stderr == ''
    expected = json.loads(baseline.stdout)
    result = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    records = [w for w in answer['meta']['warnings'] if w.get('code') == 'retired_spelling']
    assert len(records) == 1
    key = 'param:claude.' + name
    entry = RETIREMENTS[key]
    assert records[0]['field'] == key and records[0]['message'] == entry.text
    assert result.stderr == 'note: ' + entry.text + '\n'
    restored = copy.deepcopy(answer)
    restored['meta']['warnings'].remove(records[0])
    assert restored == expected
    assert query(uri) == api_before


def test_turn_slice_notices_disclose_order_and_zero_differences():
    for name in ('tail', 'last'):
        text = RETIREMENTS['param:claude.' + name].replacement
        assert 'chronological' in text and 'latest-first' in text
        assert 'zero' in text and 'uncapped' in text


def test_canonical_controls_emit_no_retirement_notice(transcript):
    result = _run_reveal_in(transcript.parent, 'claude', 'session/my-session',
                            '--view', 'messages', '--sort=-message_index', '--limit', '1', '--format', 'json')
    assert result.returncode == 0 and result.stderr == ''
    assert not any(w.get('code') == 'retired_spelling' for w in json.loads(result.stdout)['meta']['warnings'])


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_notice_is_json_only_and_fresh_canonical_request_has_none(transcript, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    async def scenario(session):
        legacy = await session.call_tool('reveal_query', {
            'uri': 'claude://session/my-session?last', 'provenance': True})
        assert not legacy.is_error, _text(legacy)
        answer = json.loads(_text(legacy))
        notices = [w for w in answer['meta']['warnings'] if w.get('code') == 'retired_spelling']
        assert [w['field'] for w in notices] == ['param:claude.last']
        canonical = await session.call_tool('reveal_query', {
            'uri': 'claude://session/my-session?view=messages&sort=-message_index&limit=1', 'provenance': True})
        assert not canonical.is_error, _text(canonical)
        assert not any(w.get('code') == 'retired_spelling' for w in json.loads(_text(canonical))['meta']['warnings'])
    _run(transcript.parent, scenario)
