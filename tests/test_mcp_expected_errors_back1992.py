"""Expected diagnostics and untrusted text through the real SDK stdio boundary."""
import asyncio
import json
import os
import sys

import pytest

pytest.importorskip('mcp')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver.exceptions import ToolError

pytestmark = [pytest.mark.mcp, pytest.mark.component]

# Exercise the real registered structure tool with deterministic capture outcomes.
# Injection happens in the child, so subprocess/fork patch inheritance is irrelevant.
_CAPTURE_SERVER = '''
from reveal import mcp_server
from reveal.display import structure

def display(analyzer, *args):
    name = analyzer.path
    from pathlib import Path
    scenario = Path(name).stem
    if scenario == 'crash':
        raise RuntimeError('PRIVATE_CRASH_DETAIL')
    if scenario == 'operational':
        raise PermissionError('PUBLIC_PERMISSION_DETAIL')
    if scenario == 'empty':
        raise SystemExit(3)
    if scenario == 'literal':
        print('[reveal error: literal source text]')
    elif scenario == 'partial':
        print('usable partial narrative')
        raise SystemExit(3)
    else:
        print('negative finding')
        raise SystemExit(1)

structure.show_structure = display
mcp_server.main()
'''


def _text(result):
    return '\n'.join(item.text for item in result.content if item.type == 'text')


def _run(tmp_path, scenario, code=None):
    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=['-c', code] if code else ['-m', 'reveal.mcp_server'],
            env={**os.environ, 'REVEAL_DISK_CACHE': '0'},
        )
        with (tmp_path / 'server-stderr.txt').open('w', encoding='utf-8') as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await scenario(session)
    asyncio.run(asyncio.wait_for(exercise(), timeout=60))


def test_expected_diagnostics_reach_stdio_client(tmp_path):
    path = tmp_path / 'demo.py'
    path.write_text('def first():\n    return 1\n', encoding='utf-8')
    missing = tmp_path / 'missing.py'

    async def scenario(session):
        result = await session.call_tool('reveal_structure', {'path': str(missing)})
        assert result.is_error
        assert 'path not found' in _text(result)
        assert missing.name in _text(result)
        invalid = await session.call_tool('reveal_nav', {
            'path': str(path), 'element': 'first', 'flag': 'unknown_flag'})
        assert invalid.is_error
        assert 'unknown nav flag' in _text(invalid)
        invalid_rule = await session.call_tool('reveal_check', {
            'path': str(path), 'select': 'NOT_A_RULE'})
        assert invalid_rule.is_error
        assert 'NOT_A_RULE' in _text(invalid_rule)
        # A sibling tool and a source edit remain successful in the same session.
        before = await session.call_tool('reveal_element', {'path': str(path), 'element': 'first'})
        assert not before.is_error
        assert 'return 1' in _text(before)
        path.write_text('def first():\n    return 2\n', encoding='utf-8')
        after = await session.call_tool('reveal_element', {'path': str(path), 'element': 'first'})
        assert not after.is_error
        assert 'return 2' in _text(after)
        absent = await session.call_tool('reveal_trace', {'path': str(path.parent), 'entry_point': 'absent'})
        assert not absent.is_error

    _run(tmp_path, scenario)


@pytest.mark.parametrize('name,is_error,visible,hidden', [
    ('operational', True, 'PUBLIC_PERMISSION_DETAIL', ''),
    ('crash', True, '', 'PRIVATE_CRASH_DETAIL'),
    ('literal', False, '[reveal error: literal source text]', ''),
    ('partial', False, 'usable partial narrative', ''),
    ('negative', False, 'negative finding', ''),
    ('empty', False, '[reveal exited with code 3]', ''),
])
def test_stdio_preserves_capture_origin_and_narrative(tmp_path, name, is_error, visible, hidden):
    path = tmp_path / f'{name}.py'
    path.write_text('VALUE = 1\n', encoding='utf-8')

    async def scenario(session):
        result = await session.call_tool('reveal_structure', {'path': str(path)})
        assert result.is_error is is_error
        if visible:
            assert visible in _text(result)
        if hidden:
            assert _text(result).strip()
            assert hidden not in _text(result)
            assert hidden not in json.dumps(result.structured_content)

    _run(tmp_path, scenario, _CAPTURE_SERVER)
    if hidden:
        assert hidden in (tmp_path / 'server-stderr.txt').read_text(encoding='utf-8')


@pytest.mark.parametrize('exception_class,detail,public', [
    ('RuntimeError', 'PRIVATE_OUTER_DETAIL', False),
    ('PermissionError', 'PUBLIC_OUTER_DETAIL', True),
])
def test_stdio_masks_exception_outside_capture(tmp_path, exception_class, detail, public):
    path = tmp_path / 'demo.py'
    path.write_text('VALUE = 1\n', encoding='utf-8')
    code = f"""
from reveal import mcp_server, registry

def broken(*args, **kwargs):
    raise {exception_class}('{detail}')

registry.get_analyzer = broken
mcp_server.main()
"""

    async def scenario(session):
        for tool, arguments in (
            ('reveal_structure', {'path': str(path)}),
            ('reveal_element', {'path': str(path), 'element': 'VALUE'}),
        ):
            result = await session.call_tool(tool, arguments)
            assert result.is_error
            assert _text(result).strip()
            assert (detail in _text(result)) is public
            assert detail not in json.dumps(result.structured_content)

    _run(tmp_path, scenario, code)
    if not public:
        assert detail in (tmp_path / 'server-stderr.txt').read_text(encoding='utf-8')


def test_direct_capture_string_and_registered_controls(tmp_path):
    from reveal import mcp_server
    missing = tmp_path / 'missing.py'
    direct = mcp_server.reveal_structure(str(missing))
    assert isinstance(direct, str)
    assert direct == f'[reveal error: path not found: {missing}]'
    assert json.loads(json.dumps({'result': direct}))['result'] == direct
    registered = mcp_server.mcp._tool_manager._tools['reveal_structure'].fn
    with pytest.raises(ToolError, match='path not found'):
        registered(path=str(missing))

    def broken():
        raise RuntimeError('PRIVATE_DIRECT_DETAIL')

    assert mcp_server._run_and_capture(broken) == '[reveal error: PRIVATE_DIRECT_DETAIL]'


def test_unknown_adapter_remains_nonerror_stdio_result(tmp_path):
    async def scenario(session):
        result = await session.call_tool('reveal_query', {'uri': 'no-such-adapter://x'})
        assert not result.is_error
        assert '[reveal exited with code 1]' in _text(result)
        assert 'Unsupported URI scheme' in _text(result)

    _run(tmp_path, scenario)
