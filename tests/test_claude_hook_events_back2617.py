"""Hook event bodies and script catalogs qualify the sources they actually consume."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from test_claude_source_evidence_back2617 import transcript
from test_claude_workspace_lists_back2617 import workspace_home


def test_missing_hook_event_is_request_error(transcript, workspace_home):
    result = _run_reveal_in(transcript.parent, 'claude://hooks/absent', '--format', 'json')
    assert result.returncode == 2


def test_hook_body_decode_repair_retains_body_with_loss(transcript, workspace_home):
    path = workspace_home / 'hooks' / 'PostToolUse'
    path.write_bytes(b'echo \xff\n')
    result = _run_reveal_in(transcript.parent, 'claude://hooks/PostToolUse', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['content'] == 'echo \ufffd\n'
    assert answer['source'] == path.as_posix() and answer['source_type'] == 'file'


@pytest.mark.parametrize('phase', ['select', 'read', 'metadata'])
def test_hook_file_failures_are_analysis_loss(transcript, workspace_home, monkeypatch, phase):
    path = workspace_home / 'hooks' / 'PostToolUse'
    original_stat, original_read = Path.stat, Path.read_text
    calls = 0
    def stat(selected, *args, **kwargs):
        nonlocal calls
        if selected == path:
            calls += 1
            if phase == 'select' or (phase == 'metadata' and calls > 1):
                raise PermissionError('injected hook metadata denial')
        return original_stat(selected, *args, **kwargs)
    def read(selected, *args, **kwargs):
        if selected == path and phase == 'read':
            raise FileNotFoundError('injected hook disappearance after selection')
        return original_read(selected, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    monkeypatch.setattr(Path, 'read_text', read)
    result = _run_reveal_in(transcript.parent, 'claude://hooks/PostToolUse', '--format', 'json')
    assert result.returncode == 3
    proof = json.loads(result.stdout)['meta']['workspace_analysis']
    assert not proof['request_rejected']
    if phase == 'metadata':
        assert 'exit 0' in json.loads(result.stdout)['content']


@pytest.mark.parametrize('loss', ['enumeration', 'entry'])
def test_hook_directory_retains_known_scripts(transcript, workspace_home, monkeypatch, loss):
    event = workspace_home / 'hooks' / 'Start'
    event.mkdir()
    good, bad = event / 'good.sh', event / 'bad.sh'
    good.write_text('echo good', encoding='utf-8')
    bad.write_text('echo bad', encoding='utf-8')
    original_stat, original_entries = Path.stat, Path.iterdir
    def stat(selected, *args, **kwargs):
        if selected == bad and loss == 'entry':
            raise PermissionError('injected hook entry denial')
        return original_stat(selected, *args, **kwargs)
    def entries(selected):
        if selected == event and loss == 'enumeration':
            yield good
            raise PermissionError('injected hook partial enumeration')
        yield from original_entries(selected)
    monkeypatch.setattr(Path, 'stat', stat)
    monkeypatch.setattr(Path, 'iterdir', entries)
    result = _run_reveal_in(transcript.parent, 'claude://hooks/Start', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert [row['name'] for row in answer['scripts']] == ['good.sh']
    assert answer['source'] == event.as_posix() and answer['source_type'] == 'directory'


@pytest.mark.parametrize('kind', ['file', 'directory'])
@pytest.mark.parametrize('erase', ['proof', 'observations'])
def test_hook_event_presentation_cannot_erase_known_source(transcript, workspace_home, monkeypatch, kind, erase):
    name = 'PostToolUse'
    if kind == 'directory':
        name = 'Start'
        event = workspace_home / 'hooks' / name
        event.mkdir()
        (event / 'script.sh').write_text('echo body', encoding='utf-8')
    def post_process(self, result, args):
        if erase == 'proof':
            result['meta'].pop('workspace_analysis')
        else:
            result['content' if kind == 'file' else 'scripts'] = '' if kind == 'file' else []
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://hooks/' + name, '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_empty_directory_and_lost_directory_metadata_are_distinct(transcript, workspace_home):
    event = workspace_home / 'hooks' / 'Start'
    event.mkdir()
    empty = _run_reveal_in(transcript.parent, 'claude://hooks/Start', '--format', 'json')
    assert empty.returncode == 0
    (event / 'lost.sh').symlink_to(event / 'nonexistent')
    failed = _run_reveal_in(transcript.parent, 'claude://hooks/Start', '--format', 'json')
    assert failed.returncode == 3
    answer = json.loads(failed.stdout)
    assert answer['scripts'] == []
    assert answer['meta']['workspace_analysis']['failed_entries'] == 1


@pytest.mark.mcp
@pytest.mark.component
@pytest.mark.parametrize('kind', ['file', 'directory'])
def test_sdk_hook_event_partial_failed_and_fresh(transcript, workspace_home, monkeypatch, kind):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(workspace_home))
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(workspace_home / 'projects'))
    event = workspace_home / 'hooks' / ('PostToolUse' if kind == 'file' else 'Start')
    if kind == 'file':
        event.write_bytes(b'echo \xff\n')
    else:
        event.mkdir()
        (event / 'good.sh').write_text('echo good', encoding='utf-8')
        (event / 'lost.sh').symlink_to(event / 'nonexistent')
    async def scenario(session):
        request = {'uri': 'claude://hooks/' + event.name, 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        proof = json.loads(_text(partial))['meta']['workspace_analysis']
        assert proof['recovered_entries'] == 1 if kind == 'file' else proof['failed_entries'] == 1
        if kind == 'file':
            event.unlink()
        else:
            (event / 'good.sh').unlink()
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        if kind == 'file':
            event.write_text('echo fresh', encoding='utf-8')
        else:
            (event / 'lost.sh').unlink()
            (event / 'fresh.sh').write_text('echo fresh', encoding='utf-8')
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        answer = json.loads(_text(healthy))
        assert answer['meta']['workspace_analysis']['failed_operations'] == 0
        assert answer['meta']['workspace_analysis']['recovered_entries'] == 0
    _run(transcript.parent, scenario)
