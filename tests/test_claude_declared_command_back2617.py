"""The named Claude command and URI share bound controls and one answer owner."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from test_claude_source_evidence_back2617 import transcript
from test_claude_workspace_lists_back2617 import workspace_home


@pytest.fixture
def command_home(transcript, workspace_home, monkeypatch):
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_HOME', workspace_home)
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_JSON', workspace_home.parent / '.claude.json')
    return workspace_home


@pytest.mark.parametrize('resource,options,query', [
    ('sessions', ['--where', 'session~=home', '--limit', '1'], 'where=session~=home&limit=1'),
    ('session/my-session', ['--view', 'messages', '--match', 'Fixed', '--limit', '1'], 'view=messages&match=Fixed&limit=1'),
    ('session/my-session', ['--view', 'errors', '--match', 'failed'], 'view=errors&match=failed'),
    ('session/my-session', ['--view', 'tools', '--tools', 'Bash', '--detail', 'full'], 'view=tools&tools=Bash&detail=full'),
    ('session/my-session', ['--view', 'messages', '--detail', 'raw', '--limit', '1'], 'view=messages&detail=raw&limit=1'),
    ('history', ['--match', 'auth', '--limit', '1'], 'match=auth&limit=1'),
    ('settings', ['--key', 'model'], 'key=model'),
    ('config', ['--key', 'missing'], 'key=missing'),
    ('plans', ['--match', 'signed', '--limit', '1'], 'match=signed&limit=1'),
    ('agents', ['--match', 'Review'], 'match=Review'),
    ('info', [], ''),
])
def test_command_and_uri_have_equal_json_and_exit(transcript, command_home, resource, options, query):
    command = _run_reveal_in(transcript.parent, 'claude', resource, *options, '--format', 'json')
    uri = _run_reveal_in(transcript.parent, 'claude://' + resource + ('?' + query if query else ''), '--format', 'json')
    assert command.returncode == uri.returncode == 0
    assert json.loads(command.stdout) == json.loads(uri.stdout)


@pytest.mark.parametrize('form', ['command', 'uri'])
def test_base_path_override_reconfigures_the_same_store(transcript, command_home, tmp_path, form):
    from claude_session_fixture import build_claude_home
    other = build_claude_home(tmp_path / 'other')
    for path in (other / 'projects').rglob('*.jsonl'):
        path.write_text('', encoding='utf-8')
    args = ['claude', 'session/my-session', '--view', 'messages'] if form == 'command' else ['claude://session/my-session?view=messages']
    result = _run_reveal_in(transcript.parent, *args, '--base-path', str(other / 'projects'), '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['messages'] == [] and answer['source'].startswith(other.as_posix())


def test_command_help_teaches_own_controls(transcript):
    result = _run_reveal_in(transcript.parent, 'claude', '--help')
    assert result.returncode == 0
    for option in ('--view', '--detail', '--where', '--match', '--sort', '--limit', '--offset'):
        assert option in result.stdout


@pytest.mark.parametrize('form', ['command', 'uri'])
def test_declared_forms_keep_source_loss_and_output_failure(transcript, command_home, form):
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write('{"broken\n')
    args = ['claude', 'session/my-session', '--view', 'messages'] if form == 'command' else ['claude://session/my-session?view=messages']
    partial = _run_reveal_in(transcript.parent, *args, '--format', 'json')
    assert partial.returncode == 3
    assert json.loads(partial.stdout)['meta']['transcript_analysis']['failed_records'] == 1
    failed = _run_reveal_in(transcript.parent, *args, '--output', 'json=' + str(transcript.parent / 'missing' / 'answer.json'))
    assert failed.returncode == 3


@pytest.mark.parametrize('form', ['command', 'uri'])
def test_displayed_session_stats_remain_available(transcript, command_home, form):
    args = ['claude', 'sessions', '--limit', '1'] if form == 'command' else ['claude://sessions?limit=1']
    result = _run_reveal_in(transcript.parent, *args, '--with-stats', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['with_stats'] is True
    assert answer['recent_sessions'][0]['message_count'] == 8


@pytest.mark.parametrize('form', ['command', 'uri'])
def test_stats_rejects_non_listing_scope(transcript, command_home, form):
    args = ['claude', 'session/my-session'] if form == 'command' else ['claude://session/my-session']
    result = _run_reveal_in(transcript.parent, *args, '--with-stats', '--format', 'json')
    assert result.returncode == 2
    assert 'session listing' in json.loads(result.stdout)['error']


def test_composite_receipt_reports_applied_api_overlay_values(transcript):
    from reveal.api import query
    result = query('claude://session/my-session?tools=Read&contains=failed', tools='Bash')
    assert json.loads(result['query']) == {'tools': 'Bash', 'contains': 'failed'}
