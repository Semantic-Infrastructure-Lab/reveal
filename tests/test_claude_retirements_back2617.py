"""Legacy Claude query names retain answers and disclose their canonical replacements."""
import copy
import json

import pytest

from conftest import _run_reveal_in, is_request_note
from reveal import query
from reveal.cli.invocation import RETIREMENTS, request_note_covers
from test_claude_source_evidence_back2617 import transcript
from test_retirements_back2066 import _renders


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
    every = [w for w in answer['meta']['warnings'] if w.get('code') == 'retired_spelling']
    # A URI that spells a query string says its one request note when the request has a canonical form (BACK-2716); a
    # standalone word no flag spells (summary, search, contains, tail and its word last, full, raw) gives it none.
    renders = _renders('claude', resource)
    assert sum(map(is_request_note, every)) == (1 if renders else 0)
    records = [w for w in every if not is_request_note(w)]
    key = 'param:claude.' + name
    entry = RETIREMENTS[key]
    # A covered spelling's note is the request note itself (it spells the canonical request); the rest keep their own,
    # and so does a covered one whose request has no canonical form (step 4).
    assert len(records) == (0 if request_note_covers(key) and renders else 1)
    for record in records:
        assert record['field'] == key and record['message'] == entry.text
    assert result.stderr == ''  # the JSON carries the note (BACK-2659)
    restored = copy.deepcopy(answer)
    for record in records:
        restored['meta']['warnings'].remove(record)
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
        # `last` is a word of the standalone `tail`, which no flag spells: the request has no canonical form, so it says
        # no request note and `last` keeps its own (BACK-2716 step 4).
        assert [w['field'] for w in answer['meta']['warnings'] if w.get('code') == 'retired_spelling'] == [
            'param:claude.last']
        canonical = await session.call_tool('reveal_query', {
            'uri': 'claude://session/my-session?view=messages&sort=-message_index&limit=1', 'provenance': True})
        assert not canonical.is_error, _text(canonical)
        assert not any(w.get('code') == 'retired_spelling' and not is_request_note(w)
                       for w in json.loads(_text(canonical))['meta']['warnings'])  # only the URI's request note (BACK-2716)
    _run(transcript.parent, scenario)
