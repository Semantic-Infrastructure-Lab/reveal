"""api.query names a removed noun or scheme by its RETIREMENTS row, as the CLI does (BACK-2803, BACK-2771).

The noun form reads the CLI router's one predicate (``invocation.is_command_word``): a removed ``subcommand:`` row keeps
its word a noun, refused with the row's text instead of "neither a noun nor a URI". The URI form's unknown-scheme
branch reads the ``scheme:`` row before "Unsupported URI scheme". The API's exit raises ``RequestValidationError``
with the row's text, its cause the error stage's own ``RetiredSpellingError`` (never a ``ValueError`` subclass).
"""
from dataclasses import replace

import pytest

from reveal import api
from reveal.cli.invocation import COMMANDS, RETIREMENTS, RetiredSpellingError
from reveal.errors import RequestValidationError


@pytest.fixture
def proj(tmp_path):
    (tmp_path / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    return tmp_path


def _remove(monkeypatch, noun):
    key = f'subcommand:{noun}'
    monkeypatch.setitem(RETIREMENTS, key, replace(RETIREMENTS[key], stage='error', removed=True))
    monkeypatch.delitem(COMMANDS, noun)
    return RETIREMENTS[key]


@pytest.mark.parametrize('noun', ['hotspots', 'deps', 'trace', 'architecture', 'testability'])
def test_the_noun_form_names_a_removed_nouns_row(proj, monkeypatch, noun):
    row = _remove(monkeypatch, noun)
    with pytest.raises(RequestValidationError) as caught:
        api.query(noun, str(proj))
    assert str(caught.value) == row.text
    assert isinstance(caught.value.__cause__, RetiredSpellingError)


def test_an_unknown_noun_still_names_the_nouns(proj, monkeypatch):
    _remove(monkeypatch, 'hotspots')
    with pytest.raises(ValueError, match='neither a noun nor a URI'):
        api.query('nosuchnoun', str(proj))


def test_a_live_noun_still_answers_beside_a_removed_one(proj, monkeypatch):
    _remove(monkeypatch, 'hotspots')
    document = api.query('ast', str(proj))
    assert document['type'] == 'ast_query'


def test_a_removed_scheme_names_its_row():
    with pytest.raises(RequestValidationError) as caught:
        api.query('python://')
    assert str(caught.value) == RETIREMENTS['scheme:python'].text
    assert isinstance(caught.value.__cause__, RetiredSpellingError)


def test_an_unknown_scheme_is_still_unsupported():
    with pytest.raises(ValueError, match='Unsupported URI scheme: nosuch://'):
        api.query('nosuch://x')
