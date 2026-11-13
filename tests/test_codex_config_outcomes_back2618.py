"""Codex TOML acquisition and masked key observations retain truthful outcomes."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal import query
from test_codex_declared_api_back2618 import codex


@pytest.mark.parametrize('state,exit_code', [('healthy', 0), ('empty', 0), ('missing', 2), ('malformed', 3), ('decode', 3), ('directory', 3)])
def test_configuration_source_outcomes(codex, state, exit_code):
    path = codex / 'config.toml'
    if state == 'empty':
        path.write_bytes(b'')
    elif state == 'missing':
        path.unlink()
    elif state == 'malformed':
        path.write_bytes(b'model = = broken\n')
    elif state == 'decode':
        path.write_bytes(b'model = "\xff"\n')
    elif state == 'directory':
        path.unlink()
        path.mkdir()
    result = _run_reveal_in(codex.parent, 'codex://config', '--format', 'json')
    assert result.returncode == exit_code
    proof = json.loads(result.stdout)['meta']['installation_analysis']
    assert proof['source'] == path.as_posix()
    assert proof['request_rejected'] == (state == 'missing')
    assert bool(proof['failed_operations']) == (state in ('malformed', 'decode', 'directory'))


@pytest.mark.parametrize('key,value,exit_code', [('enabled', False, 0), ('budget', 0, 0), ('empty', '', 0), ('absent', None, 2)])
def test_key_presence_is_distinct_from_falsy_value(codex, key, value, exit_code):
    (codex / 'config.toml').write_text('enabled = false\nbudget = 0\nempty = ""\n', encoding='utf-8')
    result = _run_reveal_in(codex.parent, 'codex://config?key=' + key, '--format', 'json')
    assert result.returncode == exit_code
    answer = json.loads(result.stdout)
    assert answer['value'] == value and type(answer['value']) is type(value)
    native = query('codex://config?key=' + key)
    assert native['value'] == value and 'error' not in native
    if key == 'absent':
        assert 'absent' in answer['error']
    else:
        assert 'error' not in answer
    assert answer['meta']['installation_analysis']['request_rejected'] == (key == 'absent')


def test_configuration_metadata_denial_is_not_missing_input(codex, monkeypatch):
    path = codex / 'config.toml'
    original = Path.stat
    def stat(self, *args, **kwargs):
        if self == path:
            raise PermissionError('config metadata denied')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    answer = query('codex://config')
    proof = answer['meta']['installation_analysis']
    assert not proof['request_rejected'] and proof['failed_operations'] == 1
    assert proof['operations'][0]['phase'] == 'select'


@pytest.mark.parametrize('field', ['receipt', 'source', 'value', 'key'])
def test_masked_configuration_observations_survive_presentation(codex, monkeypatch, field):
    from reveal.adapters.codex.adapter import CodexAdapter
    (codex / 'config.toml').write_text('enabled = false\n', encoding='utf-8')
    def corrupt(self, result, args):
        if field == 'receipt':
            result['meta'].pop('installation_analysis', None)
        else:
            result[field] = 'changed'
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://config?key=enabled', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_masking_precedes_key_observation_and_receipts_do_not_copy_secrets(codex):
    marker = 'sk-FAKE-CONFIG-SECRET-UNIQUE'
    (codex / 'config.toml').write_text('api_key = "' + marker + '"\n', encoding='utf-8')
    answer = query('codex://config?key=api_key')
    assert marker not in json.dumps(answer)
    assert answer['value'] and answer['value'] != marker
    assert answer['meta']['installation_analysis']['usable']


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_configuration_missing_key_failed_source_and_repaired_value(codex, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    path = codex / 'config.toml'
    path.write_text('enabled = false\n', encoding='utf-8')
    monkeypatch.setenv('REVEAL_CODEX_HOME', str(codex))
    monkeypatch.setenv('REVEAL_CODEX_DB', str(codex / 'state_5.sqlite'))
    async def scenario(session):
        request = {'uri': 'codex://config?key=enabled', 'provenance': True}
        first = await session.call_tool('reveal_query', request)
        assert not first.is_error, _text(first)
        assert json.loads(_text(first))['value'] is False
        missing = await session.call_tool('reveal_query', {'uri': 'codex://config?key=absent', 'provenance': True})
        assert missing.is_error and 'absent' in _text(missing)
        path.write_bytes(b'broken = =\n')
        assert (await session.call_tool('reveal_query', request)).is_error
        path.write_text('enabled = false\n', encoding='utf-8')
        repaired = await session.call_tool('reveal_query', request)
        assert not repaired.is_error, _text(repaired)
        assert json.loads(_text(repaired))['value'] is False
    _run(codex.parent, scenario)


@pytest.mark.parametrize('key', ['', '?key=enabled', '?key=absent'])
def test_parsed_config_survives_close_loss_after_masking(codex, monkeypatch, key):
    import io
    import reveal.adapters.codex.handlers.system as module
    class Stream:
        def __enter__(self): return io.BytesIO(b'enabled = false\napi_key = "sk-FAKE-CLOSE-SECRET"\n')
        def __exit__(self, *args): raise OSError('config close interrupted')
    monkeypatch.setattr(module, 'open', lambda *args, **kwargs: Stream(), raising=False)
    result = _run_reveal_in(codex.parent, 'codex://config' + key, '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert 'FAKE-CLOSE-SECRET' not in result.stdout
    proof = answer['meta']['installation_analysis']
    assert proof['parsed'] and proof['usable'] and proof['failed_operations'] == 1
    assert proof['operations'][1]['phase'] == 'load'
    if key:
        assert answer['value'] is (None if 'absent' in key else False)
    else:
        assert answer['config']['enabled'] is False


def test_repeated_config_read_refreshes_source_and_key_decisions(codex):
    from reveal.adapters.codex.adapter import CodexAdapter
    path = codex / 'config.toml'
    adapter = CodexAdapter('config', query='key=enabled')
    assert adapter.get_structure()['value'] is None
    path.write_bytes(b'broken = =\n')
    assert adapter.get_structure()['meta']['installation_analysis']['failed_operations'] == 1
    path.write_text('enabled = false\n', encoding='utf-8')
    result = adapter.get_structure()
    assert result['value'] is False
    assert not result['meta']['installation_analysis']['request_rejected']


def test_api_key_overrides_stay_literal_and_none_restores_whole_config(codex):
    key = 'a&b=%26+雪'
    (codex / 'config.toml').write_text(json.dumps(key, ensure_ascii=False) + ' = false\n', encoding='utf-8')
    assert query('codex://config?key=absent', key=key)['value'] is False
    whole = query('codex://config?key=absent', key=None)
    assert whole['config'][key] is False and 'key' not in whole
    assert not whole['meta']['installation_analysis']['request_rejected']


def test_nested_boolean_cannot_be_replaced_by_equal_integer(codex, monkeypatch):
    from reveal.adapters.codex.adapter import CodexAdapter
    (codex / 'config.toml').write_text('enabled = false\n', encoding='utf-8')
    def corrupt(self, result, args):
        result['config']['enabled'] = 0
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://config', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.parametrize('key', ['', '?key=unknown_number', '?key=when'])
def test_valid_toml_nan_and_datetime_keep_native_observations(codex, key):
    import datetime
    import math
    (codex / 'config.toml').write_text('unknown_number = nan\nwhen = 2026-11-12T12:00:00Z\n', encoding='utf-8')
    native = query('codex://config' + key)
    if key == '?key=unknown_number':
        assert math.isnan(native['value'])
    elif key == '?key=when':
        assert isinstance(native['value'], datetime.datetime)
    result = _run_reveal_in(codex.parent, 'codex://config' + key, '--format', 'json')
    assert result.returncode == 0


def test_configuration_output_failure_is_exit_three(codex, tmp_path):
    result = _run_reveal_in(codex.parent, 'codex://config', '--output', 'json=' + str(tmp_path / 'absent' / 'config.json'))
    assert result.returncode == 3
