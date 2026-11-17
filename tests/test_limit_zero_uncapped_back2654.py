"""Caps row (COMMAND_MODEL, BACK-2654 item 2b): `--limit 0` / `?limit=0` is the uncapped answer on every noun.

ast, git, json and markdown declared `limit` zero as an empty page, while metrics, calls, imports and claude
uncapped it. Each case runs on a fixture the noun's default cap binds (ast's 200-result auto-cap, git's 20-commit
history page) or a one-row cap binds (json, markdown), on the URI form, the subcommand and `api.query`; offset still
pages the uncapped answer, and `--max-items 0` stays the empty output budget.
"""
import json

import pytest

from conftest import _run_reveal_direct as run


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    (root / 'docs').mkdir(parents=True)
    (root / 'many.py').write_text(''.join(f'def fn_{i}():\n    return {i}\n\n\n' for i in range(230)),
                                  encoding='utf-8')
    for i in range(5):
        (root / 'docs' / f'd{i}.md').write_text(f'---\ntitle: Doc {i}\n---\n# Doc {i}\n', encoding='utf-8')
    (root / 'rows.json').write_text(json.dumps([{'n': i} for i in range(7)]), encoding='utf-8')
    import pygit2
    repo = pygit2.init_repository(str(root / 'repo'))
    sig = pygit2.Signature('Fixture', 'fixture@example.com', 1700000000, 0)
    parents = []
    for i in range(25):
        (root / 'repo' / 'f.txt').write_text(f'{i}\n', encoding='utf-8')
        repo.index.add('f.txt')
        repo.index.write()
        parents = [repo.create_commit('HEAD', sig, sig, f'c{i}', repo.index.write_tree(), parents)]
    return root


# noun -> (URI resource and query, subcommand argv, the answer's row field)
CASES = {
    'ast': ('ast://proj', ['ast', 'proj'], 'results'),
    'git': ('git://proj/repo?view=history', ['git', 'proj/repo', '--view', 'history'], 'history'),
    'json': ('json://proj/rows.json', ['json', 'proj/rows.json'], 'value'),
    'markdown': ('markdown://proj/docs', ['markdown', 'proj/docs'], 'results'),
}
TOTALS = {'ast': 230, 'git': 25, 'json': 7, 'markdown': 5}
DEFAULT_CAPPED = {'ast': 200, 'git': 20}  # the default cap the fixture exceeds


def _uri(noun, extra):
    uri = CASES[noun][0]
    return uri + ('&' if '?' in uri else '?') + extra


def _rows(result, noun):
    rows = result.get(CASES[noun][2])
    assert isinstance(rows, list), result
    return len(rows)


def _cli(*argv):
    answer = run(*argv, '--format', 'json')
    assert answer.returncode == 0, answer.stderr
    return json.loads(answer.stdout)


@pytest.mark.parametrize('noun', sorted(CASES))
def test_limit_zero_is_every_row_on_both_forms(tree, noun):
    uri_zero = _rows(_cli(_uri(noun, 'limit=0')), noun)
    flag_zero = _rows(_cli(CASES[noun][0], '--limit', '0'), noun)
    typed_zero = _rows(_cli(*CASES[noun][1], '--limit', '0'), noun)
    assert uri_zero == flag_zero == typed_zero == TOTALS[noun]


@pytest.mark.parametrize('noun', sorted(CASES))
def test_the_cap_binds_on_the_fixture(tree, noun):
    """Control: without limit=0 the default cap (or limit=1) cuts this fixture."""
    if noun in DEFAULT_CAPPED:
        assert _rows(_cli(CASES[noun][0]), noun) == DEFAULT_CAPPED[noun]
    assert _rows(_cli(_uri(noun, 'limit=1')), noun) == 1


@pytest.mark.parametrize('noun', sorted(CASES))
def test_offset_pages_the_uncapped_answer(tree, noun):
    assert _rows(_cli(_uri(noun, 'limit=0&offset=2')), noun) == TOTALS[noun] - 2


@pytest.mark.parametrize('noun', sorted(CASES))
def test_api_query_limit_zero_is_every_row(tree, noun):
    from reveal import api
    assert _rows(api.query(_uri(noun, 'limit=0')), noun) == TOTALS[noun]
    assert _rows(api.query(CASES[noun][0], limit=0), noun) == TOTALS[noun]


def test_max_items_zero_stays_an_empty_output_budget(tree):
    """--max-items is a separate output budget whose zero is an empty page (Caps row); limit=0 does not change it."""
    answer = run('ast://proj', '--max-items', '0', '--format', 'json')
    assert answer.returncode == 0, answer.stderr
    assert json.loads(answer.stdout)['results'] == []
