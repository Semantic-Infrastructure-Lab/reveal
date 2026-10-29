"""Real registered MCP queries return the compact map and retain loss outcomes."""
import json
from urllib.parse import quote

import pytest

pytest.importorskip('mcp')
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]


def project(root):
    root.mkdir()
    (root / 'a.py').write_text('from b import value\n', encoding='utf-8')
    (root / 'b.py').write_text('value = 1\n', encoding='utf-8')
    (root / 'c.py').write_text('from b import value\n', encoding='utf-8')
    return 'overview://' + quote(root.as_posix(), safe='/.:' )


def test_registered_stdio_text_json_top_zero_and_scope_only(tmp_path):
    uri = project(tmp_path / 'space & percent% project')
    async def scenario(session):
        result = await session.call_tool('reveal_query', {'uri': uri, 'provenance': True})
        assert not result.is_error, _text(result)
        body = json.loads(_text(result))
        assert body['type'] == 'overview' and body['map_status'] == 'complete'
        assert body['map']['fan_in']['rows'] == [{'file': 'b.py', 'fan_in': 2, 'fan_out': 0}]
        assert body['scope']['total_code_files'] == 3
        assert not {'stats', 'git_log', 'complex_functions'} & body.keys()
        assert body['execution']['command']
        zero = await session.call_tool('reveal_query', {'uri': uri + '?top=0', 'provenance': True})
        assert not zero.is_error
        assert json.loads(_text(zero))['map']['fan_in'] == {'rows': [], 'total': 1, 'returned': 0, 'omitted': 1}
        text = await session.call_tool('reveal_query', {'uri': uri})
        assert not text.is_error and 'Most imported files' in _text(text)
        assert 'b.py  fan-in 2' in _text(text)
        scope = await session.call_tool('reveal_query', {'uri': uri + '?no_imports=true', 'provenance': True})
        assert not scope.is_error and json.loads(_text(scope))['map'] is None
        obsolete = await session.call_tool('reveal_query', {'uri': uri + '?tests=include'})
        assert obsolete.is_error and 'metrics://' in _text(obsolete)
    _run(tmp_path, scenario)


def test_registered_stdio_capped_map_is_partial_not_failed_or_clean(tmp_path):
    uri = project(tmp_path / 'partial')
    server = '''
from reveal import mcp_server
from reveal.analyzers.imports import service
original = service.path_scope
service.path_scope = lambda root: original(root, cap=2)
mcp_server.main()
'''
    async def scenario(session):
        result = await session.call_tool('reveal_query', {'uri': uri + '?top=0', 'provenance': True})
        assert not result.is_error, _text(result)
        body = json.loads(_text(result))
        assert body['map_status'] == 'incomplete'
        assert body['map']['metadata']['scan_budget']['capped'] is True
        assert body['map']['fan_in']['rows'] == []
        assert any(w['type'] == 'scan_capped' for w in body['meta']['warnings'])
        scope = await session.call_tool('reveal_query', {'uri': uri + '?no_imports=true', 'provenance': True})
        assert not scope.is_error and json.loads(_text(scope))['map_status'] == 'not_requested'
    _run(tmp_path, scenario, code=server)


def test_registered_stdio_required_graph_failure_is_tool_error(tmp_path):
    uri = project(tmp_path / 'failed')
    server = '''
from reveal import mcp_server
from reveal.analyzers.imports import service
def unavailable(scope, **kwargs):
    raise OSError('controlled required graph failure')
service.analyze = unavailable
mcp_server.main()
'''
    async def scenario(session):
        result = await session.call_tool('reveal_query', {'uri': uri, 'provenance': True})
        assert result.is_error
        assert '"map_status": "complete"' not in _text(result)
        scope = await session.call_tool('reveal_query', {'uri': uri + '?no_imports=true', 'provenance': True})
        assert not scope.is_error
        body = json.loads(_text(scope))
        assert body['map'] is None and body['map_status'] == 'not_requested'
        assert not body.get('meta', {}).get('errors')
    _run(tmp_path, scenario, code=server)
