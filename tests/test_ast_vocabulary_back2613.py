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


# --- REDs: the bugs and rulings of the Step 1 inventory (mevama-1121 mv-ast) --------------------------------

def _request_replacements(document):
    return [replacement for field, replacement in notes(document) if field == 'request:ast']


def _says_calls_noun(document):
    return any('reveal calls' in (replacement or '') for _field, replacement in notes(document))


# B1 / Q3: the retired call-graph view notes its row on every spelling, and no note recommends --view calls.

@pytest.mark.parametrize('argv', [['--view', 'calls'], ['--show', 'calls']])
def test_b1_calls_view_flag_notes_the_calls_noun(tree, argv):
    code, answer, _ = doc(tree, 'ast', 'pkg', *argv)
    assert code == 0 and _says_calls_noun(answer), notes(answer)
    text = run(tree, 'ast', 'pkg', *argv)
    assert 'reveal calls' in text.stderr, text.stderr


@pytest.mark.parametrize('key', ['show', 'view'])
def test_b1_calls_view_uri_says_its_row_not_view_calls(tree, key):
    code, answer, _ = doc(tree, f'ast://pkg?{key}=calls')
    assert code == 0 and _says_calls_noun(answer), notes(answer)
    assert not any(r.endswith('--view calls') for r in _request_replacements(answer)), notes(answer)


def test_b1_calls_view_api_and_mcp_note(tree):
    assert _says_calls_noun(_api(tree, view='calls')), notes(_api(tree, view='calls'))
    from reveal.mcp_server import reveal_run
    assert 'reveal calls' in reveal_run(['ast', str(tree / 'pkg'), '--view', 'calls'])


# B2 / Q2: a retired where field notes its existing row wherever it is spelled.

@pytest.mark.parametrize('argv', [['ast', 'pkg', '--where', 'calls=beta'], ['ast://pkg?where=calls=beta'],
                                  ['ast', 'pkg', '--where', 'callee_of=beta']])
def test_b2_retired_where_field_notes_its_row(tree, argv):
    code, answer, _ = doc(tree, *argv)
    key = 'callee_of' if 'callee_of' in argv[-1] else 'calls'
    assert code == 0 and f'param:ast.{key}' in [field for field, _ in notes(answer)], notes(answer)


def test_b2_retired_where_field_api_and_text(tree):
    answer = _api(tree, where=['calls=beta'])
    assert 'param:ast.calls' in [field for field, _ in notes(answer)], notes(answer)
    assert 'reveal calls' in run(tree, 'ast', 'pkg', '--where', 'calls=beta').stderr


def test_b2_request_note_names_no_retired_field(tree):
    _, answer, _ = doc(tree, 'ast://pkg?calls=beta')
    assert not any('calls=beta' in r for r in _request_replacements(answer)), notes(answer)


# B3: a control the selected answer does not read exits 2 before analysis; --all on an answer with no cap is quiet.

@pytest.mark.parametrize('argv', [
    ['--view', 'dict-heatmap', '--limit', '2'], ['--view', 'dict-schemas', '--sort', 'name'],
    ['--view', 'dict-heatmap', '--kind', 'function'], ['--view', 'dict-heatmap', '--where', 'complexity>1'],
    ['--view', 'dict-heatmap', '--builtins'], ['--reveal-type', 'd', '--offset', '1'],
    ['--reveal-type', 'd', '--where', 'complexity>1'],
])
def test_b3_unread_control_exits_2(tree, argv):
    code, _, err = doc(tree, 'ast', 'pkg', *argv)
    assert code == 2 and 'is not read by this answer' in err, (code, err)


def test_b3_unread_control_uri_and_api(tree):
    code, _, err = doc(tree, 'ast://pkg?view=dict-heatmap&limit=2')
    assert code == 2 and 'is not read by this answer' in err, (code, err)
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError):
        _api(tree, view='dict-heatmap', limit=2)


