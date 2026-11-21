"""BACK-2613: ast's vocabulary under D20 -- what must not change while it moves.

These pins hold the answers ast gives today that the vocabulary package keeps: the default listing (JSON, text, exit) on
the subcommand, the URI and the typed API; the Python-evidence answers given alone; the legacy spellings' rows; and the
sibling nouns' cap controls the shared ``--all`` codec reaches (metrics, calls, imports, overview).
"""
import json

import pytest

from conftest import _run_reveal_in, without_request_notes, without_retirement_notes

A_PY = '''import os

@property
def alpha(x: int) -> int:
    if x:
        if x > 1:
            return 1
    return 2

def beta(y):
    alpha(y)
    print(y)
    return {'k': y}

class Gamma:
    def delta(self, d: dict):
        for k in d:
            if k:
                beta(k)
        return d
'''
B_PY = '''def test_one():
    assert True

def helper(a, b, c):
    return a + b + c
'''
ALL_NAMES = ['import os', 'alpha', 'beta', 'delta', 'Gamma', 'test_one', 'helper']
FUNCTIONS = ['alpha', 'beta', 'delta', 'test_one', 'helper']


@pytest.fixture
def tree(tmp_path):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'a.py').write_text(A_PY, encoding='utf-8')
    (pkg / 'b.py').write_text(B_PY, encoding='utf-8')
    (tmp_path / 'rows.json').write_text(json.dumps([{'n': 1}, {'n': 2}]), encoding='utf-8')
    return tmp_path


def run(tree, *argv):
    return _run_reveal_in(tree, *argv)


def doc(tree, *argv):
    """(exit, JSON document or None, stderr) of a JSON-mode request run from *tree*."""
    result = run(tree, *argv, '--format', 'json')
    out = result.stdout.strip()
    return result.returncode, (json.loads(out) if out.startswith('{') else None), result.stderr


def names(document):
    return [row.get('name') for row in document['results']]


def notes(document):
    """The retired_spelling warnings of a JSON answer: (field, replacement)."""
    return [(w.get('field'), w.get('replacement')) for w in (document.get('meta') or {}).get('warnings') or []
            if w.get('code') == 'retired_spelling']


def _api(tree, *args, **controls):
    from reveal import api
    return api.query('ast', str(tree / 'pkg'), *args, **controls)


# --- the default listing ------------------------------------------------------------------------------------

def test_default_listing_json_on_every_form(tree):
    code, sub, _ = doc(tree, 'ast', 'pkg')
    uri_code, uri, _ = doc(tree, 'ast://pkg')
    assert code == uri_code == 0
    assert sub['type'] == 'ast_query' and sub['query'] == 'none' and sub['show_mode'] is None
    assert (sub['total_files'], sub['total_results'], sub['displayed_results']) == (2, 7, 7)
    assert names(sub) == ALL_NAMES
    assert notes(sub) == []
    assert without_request_notes(uri) == sub
    api = _api(tree)
    assert names(api) == ALL_NAMES and api['total_results'] == 7 and notes(api) == []


def test_default_listing_text(tree):
    result = run(tree, 'ast', 'pkg')
    assert result.returncode == 0
    assert result.stdout.replace('\\', '/') == (
        'AST Query: pkg\n'
        'Files scanned: 2\n'
        'Results: 7\n'
        '\n'
        'File: pkg/a.py\n'
        '  :   1  import os [0 lines]\n'
        '  :   3  alpha [6 lines, complexity: 3]\n'
        '           called by: beta\n'
        '  :  10  beta [4 lines, complexity: 1]\n'
        '           calls:     alpha\n'
        '           called by: delta\n'
        '  :  16  delta [5 lines, complexity: 3]\n'
        '           calls:     beta\n'
        '  :  15  Gamma [6 lines]\n'
        '\n'
        'File: pkg/b.py\n'
        '  :   1  test_one [2 lines, complexity: 1]\n'
        '  :   4  helper [2 lines, complexity: 1]\n'
        '\n')


def test_kind_answer_on_every_form(tree):
    _, sub, _ = doc(tree, 'ast', 'pkg', '--kind', 'function')
    _, uri, _ = doc(tree, 'ast://pkg?kind=function')
    assert names(sub) == FUNCTIONS and sub['total_results'] == 5
    assert without_request_notes(uri) == sub
    assert names(_api(tree, kind='function')) == FUNCTIONS


def test_legacy_type_answers_as_kind_with_its_row(tree):
    _, kind, _ = doc(tree, 'ast', 'pkg', '--kind', 'function')
    code, legacy, _ = doc(tree, 'ast', 'pkg', '--type', 'function')
    assert code == 0 and [field for field, _ in notes(legacy)] == ['param:ast.type']
    assert without_retirement_notes(legacy) == kind


