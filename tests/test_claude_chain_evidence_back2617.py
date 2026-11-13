"""README continuation evidence must not turn required loss into a terminal link."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.api import query
from test_claude_source_evidence_back2617 import transcript, deny_scan


@pytest.fixture
def chain_store(transcript, monkeypatch, tmp_path):
    root = tmp_path / 'session-readmes'
    root.mkdir()
    monkeypatch.setattr(ClaudeAdapter, 'SESSIONS_DIR', root)
    return root


def readme(root, name, frontmatter):
    directory = root / name
    directory.mkdir(exist_ok=True)
    path = directory / 'README_2026-11-12.md'
    path.write_text('---\n' + frontmatter + '\n---\n# Session\n', encoding='utf-8')
    return path


@pytest.mark.parametrize('frontmatter', ['continuing_from: [\n', '- not-a-mapping',
                                        'continuing_from: [previous]'])
def test_failed_chain_metadata_is_not_a_healthy_terminal(transcript, chain_store, frontmatter):
    readme(chain_store, 'my-session', frontmatter)
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/chain', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['chain_length'] == 1
    assert answer['source'] == chain_store.as_posix()
    assert answer['meta']['chain_analysis']['failed_operations'] == 1


def test_chain_enumeration_failure_preserves_known_head(transcript, chain_store, monkeypatch):
    path = readme(chain_store, 'my-session', 'badge: head')
    deny_scan(monkeypatch, path.parent)
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/chain', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['chain'][0]['session'] == 'my-session'
    assert answer['meta']['chain_analysis']['failed_operations'] == 1


def test_chain_limit_is_source_loss_and_cycle_is_measured(transcript, chain_store):
    for i in range(51):
        readme(chain_store, 'my-session' if i == 0 else f'session-{i}',
               f'continuing_from: session-{i + 1}' if i < 50 else 'badge: tail')
    capped = _run_reveal_in(transcript.parent, 'claude://session/my-session/chain', '--format', 'json')
    assert capped.returncode == 3
    assert json.loads(capped.stdout)['meta']['chain_analysis']['stop_reason'] == 'limit'
    readme(chain_store, 'session-1', 'continuing_from: my-session')
    cycle = _run_reveal_in(transcript.parent, 'claude://session/my-session/chain', '--format', 'json')
    assert cycle.returncode == 0
    assert json.loads(cycle.stdout)['meta']['chain_analysis']['stop_reason'] == 'cycle'


def test_unconfigured_chain_does_not_read_an_unrelated_transcript(transcript, monkeypatch):
    monkeypatch.setattr(ClaudeAdapter, 'SESSIONS_DIR', None)
    def denied(self):
        raise PermissionError('transcript lookup is not a chain dependency')
    monkeypatch.setattr(ClaudeAdapter, '_find_conversation', denied)
    answer = query('claude://session/my-session/chain')
    assert answer['chain_length'] == 1 and answer['chain'][0]['readme'] is None
    assert answer['meta']['chain_analysis']['stop_reason'] == 'unconfigured'


def test_healthy_missing_readme_remains_a_disclosed_terminal(transcript, chain_store):
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/chain', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['chain_length'] == 1 and answer['chain'][0]['readme'] is None
    assert answer['meta']['chain_analysis']['stop_reason'] == 'missing-readme'


def test_latest_readme_loss_cannot_fall_back_to_an_older_healthy_link(transcript, chain_store):
    newest = readme(chain_store, 'my-session', 'badge: latest')
    newest.with_name('README_2026-01-01.md').write_text('---\nbadge: old\n---\n', encoding='utf-8')
    newest.write_bytes(b'---\nbadge: \xff\n---\n')
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/chain', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['chain'][0]['readme'] == newest.as_posix()
    assert answer['chain'][0]['badge'] is None
    assert answer['meta']['chain_analysis']['failures'][0]['cause'] == 'UnicodeDecodeError'


@pytest.mark.parametrize('erase', ['proof', 'rows'])
def test_chain_presentation_cannot_erase_source_decisions(transcript, chain_store, monkeypatch, erase):
    readme(chain_store, 'my-session', 'badge: measured')
    def post_process(self, result, args):
        if erase == 'proof':
            result['meta'].pop('chain_analysis')
        else:
            result['chain'] = []
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/chain', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_chain_partial_failed_and_fresh_followup(transcript, chain_store, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_SESSIONS_DIR', str(chain_store))
    head = readme(chain_store, 'my-session', 'continuing_from: previous')
    readme(chain_store, 'previous', 'continuing_from: [\n')
    async def scenario(session):
        request = {'uri': 'claude://session/my-session/chain', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        assert json.loads(_text(partial))['meta']['chain_analysis']['parsed_readmes'] == 1
        head.write_text('---\ncontinuing_from: [\n---\n', encoding='utf-8')
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        head.write_text('---\nbadge: repaired\n---\n', encoding='utf-8')
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['chain_analysis']['failed_operations'] == 0
    _run(transcript.parent, scenario)
