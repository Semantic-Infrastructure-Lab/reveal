"""Result outcomes (BACK-1059): one definition of a failed result, one place it sets the exit.

``reveal.utils.results.outcome_of`` says what a result reports: ``failed`` (a top-level
``error``), ``not_applicable`` (BACK-1210) or ``ok``. ``cli/routing/uri._emit_result``
exits 1 after rendering a failed result, for every URI adapter, in text and JSON alike.

Before it, each adapter or renderer decided its own exit code, and an error result from
calls://, codex://, claude:// or json:// rendered and exited 0 (BACK-1520, BACK-1525,
BACK-1526). help:// had the opposite patch: a renderer-side exemption so that its bare
``help://schemas`` listing, built as an error dict, would not exit 1. The listing is now its
own success type, and the exemption is gone.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.adapters.codex.adapter import CodexAdapter
from reveal.utils.results import outcome_of

FORMATS = ['text', 'json']


# -- the definition --------------------------------------------------------------------

@pytest.mark.parametrize('result, expected', [
    ({'type': 't', 'error': 'boom'}, 'failed'),
    ({'type': 't', 'applicable': False, 'reason': 'no tests'}, 'not_applicable'),
    ({'type': 't', 'items': []}, 'ok'),
    # An empty or falsy error is not a failure.
    ({'type': 't', 'error': ''}, 'ok'),
    ({'type': 't', 'error': None}, 'ok'),
    # Per-file problems inside an answer that was still produced.
    ({'type': 't', 'meta': {'errors': [{'code': 'parse_failed'}]}}, 'ok'),
    # An error on one item of a list belongs to that item, not to the result.
    ({'type': 't', 'checks': [{'name': 'dns', 'error': 'timeout'}]}, 'ok'),
    # Failure wins over applicability.
    ({'type': 't', 'error': 'boom', 'applicable': False}, 'failed'),
    (['not', 'a', 'dict'], 'ok'),
    (None, 'ok'),
])
def test_outcome_of(result, expected):
    assert outcome_of(result) == expected


# -- the seam, end to end --------------------------------------------------------------

@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'data.json').write_text('{"a": 1}', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json(result):
    return json.loads(result.stdout)


@pytest.mark.parametrize('fmt', FORMATS)
def test_calls_without_a_query_exits_nonzero(proj, fmt):
    """BACK-1526: calls://DIR with no target/callees/root/rank is a usage error."""
    r = _run_reveal_direct('calls://.', '--format', fmt)
    assert r.returncode == 1
    assert 'Missing required parameter' in r.stdout + r.stderr


@pytest.mark.parametrize('fmt', FORMATS)
def test_json_missing_key_exits_nonzero(proj, fmt):
    r = _run_reveal_direct('json://data.json/nokey', '--format', fmt)
    assert r.returncode == 1
    assert 'Key not found' in r.stdout + r.stderr


@pytest.mark.parametrize('fmt', FORMATS)
def test_codex_unknown_resource_exits_nonzero(proj, fmt):
    """BACK-1520."""
    r = _run_reveal_direct('codex://nonexistent_zz_1059', '--format', fmt)
    assert r.returncode == 1
    assert 'Unknown codex:// resource' in r.stdout + r.stderr


@pytest.mark.parametrize('fmt', FORMATS)
def test_claude_without_a_projects_dir_exits_nonzero(proj, fmt, monkeypatch):
    """BACK-1525: on a machine with no Claude install the listing is an error, not an
    empty success."""
    monkeypatch.setattr(ClaudeAdapter, 'CONVERSATION_BASE', proj / 'no-claude' / 'projects')
    r = _run_reveal_direct('claude://sessions', '--format', fmt)
    assert r.returncode == 1


@pytest.mark.parametrize('fmt', FORMATS)
def test_codex_without_a_db_exits_nonzero(proj, fmt, monkeypatch):
    """BACK-1525: the same for codex:// with no state DB."""
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', proj / 'no-codex' / 'state_5.sqlite')
    r = _run_reveal_direct('codex://', '--format', fmt)
    assert r.returncode == 1
    assert 'Codex DB not found' in r.stdout + r.stderr


@pytest.mark.parametrize('fmt', FORMATS)
def test_help_unknown_schema_exits_nonzero(proj, fmt):
    r = _run_reveal_direct('help://schemas/nonexistent_zz_1059', '--format', fmt)
    assert r.returncode == 1


@pytest.mark.parametrize('fmt', FORMATS)
def test_bare_help_schemas_is_an_index_not_an_error(proj, fmt):
    r = _run_reveal_direct('help://schemas', '--format', fmt)
    assert r.returncode == 0
    if fmt == 'json':
        payload = _json(r)
        assert payload['type'] == 'adapter_schema_index'
        assert 'error' not in payload
        assert 'ast' in payload['available_adapters']
    else:
        assert 'Available Adapters' in r.stdout


@pytest.mark.parametrize('uri, scheme', [
    ('calls://.', 'calls'),
    ('json://data.json/nokey', 'json'),
    ('codex://nonexistent_zz_1059', 'codex'),
    ('help://schemas/nonexistent_zz_1059', 'help'),
    ('help://ast/nonexistent_section_1059', 'help'),
])
def test_the_error_is_reported_once_and_first(proj, uri, scheme):
    """The router prints the error line before rendering; renderers add only detail.
    Before, claude/codex/help/calls renderers each printed their own 'Error:' line."""
    r = _run_reveal_direct(uri)
    assert r.returncode == 1
    assert r.stderr.startswith(f'Error ({scheme}://): '), r.stderr
    assert (r.stdout + r.stderr).count('Error') == 1, r.stdout + r.stderr


@pytest.mark.parametrize('uri', ['calls://.?target=main', 'json://data.json/a', 'ast://.'])
@pytest.mark.parametrize('fmt', FORMATS)
def test_a_real_answer_still_exits_zero(proj, fmt, uri):
    """Positive control: the seam only fires on a failed outcome."""
    r = _run_reveal_direct(uri, '--format', fmt)
    assert r.returncode == 0, r.stderr
