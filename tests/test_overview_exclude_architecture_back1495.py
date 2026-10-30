"""Overview map and census share explicit exclusions in both spellings."""
import json

import pytest

from conftest import _run_reveal_direct as run


@pytest.fixture
def tree(tmp_path):
    for name in ('a,b.py', 'c.py', 'd.py'):
        (tmp_path / name).write_text('VALUE=1\n', encoding='utf-8')
    (tmp_path / 'e.min.js').write_text('const value=1;\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('form', ['subcommand', 'uri_flag', 'uri_query'])
def test_excluded_file_leaves_census_and_component_population(tree, form):
    args = {'subcommand': ['overview', str(tree), '--exclude', 'c.py'],
            'uri_flag': [f'overview://{tree}', '--exclude', 'c.py'],
            'uri_query': [f'overview://{tree}?exclude=c.py']}[form]
    result = run(*args, '--format', 'json')
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body['scope']['total_code_files'] == 3
    assert sum(row['files'] for row in body['map']['components']['rows']) == 3
    assert body['map']['metadata']['scanned_files'] == 3


@pytest.mark.parametrize('pattern', ['a,b.py', '*.min.js'])
def test_literal_comma_and_glob_preserve_exclusion_policy(tree, pattern):
    result = run('overview', tree, '--exclude', pattern, '--format', 'json')
    assert result.returncode == 0
    body = json.loads(result.stdout)
    assert body['scope']['total_code_files'] == body['map']['metadata']['scanned_files'] == 3


def test_zero_import_files_still_count_in_scope_and_components(tree):
    body = json.loads(run('overview', tree, '--format', 'json').stdout)
    assert body['scope']['total_code_files'] == 4
    assert body['map']['fan_in']['total'] == 0
    assert sum(row['files'] for row in body['map']['components']['rows']) == 4
