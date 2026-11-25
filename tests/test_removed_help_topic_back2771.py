"""``help://NOUN`` of a removed noun exits 2 with its RETIREMENTS row's text, on every transport (BACK-2771, ruling 3).

A noun the cut deletes keeps one trace, its ``scheme:`` or ``subcommand:`` row marked ``removed``. The command router
already answers ``reveal NOUN`` with the row's text (BACK-2771 R2); help said "Element 'python' not found" (or "No
adapter named 'python'", with a list of other schemes) and never read the row. Now ``help://NOUN``,
``help://NOUN/SECTION`` and ``help://schemas/NOUN`` of a noun whose row is removed are the same refusal as the noun
itself: exit 2 with the row's text, the invalid-request document under ``--format json`` (BACK-2627 item 3),
``RequestValidationError`` from ``api.query`` and a public tool error on MCP. ``help://python`` is the shipped case;
``review`` (a subcommand row) and ``stats`` (a scheme row) are removed here the way the cut will remove them.

Controls: a live topic answers, a topic that names nothing keeps its own miss, and a retired noun that is not removed
(``stats`` at the note stage) still answers its guide.
"""
import json
from dataclasses import replace

import pytest

from conftest import _run_reveal_direct, invalid_request_document
from reveal.cli.invocation import COMMANDS, RETIREMENTS

# Each removed noun, and the row its help topic answers with (a scheme row first: it is what help:// names).
NOUNS = ['python', 'review', 'stats']


def _remove(monkeypatch, noun):
    """*noun* removed as the cut removes it, returning its row: python already is; review loses its CommandSpec,
    stats its adapter, each row at error and removed."""
    if noun == 'python':
        return RETIREMENTS['scheme:python']
    if noun == 'review':
        key = 'subcommand:review'
        monkeypatch.delitem(COMMANDS, 'review')
    else:
        from reveal.adapters.registry import _ADAPTER_REGISTRY
        key = f'scheme:{noun}'
        _ADAPTER_REGISTRY.load_all()  # loaded first, so the deleted entry is not imported again on lookup
        monkeypatch.delitem(_ADAPTER_REGISTRY, noun)
    monkeypatch.setitem(RETIREMENTS, key, replace(RETIREMENTS[key], stage='error', removed=True))
    return RETIREMENTS[key]


def _topics(noun):
    return [f'help://{noun}', f'help://schemas/{noun}', f'help://{noun}/examples']


def _error_lines(stderr):
    return [line for line in stderr.splitlines() if line.strip()]


# --- CLI -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('noun', NOUNS)
def test_a_removed_nouns_help_topic_exits_2_with_its_rows_text(monkeypatch, noun):
    row = _remove(monkeypatch, noun)
    for uri in _topics(noun):
        result = _run_reveal_direct(uri)
        assert result.returncode == 2, (uri, result.stdout[:300])
        assert result.stdout == ''
        assert _error_lines(result.stderr) == [f'error: {row.text}'], (uri, result.stderr)


@pytest.mark.parametrize('noun', NOUNS)
def test_the_help_subcommand_says_the_same(monkeypatch, noun):
    row = _remove(monkeypatch, noun)
    result = _run_reveal_direct('help', noun)
    assert result.returncode == 2
    assert _error_lines(result.stderr) == [f'error: {row.text}'], result.stderr


@pytest.mark.parametrize('noun', NOUNS)
def test_json_mode_answers_the_invalid_request_document(monkeypatch, noun):
    row = _remove(monkeypatch, noun)
    for uri in (f'help://{noun}', f'help://schemas/{noun}'):
        result = _run_reveal_direct(uri, '--format', 'json')
        document = invalid_request_document(result)
        assert document is not None, (uri, result.returncode, result.stdout[:300])
        assert document['error'] == row.text == document['meta']['errors'][0]['message']
        assert _error_lines(result.stderr) == [f'error: {row.text}'], result.stderr


# --- Python API and MCP ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize('noun', NOUNS)
def test_api_query_raises_request_validation_error_with_the_rows_text(monkeypatch, noun):
    from reveal import api
    from reveal.cli.invocation import RetiredSpellingError
    from reveal.errors import RequestValidationError
    row = _remove(monkeypatch, noun)
    for call in (lambda: api.query(f'help://{noun}'), lambda: api.query(f'help://schemas/{noun}'),
                 lambda: api.query('help', noun)):
        with pytest.raises(RequestValidationError) as raised:
            call()
        assert str(raised.value) == row.text
        assert isinstance(raised.value.__cause__, RetiredSpellingError)


def _mcp(call):
    try:
        return call()
    except Exception as exc:  # a raised tool error is the refusal on MCP; its text is the measured outcome
        return f'[reveal error: {exc}]'


@pytest.mark.parametrize('noun', NOUNS)
def test_mcp_refuses_with_the_rows_text_as_a_public_error(monkeypatch, noun):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query, reveal_run
    row = _remove(monkeypatch, noun)
    for shown in (_mcp(lambda: reveal_run([f'help://{noun}'])), _mcp(lambda: reveal_run(['help', noun])),
                  _mcp(lambda: reveal_query(f'help://schemas/{noun}'))):
        assert shown == f'[reveal error: {row.text}]', shown[:300]
    shown = _mcp(lambda: reveal_run([f'help://{noun}', '--format', 'json']))
    document = json.loads(shown.removeprefix('[reveal error: ').removesuffix(']'))
    assert document['error'] == row.text


# --- controls --------------------------------------------------------------------------------------------------------

def test_a_live_topic_beside_a_removed_noun_still_answers(monkeypatch):
    _remove(monkeypatch, 'review')
    for uri in ('help://ast', 'help://schemas/ast', 'help://quick'):
        result = _run_reveal_direct(uri)
        assert result.returncode == 0, (uri, result.stderr)
        assert result.stdout


def test_a_topic_that_names_nothing_keeps_its_own_miss(monkeypatch):
    _remove(monkeypatch, 'review')
    result = _run_reveal_direct('help://nosuchtopic')
    assert result.returncode == 2
    assert "Element 'nosuchtopic' not found" in result.stderr and 'was removed' not in result.stderr
    result = _run_reveal_direct('help://schemas/nosuchtopic')
    assert result.returncode == 2
    assert "No adapter named 'nosuchtopic'" in result.stderr and 'was removed' not in result.stderr


def test_a_retired_noun_that_is_not_removed_still_answers_its_guide():
    """The note stage: ``help://stats`` and ``help://schemas/stats`` answer as before, with no retirement note (help
    names the topic, it does not spell the scheme)."""
    for uri in ('help://stats', 'help://schemas/stats', 'help://review'):
        result = _run_reveal_direct(uri)
        assert result.returncode == 0, (uri, result.stderr)
        assert result.stdout and 'deprecated' not in result.stderr
