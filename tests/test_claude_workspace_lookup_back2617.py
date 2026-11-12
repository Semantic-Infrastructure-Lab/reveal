"""Single Markdown lookups preserve resolution choices and disclose source loss."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.api import query
from test_claude_source_evidence_back2617 import transcript
from test_claude_workspace_lists_back2617 import workspace_home


@pytest.mark.parametrize('noun', ['plans', 'agents'])
def test_missing_lookup_is_request_error(transcript, workspace_home, noun):
    result = _run_reveal_in(transcript.parent, f'claude://{noun}/absent', '--format', 'json')
    assert result.returncode == 2
    assert query(f'claude://{noun}/absent')['error']


@pytest.mark.parametrize('noun', ['plans', 'agents'])
def test_ambiguity_keeps_plural_type_and_known_candidates(transcript, workspace_home, noun):
    for name in ('choice-one', 'choice-two'):
        (workspace_home / noun / (name + '.md')).write_text('# Body\n', encoding='utf-8')
    result = _run_reveal_in(transcript.parent, f'claude://{noun}/choice', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['type'] == f'claude_{noun}' and answer['ambiguous'] is True
    assert answer['matches'] == ['choice-one', 'choice-two']
    assert answer['meta']['workspace_analysis']['lookup']['resolution'] == 'ambiguous'


@pytest.mark.parametrize('noun', ['plans', 'agents'])
@pytest.mark.parametrize('loss', ['select', 'read', 'metadata', 'decode'])
def test_lookup_source_loss_is_measured(transcript, workspace_home, monkeypatch, noun, loss):
    path = workspace_home / noun / 'selected.md'
    path.write_bytes(b'# Known body\n' if loss != 'decode' else b'# Known body \xff\n')
    original_stat, original_read = Path.stat, Path.read_text
    calls = 0
    def stat(selected, *args, **kwargs):
        nonlocal calls
        if selected == path:
            calls += 1
            if loss == 'select' or (loss == 'metadata' and calls > 1):
                raise PermissionError('injected lookup metadata denial')
        return original_stat(selected, *args, **kwargs)
    def read(selected, *args, **kwargs):
        if selected == path and loss == 'read':
            raise FileNotFoundError('injected disappearance after selection')
        return original_read(selected, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    monkeypatch.setattr(Path, 'read_text', read)
    result = _run_reveal_in(transcript.parent, f'claude://{noun}/selected', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    proof = answer['meta']['workspace_analysis']
    assert proof['request_rejected'] is False
    if loss in ('metadata', 'decode'):
        assert 'Known body' in answer['content']
        assert answer['source_type'] == 'file'


@pytest.mark.parametrize('noun', ['plans', 'agents'])
def test_partial_prefix_discovery_is_not_missing_or_complete(transcript, workspace_home, monkeypatch, noun):
    root = workspace_home / noun
    path = root / 'choice-one.md'
    path.write_text('# Body\n', encoding='utf-8')
    original = Path.iterdir
    def entries(selected):
        if selected == root:
            yield path
            raise PermissionError('injected incomplete prefix discovery')
        yield from original(selected)
    monkeypatch.setattr(Path, 'iterdir', entries)
    result = _run_reveal_in(transcript.parent, f'claude://{noun}/choice', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert 'Body' in answer['content']
    assert answer['meta']['workspace_analysis']['discovery_failures'] == 1


@pytest.mark.parametrize('erase', ['proof', 'content', 'type'])
def test_lookup_presentation_cannot_erase_or_change_response_variant(transcript, workspace_home, monkeypatch, erase):
    (workspace_home / 'plans' / 'selected.md').write_text('# Body\n', encoding='utf-8')
    def post_process(self, result, args):
        if erase == 'proof':
            result['meta'].pop('workspace_analysis')
        elif erase == 'type':
            result.update(type='claude_plans', ambiguous=True, matches=['invented'], query='selected')
        else:
            result['content'] = ''
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://plans/selected', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.parametrize('name', ['nested/item', 'nested/pre', 'nested/p[rt]e', '**/pre'])
def test_lookup_preserves_nested_and_glob_prefix_resolution(transcript, workspace_home, name):
    nested = workspace_home / 'plans' / 'nested'
    nested.mkdir()
    (nested / 'item.md').write_text('Exact body', encoding='utf-8')
    (nested / 'prefix.md').write_text('Prefix body', encoding='utf-8')
    result = _run_reveal_in(transcript.parent, 'claude://plans/' + name, '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['content'] == ('Exact body' if name.endswith('item') else 'Prefix body')


@pytest.mark.parametrize('noun', ['plans', 'agents'])
def test_empty_exact_body_precedes_prefix_ambiguity(transcript, workspace_home, noun):
    for name in ('choice', 'choice-one', 'choice-two'):
        (workspace_home / noun / (name + '.md')).write_text('', encoding='utf-8')
    result = _run_reveal_in(transcript.parent, f'claude://{noun}/choice', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['type'] == 'claude_' + noun[:-1] and answer['content'] == ''
    assert answer['meta']['workspace_analysis']['lookup']['resolution'] == 'exact'


@pytest.mark.mcp
@pytest.mark.component
@pytest.mark.parametrize('noun', ['plans', 'agents'])
def test_sdk_lookup_ambiguity_failed_partial_and_fresh(transcript, workspace_home, monkeypatch, noun):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(workspace_home))
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(workspace_home / 'projects'))
    one, two = (workspace_home / noun / (name + '.md') for name in ('choice-one', 'choice-two'))
    one.write_text('One', encoding='utf-8')
    two.write_text('Two', encoding='utf-8')
    async def scenario(session):
        request = {'uri': f'claude://{noun}/choice', 'provenance': True}
        ambiguous = await session.call_tool('reveal_query', request)
        assert not ambiguous.is_error, _text(ambiguous)
        assert json.loads(_text(ambiguous))['matches'] == ['choice-one', 'choice-two']
        two.unlink()
        one.write_bytes(b'One \xff')
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        assert json.loads(_text(partial))['meta']['workspace_analysis']['recovered_entries'] == 1
        one.unlink()
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        one.write_text('Fresh body', encoding='utf-8')
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['content'] == 'Fresh body'
    _run(transcript.parent, scenario)
