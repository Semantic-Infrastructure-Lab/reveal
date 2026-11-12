"""AST binds controls without losing repeated legacy filters or typed literal values."""
import json

import pytest

from conftest import _run_reveal_in


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'a.py').write_text('def a(x):\n    return x\n\ndef longer(x):\n    if x:\n        return x + 1\n    return 0\n', encoding='utf-8')
    return tmp_path


def answer(tree, *argv):
    result = _run_reveal_in(tree, *argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_declared_cli_uri_api_preserve_two_bounds(tree):
    from reveal.api import query
    cli = answer(tree, 'ast', 'a.py', '--where', 'lines>1', '--where', 'lines<4', '--sort', '-lines')
    uri = answer(tree, 'ast://a.py?lines>1&lines<4&sort=-lines')
    assert cli == uri
    api = query(f'ast://{tree / "a.py"}', where=['lines>1', 'lines<4'], sort='-lines')
    assert [r['name'] for r in cli['results']] == [r['name'] for r in api['results']] == ['a']


def test_kind_and_view_bind_to_existing_analysis(tree):
    a = answer(tree, 'ast', 'a.py', '--kind', 'function')
    b = answer(tree, 'ast://a.py?kind=function')
    assert a == b and a['total_results'] == 2
    a = answer(tree, 'ast', 'a.py', '--view', 'dict-heatmap')
    b = answer(tree, 'ast://a.py?view=dict-heatmap')
    assert a == b and a['type'] == 'ast_dict_heatmap'


def test_where_uri_percent_codec(tree):
    cli = answer(tree, 'ast', 'a.py', '--where', 'name~=^a$')
    uri = answer(tree, 'ast://a.py?where=name%7E%3D%5Ea%24')
    assert cli == uri


@pytest.mark.parametrize('flags', [['--limit', '-1'], ['--offset', '-1'], ['--where', 'lines>bad']])
def test_invalid_requests_reject_before_analysis(tree, flags):
    result = _run_reveal_in(tree, 'ast', 'a.py', *flags, '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['error']


def test_zero_limit_retains_the_existing_empty_page_meaning(tree):
    a = answer(tree, 'ast', 'a.py', '--limit', '0')
    b = answer(tree, 'ast://a.py?limit=0')
    assert a == b and len(a['results']) == 0 and a['total_results'] == 2


@pytest.mark.parametrize('query', ['kind=function&type=class', 'where=name%FF'])
def test_preparation_errors_are_structured_usage_failures(tree, query):
    result = _run_reveal_in(tree, 'ast://a.py?' + query, '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['type'] == 'ast_query'


def test_aliases_work_as_typed_overrides_and_conflicts_are_rejected(tree):
    from reveal.api import query
    assert query(f'ast://{tree / "a.py"}', type='function')['total_results'] == 2
    with pytest.raises(ValueError, match='conflicting spellings'):
        query(f'ast://{tree / "a.py"}', kind='function', type='class')


def test_kind_joins_all_legacy_and_canonical_constraints(tree):
    legacy = answer(tree, 'ast://a.py?type=function&type!=class&type!=import')
    canonical = answer(tree, 'ast', 'a.py', '--kind', 'function',
                       '--where', 'kind!=class', '--where', 'kind!=import')
    assert legacy == canonical and canonical['total_results'] == 2


def test_filter_codec_keeps_plus_literal_and_defaults_are_not_overrides(tree):
    a = answer(tree, 'ast', 'a.py', '--where', 'name~=^a+$')
    b = answer(tree, 'ast://a.py?where=name%7E%3D%5Ea+%24')
    assert a == b and a['total_results'] == 1


def test_repeated_where_and_per_call_overrides_are_isolated(tree):
    from reveal.api import query
    uri = f'ast://{tree / "a.py"}?where=lines%3E1&where=lines%3C4'
    assert query(uri)['total_results'] == 1
    assert query(uri, where=[])['total_results'] == 2
    assert query(uri)['total_results'] == 1
    with pytest.raises(TypeError, match='Unsupported'):
        query(uri, nonexistent_control=True)
