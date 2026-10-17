"""Legacy spellings disclose their replacement without changing the answer."""

import json

import pytest

from conftest import _run_reveal_direct


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'sample.py'
    path.write_text('def auth_gate(value):\n    return value\n', encoding='utf-8')
    return path


@pytest.mark.parametrize('spelling', ['--search', '--search=auth'])
def test_search_alias_names_replacement_and_preserves_json(source, spelling):
    flags = [spelling, 'auth'] if spelling == '--search' else [spelling]
    legacy = _run_reveal_direct(source, *flags, '--format', 'json')
    current = _run_reveal_direct(source, '--name', 'auth', '--format', 'json')
    assert legacy.returncode == current.returncode == 0
    assert json.loads(legacy.stdout) == json.loads(current.stdout)
    assert 'deprecated' in legacy.stderr and '--name' in legacy.stderr
    assert 'deprecated' not in current.stderr


def test_file_check_alias_names_replacement_and_preserves_findings(source):
    legacy = _run_reveal_direct(source, '--check', '--select', 'B001', '--format', 'json')
    current = _run_reveal_direct('check', source, '--select', 'B001', '--format', 'json')
    assert legacy.returncode == current.returncode == 0
    assert json.loads(legacy.stdout) == json.loads(current.stdout)
    assert 'deprecated' in legacy.stderr and 'reveal check' in legacy.stderr
    assert 'deprecated' not in current.stderr


def test_uri_check_is_not_the_deprecated_file_alias():
    result = _run_reveal_direct('reveal://', '--check', '--select', 'V001', '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)
    assert 'deprecated' not in result.stderr
