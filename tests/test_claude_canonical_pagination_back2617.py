"""Canonical pages are answer-row selections, independent of source completeness."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.api import query
from reveal.errors import RequestValidationError
from test_claude_source_evidence_back2617 import transcript
from test_claude_workspace_lists_back2617 import workspace_home


def test_messages_sort_then_offset_then_limit_retains_population_count(transcript):
    original = query('claude://session/my-session', view='messages')
    expected = sorted(original['messages'], key=lambda row: row['message_index'], reverse=True)[1:2]
    page = query('claude://session/my-session', view='messages', sort='-message_index', offset=1, limit=1)
    assert page['messages'] == expected
    assert page['total_turns'] == original['total_turns']
    proof = page['meta']['pagination']
    assert proof['total'] == len(original['messages']) and proof['shown'] == 1
    result = _run_reveal_in(transcript.parent,
                            'claude://session/my-session?view=messages&sort=-message_index&offset=1&limit=1', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['messages'] == expected and answer['total_turns'] == original['total_turns']


def test_limit_zero_is_uncapped_and_offset_beyond_end_is_complete(transcript):
    original = query('claude://session/my-session', view='messages')
    assert query('claude://session/my-session', view='messages', limit=0)['messages'] == original['messages']
    empty = query('claude://session/my-session', view='messages', offset=100, limit=1)
    assert empty['messages'] == [] and empty['total_turns'] == original['total_turns']


def test_explicit_uncapped_catalog_bypasses_legacy_default_display_cap(transcript):
    for index in range(25):
        (transcript.parent / f'extra-{index}.jsonl').write_bytes(transcript.read_bytes())
    result = _run_reveal_in(transcript.parent, 'claude://sessions?limit=0', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['session_count'] == len(answer['recent_sessions']) == 28
    assert answer['meta']['pagination']['limit'] == 0


@pytest.mark.parametrize('resource,field', [('plans', 'plans'), ('agents', 'agents'),
                                         ('memory', 'memories'), ('hooks', 'hooks'), ('history', 'entries')])
def test_pagination_uses_existing_list_readers(transcript, workspace_home, monkeypatch, resource, field):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_HOME', workspace_home)
    original = query('claude://' + resource)
    page = query('claude://' + resource, offset=1, limit=1)
    assert page[field] == original[field][1:2]
    result = _run_reveal_in(transcript.parent, f'claude://{resource}?offset=1&limit=1', '--format', 'json')
    assert result.returncode == 0


@pytest.mark.parametrize('resource,kwargs', [('info', {'limit': 1}),
                                         ('session/my-session', {'limit': 1}),
                                         ('session/my-session/messages', {'sort': 'invented'}),
                                         ('session/my-session/messages', {'sort': '--message_index'}),
                                         ('session/my-session/messages', {'sort': ''}),
                                         ('session/my-session/messages', {'limit': -1})])
def test_invalid_page_scope_rejects_before_api_override(transcript, resource, kwargs):
    with pytest.raises(RequestValidationError):
        query('claude://' + resource, **kwargs)


def test_page_keeps_required_record_loss_even_when_offset_hides_all_rows(transcript):
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write('{"broken\n')
    result = _run_reveal_in(transcript.parent,
                            'claude://session/my-session?view=messages&offset=100&limit=1', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['messages'] == [] and answer['meta']['transcript_analysis']['failed_records'] == 1


@pytest.mark.parametrize('field', ['pagination', 'shown'])
def test_presentation_cannot_erase_or_rewrite_page_receipt(transcript, monkeypatch, field):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    def post_process(self, result, args):
        if field == 'pagination':
            result['meta'].pop('pagination')
        else:
            result['meta']['pagination']['shown'] = 999
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session?view=messages&limit=1', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_legacy_tail_order_and_zero_are_unchanged(transcript):
    original = query('claude://session/my-session', view='messages')
    assert query('claude://session/my-session', tail=2)['messages'] == original['messages'][-2:]
    assert query('claude://session/my-session', tail=0)['messages'] == []
    with pytest.raises(RequestValidationError):
        query('claude://session/my-session?limit=-1', limit=1)


def test_canonical_page_rejects_conflicting_legacy_display_slice(transcript):
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session?view=messages&limit=1', '--head', '2', '--format', 'json')
    assert result.returncode == 2


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_pages_keep_loss_and_fresh_followups(transcript, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    original = transcript.read_bytes()
    transcript.write_bytes(original + b'{"broken\n')
    async def scenario(session):
        request = {'uri': 'claude://session/my-session?view=messages&limit=1', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert len(answer['messages']) == 1 and answer['meta']['pagination']['total'] > 1
        assert answer['meta']['transcript_analysis']['failed_records'] == 1
        transcript.write_bytes(b'{"broken\n')
        assert (await session.call_tool('reveal_query', request)).is_error
        transcript.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['transcript_analysis']['failed_records'] == 0
    _run(transcript.parent, scenario)


@pytest.mark.parametrize('resource,field', [
    ('session/my-session/prompts?raw', 'messages'), ('session/my-session/messages?raw', 'messages'),
    ('session/my-session/prompts', 'messages'), ('session/my-session/message', 'messages'),
    ('session/my-session/thinking', 'blocks'), ('session/my-session?tools=Bash', 'calls'),
    ('session/my-session/files', 'operations'), ('session/my-session/workflow', 'workflow'),
    ('session/my-session/agents', 'agents'), ('session/my-session/context', 'changes'),
    ('session/my-session/timeline', 'timeline'), ('session/my-session/errors', 'errors'),
    ('session/my-session/exchanges', 'exchanges'), ('session/my-session?search=auth', 'matches'),
    ('session/my-session?errors&contains=failed', 'results'), ('session/my-session/tokens', 'messages'),
    ('session/my-session/chain', 'chain'), ('files//home/user/proj/auth.py', 'sessions'),
    ('sessions?match=auth', 'matches'), ('hooks/Start', 'scripts'), ('config', 'projects'),
])
def test_supported_list_views_page_the_existing_observations(transcript, workspace_home, monkeypatch, resource, field):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_JSON', workspace_home.parent / '.claude.json')
    event = workspace_home / 'hooks' / 'Start'
    event.mkdir()
    for name in ('one.sh', 'two.sh'):
        (event / name).write_text('echo body', encoding='utf-8')
    original = query('claude://' + resource)
    page = query('claude://' + resource, offset=1, limit=1)
    assert page[field] == original[field][1:2]
    assert page['meta']['pagination']['total'] == len(original[field])
    separator = '&' if '?' in resource else '?'
    result = _run_reveal_in(transcript.parent, 'claude://' + resource + separator + 'offset=1&limit=1', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[field] == original[field][1:2]


def test_output_budget_can_cut_a_measured_page_without_losing_counts(transcript):
    rows = [json.loads(line) for line in transcript.read_text(encoding='utf-8').splitlines()]
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in rows + [rows[4]] * 3), encoding='utf-8')
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session?errors&contains=failed&limit=3',
                            '--max-items', '1', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert len(answer['results']) == 1
    assert answer['meta']['pagination']['shown'] == 3
    assert answer['displayed_count'] == 1


def test_page_original_scope_validation_precedes_overlay_and_none_clears_valid_page(transcript):
    with pytest.raises(RequestValidationError):
        query('claude://session/my-session?view=messages&sort=invented', sort='message_index')
    original = query('claude://session/my-session', view='messages')
    cleared = query('claude://session/my-session?view=messages&limit=1', limit=None)
    assert cleared == original


def test_invalid_uri_sort_is_an_answered_request_error(transcript):
    result = _run_reveal_in(transcript.parent, 'claude://sessions?sort=name', '--format', 'json')
    assert result.returncode == 2
    assert any(e['code'] == 'invalid_request' for e in json.loads(result.stdout)['meta']['errors'])
