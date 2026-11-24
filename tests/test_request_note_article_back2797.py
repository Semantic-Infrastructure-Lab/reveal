"""A retiring URI request's note takes the article its scheme is spoken with (BACK-2797).

``reveal 'ast://proj?limit=1'`` noted ``a ast:// request is deprecated ...``: the one generated note text
(``request_note``) put ``a`` before every scheme. The note says ``an`` before a scheme spoken with a vowel sound
(``an ast://``, ``an imports://``, ``an overview://``) and ``a`` before the others (``a markdown://``), in the one wording
every transport shows: CLI stderr, the JSON warning (``message`` and ``old``), ``api.query`` and MCP.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api, mcp_server

pytestmark = pytest.mark.mcp

# (scheme, the note's opening words)
CASES = [('ast', 'an ast:// request'), ('imports', 'an imports:// request'),
         ('overview', 'an overview:// request'), ('markdown', 'a markdown:// request')]


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (root / 'guide.md').write_text('# Guide\n\nBody.\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return 'proj'


def _request_notes(warnings):
    return [w for w in warnings if w.get('type') == 'retired_spelling' and str(w.get('field', '')).startswith('request:')]


@pytest.mark.parametrize('scheme, opening', CASES)
def test_the_cli_note_takes_the_schemes_article(project, scheme, opening):
    run = _run_reveal_direct(f'{scheme}://{project}')
    assert run.returncode == 0, run.stderr
    notes = [line for line in run.stderr.splitlines() if ':// request is deprecated' in line]
    assert notes and all(line.startswith(f'note: {opening} is deprecated') for line in notes), notes


@pytest.mark.parametrize('scheme, opening', CASES)
def test_the_json_warning_takes_the_schemes_article(project, scheme, opening):
    run = _run_reveal_direct(f'{scheme}://{project}', '--format', 'json')
    [note] = _request_notes(json.loads(run.stdout)['meta']['warnings'])
    assert note['old'] == opening and note['message'].startswith(f'{opening} is deprecated')


@pytest.mark.parametrize('scheme, opening', CASES)
def test_the_api_and_mcp_notes_take_the_schemes_article(project, scheme, opening):
    [note] = _request_notes(api.query(f'{scheme}://{project}')['meta']['warnings'])
    assert note['message'].startswith(f'{opening} is deprecated')
    assert f'[note: {opening} is deprecated' in mcp_server.reveal_run([f'{scheme}://{project}'])


@pytest.mark.parametrize('scheme, article', [
    ('ast', 'an'), ('imports', 'an'), ('overview', 'an'), ('env', 'an'), ('architecture', 'an'),
    ('xlsx', 'an'),  # x before a consonant is said "ex"
    ('markdown', 'a'), ('json', 'a'), ('sqlite', 'a'), ('help', 'a'), ('metrics', 'a'),
])
def test_the_generated_note_text_takes_the_article(scheme, article):
    """The one generator, ``request_note``: its entry's ``old`` and its text open with the article."""
    from reveal.cli.invocation import request_note
    entry = request_note(scheme, lambda form: f'reveal {scheme} proj')
    assert entry.old == f'{article} {scheme}:// request'
    assert entry.text.startswith(f'{article} {scheme}:// request is deprecated')