@pytest.mark.parametrize('argv', [
    ['--view', 'dict-heatmap', '--head', '2'], ['--view', 'dict-schemas', '--tail', '1'],
    ['--reveal-type', 'd', '--range', '1-2'],
])
def test_b3_legacy_slices_are_read_by_the_listing_only(tree, argv):
    """The legacy --head/--tail/--range slice the listing; a Python-evidence answer reads none of them, and its
    refusal lists no control it reads."""
    code, _, err = doc(tree, 'ast', 'pkg', *argv)
    assert code == 2 and 'is not read by this answer' in err and 'is read by: ast_query' in err, (code, err)
    assert 'controls this answer reads: (none)' in err, err
    code, answer, _ = doc(tree, 'ast', 'pkg', '--head', '2')
    assert code == 0 and len(answer['results']) == 2


@pytest.mark.parametrize('argv', [['--view', 'dict-heatmap', '--all'], ['--reveal-type', 'd', '--all']])
def test_b3_all_on_an_uncapped_answer_is_quiet(tree, argv):
    code, answer, err = doc(tree, 'ast', 'pkg', *argv)
    kinds = [w.get('type') for w in answer['meta']['warnings']]
    assert code == 0 and 'unused_flag' not in kinds and 'no effect' not in err, (kinds, err)


# B4: a view the noun does not have exits 2 naming its views.

@pytest.mark.parametrize('argv', [['ast', 'pkg', '--view', 'bogus'], ['ast', 'pkg', '--view', ''], ['ast://pkg?view=bogus']])
def test_b4_unknown_view_exits_2_naming_the_views(tree, argv):
    code, _, err = doc(tree, *argv)
    assert code == 2 and 'dict-heatmap' in err and 'dict-schemas' in err, (code, err)


def test_b4_unknown_view_api(tree):
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError):
        _api(tree, view='bogus')


# B5: two answer selections exit 2 naming both.

def test_b5_reveal_type_and_view_exit_2(tree):
    code, _, err = doc(tree, 'ast', 'pkg', '--reveal-type', 'd', '--view', 'dict-heatmap')
    assert code == 2 and 'reveal-type' in err and 'view' in err, (code, err)
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError):
        _api(tree, reveal_type='d', view='dict-heatmap')


# B6 / B7: a bare valueless scalar is an invalid request (exit 2), never a value.

@pytest.mark.parametrize('key', ['limit', 'kind', 'sort', 'reveal_type'])
def test_b6_b7_bare_scalar_exits_2(tree, key):
    code, _, err = doc(tree, f'ast://pkg?{key}')
    assert code == 2, (code, err)


# B8: an invalid original URI raises the same error type as the noun form.

def test_b8_invalid_uri_raises_request_validation_error(tree):
    from reveal import api
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError):
        api.query(f'ast://{tree / "pkg"}?complexity>abc')


# Q1: --all is the shared uncapping word: with --limit 0 it is one setting (BACK-2729).

MANY = 250  # past ast's 200-row default cap and calls' default ranking of 10


@pytest.fixture
def many(tree):
    """A package whose answers exceed the default caps: MANY functions, each calling the next (MANY-1 callees)."""
    big = tree / 'big'
    big.mkdir()
    (big / 'many.py').write_text(''.join(f'def f_{i}():\n    return f_{i + 1}()\n\n' for i in range(MANY)), encoding='utf-8')
    return tree


def _rows(answer):
    return answer.get('results', answer.get('entries', answer.get('files')))


# (default request, its row count at the default cap, the uncapped row count); each is asked three ways: as it is,
# with --limit 0, and with --all --limit 0 (and the URI with ?limit=0 then --all).
_Q1_REQUESTS = {
    'ast': (['ast', 'big'], 200, MANY),
    'ast-uri': (['ast://big?limit=0'], None, MANY),
    'calls': (['calls', 'big', '--sort=-callers'], 10, MANY - 1),
}


