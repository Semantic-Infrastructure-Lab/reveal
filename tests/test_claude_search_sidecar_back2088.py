"""BACK-2088: cross-session search shows a snippet for sidecar-only hits and says when it caps."""
import json

from reveal.adapters.claude.analysis.search import _extract_first_snippet
from reveal.adapters.claude.render_sessions import _render_claude_cross_session_search


def _write(tmp_path, records):
    p = tmp_path / 's.jsonl'
    p.write_text('\n'.join(json.dumps(r) for r in records) + '\n', encoding='utf-8')
    return p


_SIDECAR_ONLY = {
    'type': 'user', 'timestamp': '2026-04-05T01:02:03Z',
    'message': {'role': 'user', 'content': [
        {'type': 'tool_result', 'content': 'Output too large, saved to a file'}]},
    'toolUseResult': 'listing: docs/NEEDLE_FILE.md was renamed',
}


def test_sidecar_only_hit_gets_a_snippet(tmp_path):
    p = _write(tmp_path, [{'type': 'summary'}, _SIDECAR_ONLY])
    r = _extract_first_snippet(p, 'needle_file.md')
    assert r['excerpt'].startswith('[toolUseResult] ')
    assert 'NEEDLE_FILE.md' in r['excerpt']
    assert r['role'] == 'user' and r['message_index'] == 1


def test_content_match_beats_sidecar_match(tmp_path):
    later = {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
        {'type': 'text', 'text': 'see NEEDLE_FILE.md here'}]}}
    r = _extract_first_snippet(_write(tmp_path, [_SIDECAR_ONLY, later]), 'needle_file.md')
    assert not r['excerpt'].startswith('[toolUseResult]')
    assert r['role'] == 'assistant'


def test_renderer_discloses_the_cap(capsys):
    matches = [{'session': f's{i}', 'modified': '2026-04-05T00:00:00'} for i in range(3)]
    _render_claude_cross_session_search(
        {'term': 't', 'sessions_scanned': 9, 'match_count': 122, 'matches': matches})
    out = capsys.readouterr().out
    assert 'Showing 3 of 122' in out and '--all' in out


def test_renderer_silent_when_nothing_capped(capsys):
    _render_claude_cross_session_search(
        {'term': 't', 'sessions_scanned': 9, 'match_count': 1,
         'matches': [{'session': 's', 'modified': '2026-04-05T00:00:00'}]})
    assert 'Showing' not in capsys.readouterr().out
