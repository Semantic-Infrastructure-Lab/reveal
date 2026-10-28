"""Controls for the installed-wheel smoke, without network installs in pytest."""

import json
import subprocess

import pytest

from scripts.default_install_smoke import (
    SmokeFailure,
    clean_environment,
    create_fixture,
    validate_overview,
)

pytestmark = pytest.mark.component


def _overview(*, code=0, warnings=None, errors=None):
    meta = {
        'warnings': warnings if warnings is not None else [
            {'type': 'git_unavailable', 'message': 'pygit2 missing; install reveal-cli[git]'},
        ],
        'errors': errors or [],
    }
    return subprocess.CompletedProcess(['reveal', 'overview', '.'], code,
                                       json.dumps({'meta': meta}), '')


def test_overview_accepts_disclosed_optional_dependency():
    validate_overview(_overview())


def test_overview_rejects_old_missing_pygit2_failure():
    result = _overview(code=3, warnings=[], errors=[{'code': 'E_COMPOSE', 'message': 'git_root failed'}])
    with pytest.raises(SmokeFailure, match='overview.*exit 3'):
        validate_overview(result)


@pytest.mark.parametrize('result, reason', [
    (_overview(warnings=[]), 'git_unavailable'),
    (_overview(warnings=[{'type': 'git_unavailable', 'message': 'missing'}]), 'install hint'),
    (_overview(errors=[{'code': 'E_COMPOSE', 'message': 'failed'}]), 'analysis errors'),
])
def test_overview_does_not_accept_silent_or_incomplete_answers(result, reason):
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


def test_fixture_has_real_callers_complexity_and_changes_since_main(tmp_path):
    root = tmp_path / 'fixture'
    create_fixture(root, clean_environment(tmp_path))
    changed = subprocess.run(['git', 'diff', '--name-only', 'main...HEAD'], cwd=root,
                             capture_output=True, text=True, encoding='utf-8', timeout=10,
                             check=True)
    assert changed.stdout.strip() == 'src/auth.py'
    assert 'validate_token(token)' in (root / 'src' / 'login.py').read_text(encoding='utf-8')
    assert (root / 'src' / 'complexity.py').read_text(encoding='utf-8').count('    if ') == 10
