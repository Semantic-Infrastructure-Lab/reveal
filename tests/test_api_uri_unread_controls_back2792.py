"""``api.query(URI)`` names the controls an answer never read, as the CLI and the noun form do (BACK-2792, D21).

A request that declines on its data (``NotApplicableError``: a tree with no test files for ``patches``, a directory
outside every repository for ``git``) names the given controls it never read in the one shared
``control_unread_by_data`` warning (COMMAND_MODEL "Applicability", BACK-2696). That warning reads the dispatch's
query-key log, which the CLI's dispatch and the noun form of ``api.query`` open; the URI form opened none, so its
declines (a typed keyword, the ``?limit=`` spelling, ``git://``) said nothing about the control. The same log carries a
query parser's ``unknown_query_param`` warning, which the CLI's JSON answer carries in ``meta.warnings``; the URI form
printed it on stderr instead. A request that raises has no document, so its parser warning stays on stderr.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api

APP = 'def f():\n    return 1\n\n\ndef g():\n    return f()\n'


@pytest.fixture
def fx(tmp_path, monkeypatch):
    for name in ('notests', 'nogit'):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'app.py').write_text(APP, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cli(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, json.loads(run.stdout)


def _warnings(document):
    """*document*'s warnings without its retirement notes, which each transport renders in its own spelling."""
    return [w for w in document['meta']['warnings'] if w.get('type') != 'retired_spelling']


def _unread(document):
    return [w['fields'] for w in document['meta']['warnings'] if w.get('code') == 'control_unread_by_data']


# (API call, the CLI's words): each declines and gives a control the decline never read.
DECLINES = [
    pytest.param(lambda: api.query('patches://notests', limit=3), ('patches://notests', '--limit', '3'),
                 id='patches-typed-keyword'),
    pytest.param(lambda: api.query('patches://notests?limit=3'), ('patches://notests?limit=3',),
                 id='patches-uri-key'),
    pytest.param(lambda: api.query('git://nogit', limit=2), ('git://nogit', '--limit', '2'), id='git-typed-keyword'),
    pytest.param(lambda: api.query('git://nogit?limit=2'), ('git://nogit?limit=2',), id='git-uri-key'),
]


def _needs_git(request):
    if 'git' in request.node.callspec.id:
        pytest.importorskip('pygit2')


@pytest.mark.parametrize('call, words', DECLINES)
def test_a_decline_names_the_control_it_never_read_as_the_cli_does(fx, request, call, words):
    _needs_git(request)
    code, document = _cli(*words)
    assert code == 0 and _unread(document) == [['limit']], document['meta']
    answer = call()
    assert answer['applicable'] is False
    assert _warnings(answer) == _warnings(document)


@pytest.mark.parametrize('uri, noun, target, controls', [
    pytest.param('patches://notests', 'patches', 'notests', {'limit': 3}, id='patches'),
    pytest.param('git://nogit', 'git', 'nogit', {'limit': 2}, id='git'),
])
def test_a_decline_answers_as_the_noun_form_does(fx, request, uri, noun, target, controls):
    _needs_git(request)
    noun_form = api.query(noun, target, **controls)
    assert _unread(noun_form) == [['limit']]
    assert _warnings(api.query(uri, **controls)) == _warnings(noun_form)


@pytest.mark.parametrize('call, words', [
    pytest.param(lambda: api.query('patches://notests'), ('patches://notests',), id='patches-decline-no-control'),
    pytest.param(lambda: api.query('ast://notests', limit=1), ('ast://notests', '--limit', '1'), id='ast-read-limit'),
    pytest.param(lambda: api.query('calls://notests?callers=f'), ('calls://notests?callers=f',), id='calls-findings'),
])
def test_sibling_an_answer_with_no_unread_control_is_unchanged(fx, call, words):
    code, document = _cli(*words)
    assert code == 0 and _unread(document) == []
    answer = call()
    assert _unread(answer) == []
    assert _warnings(answer) == _warnings(document)


def test_a_parsers_unknown_key_warning_is_in_the_answer_not_on_stderr(fx, capfd):
    """``classify://`` (undeclared) warns on a key it does not know; the CLI's JSON carries it in ``meta.warnings``."""
    code, document = _cli('classify://notests/app.py?bogus=1')
    assert code == 0
    assert [w['fields'] for w in document['meta']['warnings'] if w['type'] == 'unknown_query_param'] == [['bogus']]
    capfd.readouterr()
    answer = api.query('classify://notests/app.py?bogus=1')
    assert _warnings(answer) == _warnings(document)
    assert capfd.readouterr() == ('', '')


def test_control_a_known_key_answers_quietly_on_both(fx, capfd):
    code, document = _cli('classify://notests/app.py')
    assert code == 0
    capfd.readouterr()
    answer = api.query('classify://notests/app.py')
    assert _warnings(answer) == _warnings(document) == []
    assert capfd.readouterr() == ('', '')


def test_control_a_request_that_raises_keeps_its_parser_warning_on_stderr(fx, capfd):
    """No document carries it, so the warning is not dropped: it is printed, as before."""
    with pytest.raises(FileNotFoundError, match='nope.py'):
        api.query('classify://nope.py?bogus=1')
    out, err = capfd.readouterr()
    assert out == ''
    assert "Unknown query param 'bogus' for classify://" in err
