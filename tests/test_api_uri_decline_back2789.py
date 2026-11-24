"""``api.query(URI)`` returns a decline as the noun form does (D21, BACK-2789; BACK-2760).

A request that genuinely does not apply to its target (``NotApplicableError``: a tree with no test files for
``patches``/``testability``, a directory outside every repository for ``git``, two JSON files for ``diff``) is no
failure: the CLI's declared route answers it with exit 0 and a declined document (``applicable: false``, the reason, a
``not_applicable`` warning; BACK-1210), and the noun form of ``api.query`` returns that document. The URI form raised
``NotApplicableError`` instead. D21 (Scott 2026-11-24): one failure meaning across transports, so the URI form returns
the declined document the noun form returns. A failed answer still raises and a findings answer still returns.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import PathNotFoundError, RequestValidationError

APP = 'def f():\n    return 1\n\n\ndef g():\n    return f()\n'

# (URI, noun, target, the noun's CLI words): one request per decline source, spelled with no query string.
DECLINES = [
    pytest.param('patches://notests', 'patches', 'notests', ('patches', 'notests'), id='patches-no-tests'),
    pytest.param('testability://notests', 'testability', 'notests', ('testability', 'notests'),
                 id='testability-no-tests'),
    pytest.param('git://nogit', 'git', 'nogit', ('git', 'nogit'), id='git-outside-a-repository'),
    pytest.param('diff://json://a.json:json://b.json', 'diff', 'json://a.json:json://b.json',
                 ('diff', 'json://a.json', 'json://b.json'), id='diff-json'),
]


@pytest.fixture
def fx(tmp_path, monkeypatch):
    for name in ('notests', 'nogit'):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'app.py').write_text(APP, encoding='utf-8')
    (tmp_path / 'a.json').write_text('{"a": 1}\n', encoding='utf-8')
    (tmp_path / 'b.json').write_text('{"a": 2}\n', encoding='utf-8')
    (tmp_path / 'd.json').write_text('{"a": 1}\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _needs(uri):
    if uri.startswith('git://'):
        pytest.importorskip('pygit2')


def _cli(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, json.loads(run.stdout)


def _answer(document):
    """*document* without its retirement notes, which each transport renders in its own spelling (an analysis-only
    scheme's URI says its request note even with no query string; ``testability`` notes as a retired noun; BACK-2716)."""
    meta = dict(document['meta'])
    meta['warnings'] = [w for w in meta['warnings'] if w.get('type') != 'retired_spelling']
    return {**document, 'meta': meta}


def _notes(document):
    return [w['field'] for w in document['meta']['warnings'] if w.get('type') == 'retired_spelling']


@pytest.mark.parametrize('uri, noun, target, words', DECLINES)
def test_the_uri_form_returns_the_declined_document_the_noun_form_returns(fx, uri, noun, target, words):
    _needs(uri)
    declined = api.query(uri)
    assert _answer(declined) == _answer(api.query(noun, target))
    assert declined['applicable'] is False
    assert 'not_applicable' in [w['type'] for w in declined['meta']['warnings']]


@pytest.mark.parametrize('uri, noun, target, words', DECLINES)
def test_the_uri_forms_decline_is_the_clis_document_with_the_same_notes(fx, uri, noun, target, words):
    _needs(uri)
    code, document = _cli(uri)
    assert code == 0
    declined = api.query(uri)
    assert _answer(declined) == _answer(document)
    assert _notes(declined) == _notes(document)


@pytest.mark.parametrize('uri, noun, target, words', DECLINES)
def test_sibling_the_noun_form_returns_the_clis_decline(fx, uri, noun, target, words):
    _needs(uri)
    code, document = _cli(*words)
    assert code == 0
    answer = api.query(noun, target)
    assert answer['applicable'] is False and answer['reason']
    assert answer == document


def test_a_typed_keyword_on_a_declined_uri_returns_the_decline(fx):
    declined = api.query('patches://notests', limit=3)
    assert declined['applicable'] is False
    assert declined['type'] == 'patches_scan'


@pytest.mark.xfail(strict=True, reason='BACK-2789: the URI form records no reads, so a decline cannot name the given '
                                        'controls it never read (control_unread_by_data) as the CLI dispatch does')
def test_a_declines_unread_keyword_is_named_alike_in_both_forms(fx):
    """A keyword the declined answer never read is named by the one shared warning on the noun form (BACK-2696)."""
    assert _answer(api.query('patches://notests', limit=3)) == _answer(api.query('patches', 'notests', limit=3))


def test_control_a_failed_answer_still_raises(fx):
    with pytest.raises(PathNotFoundError, match='^Path not found: nope$'):
        api.query('ast://nope')
    with pytest.raises(RequestValidationError, match='^Unknown query: a~~~$'):
        api.query('json://d.json?view=value&where=a~~~')


def test_control_a_test_root_that_does_not_exist_still_raises(fx):
    """The request check runs before the analysis could decline (BACK-2325): an invalid request, exit 2."""
    assert _cli('testability', 'notests', '--test-paths', 'nope')[0] == 2
    with pytest.raises(RequestValidationError, match='^Test path not found: nope$'):
        api.query('testability://notests?test-paths=nope')


def test_control_a_findings_answer_still_returns(fx):
    answer = api.query('calls://notests?callers=f')
    assert answer['type'] == 'calls_query'
    assert 'applicable' not in answer
    assert answer['source'] == api.query('calls', 'notests', callers='f')['source'] == 'notests'
