"""BACK-2701: a legacy word whose codec says "the control's default" is not a given control on the URI either.

``verbose=false`` is the default of the control verbose stands for. The typed path (``api.query(..., verbose=False)``)
already discards it; ``?against=HEAD&verbose=false`` exited 2 naming ``all``, which the comparison does not read.
"""
import json

import pygit2
import pytest
from conftest import _run_reveal_direct as run

from reveal import api


@pytest.fixture
def repo(tmp_path):
    (tmp_path / 'app.py').write_text('def go():\n    return 1\n', encoding='utf-8')
    git = pygit2.init_repository(str(tmp_path))
    git.index.add('app.py')
    git.index.write()
    who = pygit2.Signature('F', 'f@example.com', 1700000000, 0)
    git.create_commit('HEAD', who, who, 'one', git.index.write_tree(), [])
    return tmp_path


def _cli(*argv):
    response = run(*argv, '--format', 'json')
    return response.returncode, response.stdout


def test_uri_verbose_false_is_not_given_on_the_comparison(repo):
    code, out = _cli(f'overview://{repo}?against=HEAD&verbose=false')
    assert code == 0 and json.loads(out)['type'] == 'overview_diff'


def test_uri_verbose_false_answers_as_typed_false_and_as_omitted(repo):
    uri = f'overview://{repo}?against=HEAD'
    omitted = api.query(uri)
    assert api.query(uri + '&verbose=false')['type'] == omitted['type'] == 'overview_diff'
    assert api.query(uri, verbose=False)['type'] == 'overview_diff'


def test_verbose_true_and_all_false_still_exit_2_on_the_comparison(repo):
    for query in ('verbose=true', 'all=false', 'all=true'):
        code, out = _cli(f'overview://{repo}?against=HEAD&{query}')
        assert code == 2, query
