"""Workspace listing input loss is measured before content filters."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from test_claude_source_evidence_back2617 import transcript


@pytest.fixture
def workspace_home(transcript, monkeypatch):
    home = transcript.parent.parent.parent
    for name, path in {'PLANS_DIR': home / 'plans', 'AGENTS_DIR': home / 'agents',
                       'HOOKS_DIR': home / 'hooks', 'CONVERSATION_BASE': home / 'projects'}.items():
        monkeypatch.setattr(ClaudeAdapter, name, path)
    return home


@pytest.mark.parametrize('resource,directory', [('plans', 'plans'), ('agents', 'agents'),
                                              ('memory', 'projects/my-project/memory')])
@pytest.mark.parametrize('filtered', [False, True])
def test_workspace_read_loss_precedes_content_filter(transcript, workspace_home, monkeypatch, resource, directory, filtered):
    denied = workspace_home / directory / 'denied.md'
    denied.write_text('# auth\n', encoding='utf-8')
    original = Path.read_text
    def read(path, *args, **kwargs):
        if path == denied:
            raise PermissionError('injected workspace read denial')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    uri = 'claude://' + resource + ('?search=unfindable' if filtered else '')
    result = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert result.returncode == 3
    proof = json.loads(result.stdout)['meta']['workspace_analysis']
    assert proof['failed_entries'] == 1
    assert proof['candidate_entries'] == proof['analyzed_entries'] + proof['failed_entries']


@pytest.mark.parametrize('resource,directory', [('plans', 'plans'), ('agents', 'agents'),
                                              ('memory', 'projects/my-project/memory')])
def test_workspace_replacement_decode_is_disclosed(transcript, workspace_home, resource, directory):
    (workspace_home / directory / 'repaired.md').write_bytes(b'# repaired \xff\n')
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['workspace_analysis']['recovered_entries'] == 1


@pytest.mark.parametrize('resource', ['plans', 'agents', 'memory', 'hooks'])
def test_workspace_enumeration_loss_is_not_empty_success(transcript, workspace_home, monkeypatch, resource):
    root = workspace_home / ('projects' if resource == 'memory' else resource)
    original = Path.iterdir
    def entries(path):
        if path == root:
            raise PermissionError('injected workspace enumeration denial')
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', entries)
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['workspace_analysis']['discovery_failures'] == 1


@pytest.mark.parametrize('resource', ['plans', 'agents', 'memory', 'hooks'])
def test_missing_workspace_root_is_a_public_request_error(transcript, workspace_home, monkeypatch, resource):
    name = {'plans': 'PLANS_DIR', 'agents': 'AGENTS_DIR', 'memory': 'CONVERSATION_BASE', 'hooks': 'HOOKS_DIR'}[resource]
    monkeypatch.setattr(ClaudeAdapter, name, workspace_home / 'missing-workspace-root')
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['meta']['workspace_analysis']['request_rejected'] is True


@pytest.mark.parametrize('resource,field', [('plans', 'plans'), ('agents', 'agents'),
                                          ('memory', 'memories'), ('hooks', 'hooks')])
@pytest.mark.parametrize('erase', ['proof', 'rows'])
def test_workspace_presentation_cannot_erase_source_decisions(transcript, workspace_home, monkeypatch, resource, field, erase):
    def post_process(self, result, args):
        if erase == 'proof':
            result['meta'].pop('workspace_analysis')
        else:
            result[field] = []
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.mcp
@pytest.mark.component
@pytest.mark.parametrize('resource', ['plans', 'agents', 'memory'])
def test_sdk_workspace_partial_failed_and_fresh_source(transcript, workspace_home, monkeypatch, resource):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(workspace_home))
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(workspace_home / 'projects'))
    directory = workspace_home / ({'memory': 'projects/my-project/memory'}.get(resource, resource))
    repaired = directory / 'repaired.md'
    repaired.write_bytes(b'# repaired \xff\n')
    originals = {path: path.read_bytes() for path in directory.glob('*.md')}
    async def scenario(session):
        request = {'uri': 'claude://' + resource, 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        assert json.loads(_text(partial))['meta']['workspace_analysis']['recovered_entries'] == 1
        for path in originals:
            path.unlink()
            path.mkdir()  # named candidates remain, but none can be read as text
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        for path, data in originals.items():
            path.rmdir()
            path.write_bytes(data.replace(b'\xff', b'recovered'))
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['workspace_analysis']['recovered_entries'] == 0
    _run(transcript.parent, scenario)
