"""Independent direct JSON root execution and actual SDK consumer contracts."""
import builtins
import errno
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from conftest import without_request_notes
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
def test_introspection_stays_legacy_while_navigation_qualifies(tmp_path, suffix):
    path = tmp_path / 'legacy.json'
    path.write_text('{"answer":42}', encoding='utf-8')
    uri = f'json://{path.as_posix()}{suffix}'
    response = run(uri, '--format', 'json')
    assert response.returncode == 0
    assert without_request_notes(json.loads(response.stdout)) == without_request_notes(api.query(uri))  # each in its own form (BACK-2716)
    path.unlink()
    missing = run(uri, '--format', 'json')
    assert missing.returncode == 2  # a missing path is an invalid resource in every mode (BACK-2533)


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [False, True])
def test_actual_sdk_root_parse_read_refusal_privacy_and_repair(tmp_path, provenance):
    path = tmp_path / 'root.json'
    path.write_text('{"answer":42}', encoding='utf-8')
    (tmp_path / 'output.json').write_text('{"answer":44}', encoding='utf-8')
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
from reveal.adapters.json.renderer import JsonRenderer
from reveal.utils import json_utils
original_render = JsonRenderer.render_structure
original_json = json_utils.print_json_result

def render(result, *args, **kwargs):
    if Path(result.get('file', result.get('source', ''))).name == 'output.json':
        raise PermissionError(errno.EACCES, 'PUBLIC_JSON_OUTPUT_DENIED')
    return original_render(result, *args, **kwargs)

def json_render(result, *args, **kwargs):
    if Path(result.get('file', result.get('source', ''))).name == 'output.json':
        raise PermissionError(errno.EACCES, 'PUBLIC_JSON_OUTPUT_DENIED')
    return original_json(result, *args, **kwargs)

JsonRenderer.render_structure = staticmethod(render)
json_utils.print_json_result = json_render
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
        output = await request(f'json://{(tmp_path / "output.json").as_posix()}')
        assert output.is_error and 'PUBLIC_JSON_OUTPUT_DENIED' in _text(output)
        path.unlink()
        missing = await request()
        assert missing.is_error and _text(missing).strip()

    _run(tmp_path, scenario, code)


def test_element_and_check_keep_legacy_policy_and_stdin_answers_like_the_request(tmp_path):
    from conftest import _run_reveal_in
    path = tmp_path / 'excluded.json'
    path.write_text('{"answer":42}', encoding='utf-8')
    uri = f'json://{path.as_posix()}'
    # The element is named in the URI; api.query's element_name is refused on a declared noun (BACK-2687).
    keyed = api.query(f'{uri}/answer')
    assert (keyed['type'], keyed['path'], keyed['value_type'], keyed['value']) == ('json_value', 'answer', 'int', 42)
    # --check never changed a JSON answer: a note-stage legacy modifier since BACK-2673 (BACK-2708 ruling 2), noted
    # once instead of named unused, answering as without it.
    checked = run(uri, '--check', '--format', 'json')
    assert checked.returncode == 0, checked.stderr
    warnings = json.loads(checked.stdout)['meta']['warnings']
    assert not [w for w in warnings if w['type'] == 'unused_flag']
    assert [w['field'] for w in warnings if w['type'] == 'retired_spelling'] == ['flag:json.--check']
    assert 'has no effect' not in checked.stderr
    checked_text = run(uri, '--check')
    assert checked_text.returncode == 0
    assert checked_text.stderr.count('note: json --check is deprecated') == 1
    path.write_text('{INVALID', encoding='utf-8')
    # A positional element on json:// was never read; it is refused before the file is (BACK-2522).
    assert run(uri, 'answer', '--format', 'json').returncode == 2
    failed = run(uri, '--check', '--format', 'json')
    direct = run(uri, '--format', 'json')
    assert failed.returncode == direct.returncode  # --check changes nothing, a failed read included
    batch = _run_reveal_in(tmp_path, '--stdin', '--format', 'json', stdin=uri + '\n')
    assert batch.returncode == direct.returncode == 3  # a --stdin line is the direct request (BACK-2325)
    assert json.loads(batch.stdout)['error']
    path.unlink()
    missing = run(uri, '--check', '--format', 'json')
    assert missing.returncode == 2  # BACK-2533: a missing path exits 2 before --check is considered
    assert 'excluded.json' in missing.stdout + missing.stderr
