"""BACK-1614: claude:// reads malformed session files by skipping the bad parts,
with each catch narrowed to the shape errors a foreign JSONL file can have, so a
bug in reveal is no longer swallowed with them."""

import json

from reveal.adapters.claude.analysis.messages import _extract_text, _iter_thinking_blocks
from reveal.adapters.claude.analysis.search import _extract_first_snippet
from reveal.adapters.claude.handlers.sessions import (
    _parse_readme_frontmatter, _read_session_stats, _scan_jsonl_for_title)

_ODD_LINES = [
    '["a", "list", "not", "an", "object"]',
    '{"type": "user", "message": "a string, not an object"}',
    '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": 7}}]}}',
    '{"type": "user", "message": {"content": "deploy the widget service"}, "timestamp": "2026-10-02T10:00:00Z"}',
    '{"truncated mid-wri',
]


def _write(tmp_path, lines):
    path = tmp_path / 's.jsonl'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def test_title_scan_skips_odd_lines(tmp_path):
    assert _scan_jsonl_for_title(_write(tmp_path, _ODD_LINES)) == 'deploy the widget service'


def test_title_scan_of_missing_file_is_none(tmp_path):
    assert _scan_jsonl_for_title(tmp_path / 'gone.jsonl') is None


def test_stats_tolerate_a_non_string_timestamp(tmp_path):
    lines = ['{"timestamp": 12345}', '{"timestamp": "2026-10-02T10:05:00Z"}']
    assert _read_session_stats(_write(tmp_path, lines)) == {'message_count': 2}


def test_snippet_search_skips_odd_lines(tmp_path):
    snippet = _extract_first_snippet(_write(tmp_path, _ODD_LINES), 'widget')
    assert snippet['excerpt'] and snippet['role'] == 'user'


def test_text_and_thinking_skip_non_string_fields():
    assert _extract_text([{'type': 'text', 'text': None}, {'type': 'text', 'text': 'ok'}]) == 'ok'
    blocks = list(_iter_thinking_blocks([{'type': 'thinking', 'thinking': None},
                                          {'type': 'thinking', 'thinking': 'hmm'}], 0, None))
    assert [b['content'] for b in blocks] == ['hmm']


def test_frontmatter_that_is_not_a_mapping_is_empty(tmp_path):
    readme = tmp_path / 'README.md'
    readme.write_text('---\n- a\n- list\n---\nbody\n', encoding='utf-8')
    assert _parse_readme_frontmatter(readme) == {}
    readme.write_text('---\nproject: reveal\n---\n', encoding='utf-8')
    assert _parse_readme_frontmatter(readme) == {'project': 'reveal'}
    assert json.dumps(_parse_readme_frontmatter(tmp_path / 'missing.md')) == '{}'
