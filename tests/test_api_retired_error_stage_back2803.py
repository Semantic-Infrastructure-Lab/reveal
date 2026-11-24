"""An error-stage retirement raises ``RequestValidationError`` from the Python API, as every other request the CLI exits 2
on does (BACK-2803, D21).

``retirement_note`` raises ``RetiredSpellingError`` at the error stage (the CLI prints its row's text and exits 2). The
API's docstrings promise ``RequestValidationError`` for every exit 2, so the API maps the error at its exit, keeping the
row's text and chaining the retirement as the cause. ``RetiredSpellingError`` itself is never a ``ValueError``: the
``except ValueError`` around ``request_note`` would swallow the cut (retire R1 report, section 3). Each case runs at the
note stage too, where it answers with its note (the negative control).
"""
from dataclasses import replace

import pytest

from reveal import api
from reveal.cli import invocation
from reveal.cli.invocation import RETIREMENTS, RetiredSpellingError
from reveal.errors import RequestValidationError

REQUEST = 'request:ast'
# (row key, the API call that spells it): every API entry, and both forms of query.
CASES = {
    'subcommand:hotspots': lambda: api.query('hotspots', 'proj'),
    'scheme:hotspots': lambda: api.query('hotspots://proj'),
    REQUEST: lambda: api.query('ast://proj'),
    'param:calls.top': lambda: api.query('calls', 'proj', top=3, sort='-callers'),
    'flag:--search': lambda: api.analyze('proj/app.py', search='main'),
    'python:element.element_type': lambda: api.element('proj/app.py', 'main', element_type='function'),
}


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'proj').mkdir()
    (tmp_path / 'proj' / 'app.py').write_text('def main():\n    return helper()\n\n\ndef helper():\n    return 1\n',
                                              encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _at_error_stage(monkeypatch, key):
    if key == REQUEST:
        monkeypatch.setattr(invocation, 'REQUEST_STAGE', 'error')
    else:
        monkeypatch.setitem(RETIREMENTS, key, replace(RETIREMENTS[key], stage='error'))


def _noted_fields(document):
    return [w.get('field') for w in (document.get('meta') or {}).get('warnings') or []
            if w.get('code') == 'retired_spelling']


@pytest.mark.parametrize('key', sorted(CASES))
def test_an_error_stage_row_raises_request_validation_error_with_its_text(proj, monkeypatch, key):
    _at_error_stage(monkeypatch, key)
    with pytest.raises(RequestValidationError) as caught:
        CASES[key]()
    cause = caught.value.__cause__
    assert isinstance(cause, RetiredSpellingError), repr(cause)
    assert cause.key == key
    assert str(caught.value) == cause.entry.text
    if key != REQUEST:  # the request note's text is generated per request; a row's is the table's
        assert str(caught.value) == RETIREMENTS[key].text


@pytest.mark.parametrize('key', sorted(CASES))
def test_at_the_note_stage_the_same_call_answers_with_its_note(proj, key):
    assert key in _noted_fields(CASES[key]())


def test_the_request_note_at_the_cut_is_refused_not_swallowed(proj, monkeypatch):
    """The trap the mapping avoids: a refusal raised as a ValueError inside the request is taken by the ``except
    ValueError`` around ``request_note`` and the request answers with no note. Mapped at the exit, it is refused."""
    _at_error_stage(monkeypatch, REQUEST)
    with pytest.raises(RequestValidationError, match=r'^an ast:// request is deprecated; use api\.query\("ast"'):
        api.query('ast://proj', kind='function')
