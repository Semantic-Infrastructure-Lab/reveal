"""Decoded matches and snippets must survive JSON spelling and case expansion."""
import json
import builtins
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

import pytest

from reveal import api
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.adapters.claude.analysis.messages import _collect_block_matches, _find_excerpt
from reveal.adapters.claude.analysis.search import search_sessions_for_term


def session(root, text, escaped=True, block=None):
    project = root / 'synthetic-project'
    project.mkdir(parents=True, exist_ok=True)
    path = project / 'sample.jsonl'
    role = 'user' if block is None else 'assistant'
    record = {'type': role, 'timestamp': '2026-10-30T12:00:00Z',
              'message': {'role': role, 'content': text if block is None else [block]}}
    path.write_text(json.dumps(record, ensure_ascii=escaped) + '\n', encoding='utf-8')
    return path


@pytest.mark.parametrize('text,term,whole', [
    ('CAFÉ', 'café', False), ('café', 'café', False), ('a"b', 'a"b', False),
    ('C:\\work\\demo', 'C:\\work\\demo', False), ('🔧', '🔧', False),
    ('Istanbul', 'ıstanbul', True), ('ſearch', 'search', True),
    ('line\nbreak', 'line\nbreak', False),
    ('Straße', 'STRASSE', False), ('cafe\u0301', 'café', False),
])
@pytest.mark.parametrize('escaped', [False, True])
def test_cross_session_search_uses_decoded_owner(tmp_path, text, term, whole, escaped):
    session(tmp_path, text, escaped)
    with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
        result = api.query('claude://?search=' + quote(term, safe='') + ('&word' if whole else ''))
    expected = 0 if text in ('Straße', 'cafe\u0301') else 1
    assert result['match_count'] == expected
    if expected:
        assert result['matches'][0]['message_index'] == 0
        assert result['matches'][0]['excerpt']


@pytest.mark.parametrize('target', ['/workspace/café.py', r'C:\work\demo.py', '/workspace/🔧.py'])
def test_file_tracking_uses_decoded_exact_paths(tmp_path, target):
    block = {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': target}}
    session(tmp_path, '', block=block)
    with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
        result = api.query('claude://files/' + target)
        negative = api.query('claude://files/definitely-absent')
    assert result['match_count'] == 1
    assert result['sessions'][0]['total_ops'] == 1
    assert negative['match_count'] == 0


@pytest.mark.parametrize('kind', ['text', 'thinking', 'tool_result'])
def test_expanded_case_offsets_keep_matching_excerpt(kind):
    text = 'İ' * 80 + ' needle ' + 'z' * 200
    key = {'text': 'text', 'thinking': 'thinking', 'tool_result': 'content'}[kind]
    matches = _collect_block_matches([{'type': kind, key: text}], 'needle', 'needle',
                                     3, 'assistant', '', window_chars=60)
    assert len(matches) == 1
    assert 'needle' in matches[0]['excerpt']
    assert matches[0]['message_index'] == 3


def test_whole_word_excerpt_uses_original_regex_match_position():
    text = 'x ' * 100 + 'Istanbul ' + 'z' * 100
    matches = _collect_block_matches([{'type': 'text', 'text': text}], 'ıstanbul',
                                     'ıstanbul', 0, 'user', '', whole_word=True, window_chars=60)
    assert len(matches) == 1 and 'Istanbul' in matches[0]['excerpt']


def test_tool_name_match_uses_name_not_nonmatching_input_excerpt():
    block = {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': '/unrelated'}}
    result = _collect_block_matches([block], 'read', 'Read', 0, 'assistant', '')
    assert 'Read' in result[0]['excerpt']


def test_raw_schema_metadata_is_not_a_content_match(tmp_path):
    path = session(tmp_path, 'unrelated')
    result = search_sessions_for_term([{'path': str(path), 'session': 'sample', 'modified': ''}], 'timestamp')
    assert result == []


def test_nonmatching_foreign_metadata_does_not_break_decoded_search(tmp_path):
    path = session(tmp_path, 'needle')
    leading = {'type': 'user', 'timestamp': 42, 'message': {'content': 'unrelated'}}
    path.write_text(json.dumps(leading) + '\n' + path.read_text(encoding='utf-8'), encoding='utf-8')
    with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
        result = api.query('claude://?search=needle')
    assert result['match_count'] == 1
    assert result['matches'][0]['message_index'] == 1


@pytest.mark.parametrize('tracking', [False, True])
def test_decoded_read_failure_is_disclosed_and_repair_is_fresh(tmp_path, monkeypatch, tracking):
    block = {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': '/workspace/needle.py'}}
    good = session(tmp_path, 'needle', block=block if tracking else None)
    bad = good.with_name('denied.jsonl')
    bad.write_bytes(good.read_bytes())
    original = builtins.open

    def denied(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file) == bad:
            raise PermissionError(13, 'READ_DENIED', str(bad))
        return original(file, *args, **kwargs)

    request = 'claude://files/needle.py' if tracking else 'claude://?search=needle'
    with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
        with monkeypatch.context() as context:
            context.setattr(builtins, 'open', denied)
            result = api.query(request)
            assert result['match_count'] == 1
            warning, = [w for w in result['meta']['warnings'] if w['type'] == 'entries_skipped']
            assert warning['count'] == 1 and warning['files'] == ['denied.jsonl']
        assert api.query(request)['match_count'] == 2
