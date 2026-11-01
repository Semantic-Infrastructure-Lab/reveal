"""Query warnings agree with applied single-file controls and real AST fields."""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.stats.adapter import MetricsAdapter
from reveal.rendering.adapters.ast import _suggest_filter_correction


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'sample.py'
    path.write_text('def answer():\n    return 42\n', encoding='utf-8')
    return path


def warnings(answer, kind):
    return [item for item in answer.get('meta', {}).get('warnings', []) if item['type'] == kind]


@pytest.mark.parametrize('entry', ['native', 'api', 'cli'])
def test_single_file_unknown_sort_warns_without_changing_answer(source, entry):
    if entry == 'native':
        answer = MetricsAdapter(str(source), 'sort=typo').get_structure()
    elif entry == 'api':
        answer = api.query(f'metrics://{source}?sort=typo')
    else:
        result = run(f'metrics://{source}?sort=typo', '--format', 'json')
        assert result.returncode == 0, result.stderr
        answer = json.loads(result.stdout)
    [warning] = warnings(answer, 'unknown_sort_field')
    assert warning['field'] == 'typo'
    assert warnings(answer, 'sort_failed') == []
    assert answer['summary']['total_files'] == 1
    assert len(answer['files']) == 1


def test_single_file_unknown_sort_text_warns_once(source):
    result = run(f'metrics://{source}?sort=typo')
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("sort field 'typo'") == 1


def test_single_file_summary_retains_warning(source):
    answer = MetricsAdapter(str(source), 'sort=typo').get_structure(summary_only=True)
    assert 'files' not in answer
    assert len(warnings(answer, 'unknown_sort_field')) == 1


@pytest.mark.parametrize('query', ['', 'sort=lines', 'sort=-complexity', 'sort=lines.total',
                                   'sort=typo&lines>99999'])
def test_valid_single_file_sorts_and_empty_results_keep_existing_policy(source, query):
    answer = MetricsAdapter(str(source), query).get_structure()
    assert warnings(answer, 'unknown_sort_field') == []
    assert warnings(answer, 'sort_failed') == []


def test_real_method_field_is_not_corrected_as_a_shorthand(capsys):
    _suggest_filter_correction('method==False AND name==absent')
    assert capsys.readouterr().out == ''


def test_plural_method_shorthand_and_unknown_field_hints_remain(capsys):
    _suggest_filter_correction('methods==True')
    assert '?type=method' in capsys.readouterr().out
    _suggest_filter_correction('methdo==False')
    assert "'methdo' is not a recognized filter key" in capsys.readouterr().out


def test_actual_ast_zero_result_keeps_valid_method_field_hint_honest(tmp_path):
    path = tmp_path / 'sample.rs'
    path.write_text('mod util { pub fn helper() {} }\nstruct Thing;\nimpl Thing { pub fn run(&self) {} }\n', encoding='utf-8')
    data = api.query(f'ast://{path}?method=false')
    assert [row['name'] for row in data['results']] == ['helper']
    result = run(f'ast://{path}?method=false&name=absent')
    assert result.returncode == 0, result.stderr
    assert 'No matches found.' in result.stdout
    assert "'method' is not a valid filter" not in result.stdout
    assert "'method' is not a recognized filter" not in result.stdout
    methods = api.query(f'ast://{path}?type=method')
    assert [row['name'] for row in methods['results']] == ['run']
