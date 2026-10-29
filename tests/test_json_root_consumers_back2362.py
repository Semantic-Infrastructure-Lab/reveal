"""Independent direct JSON root execution and actual SDK consumer contracts."""
import builtins
import errno
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = pytest.mark.component


@pytest.mark.parametrize('value', [{'answer': 42}, [], {}, None])
def test_healthy_empty_and_null_roots_keep_complete_json_value(tmp_path, value):
    path = tmp_path / 'value.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    uri = f'json://{path.as_posix()}'
    result = api.query(uri)
    response = run(uri, '--format', 'json')
    assert response.returncode == 0
    answer = json.loads(response.stdout)
    assert answer == result and answer['type'] == 'json_value'
    assert answer['value'] == value


@pytest.mark.parametrize('case,expected', [('parse', 3), ('missing', 2), ('directory', 2)])
def test_root_failures_keep_authored_cli_diagnostic_and_expected_exit(tmp_path, case, expected):
    path = tmp_path / 'bad.json'
    if case == 'parse':
        path.write_text('{PRIVATE_BROKEN_JSON', encoding='utf-8')
    elif case == 'directory':
        path.mkdir()
    response = run(f'json://{path.as_posix()}', '--format', 'json')
    assert response.returncode == expected, (response.stdout, response.stderr)
    answer = json.loads(response.stdout)
    assert answer['type'] == 'json_value' and answer['error']
    diagnostic = response.stdout + response.stderr
    expected_text = {'parse': 'not valid JSON', 'missing': 'not found', 'directory': 'file'}[case]
    assert expected_text.lower() in diagnostic.lower()
    exception = FileNotFoundError if case == 'missing' else ValueError
    with pytest.raises(exception):
        api.query(f'json://{path.as_posix()}')


def test_required_read_denial_is_reached_and_repair_and_output_keep_policy(tmp_path, monkeypatch):
    path = tmp_path / 'denied.json'
    path.write_text('{"answer":42}', encoding='utf-8')
    uri = f'json://{path.as_posix()}'
    original = builtins.open
    attempts = []
    def opened(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file).resolve() == path.resolve():
            attempts.append(str(file))
            raise PermissionError(errno.EACCES, 'PUBLIC_JSON_READ_DENIED', str(file))
        return original(file, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', opened)
        response = run(uri, '--format', 'json')
        assert attempts
        assert response.returncode == 3, (response.stdout, response.stderr)
        assert json.loads(response.stdout)['type'] == 'json_value'
        assert 'PUBLIC_JSON_READ_DENIED' in response.stdout + response.stderr
        with pytest.raises(PermissionError):
            api.query(uri)
    clean = api.query(uri)
    assert clean['value'] == {'answer': 42}
    artifact = tmp_path / 'answer.json'
    response = run(uri, '--output', f'json={artifact}')
    assert response.returncode == 0
    assert json.loads(artifact.read_text(encoding='utf-8'))['value'] == clean['value']
    output = run(uri, '--output', f'json={tmp_path}')
    assert output.returncode == 3
    path.write_text('{"answer":99}', encoding='utf-8')
    assert api.query(uri)['value'] == {'answer': 99}


@pytest.mark.parametrize('suffix', ['?keys', '/answer', '?length'])
def test_legacy_query_navigation_and_missing_resource_exits_are_preserved(tmp_path, suffix):
    path = tmp_path / 'legacy.json'
    path.write_text('{"answer":42}', encoding='utf-8')
    uri = f'json://{path.as_posix()}{suffix}'
    response = run(uri, '--format', 'json')
    assert response.returncode == 0
    assert json.loads(response.stdout) == api.query(uri)
    path.unlink()
    missing = run(uri, '--format', 'json')
    assert missing.returncode == 1  # excluded legacy route; preflight wording may change


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [False, True])
def test_actual_sdk_root_parse_read_refusal_privacy_and_repair(tmp_path, provenance):
    path = tmp_path / 'root.json'
    path.write_text('{"answer":42}', encoding='utf-8')
    marker = tmp_path / 'deny-reader'
    reached = tmp_path / 'reader-reached'
    code = '''
import builtins
import errno
from pathlib import Path
from reveal import mcp_server
original = builtins.open

def opened(file, *args, **kwargs):
    if isinstance(file, (str, Path)) and Path(file).name == 'root.json' and Path(MARKER).exists():
        Path(REACHED).touch()
        raise PermissionError(errno.EACCES, 'PUBLIC_JSON_READER_DENIED', str(file))
    return original(file, *args, **kwargs)

builtins.open = opened
mcp_server.main()
'''.replace('MARKER', repr(str(marker))).replace('REACHED', repr(str(reached)))

    async def scenario(session):
        async def request(uri=None):
            return await session.call_tool('reveal_query', {
                'uri': uri or f'json://{path.as_posix()}', 'provenance': provenance})
        healthy = await request()
        assert not healthy.is_error and '42' in _text(healthy)
        if provenance:
            answer = json.loads(_text(healthy))
            assert answer['type'] == 'json_value' and answer['value'] == {'answer': 42}
        path.write_text('{PRIVATE_JSON_PARSE', encoding='utf-8')
        malformed = await request()
        assert malformed.is_error, _text(malformed)
        masked = _text(malformed)
        assert 'Internal error executing tool reveal_query' in masked
        assert not any(detail in masked for detail in ('PRIVATE_JSON_PARSE', 'not valid JSON', 'Parse error', 'root.json'))
        path.write_text('{"answer":43}', encoding='utf-8')
        repaired = await request()
        assert not repaired.is_error and '43' in _text(repaired)
        marker.touch()
        denied = await request()
        assert reached.exists()
        assert denied.is_error and _text(denied).strip()
        marker.unlink()
        restored = await request()
        assert not restored.is_error and '43' in _text(restored)
        if provenance:
            assert json.loads(_text(restored))['value'] == {'answer': 43}
        path.unlink()
        missing = await request()
        assert missing.is_error and _text(missing).strip()

    _run(tmp_path, scenario, code)


def test_element_check_and_stdin_batch_keep_legacy_policy(tmp_path):
    from conftest import _run_reveal_in
    path = tmp_path / 'excluded.json'
    path.write_text('{"answer":42}', encoding='utf-8')
    uri = f'json://{path.as_posix()}'
    assert api.query(uri, element_name='answer') == {'name': 'answer', 'value': 42, 'type': 'int'}
    checked = run(uri, '--check', '--format', 'json')
    assert checked.returncode == 0 and 'has no effect' in checked.stderr
    path.write_text('{INVALID', encoding='utf-8')
    for tail in [('answer',), ('--check',)]:
        failed = run(uri, *tail, '--format', 'json')
        assert failed.returncode == 1
    batch = _run_reveal_in(tmp_path, '--stdin', '--format', 'json', stdin=uri + '\n')
    assert batch.returncode == 1
    assert json.loads(batch.stdout)['error']
    path.unlink()
    for tail in [('answer',), ('--check',)]:
        missing = run(uri, *tail, '--format', 'json')
        assert missing.returncode == 1
        assert 'excluded.json' in missing.stdout + missing.stderr
