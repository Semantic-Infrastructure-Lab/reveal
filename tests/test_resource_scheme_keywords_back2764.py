"""``diff://``, ``help://`` and ``reveal://`` refuse an unknown keyword, and their positional element is a noted legacy
spelling (BACK-2764 option B; help:// and reveal:// BACK-2767, diff:// BACK-2768).

The three schemes forwarded every query key and ``reveal.api.query`` keyword they did not read: ``api.query('reveal://config',
bogus=1)`` answered, ``reveal 'reveal://config?bogus=1'`` exited 0 with an "has no effect" note, ``help://quick?bogus=1``
exited 2 as "Element 'quick?bogus=1' not found" and ``diff://a:b?bogus=1`` as "File not found". COMMAND_MODEL "Applicability"
and the exit-code rules: an unknown control is an invalid request, exit 2, naming it, on the CLI, the API and MCP.

Their positional element (``reveal help:// quick``, ``reveal diff://a.py:b.py ok``, ``reveal reveal://FILE ELEMENT``) is a
supported spelling: it keeps answering until the cut, with one generated note naming what replaces it (D5, D18, D20): the
topic or the element in the URI (``help://quick``, ``diff://a.py:b.py/ok``), and for a reveal source file the path read of
that file (``reveal reveal://FILE`` names its path). The API's ``diff://a.py:b.py/ok`` answers the element, as the CLI does.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402

from reveal import api  # noqa: E402
from reveal.errors import RequestValidationError, UnsupportedOverrideError  # noqa: E402

pytestmark = [pytest.mark.component]

# help:// and reveal:// are declared nouns (BACK-2767). diff:// is held: its positional element is the only spelling
# for a URI side (diff://git://A/f.py:git://B/f.py NAME; the embedded /NAME splits plain file paths only), so a note
# naming diff://LEFT:RIGHT/ELEMENT would name a replacement that does not answer (BACK-2768).
DIFF_HELD = pytest.mark.xfail(strict=True, reason='BACK-2768 diff:// held: the element form has no replacement for a '
                                                  'URI side yet (pathread P5 section 4)')

ELEMENT_FORMS = {
    # key -> (CLI words, the answer's type, what the note names)
    'target:help.element': (('help://', 'quick'), 'help_quick', 'help://TOPIC'),
    'target:diff.element': (('diff://{a}:{b}', 'ok'), 'diff_element', 'diff://LEFT:RIGHT/ELEMENT'),
    'target:reveal.element': (('reveal://adapters/env.py', 'EnvAdapter'), 'code_element', 'reveal PATH ELEMENT'),
}


@pytest.fixture
def pair(tmp_path):
    a, b = tmp_path / 'ok.py', tmp_path / 'ok2.py'
    a.write_text('def ok():\n    return 1\n', encoding='utf-8')
    b.write_text('def ok():\n    return 2\n', encoding='utf-8')
    return {'a': a.as_posix(), 'b': b.as_posix()}


def _uris(pair):
    return {'help': 'help://quick', 'diff': f"diff://{pair['a']}:{pair['b']}", 'reveal': 'reveal://config'}


def _notes(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or []
            if isinstance(w, dict) and w.get('code') == 'retired_spelling']


# --- unknown keywords: exit 2 / UnsupportedOverrideError, naming the key -------------------------------------------

@pytest.mark.parametrize('scheme', ['help', pytest.param('diff', marks=DIFF_HELD), 'reveal'])
def test_api_refuses_an_unknown_keyword(pair, scheme):
    with pytest.raises(UnsupportedOverrideError, match='bogus_kw'):
        api.query(_uris(pair)[scheme], bogus_kw=1)


@pytest.mark.parametrize('scheme', ['help', pytest.param('diff', marks=DIFF_HELD), 'reveal'])
def test_cli_refuses_an_unknown_query_key(pair, scheme):
    run = _run_reveal_direct(f"{_uris(pair)[scheme]}?bogus=1", '--format', 'json')
    assert run.returncode == 2, (run.returncode, run.stderr)
    json.loads(run.stdout)  # the invalid-request JSON document, not empty stdout
    assert "unsupported control 'bogus'" in run.stdout + run.stderr, (run.stdout[:400], run.stderr[:400])


@DIFF_HELD
def test_api_refuses_an_unknown_keyword_beside_the_element_form(pair):
    with pytest.raises(UnsupportedOverrideError, match='bogus_kw'):
        api.query(f"diff://{pair['a']}:{pair['b']}", 'ok', bogus_kw=1)


@pytest.mark.parametrize('scheme', ['help', pytest.param('diff', marks=DIFF_HELD), 'reveal'])
def test_mcp_refuses_an_unknown_query_key(pair, scheme):
    from reveal.mcp_server import reveal_query, _ToolFailure
    answer = reveal_query(f'{_uris(pair)[scheme]}?bogus=1')
    assert isinstance(answer, _ToolFailure), (scheme, str(answer)[:300])
    assert "unsupported control 'bogus'" in str(answer), (scheme, str(answer)[:300])


# --- the element form: the same answer, plus one note naming the replacement ----------------------------------------

def _element_keys():
    return [pytest.param(key, marks=DIFF_HELD) if key.startswith('target:diff.') else key
            for key in sorted(ELEMENT_FORMS)]


@pytest.mark.parametrize('key', _element_keys())
def test_cli_element_form_answers_with_its_note(pair, key):
    words, answer_type, replacement = ELEMENT_FORMS[key]
    run = _run_reveal_direct(*(w.format(**pair) for w in words), '--format', 'json')
    assert run.returncode == 0, (run.returncode, run.stderr)
    doc = json.loads(run.stdout)
    assert doc['type'] == answer_type
    notes = _notes(doc)
    assert [n['field'] for n in notes] == [key], notes
    assert replacement in notes[0]['message'], notes[0]['message']


@pytest.mark.parametrize('key', _element_keys())
def test_api_element_form_answers_with_its_note(pair, key):
    words, answer_type, replacement = ELEMENT_FORMS[key]
    uri, element = (w.format(**pair) for w in words)
    doc = api.query(uri, element)
    assert doc['type'] == answer_type
    assert [n['field'] for n in _notes(doc)] == [key], _notes(doc)


def test_cli_element_form_text_prints_the_note_once(pair):
    run = _run_reveal_direct('help://', 'quick')
    assert run.returncode == 0
    assert run.stderr.count('help://TOPIC') == 1, run.stderr


def test_api_diff_embedded_element_answers_the_element(pair):
    """The replacement the diff note names answers on the API as on the CLI (it answered the whole comparison)."""
    doc = api.query(f"diff://{pair['a']}:{pair['b']}/ok")
    assert doc['type'] == 'diff_element', doc.get('type')
    cli = json.loads(_run_reveal_direct(f"diff://{pair['a']}:{pair['b']}/ok", '--format', 'json').stdout)
    assert cli['type'] == 'diff_element'


def test_api_diff_embedded_element_not_found_is_an_invalid_request(pair):
    with pytest.raises(RequestValidationError):
        api.query(f"diff://{pair['a']}:{pair['b']}/nosuch")


# --- controls: what already answered keeps answering, with no note -------------------------------------------------

def test_controls_answer_without_a_note(pair):
    for uri, answer_type in (('help://quick', 'help_quick'), ('reveal://config', 'reveal_structure'),
                             (f"diff://{pair['a']}:{pair['b']}", 'diff_comparison')):
        run = _run_reveal_direct(uri, '--format', 'json')
        assert run.returncode == 0, (uri, run.stderr)
        doc = json.loads(run.stdout)
        assert doc['type'] == answer_type and _notes(doc) == [], (uri, _notes(doc))
        assert api.query(uri)['type'] == answer_type


def test_help_search_binds_its_declared_keys(pair):
    run = _run_reveal_direct('help://search?search=navigation&top=2', '--format', 'json')
    assert run.returncode == 0, run.stderr
    doc = json.loads(run.stdout)
    assert doc['type'] == 'help_search' and doc['query'] == 'navigation'
    typed = api.query('help://search', search='navigation', top=2)
    assert typed['type'] == 'help_search' and typed['query'] == 'navigation', typed.get('error') or typed.get('message')
    assert typed.get('results') == doc.get('results')
