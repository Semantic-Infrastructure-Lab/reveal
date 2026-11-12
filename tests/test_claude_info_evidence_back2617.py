"""Installation inventory preserves measured absence and partial path metadata."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from test_claude_source_evidence_back2617 import transcript


@pytest.fixture
def info_home(transcript, monkeypatch):
    home = transcript.parent.parent.parent
    for name, path in {'CLAUDE_HOME': home, 'CONVERSATION_BASE': home / 'projects',
                       'PLANS_DIR': home / 'plans', 'CLAUDE_JSON': home.parent / '.claude.json',
                       'AGENTS_DIR': home / 'agents', 'HOOKS_DIR': home / 'hooks'}.items():
        monkeypatch.setattr(ClaudeAdapter, name, path)
    monkeypatch.setattr(ClaudeAdapter, 'SESSIONS_DIR', None)
    return home


def deny_stat(monkeypatch, paths):
    original = Path.stat
    def denied(path, *args, **kwargs):
        if path in paths:
            raise PermissionError('injected metadata denial')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', denied)


def test_info_metadata_denial_keeps_other_paths_without_claiming_absence(transcript, info_home, monkeypatch):
    denied = info_home / 'settings.json'
    deny_stat(monkeypatch, {denied})
    result = _run_reveal_in(transcript.parent, 'claude://info', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['paths']['settings']['exists'] is None
    assert answer['paths']['history']['exists'] is True
    proof = answer['meta']['info_analysis']
    assert proof['candidate_paths'] == 8 and proof['failed_paths'] == 1
    assert proof['analyzed_paths'] == proof['usable_paths'] == 7


def test_info_text_marks_metadata_denial_as_unreadable(transcript, info_home, monkeypatch):
    deny_stat(monkeypatch, {info_home / 'settings.json'})
    result = _run_reveal_in(transcript.parent, 'claude://info')
    assert result.returncode == 3
    row = next(line for line in result.stdout.splitlines() if line.strip().startswith('settings '))
    assert 'unreadable' in row and '[not found]' not in row


def test_info_partial_directory_count_retains_observed_entries(transcript, info_home, monkeypatch):
    plans = info_home / 'plans'
    original = Path.iterdir
    def interrupted(path):
        if path == plans:
            yield plans / 'known-name.md'
            raise PermissionError('injected partial directory count')
        yield from original(path)
    monkeypatch.setattr(Path, 'iterdir', interrupted)
    result = _run_reveal_in(transcript.parent, 'claude://info', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['paths']['plans']['exists'] is True
    assert answer['paths']['plans']['count'] is None
    assert answer['paths']['plans']['entries_seen'] == 1
    assert answer['meta']['info_analysis']['usable_paths'] == 8


def test_optional_path_absence_is_a_complete_inventory(transcript, info_home):
    (info_home / 'settings.json').unlink()
    result = _run_reveal_in(transcript.parent, 'claude://info', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['paths']['settings']['exists'] is False
    assert answer['meta']['info_analysis']['analyzed_paths'] == 8
    assert answer['meta']['info_analysis']['failed_paths'] == 0


def test_nondirectory_parent_is_confirmed_optional_absence(transcript, info_home, monkeypatch, tmp_path):
    parent = tmp_path / 'plain-file'
    parent.write_text('not a directory', encoding='utf-8')
    monkeypatch.setattr(ClaudeAdapter, 'PLANS_DIR', parent / 'plans')
    result = _run_reveal_in(transcript.parent, 'claude://info', '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['paths']['plans']['exists'] is False


@pytest.mark.parametrize('erase', ['proof', 'path', 'presence'])
def test_info_presentation_cannot_change_measured_metadata(transcript, info_home, monkeypatch, erase):
    def post_process(self, result, args):
        if erase == 'proof':
            result['meta'].pop('info_analysis')
        elif erase == 'path':
            result['paths'].pop('settings')
        else:
            result['paths']['settings']['exists'] = False
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://info', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_info_legacy_batch_keeps_native_metadata_failure_marker(transcript, info_home, monkeypatch):
    deny_stat(monkeypatch, {info_home / 'settings.json'})
    result = _run_reveal_in(transcript.parent, '--stdin', '--batch', '--format', 'json',
                            stdin='claude://info\n')
    assert result.returncode == 2
    answer = json.loads(result.stdout)['results'][0]['data']
    assert answer['error'] and answer['paths']['history']['exists'] is True


def test_info_output_failure_overrides_complete_inventory(transcript, info_home):
    result = _run_reveal_in(transcript.parent, 'claude://info', '--format', 'json',
                            '--output', 'json=' + str(transcript.parent / 'absent-info-output' / 'answer.json'))
    assert result.returncode == 3


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_info_partial_failed_and_fresh_followup(transcript, info_home, monkeypatch, tmp_path):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(info_home))
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(info_home / 'projects'))
    monkeypatch.setenv('REVEAL_CLAUDE_JSON', str(info_home.parent / '.claude.json'))
    marker = tmp_path / 'metadata-failure-mode'
    monkeypatch.setenv('REVEAL_TEST_INFO_FAILURE_MODE', str(marker))
    server = '''
import os
from pathlib import Path
from reveal import mcp_server
home = Path(os.environ['REVEAL_CLAUDE_HOME'])
marker = Path(os.environ['REVEAL_TEST_INFO_FAILURE_MODE'])
targets = {home, home / 'projects', home / 'history.jsonl', home / 'plans',
           home / 'settings.json', Path(os.environ['REVEAL_CLAUDE_JSON']), home / 'agents', home / 'hooks'}
original = Path.stat
def stat(path, *args, **kwargs):
    if path in targets and marker.exists():
        mode = marker.read_text(encoding='utf-8')
        if mode == 'all' or path == home / 'settings.json':
            raise PermissionError('injected metadata denial')
    return original(path, *args, **kwargs)
Path.stat = stat
mcp_server.main()
'''
    async def scenario(session):
        request = {'uri': 'claude://info', 'provenance': True}
        marker.write_text('partial', encoding='utf-8')
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert answer['paths']['settings']['exists'] is None
        assert answer['meta']['info_analysis']['usable_paths'] == 7
        marker.write_text('all', encoding='utf-8')
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        marker.unlink()
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['info_analysis']['failed_paths'] == 0
    _run(transcript.parent, scenario, code=server)
