"""Controls for the installed-wheel smoke, without network installs in pytest."""

import json
import subprocess

import pytest

from scripts.default_install_smoke import (
    SmokeFailure,
    clean_environment,
    create_fixture,
    readme_commands,
    validate_overview,
    validate_queries,
)

pytestmark = pytest.mark.component


def _overview(*, code=0, errors=None, **overrides):
    answer = {
        'scope': {'complete': True, 'total_code_files': 3},
        'map_status': 'complete',
        'map': {
            'metadata': {'scanned_files': 3},
            'fan_in': {'rows': [{'file': 'src/auth.py', 'fan_in': 1, 'fan_out': 0}]},
            'entrypoints': {'rows': [{'file': 'src/login.py', 'fan_out': 1}]},
        },
        'meta': {'errors': errors or []},
    }
    answer.update(overrides)
    return subprocess.CompletedProcess(['reveal', 'overview', '.'], code, json.dumps(answer), '')


def test_overview_accepts_complete_core_only_map():
    validate_overview(_overview())


def test_overview_rejects_old_missing_pygit2_failure():
    result = _overview(code=3, errors=[{'code': 'E_COMPOSE', 'message': 'git_root failed'}])
    with pytest.raises(SmokeFailure, match='overview.*exit 3'):
        validate_overview(result)


@pytest.mark.parametrize('overrides, reason', [
    ({'scope': {}}, 'code scope'),
    ({'scope': {'complete': False, 'total_code_files': 3}}, 'code scope'),
    ({'map': None}, 'import map'),
    ({'map_status': 'incomplete'}, 'import map'),
    ({'errors': [{'code': 'E_COMPOSE', 'message': 'failed'}]}, 'analysis errors'),
])
def test_overview_does_not_accept_silent_or_incomplete_answers(overrides, reason):
    with pytest.raises(SmokeFailure, match=reason):
        validate_overview(_overview(**overrides))


@pytest.mark.parametrize('section, reason', [('fan_in', 'auth import'), ('entrypoints', 'login entrypoint')])
def test_overview_requires_real_fixture_relationships(section, reason):
    result = _overview()
    answer = json.loads(result.stdout)
    answer['map'][section]['rows'] = []
    result.stdout = json.dumps(answer)
    with pytest.raises(SmokeFailure, match=reason):
        validate_overview(result)


def test_environment_removes_source_and_user_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv('PYTHONPATH', str(tmp_path / 'source'))
    monkeypatch.setenv('PYTHONHOME', str(tmp_path / 'another-python'))
    monkeypatch.setenv('REVEAL_C901_THRESHOLD', '999')
    monkeypatch.setenv('REVEAL_CONFIG', str(tmp_path / 'foreign-config'))
    env = clean_environment(tmp_path)
    assert 'PYTHONPATH' not in env and 'PYTHONHOME' not in env
    assert 'REVEAL_C901_THRESHOLD' not in env and 'REVEAL_CONFIG' not in env
    assert env['PYTHONNOUSERSITE'] == '1'
    assert env['REVEAL_DISK_CACHE'] == '0'
    assert env['XDG_CONFIG_HOME'] == str(tmp_path / 'config')


def test_readme_commands_preserve_quoted_uri_and_drop_comments(tmp_path):
    readme = tmp_path / 'README.md'
    readme.write_text('# Example\n```bash\nreveal \'ast://src/?complexity>10\' # a question\n'
                      'reveal check src/\n```\n', encoding='utf-8')
    assert readme_commands(readme) == [('ast://src/?complexity>10',), ('check', 'src/')]


def test_readme_with_no_examples_is_not_a_passing_empty_smoke(tmp_path):
    readme = tmp_path / 'README.md'
    readme.write_text('# No examples\n', encoding='utf-8')
    with pytest.raises(SmokeFailure, match='no first-screen'):
        readme_commands(readme)


@pytest.mark.parametrize('wrong', [None, 'calls', 'ast'])
def test_queries_require_the_expected_answers(wrong):
    calls = {'total_callers': 1, 'levels': [{'callers': [
        {'file': 'src/login.py', 'caller': 'run_login'},
    ]}]}
    ast = {'total_results': 1, 'results': [
        {'file': 'src/complexity.py', 'name': 'classify', 'complexity': 11},
    ]}
    if wrong == 'calls':
        calls['levels'][0]['callers'] = []
    if wrong == 'ast':
        ast['results'][0]['complexity'] = 1
    if wrong:
        with pytest.raises(SmokeFailure, match=wrong):
            validate_queries(calls, ast)
    else:
        validate_queries(calls, ast)


def test_fixture_has_real_callers_complexity_and_changes_since_main(tmp_path):
    root = tmp_path / 'fixture'
    create_fixture(root, clean_environment(tmp_path))
    changed = subprocess.run(['git', 'diff', '--name-only', 'main...HEAD'], cwd=root,
                             capture_output=True, text=True, encoding='utf-8', timeout=10,
                             check=True)
    assert changed.stdout.strip() == 'src/auth.py'
    assert 'validate_token(token)' in (root / 'src' / 'login.py').read_text(encoding='utf-8')
    assert (root / 'src' / 'complexity.py').read_text(encoding='utf-8').count('    if ') == 10
