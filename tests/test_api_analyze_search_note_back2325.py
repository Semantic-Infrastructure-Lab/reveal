"""``api.analyze(PATH, search=X)`` says the retirement note ``reveal PATH --search X`` says (D21, BACK-2325, A6's B12).

``--search`` is deprecated (``flag:--search``, replaced by ``--name``). The CLI's JSON carries its note in
``meta.warnings``; ``api.analyze`` answers through the same path read but never noted it, so its document differed
from the CLI's by that one entry. The note joins the API's invocation log, as every other retirement note does: in the
returned document, never on the caller's stderr.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text('def foo():\n    return 1\n\n\ndef bar():\n    return 2\n', encoding='utf-8')
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'a.py').write_text('def foo():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _notes(document):
    return [w for w in document.get('meta', {}).get('warnings', []) if w.get('type') == 'retired_spelling']


def _cli(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


@pytest.mark.parametrize('target', ['ok.py', 'd'])
def test_the_api_says_the_clis_search_note_in_its_document(fx, target, capsys):
    document = api.analyze(target, search='foo')
    assert capsys.readouterr().err == ''
    cli = _cli(target, '--search', 'foo')
    assert [note['field'] for note in _notes(cli)] == ['flag:--search']
    assert _notes(document) == _notes(cli)
    assert document == cli


@pytest.mark.parametrize('target', ['ok.py', 'd'])
def test_sibling_the_replacement_says_no_note(fx, target):
    assert _notes(api.analyze(target, name='foo')) == []
    assert _notes(_cli(target, '--name', 'foo')) == []
