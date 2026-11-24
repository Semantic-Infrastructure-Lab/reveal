"""``api.element(PATH, NAME, element_type=KIND)`` is a supported legacy spelling until 1.0 (D5; ruling S2 of BACK-2325).

No element spelling of the CLI names a kind and a name together (``function:foo`` is a miss; ``TYPE:N`` takes a number),
so the keyword keeps its earlier lookup unchanged until the cut and says its replacement through its RETIREMENTS row
``python:element.element_type``: in the returned document's ``meta.warnings``, and for a None in the invocation log a
host keeps. Nothing is printed on stderr. At the cut the row raises.
"""
import pytest

from reveal import api
from reveal.cli import invocation
from reveal.cli.invocation import RETIREMENTS, RetiredSpellingError, Retirement
from reveal.utils.invocation_log import log_scope

KEY = 'python:element.element_type'
OK_PY = 'def foo():\n    return 1\n\n\nclass K:\n    def m(self):\n        return 2\n'


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text(OK_PY, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _notes(document):
    return [w for w in document['meta']['warnings'] if w.get('code') == 'retired_spelling']


def test_the_typed_lookup_answers_as_before_and_notes_its_replacement(fx, capsys):
    document = api.element('ok.py', 'foo', element_type='function')
    assert document['name'] == 'foo' and document['content'] == 'def foo():\n    return 1'
    assert [(w['field'], w['message']) for w in _notes(document)] == [(KEY, RETIREMENTS[KEY].text)]
    assert RETIREMENTS[KEY].text == (
        'api.element(PATH, NAME, element_type=KIND) is deprecated and works until 1.0; use api.element(PATH, NAME), '
        'which names the element as reveal PATH NAME does (Class.method for a method).')
    assert capsys.readouterr().err == ''


def test_a_miss_of_that_kind_is_still_none_and_the_hosts_log_keeps_the_note(fx, capsys):
    with log_scope(to_stderr=False) as log:
        assert api.element('ok.py', 'foo', element_type='class') is None
    assert list(log.noted) == [KEY]
    assert capsys.readouterr().err == ''


def test_at_the_cut_the_row_raises(fx, monkeypatch):
    monkeypatch.setitem(invocation.RETIREMENTS, KEY, Retirement(RETIREMENTS[KEY].old, RETIREMENTS[KEY].replacement,
                                                                stage='error'))
    with pytest.raises(RetiredSpellingError):
        api.element('ok.py', 'foo', element_type='function')


def test_control_the_element_read_carries_no_note(fx):
    assert _notes(api.element('ok.py', 'foo')) == []