@pytest.mark.parametrize('label', sorted(_Q1_REQUESTS))
def test_q1_all_with_limit_0_is_the_limit_0_answer(many, label):
    request, capped, uncapped = _Q1_REQUESTS[label]
    zero_request = request if label == 'ast-uri' else [*request, '--limit', '0']
    code, zero, err = doc(many, *zero_request)
    assert code == 0 and len(_rows(zero)) == uncapped, err
    if capped is not None:
        _, default, _ = doc(many, *request)
        assert len(_rows(default)) == capped  # the default cap is real, so the equality below is not vacuous
    code, both, err = doc(many, *zero_request, '--all')
    assert code == 0, err
    assert both == zero


def test_q1_metrics_all_with_limit_0_is_the_limit_0_answer(many):
    _, zero, _ = doc(many, 'metrics', 'big', '--limit', '0')
    code, both, err = doc(many, 'metrics', 'big', '--all', '--limit', '0')
    assert code == 0 and both == zero, err


# Q5: kind is the where field and the echo; type is its legacy field word with the param:ast.type note.

def test_q5_where_type_notes_and_where_kind_does_not(tree):
    _, legacy, _ = doc(tree, 'ast', 'pkg', '--where', 'type=function')
    _, canonical, _ = doc(tree, 'ast', 'pkg', '--where', 'kind=function')
    assert 'param:ast.type' in [field for field, _ in notes(legacy)], notes(legacy)
    assert notes(canonical) == [] and names(canonical) == FUNCTIONS
    assert 'param:ast.type' in [field for field, _ in notes(_api(tree, where=['type=function']))]


def test_q5_echo_and_request_note_say_kind(tree):
    assert doc(tree, 'ast', 'pkg', '--kind', 'function')[1]['query'] == 'kind==function'
    _, answer, _ = doc(tree, 'ast://pkg?type!=function')
    assert any("kind!=function" in r for r in _request_replacements(answer)), notes(answer)


# Q6: --reveal-type names a variable; one with no occurrence is a target that matches nothing (plan rule 9).

def test_q6_reveal_type_no_occurrence_exits_2(tree):
    code, _, err = doc(tree, 'ast', 'pkg', '--reveal-type', 'nonexistent_zz')
    assert code == 2 and 'nonexistent_zz' in err, (code, err)
    assert doc(tree, 'ast://pkg?reveal-type=nonexistent_zz')[0] == 2
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError):
        _api(tree, reveal_type='nonexistent_zz')


# Q10: nesting_depth is the where field; depth its legacy field word, noted; the element key stays depth.

def test_q10_nesting_depth_is_the_where_field(tree):
    code, answer, _ = doc(tree, 'ast', 'pkg', '--where', 'nesting_depth>1')
    assert code == 0 and names(answer) == ['alpha', 'delta'] and notes(answer) == []
    assert all('depth' in row for row in answer['results'])


def test_q10_depth_field_notes_nesting_depth(tree):
    _, answer, _ = doc(tree, 'ast', 'pkg', '--where', 'depth>1')
    rows = dict(notes(answer))
    assert 'param:ast.depth' in rows and 'nesting_depth' in rows['param:ast.depth'], notes(answer)
    _, bare, _ = doc(tree, 'ast://pkg?depth>1')
    assert any('nesting_depth>1' in r for r in _request_replacements(bare)), notes(bare)


# --- BACK-2627 collision record: ast's answer --view and the element views share a flag name ----------------------

def test_view_after_an_ast_uri_binds_the_ast_answer_view(tree):
    code, answer, _ = doc(tree, 'ast://pkg', '--view', 'dict-heatmap')
    assert code == 0 and answer['type'] == 'ast_dict_heatmap'


def test_the_path_read_router_takes_no_answer_view(tree):
    """``reveal DIR --name X`` builds an ast request internally; an ast answer view is not a path-read flag."""
    assert run(tree, 'pkg', '--name', 'alp', '--view', 'dict-heatmap').returncode == 2


@pytest.mark.xfail(strict=True, reason='BACK-2627: element --view boundary|effects|flow|exits|vars lands on the path '
                                       'read; until then the main parser does not know --view')
def test_element_view_on_a_path_read(tree):
    assert run(tree, 'pkg/a.py', 'alpha', '--view', 'boundary').returncode == 0
