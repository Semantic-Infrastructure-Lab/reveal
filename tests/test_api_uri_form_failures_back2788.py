"""``api.query(URI)`` raises a declared noun's failed answer as the noun form does (D21, BACK-2788).

The CLI answers a declared noun's URI through its declared route, which exits on the answer's execution facts: 2 for
an invalid request, 3 for a failed analysis. The noun form of ``api.query`` maps those facts to exceptions
(``typed._failure``: ``RequestValidationError`` with the CLI's message; the cause, or ``AnalysisFailedError`` carrying
the document). The URI form returned the failed document instead: ``json://F?view=value&where=a~~~`` returned
``error: Unknown query: a~~~`` where ``reveal`` exits 2, and ``ast://bad.xml`` returned an ``analysis_failed`` answer
where it exits 3. The URI form now maps the same facts through the same mapping.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import AnalysisFailedError, RequestValidationError

INVALID = [
    ('json://d.json?view=value&where=a~~~', {}, 'Unknown query: a~~~'),
    ('json://d.json', {'view': 'value', 'where': 'a~~~'}, 'Unknown query: a~~~'),
    ('json://obj.json/absent', {}, None),
]


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'ok.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'd.json').write_text('{"a": 1}\n', encoding='utf-8')
    (tmp_path / 'obj.json').write_text('{"present": 1}\n', encoding='utf-8')
    (tmp_path / 'bad.json').write_text('{"a": ', encoding='utf-8')
    (tmp_path / 'bad.xml').write_text('<a><b>', encoding='utf-8')
    (tmp_path / 'mixed').mkdir()
    (tmp_path / 'mixed' / 'ok.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'mixed' / 'bad.xml').write_text('<a><b>', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cli(uri):
    run = _run_reveal_direct(uri, '--format', 'json')
    return run.returncode, json.loads(run.stdout)


@pytest.mark.parametrize('uri, controls, message', INVALID)
def test_an_invalid_request_raises_the_clis_message(fx, uri, controls, message):
    _code, document = _cli(uri if not controls else f'{uri}?view=value&where=a~~~')
    with pytest.raises(RequestValidationError) as raised:
        api.query(uri, **controls)
    assert str(raised.value) == (message or document['error'])


@pytest.mark.parametrize('uri', ['json://d.json?view=value&where=a~~~', 'json://obj.json/absent'])
def test_sibling_the_cli_exits_2(fx, uri):
    assert _cli(uri)[0] == 2


def test_sibling_the_noun_form_raises_it(fx):
    with pytest.raises(RequestValidationError, match='^Unknown query: a~~~$'):
        api.query('json', 'd.json', view='value', where='a~~~')


def test_a_failed_analysis_raises_with_the_document(fx):
    code, document = _cli('ast://bad.xml')
    assert code == 3
    with pytest.raises(AnalysisFailedError) as raised:
        api.query('ast://bad.xml')
    failed = raised.value.result
    assert failed is not None and failed['type'] == document['type'] == 'ast_query'
    assert failed['source'] == document['source'] == 'bad.xml'
    assert 'analysis_failed' in [w['type'] for w in failed['meta']['warnings']]
    assert 'XML parse error' in str(raised.value)


def test_sibling_the_noun_form_raises_the_failed_analysis(fx):
    with pytest.raises(AnalysisFailedError, match='XML parse error'):
        api.query('ast', 'bad.xml')


@pytest.mark.parametrize('uri', ['json://d.json?view=value', 'json://obj.json/present', 'ast://d', 'ast://mixed'])
def test_control_an_answer_the_cli_exits_0_on_returns(fx, uri):
    assert _cli(uri)[0] == 0
    assert isinstance(api.query(uri), dict)


def test_control_a_raised_cause_is_unchanged(fx):
    """A source that cannot be parsed raises its own ValueError before any answer (the CLI's exit 3, its cause)."""
    assert _cli('json://bad.json')[0] == 3
    with pytest.raises(ValueError, match='not valid JSON') as raised:
        api.query('json://bad.json')
    assert not isinstance(raised.value, RequestValidationError)


def test_control_a_noun_the_cli_answers_by_its_legacy_route_keeps_returning(fx):
    """stats:// is no declared noun: the CLI answers it by the generic URI route, which reads no execution facts and
    exits 0 here; its own facts call the tree failed, so the URI form must not map them."""
    assert _cli('stats://mixed')[0] == 0
    assert api.query('stats://mixed')['type'] == 'stats_summary'