def test_ranking_order_in_json(tree):
    code, ranked, _ = doc(tree, 'ast', 'pkg', '--sort=-name', '--kind', 'function')
    assert code == 0 and names(ranked) == ['test_one', 'helper', 'delta', 'beta', 'alpha']
    _, top, _ = doc(tree, 'ast', 'pkg', '--sort=-complexity', '--limit', '2')
    assert names(top) == ['alpha', 'delta'] and (top['total_results'], top['displayed_results']) == (7, 2)


@pytest.mark.parametrize('argv,expected', [
    (['--limit', '0'], ALL_NAMES), (['--all'], ALL_NAMES), (['--offset', '5'], ['test_one', 'helper']),
    (['--max-items', '0'], []),
])
def test_caps_and_pages(tree, argv, expected):
    code, answer, _ = doc(tree, 'ast', 'pkg', *argv)
    assert code == 0 and names(answer) == expected and answer['total_results'] == 7


@pytest.mark.parametrize('argv', [['--limit', '2', '--all'], ['--limit', '-1'], ['--offset', '-1'],
                                  ['--limit', '1.5'], ['--kind', 'function', '--kind', 'class']])
def test_invalid_caps_and_conflicts_exit_2(tree, argv):
    assert doc(tree, 'ast', 'pkg', *argv)[0] == 2


def test_missing_path_exits_2_on_every_form(tree):
    assert doc(tree, 'ast', 'pkg/nonexistent')[0] == 2
    assert doc(tree, 'ast://pkg/nonexistent')[0] == 2
    from reveal import api
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError):
        api.query('ast', str(tree / 'pkg' / 'nonexistent'))


# --- filters that keep answering while their spelling moves -------------------------------------------------

@pytest.mark.parametrize('expression,expected', [
    ('lines>3', ['alpha', 'beta', 'delta', 'Gamma']), ('complexity>1', ['alpha', 'delta']),
    ('depth>1', ['alpha', 'delta']), ('calls=beta', ['delta']), ('callee_of=beta', ['alpha']),
    ('callers>0', ['alpha', 'beta']), ('decorator=property', ['alpha']), ('param_type=dict', ['delta']),
    ('return_type=int', ['alpha']), ('name=a*|b*', ['alpha', 'beta']), ('kind=method', ['delta']),
])
def test_where_rows(tree, expression, expected):
    code, answer, _ = doc(tree, 'ast', 'pkg', '--where', expression)
    assert code == 0 and names(answer) == expected


def test_bare_uri_filters_answer_as_where(tree):
    _, where, _ = doc(tree, 'ast', 'pkg', '--where', 'lines>3', '--where', 'lines<6')
    _, bare, _ = doc(tree, 'ast://pkg?lines>3&lines<6')
    assert names(where) == ['beta', 'delta'] and without_request_notes(bare) == where


def test_bare_retired_call_filters_keep_their_own_row(tree):
    for key in ('calls', 'callee_of'):
        code, answer, _ = doc(tree, f'ast://pkg?{key}=beta')
        assert code == 0 and f'param:ast.{key}' in [field for field, _ in notes(answer)]


# --- the Python-evidence answers, given alone ---------------------------------------------------------------

@pytest.mark.parametrize('view', ['dict-heatmap', 'dict-schemas'])
def test_dict_views_alone(tree, view):
    code, answer, _ = doc(tree, 'ast', 'pkg', '--view', view)
    _, uri, _ = doc(tree, f'ast://pkg?view={view}')
    assert code == 0 and answer['type'] == 'ast_' + view.replace('-', '_')
    assert answer['analysis']['candidate_files'] == 2 and without_request_notes(uri) == answer


def test_reveal_type_alone(tree):
    code, answer, _ = doc(tree, 'ast', 'pkg', '--reveal-type', 'd')
    assert code == 0 and answer['type'] == 'ast_reveal_type' and answer['total_results'] >= 1


# --- sibling nouns the shared codecs reach (negative controls) ----------------------------------------------

def test_json_view_and_limit_unchanged(tree):
    code, keys, _ = doc(tree, 'json', 'rows.json', '--view', 'keys')
    _, legacy, _ = doc(tree, 'json://rows.json?keys')
    assert code == 0 and without_request_notes(without_retirement_notes(legacy)) == keys


@pytest.mark.parametrize('argv,expected', [
    (['metrics', 'pkg', '--limit', '1'], 0), (['metrics://pkg?limit'], 2), (['metrics', 'pkg', '--all', '--limit', '2'], 2),
    (['calls', 'pkg', '--sort=-callers', '--limit', '1'], 0), (['calls', 'pkg', '--sort=-callers', '--all', '--limit', '2'], 2),
    (['imports', 'pkg', '--sort=-fan-in', '--all', '--limit', '0'], 0), (['overview', 'pkg', '--all', '--limit', '0'], 0),
])
def test_sibling_cap_controls(tree, argv, expected):
    assert doc(tree, *argv)[0] == expected
