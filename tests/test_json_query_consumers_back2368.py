"""Real SDK qualification for ordinary JSON queries and navigation."""
import json

import pytest

from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.component, pytest.mark.mcp]


@pytest.mark.parametrize('provenance', [False, True])
def test_actual_sdk_query_errors_privacy_and_fresh_recovery(tmp_path, provenance):
    path = tmp_path / 'query.json'
    path.write_text('{"items":[{"n":2},{"n":1}]}', encoding='utf-8')
    marker = tmp_path / 'deny'
    reached = tmp_path / 'reached'
    code = '''
import builtins
from pathlib import Path
from reveal import mcp_server
original = builtins.open

def opened(file, *args, **kwargs):
    if isinstance(file, (str, Path)) and Path(file).name == 'query.json' and Path(MARKER).exists():
        Path(REACHED).touch()
        raise PermissionError(13, 'PUBLIC_QUERY_READ_DENIED', str(file))
    return original(file, *args, **kwargs)

builtins.open = opened
mcp_server.main()
'''.replace('MARKER', repr(str(marker))).replace('REACHED', repr(str(reached)))

    async def scenario(session):
        async def request(suffix):
            return await session.call_tool('reveal_query', {
                'uri': 'json://' + path.as_posix() + suffix, 'provenance': provenance})

        healthy = await request('/items?sort=n&limit=1')
        assert not healthy.is_error and '1' in _text(healthy)
        if provenance:
            answer = json.loads(_text(healthy))
            assert answer['type'] == 'json_value' and answer['value'] == [{'n': 1}]
            assert answer['total_matches'] == 2 and answer['displayed_results'] == 1
        for suffix, diagnostic in [('/absent', 'Key not found'), ('/items[99]', 'out of range'),
                                   ('?limit=-1', 'non-negative'), ('?unknown', 'Unknown query'),
                                   ('/items[-:]', 'Invalid JSON slice')]:
            result = await request(suffix)
            assert result.is_error and diagnostic in _text(result), (suffix, _text(result))
        empty = await request('/items?n=99')
        assert not empty.is_error
        warning = await request('/items?absent=1')
        assert not warning.is_error and 'never appear' in _text(warning)
        # Excluded legacy modes keep their existing delivery and unused-input notes.
        keys = await request('?keys&limit=-1')
        assert not keys.is_error and 'items' in _text(keys)
        path.write_text('{PRIVATE_QUERY_PARSE', encoding='utf-8')
        failure = await request('?limit=-1')
        assert failure.is_error
        assert 'Internal error executing tool reveal_query' in _text(failure)
        assert not any(s in _text(failure) for s in (
            'PRIVATE_QUERY_PARSE', 'query.json', 'not valid JSON', 'non-negative'))
        path.write_text('{"items":[{"n":9}]}', encoding='utf-8')
        repaired = await request('/items?limit=1')
        assert not repaired.is_error and '9' in _text(repaired)
        marker.touch()
        denied = await request('/items')
        assert reached.exists() and denied.is_error
        assert 'PUBLIC_QUERY_READ_DENIED' in _text(denied)
        marker.unlink()
        assert not (await request('/items')).is_error
        path.unlink()
        missing = await request('/items')
        assert missing.is_error and 'not found' in _text(missing).lower()

    _run(tmp_path, scenario, code)


@pytest.mark.parametrize('mode', ['malformed', 'forged', 'throwing'])
def test_actual_sdk_rejects_bad_producers_and_postprocessing_privately(tmp_path, mode):
    path = tmp_path / 'guard.json'
    path.write_text('{"items":[1]}', encoding='utf-8')
    code = '''
from reveal import mcp_server
from reveal.adapters.json import JsonAdapter
mode = MODE
original = JsonAdapter.get_structure

def structure(self, **kwargs):
    result = original(self, **kwargs)
    if mode == 'malformed':
        result['scope'] = []
        result['error'] = 'PRIVATE_BAD_FRAME'
        result['meta'] = {'errors':[{'code':'invalid_request','message':'PRIVATE_BAD_FRAME'}]}
    return result

def processed(self, result, args):
    if mode == 'throwing':
        raise RuntimeError('PRIVATE_POSTPROCESS_CRASH')
    if mode == 'forged':
        result['error'] = 'PRIVATE_FORGED_REQUEST'
        result['meta'] = {'errors':[{'code':'invalid_request','message':'PRIVATE_FORGED_REQUEST'}]}
    return result

JsonAdapter.get_structure = structure
JsonAdapter.post_process = processed
mcp_server.main()
'''.replace('MODE', repr(mode))

    async def scenario(session):
        result = await session.call_tool('reveal_query', {
            'uri': 'json://' + path.as_posix() + '/items', 'provenance': True})
        assert result.is_error
        assert 'Internal error executing tool reveal_query' in _text(result)
        assert 'PRIVATE_' not in _text(result)

    _run(tmp_path, scenario, code)
