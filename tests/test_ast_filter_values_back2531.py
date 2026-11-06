"""BACK-2531: an ast:// filter VALUE that cannot match is not a genuine zero.

A numeric field compared with a non-number (``complexity>abc``, a doubled operator such as
``complexity>>3``, a range with a non-numeric end), and an ordering comparison of any field with
a non-number (``name>a`` never matched: ordering compares numbers), is an invalid request: exit 2.
A ``type=`` that names no element category in the scan answers, but says so and lists the
categories present (types differ by language, so the set is open and this is a warning, like
a misspelled filter key, BACK-1111).
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'a.py').write_text(
        'class C:\n    def m(self, x):\n        if x:\n            return 1\n        return 2\n\n'
        'def f(a):\n    for i in a:\n        if i:\n            print(i)\n',
        encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('query', [
    'complexity>abc', 'complexity>>3', 'complexity=abc', 'depth<x', 'lines=10..abc', 'callers>many',
    'lines>=ten&type=function', 'name>a',
])
def test_numeric_field_with_a_non_number_exits_2(tree, query):
    result = _run_reveal_direct(f'ast://{tree}?{query}')
    assert result.returncode == 2, (result.returncode, result.stdout[-300:], result.stderr[-300:])
    field = query.split('&')[0].split('>')[0].split('<')[0].split('=')[0]
    assert field in result.stderr and 'number' in result.stderr
    assert 'No matches found' not in result.stdout


@pytest.mark.parametrize('query', [
    'complexity>1', 'complexity>1.5', 'complexity=>1', 'complexity!=99', 'lines=1..50', 'depth<9',
    'callers>=0', 'name=f', 'name~=^m',
])
def test_numeric_and_non_numeric_controls_still_answer(tree, query):
    result = _run_reveal_direct(f'ast://{tree}?{query}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['results'], query


def test_type_that_names_no_category_warns_with_the_categories_present(tree):
    result = _run_reveal_direct(f'ast://{tree}?type=functoin', '--format', 'json')
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['results'] == []
    warning = next(w for w in data['meta']['warnings'] if w['type'] == 'unknown_type_value')
    assert "'functoin'" in warning['message']
    assert 'functions' in warning['message'] and 'classes' in warning['message']
    text = _run_reveal_direct(f'ast://{tree}?type=functoin|clas')
    assert "'functoin'" in text.stdout + text.stderr and "'clas'" in text.stdout + text.stderr


@pytest.mark.parametrize('query', ['type=function', 'type=class|method', 'type!=class'])
def test_matching_type_has_no_type_warning(tree, query):
    data = json.loads(_run_reveal_direct(f'ast://{tree}?{query}', '--format', 'json').stdout)
    assert data['results']
    assert not [w for w in data['meta']['warnings'] if w['type'] == 'unknown_type_value']


@pytest.mark.parametrize('doubled, single', [('complexity==2', 'complexity=2'), ('name==f', 'name=f'),
                                             ('type==function', 'type=function')])
def test_double_equals_is_equality(tree, doubled, single):
    # '==' left its second '=' in the value, so it matched nothing (exit 0, no warning).
    def names(query):
        result = _run_reveal_direct(f'ast://{tree}?{query}', '--format', 'json')
        assert result.returncode == 0, result.stderr
        return sorted(r['name'] for r in json.loads(result.stdout)['results'])
    assert names(single) and names(doubled) == names(single)
