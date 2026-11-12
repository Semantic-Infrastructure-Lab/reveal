"""Installation JSON sources distinguish healthy absence, read loss and key semantics."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.api import query
from test_claude_source_evidence_back2617 import transcript


@pytest.fixture
def installation(transcript, monkeypatch):
    home = transcript.parent.parent.parent
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_HOME', home)
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_JSON', home.parent / '.claude.json')
    return {'settings': home / 'settings.json', 'config': home.parent / '.claude.json'}


@pytest.mark.parametrize('resource', ['settings', 'config'])
def test_missing_install_json_is_a_request_error_but_malformed_source_is_analysis_loss(
        transcript, installation, resource):
    path = installation[resource]
    path.write_text('{"truncated":', encoding='utf-8')
    malformed = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert malformed.returncode == 3
    path.unlink()
    missing = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert missing.returncode == 2
    answer = query('claude://' + resource)
    assert answer['error']
    assert answer['meta']['installation_analysis']['request_rejected'] is True


def test_settings_and_config_keep_distinct_missing_key_semantics(transcript, installation):
    settings = _run_reveal_in(transcript.parent, 'claude://settings?key=absent', '--format', 'json')
    assert settings.returncode == 2
    config = _run_reveal_in(transcript.parent, 'claude://config?key=absent', '--format', 'json')
    assert config.returncode == 0 and json.loads(config.stdout)['value'] is None
    assert query('claude://settings', key='absent')['error']


def test_config_decode_repair_retains_values_with_source_loss(transcript, installation):
    installation['config'].write_bytes(b'{"autoUpdates":"repaired \xff"}')
    result = _run_reveal_in(transcript.parent, 'claude://config', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['flags']['autoUpdates'] == 'repaired \ufffd'
    assert answer['meta']['installation_analysis']['recovered_operations'] == 1


@pytest.mark.parametrize('resource', ['settings', 'config'])
def test_valid_empty_document_is_measured_success(transcript, installation, resource):
    installation[resource].write_text('{}', encoding='utf-8')
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 0
    proof = json.loads(result.stdout)['meta']['installation_analysis']
    assert proof['selected'] is True and proof['parsed'] is True and proof['usable'] is True
    assert proof['failed_operations'] == 0


@pytest.mark.parametrize('resource', ['settings', 'config'])
@pytest.mark.parametrize('value', [None, False, 0])
def test_scalar_key_values_are_present_successes(transcript, installation, resource, value):
    installation[resource].write_text(json.dumps({'value': value}), encoding='utf-8')
    result = _run_reveal_in(transcript.parent, 'claude://' + resource + '?key=value', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert 'value' in answer and answer['value'] == value and type(answer['value']) is type(value)


@pytest.mark.parametrize('resource', ['settings', 'config'])
def test_loss_after_selection_is_not_request_absence(transcript, installation, monkeypatch, resource):
    from pathlib import Path
    from reveal.adapters.claude.handlers import system
    path = installation[resource]
    if resource == 'settings':
        def disappeared(*args, **kwargs):
            raise FileNotFoundError('injected disappearance after selection')
        monkeypatch.setattr(system, 'open', disappeared, raising=False)
    else:
        original = Path.read_text
        def disappeared(selected, *args, **kwargs):
            if selected == path:
                raise FileNotFoundError('injected disappearance after selection')
            return original(selected, *args, **kwargs)
        monkeypatch.setattr(Path, 'read_text', disappeared)
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 3
    proof = json.loads(result.stdout)['meta']['installation_analysis']
    assert proof['selected'] is True and proof['request_rejected'] is False
    assert proof['failed_operations'] == 1


@pytest.mark.parametrize('resource', ['settings', 'config'])
def test_selection_permission_failure_cannot_look_missing(transcript, installation, monkeypatch, resource):
    from pathlib import Path
    path = installation[resource]
    original = Path.stat
    def denied(selected, *args, **kwargs):
        if selected == path:
            raise PermissionError('injected selection failure')
        return original(selected, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', denied)
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 3
    proof = json.loads(result.stdout)['meta']['installation_analysis']
    assert proof['selected'] is False and proof['request_rejected'] is False


@pytest.mark.parametrize('resource', ['settings', 'config'])
def test_scalar_presentation_preserves_false_and_zero_distinction(transcript, installation, monkeypatch, resource):
    installation[resource].write_text('{"value":false}', encoding='utf-8')
    def change(self, result, args):
        result['value'] = 0
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', change)
    result = _run_reveal_in(transcript.parent, 'claude://' + resource + '?key=value', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.parametrize('resource,field', [('settings', 'settings'), ('config', 'projects')])
@pytest.mark.parametrize('erase', ['proof', 'rows'])
def test_installation_presentation_cannot_erase_source_observations(
        transcript, installation, monkeypatch, resource, field, erase):
    def post_process(self, result, args):
        if erase == 'proof':
            result['meta'].pop('installation_analysis')
        else:
            result[field] = {} if resource == 'settings' else []
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.parametrize('resource', ['settings', 'config'])
def test_required_installation_output_failure_overrides_healthy_source(transcript, installation, resource):
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json',
                            '--output', 'json=' + str(transcript.parent / 'absent-output' / 'answer.json'))
    assert result.returncode == 3


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_installation_partial_failed_fresh_and_public_request_errors(transcript, installation, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(installation['settings'].parent))
    monkeypatch.setenv('REVEAL_CLAUDE_JSON', str(installation['config']))
    config = installation['config']
    config.write_bytes(b'{"autoUpdates":"repaired \xff"}')
    async def scenario(session):
        request = {'uri': 'claude://config', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        assert json.loads(_text(partial))['meta']['installation_analysis']['recovered_operations'] == 1
        config.write_text('{"truncated":', encoding='utf-8')
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        config.write_text('{"autoUpdates":false}', encoding='utf-8')
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['flags']['autoUpdates'] is False
        missing_key = await session.call_tool('reveal_query', {'uri': 'claude://settings?key=absent'})
        assert missing_key.is_error and 'Key not found' in _text(missing_key)
        config.unlink()
        absent = await session.call_tool('reveal_query', request)
        assert absent.is_error and 'Config not found' in _text(absent)
    _run(transcript.parent, scenario)


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_repaired_document_does_not_excuse_corrupted_presentation(transcript, installation, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_JSON', str(installation['config']))
    installation['config'].write_bytes(b'{"autoUpdates":"repaired \xff"}')
    server = '''
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal import mcp_server
def erase(self, result, args):
    if result.get('type') == 'claude_config':
        result['flags'] = {}
    return result
ClaudeAdapter.post_process = erase
mcp_server.main()
'''
    async def scenario(session):
        answer = await session.call_tool('reveal_query', {'uri': 'claude://config', 'provenance': True})
        assert answer.is_error, _text(answer)
    _run(transcript.parent, scenario, code=server)
