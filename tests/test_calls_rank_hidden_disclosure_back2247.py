"""``calls ?rank=callers`` text names the tree gitignore hid, as the other views do (BACK-2247).

A scope whose every source file is gitignored ranked nothing and said only ``Confidence withheld``.
JSON carried the ``scope_hidden`` warning and the ``?callers=``, ``?callees=`` and ``?uncalled`` text
printed ``No files left to analyze: N entries hidden by .gitignore``; the ranking text printed none of the
caveats that explain an empty answer, because each text view chose for itself which warnings to print.
"""
import json

import pytest

from conftest import _run_reveal_direct as run

pytestmark = pytest.mark.component

HIDDEN = 'No files left to analyze'


def _ignored_corpus(tmp_path):
    corpus = tmp_path / 'corpus'
    corpus.mkdir()
    (corpus / '.gitignore').write_text('*.py\n', encoding='utf-8')
    (corpus / 'm.py').write_text('def a():\n    b()\n\n\ndef b():\n    pass\n', encoding='utf-8')
    return corpus


def _healthy_corpus(tmp_path):
    corpus = tmp_path / 'healthy'
    corpus.mkdir()
    (corpus / 'm.py').write_text('def a():\n    b()\n\n\ndef b():\n    pass\n', encoding='utf-8')
    return corpus


def _text(root, query):
    result = run('calls://' + str(root) + '?' + query)
    assert result.returncode == 0, (query, result.stderr)
    return result.stdout


@pytest.mark.parametrize('query', ['rank=callers', 'callers=b', 'callees=a', 'uncalled'])
def test_every_text_view_names_the_hidden_tree(tmp_path, query):
    assert HIDDEN in _text(_ignored_corpus(tmp_path), query)


def test_the_ranking_json_already_carries_it(tmp_path):
    """Control: the data was always there; the text view dropped it."""
    result = run('calls://' + str(_ignored_corpus(tmp_path)) + '?rank=callers', '--format', 'json')
    warnings = json.loads(result.stdout)['meta']['warnings']
    assert any(w.get('type') == 'scope_hidden' for w in warnings)


def test_the_ranking_text_of_a_healthy_corpus_is_unchanged(tmp_path):
    """Control: a ranking with entries prints no caveat list, and no hidden note where nothing was hidden."""
    out = _text(_healthy_corpus(tmp_path), 'rank=callers')
    assert HIDDEN not in out and '  b  (1 caller)' in out
    assert 'Dynamic dispatch' not in out


def test_an_empty_ranking_prints_the_caveats_an_empty_callers_view_does(tmp_path):
    corpus = tmp_path / 'prose'
    corpus.mkdir()
    (corpus / 'notes.txt').write_text('No supported source here.\n', encoding='utf-8')
    ranking = _text(corpus, 'rank=callers')
    # An absent name is a usage error (exit 2), but the view still prints its caveats.
    callers = run('calls://' + str(corpus) + '?callers=b')
    assert 'Dynamic dispatch' in callers.stdout + callers.stderr and 'Dynamic dispatch' in ranking
