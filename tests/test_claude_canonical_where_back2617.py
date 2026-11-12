"""Name predicates retain the listing's case-insensitive literal substring identity."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.api import query
from reveal.errors import RequestValidationError
from test_claude_source_evidence_back2617 import transcript


def test_session_predicate_retains_legacy_name_filter_population(transcript):
    canonical = query('claude://sessions', where='session~=HOME-USER-PROJ')
    original = query('claude://sessions', filter='HOME-USER-PROJ')
    assert canonical['recent_sessions'] == original['recent_sessions']
    assert canonical['session_count'] == original['session_count'] == 2
    assert canonical['scope']['where'] == ['session~=HOME-USER-PROJ']
    assert query('claude://sessions', where='session~=my-session')['session_count'] == 0


def test_repeated_predicates_and_legacy_filter_intersect(transcript):
    answer = query('claude://sessions', where=['session~=home', 'session~=proj'], filter='HOME-')
    assert answer['session_count'] == 2
    result = _run_reveal_in(transcript.parent,
                            'claude://sessions?where=session~=home&where=session~=proj', '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['session_count'] == 2


@pytest.mark.parametrize('resource,where', [('settings', 'session~=my'), ('search/auth', 'session~=my'),
                                         ('sessions?match=auth', 'session~=my'),
                                         ('sessions', 'title~=auth'), ('sessions', 'session>my')])
def test_where_rejects_unsupported_scope_or_predicate(transcript, resource, where):
    with pytest.raises(RequestValidationError):
        query('claude://' + resource, where=where)


def test_empty_predicates_and_none_override_are_distinct_from_invalid_original(transcript):
    assert query('claude://sessions', where=[])['session_count'] == 3
    assert query('claude://sessions?where=session~=absent', where=None)['session_count'] == 3
    with pytest.raises(RequestValidationError):
        query('claude://sessions?where=title~=auth', where='session~=my')


@pytest.mark.parametrize('field', ['where', 'where_rule'])
def test_presentation_cannot_erase_requested_predicate_scope(transcript, monkeypatch, field):
    def post_process(self, result, args):
        result['scope'].pop(field)
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://sessions?where=session~=my', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_where_values_remain_literal_across_api_and_uri(transcript):
    from urllib.parse import quote
    name = 'a&errors=%26+雪'
    directory = transcript.parent.parent / ('project-sessions-' + name)
    directory.mkdir()
    (directory / 'record.jsonl').write_bytes(transcript.read_bytes())
    expression = 'session~=' + name
    api = query('claude://sessions', where=expression)
    assert api['session_count'] == 1
    result = _run_reveal_in(transcript.parent, 'claude://sessions?where=' + quote(expression, safe=''), '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['session_count'] == 1 and answer['scope']['where'] == [expression]


def test_where_cannot_hide_catalog_acquisition_loss(transcript, monkeypatch):
    from pathlib import Path
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path == transcript:
            raise PermissionError('injected catalog entry denial')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    result = _run_reveal_in(transcript.parent, 'claude://sessions?where=session~=totally-absent', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['session_count'] == 0 and answer['meta']['session_catalog']['failed_entries'] == 1


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_where_keeps_scope_and_source_outcomes(transcript, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    originals = {path: path.read_bytes() for path in transcript.parent.glob('*.jsonl')}
    broken = transcript.parent / 'damaged.jsonl'
    broken.mkdir()
    async def scenario(session):
        request = {'uri': 'claude://sessions?where=session~=home-user-proj', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert answer['session_count'] == 2 and answer['meta']['session_catalog']['failed_entries'] == 1
        assert answer['scope']['where'] == ['session~=home-user-proj']
        for path in originals:
            path.unlink()
        assert (await session.call_tool('reveal_query', request)).is_error
        broken.rmdir()
        for path, data in originals.items():
            path.write_bytes(data)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['session_catalog']['failed_entries'] == 0
    _run(transcript.parent, scenario)
