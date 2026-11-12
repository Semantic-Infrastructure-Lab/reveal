"""Workflow canonical controls reuse existing exact-tool and literal-text selection."""
import json

import pytest

from conftest import _run_reveal_in
from reveal import query
from reveal.errors import RequestValidationError
from test_claude_source_evidence_back2617 import transcript


@pytest.mark.parametrize('params,legacy,tools', [
    ({'where': ['tool==bAsH']}, ['--type', 'bash'], ['Bash']),
    ({'match': 'auth.py'}, ['--name', 'auth.py'], ['Read', 'Bash', 'Edit']),
    ({'match': 'pytest'}, ['--name', 'pytest'], ['Bash']),
    ({'match': 'rEaD'}, ['--name', 'read'], ['Read']),
    ({'where': ['tool==Edit'], 'match': 'auth.py'}, ['--type', 'Edit', '--name', 'auth.py'], ['Edit']),
])
def test_api_selection_matches_the_existing_cli_population(transcript, params, legacy, tools):
    canonical = query('claude://session/my-session', view='workflow', **params)
    old = _run_reveal_in(transcript.parent, 'claude://session/my-session/workflow', *legacy, '--format', 'json')
    assert old.returncode == 0
    assert canonical['workflow'] == json.loads(old.stdout)['workflow']
    assert [step['tool'] for step in canonical['workflow']] == tools
    assert canonical['total_steps'] == 3


def test_selection_precedes_paging_and_both_cli_spellings_agree(transcript):
    api = query('claude://session/my-session', view='workflow', where=['tool==Bash'], limit=1)
    assert [step['tool'] for step in api['workflow']] == ['Bash']
    assert api['meta']['pagination']['total'] == 1
    named = _run_reveal_in(transcript.parent, 'claude', 'session/my-session', '--view', 'workflow',
                           '--where', 'tool==Bash', '--limit', '1', '--format', 'json')
    uri = _run_reveal_in(transcript.parent, 'claude://session/my-session?view=workflow&where=tool==Bash&limit=1', '--format', 'json')
    assert named.returncode == uri.returncode == 0
    assert json.loads(named.stdout) == json.loads(uri.stdout)


def test_tool_predicate_is_equality_and_repeated_constraints_are_anded(transcript):
    assert query('claude://session/my-session/workflow', where=['tool==Ba'])['workflow'] == []
    assert query('claude://session/my-session/workflow', where=['tool==Read', 'tool==Edit'])['workflow'] == []


@pytest.mark.parametrize('resource,expression', [('sessions', 'tool==Bash'),
                                               ('session/my-session/workflow', 'session~=my'),
                                               ('session/my-session/workflow', 'tool~=Ba')])
def test_predicate_fields_and_operators_remain_reader_specific(transcript, resource, expression):
    with pytest.raises(RequestValidationError, match='where'):
        query('claude://' + resource, where=[expression])


@pytest.mark.parametrize('field', ['receipt', 'counts', 'page'])
def test_presentation_cannot_drop_measured_workflow_selection(transcript, monkeypatch, field):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    def corrupt(self, result, args):
        if field == 'receipt':
            result['meta'].pop('workflow_selection', None)
        elif field == 'counts':
            result['meta']['workflow_selection']['selected'] = 999
        else:
            result['meta']['pagination'] = 'invalid'
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', corrupt)
    answer = _run_reveal_in(transcript.parent, 'claude://session/my-session/workflow?match=auth.py&limit=1', '--format', 'json')
    assert answer.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(answer.stdout)['meta']['errors'])


def test_filtering_all_known_steps_cannot_hide_source_loss(transcript):
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write('{broken\n')
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/workflow?where=tool==Absent', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['workflow'] == []
    assert answer['meta']['transcript_analysis']['failed_records'] == 1


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_workflow_selection_preserves_partial_failed_and_fresh_sources(transcript, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    original = transcript.read_bytes()
    transcript.write_bytes(original + b'{broken\n')
    async def scenario(session):
        request = {'uri': 'claude://session/my-session/workflow?where=tool==Absent&limit=0', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert answer['workflow'] == []
        assert answer['meta']['transcript_analysis']['failed_records'] == 1
        assert answer['meta']['workflow_selection']['before'] == 3
        transcript.write_bytes(b'{broken\n')
        assert (await session.call_tool('reveal_query', request)).is_error
        transcript.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['transcript_analysis']['failed_records'] == 0
    _run(transcript.parent, scenario)


def test_workflow_predicate_and_match_codecs_keep_literal_api_values(transcript):
    from urllib.parse import quote
    tool = 'Bash&%41=+π'
    transcript.write_text(transcript.read_text(encoding='utf-8').replace('"Bash"', json.dumps(tool)), encoding='utf-8')
    expression = 'tool==' + tool
    api = query('claude://session/my-session/workflow', where=[expression], match=tool)
    uri = query('claude://session/my-session/workflow?where=' + quote(expression, safe='') + '&match=' + quote(tool, safe=''))
    assert api == uri
    assert [step['tool'] for step in api['workflow']] == [tool]


def test_workflow_none_omits_valid_controls_and_invalid_originals_still_reject(transcript):
    answer = query('claude://session/my-session/workflow?where=tool==Bash&match=pytest', where=None, match=None)
    assert len(answer['workflow']) == 3
    assert 'workflow_selection' not in answer['meta']
    with pytest.raises(RequestValidationError):
        query('claude://session/my-session/workflow?where=tool~=Ba', where=None)
