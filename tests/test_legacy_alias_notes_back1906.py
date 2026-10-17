"""Legacy spellings disclose their replacement without changing the answer."""

import json
from io import StringIO

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


@pytest.mark.parametrize('has_issue', [False, True])
def test_file_check_alias_names_replacement_and_preserves_findings(source, has_issue):
    if has_issue:
        source.write_text('try:\n    work()\nexcept:\n    pass\n', encoding='utf-8')
    legacy = _run_reveal_direct(source, '--check', '--select', 'B001', '--format', 'json')
    current = _run_reveal_direct('check', source, '--select', 'B001', '--format', 'json')
    assert legacy.returncode == current.returncode == int(has_issue)
    assert json.loads(legacy.stdout) == json.loads(current.stdout)
    if has_issue:
        assert 'B001' in legacy.stdout
    assert 'deprecated' in legacy.stderr and 'reveal check' in legacy.stderr
    assert 'deprecated' not in current.stderr


def test_uri_check_is_not_the_deprecated_file_alias():
    result = _run_reveal_direct('reveal://', '--check', '--select', 'V001', '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)
    assert 'deprecated' not in result.stderr


@pytest.mark.parametrize('degraded', [False, True])
def test_stdin_check_keeps_required_batch_spelling(source, monkeypatch, degraded):
    other = source.parent / 'other.py'
    other.write_text('def broken(:\n' if degraded else 'value = 1\n', encoding='utf-8')
    monkeypatch.setattr('sys.stdin', StringIO(f'{source}\n{other}\n'))
    result = _run_reveal_direct('--stdin', '--check', '--select', 'B001', '--format', 'json')
    assert result.returncode == (3 if degraded else 0)
    decoder = json.JSONDecoder()
    remaining = result.stdout.lstrip()
    payloads = []
    while remaining:
        payload, end = decoder.raw_decode(remaining)
        payloads.append(payload)
        remaining = remaining[end:].lstrip()
    assert len(payloads) == 2
    assert all(p['type'] == 'check' for p in payloads)
    assert {p['source'].replace('\\', '/').rsplit('/', 1)[-1] for p in payloads} == {
        'sample.py', 'other.py'}
    assert 'deprecated' not in result.stderr
