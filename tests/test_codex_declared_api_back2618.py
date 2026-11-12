"""Codex typed controls bind at the existing SQLite and JSONL reader boundary."""
import json

import pytest

from codex_session_fixture import DOC_SESSION_ID, build_codex_home
from reveal.api import query
from reveal.adapters.codex.adapter import CodexAdapter


@pytest.fixture
def codex(tmp_path, monkeypatch):
    home = build_codex_home(tmp_path)
    monkeypatch.setattr(CodexAdapter, 'CODEX_HOME', home)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', home / 'state_5.sqlite')
    return home


def add_messages(home, term, count=1):
    path = next((home / 'sessions').rglob('*.jsonl'))
    with path.open('a', encoding='utf-8') as handle:
        for _ in range(count):
            handle.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': term}}) + '\n')


def test_search_override_stays_literal(codex):
    needle = 'a&tokens=%26+雪'
    add_messages(codex, needle)
    result = query('codex://sessions?search=absent', search=needle)
    assert result['type'] == 'codex_content_search' and result['total'] == 1
    assert result['sessions'][0]['match_count'] == 1


def test_zero_matches_override_removes_only_the_snippet_cap(codex):
    add_messages(codex, 'needle', 6)
    result = query('codex://sessions?search=needle&matches=1', matches=0)
    assert result['sessions'][0]['match_count'] == 6
    assert len(result['sessions'][0]['matches']) == 6


@pytest.mark.parametrize('flag', ['last', 'tokens', 'goal'])
def test_false_presence_override_restores_session_overview(codex, flag):
    result = query(f'codex://{DOC_SESSION_ID}?{flag}', **{flag: False})
    assert result['type'] == 'codex_session_overview'


@pytest.mark.parametrize('value', [False, None])
def test_full_override_restores_bounded_text_default(codex, value):
    result = query(f'codex://{DOC_SESSION_ID}/exchanges?full', full=value)
    assert result['full'] is False and result['exchanges']


def test_none_search_restores_omitted_list_mode(codex):
    result = query('codex://sessions?search=absent', search=None)
    assert result['type'] == 'codex_session_list' and result['total'] == 1


def test_metadata_date_override_reaches_existing_index_owner(codex):
    result = query('codex://sessions?filter=auth-refactor&until=1900-01-01', until='2100-01-01')
    assert result['type'] == 'codex_session_list' and result['total'] == 1


def test_unknown_override_rejects(codex):
    with pytest.raises(TypeError, match='Unsupported declared'):
        query('codex://sessions', invented_control=True)


def test_original_bad_matches_cannot_be_hidden(codex):
    with pytest.raises(ValueError, match='matches'):
        query('codex://sessions?search=authentication&matches=-1', matches=0)
