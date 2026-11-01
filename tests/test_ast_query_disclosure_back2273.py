"""AST query echoes and absence hints describe the requested predicates."""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.ast.queries import format_query, parse_query


@pytest.mark.parametrize('query, expected', [
    ('complexity>0', 'complexity>0'),
    ('lines=1', 'lines==1'),
    ('depth<=1', 'depth<=1'),
    ('callers!=0', 'callers!=0'),
    ('lines>=0&lines<=1', 'lines>=0 AND lines<=1'),
])
def test_zero_one_query_literals_remain_numeric(query, expected):
    assert format_query(parse_query(query)) == expected


@pytest.mark.parametrize('literal, expected', [('true', True), ('false', False)])
def test_actual_boolean_literals_keep_their_meaning(literal, expected):
    parsed = parse_query(f'has_annotations={literal}')
    assert parsed['has_annotations']['value'] is expected
    assert format_query(parsed) == f'has_annotations=={expected}'


@pytest.mark.parametrize('query, expected', [('name~=1', 'name~=1'), ('name=1*', 'name=1* (glob)')])
def test_regex_and_glob_numeric_text_is_not_coerced(query, expected):
    parsed = parse_query(query)
    assert isinstance(parsed['name']['value'], str)
    assert format_query(parsed) == expected


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'example.py'
    path.write_text('VALUE = 1\n\ndef authenticate():\n    return VALUE\n\ndef typed(x: int) -> int:\n    return x\n', encoding='utf-8')
    return path


@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_cli_echoes_numeric_predicate_without_changing_matches(source, output_format):
    result = run(f'ast://{source}?type=function&complexity>0', '--format', output_format)
    assert result.returncode == 0, result.stderr
    assert 'complexity>0' in result.stdout
    assert 'complexity>False' not in result.stdout
    if output_format == 'json':
        answer = json.loads(result.stdout)
        assert {row['name'] for row in answer['results']} == {'authenticate', 'typed'}


def test_combined_predicate_zero_does_not_claim_existing_name_is_absent(source):
    result = run(f'ast://{source}?name~=authenticate&type=function&complexity>10')
    assert result.returncode == 0, result.stderr
    assert 'No matches found.' in result.stdout
    assert 'not a named code element' not in result.stdout
    assert 'reveal_type=authenticate' not in result.stdout


def test_sole_name_query_keeps_variable_hint(source):
    result = run(f'ast://{source}?name=VALUE')
    assert result.returncode == 0, result.stderr
    assert 'not a named code element' in result.stdout
    assert 'reveal_type=VALUE' in result.stdout
