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
    phase = ['starting the server']

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=['-c', code] if code else ['-m', 'reveal.mcp_server'],
            env={**os.environ, 'REVEAL_DISK_CACHE': '0'},
        )
        with (tmp_path / 'server-stderr.txt').open('w', encoding='utf-8') as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    phase[0] = 'session.initialize()'
                    await session.initialize()
                    phase[0] = 'the scenario'
                    await scenario(session)
    # 60 s timed out repeatedly on the loaded 1.8.1 compat leg (BACK-2050); a real hang still fails.
    try:
        asyncio.run(asyncio.wait_for(exercise(), timeout=180))
    except (asyncio.TimeoutError, TimeoutError):
        stderr = (tmp_path / 'server-stderr.txt').read_text(encoding='utf-8', errors='replace')
        pytest.fail(f'MCP stdio run timed out after 180 s while {phase[0]}; server stderr tail:\n'
                    f'{stderr[-3000:] or "(empty)"}', pytrace=False)


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


@pytest.mark.parametrize('tool', ['reveal_structure', 'reveal_query'])
def test_registered_crash_logging_cannot_enter_sibling_capture(tmp_path, monkeypatch, tool):
    import concurrent.futures
    import logging
    import threading
    from reveal import mcp_server
    from reveal.display import structure

    path = tmp_path / 'demo.py'
    path.write_text('VALUE = 1\n', encoding='utf-8')
    probed = threading.Event()
    entered = threading.Event()
    release = threading.Event()
    classification = threading.Event()
    acquired = []
    original = mcp_server._raise_if_tool_failure

    class CurrentStderr(logging.Handler):
        def emit(self, record):
            print(self.format(record), file=sys.stderr)

    handler = CurrentStderr()
    logger = logging.getLogger(mcp_server.__name__)
    logger.addHandler(handler)

    def crash(*args, **kwargs):
        raise RuntimeError('PRIVATE_CONCURRENT_DETAIL')

    def classify(result, tool_name):
        classification.set()
        assert probed.wait(timeout=10)
        if acquired[0]:
            assert entered.wait(timeout=10)
        try:
            return original(result, tool_name)
        finally:
            release.set()

    def sibling():
        assert classification.wait(timeout=10)
        got_lock = mcp_server._capture_lock.acquire(blocking=False)
        acquired.append(got_lock)
        if got_lock:
            mcp_server._capture_lock.release()
        probed.set()

        def render():
            entered.set()
            assert release.wait(timeout=10)
            print('sibling narrative')

        return mcp_server._run_and_capture(render)

    monkeypatch.setattr(structure, 'show_structure', crash)
    monkeypatch.setattr(mcp_server, '_raise_if_tool_failure', classify)
    from reveal.adapters.surface import SurfaceAdapter
    monkeypatch.setattr(SurfaceAdapter, 'get_structure', crash)
    registered = mcp_server.mcp._tool_manager._tools[tool].fn
    arguments = {'path': str(path)} if tool == 'reveal_structure' else {'uri': f'surface://{tmp_path}'}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            other = pool.submit(sibling)
            failed = pool.submit(registered, **arguments)
            with pytest.raises(ToolError, match='Internal error'):
                failed.result(timeout=15)
            text = other.result(timeout=15)
        assert text == 'sibling narrative\n'
        assert acquired == [False]
    finally:
        release.set()
        logger.removeHandler(handler)


def test_stdio_answers_when_a_native_extension_panics(tmp_path):
    """A PyO3 PanicException is a BaseException, so it skipped every ``except Exception`` and the
    client never got a reply (BACK-2050: tree-sitter 'Node is unsendable' on language-pack 1.8.1)."""
    path = tmp_path / 'demo.py'
    path.write_text('VALUE = 1\n', encoding='utf-8')
    code = """
from reveal import mcp_server, registry

class PanicException(BaseException):
    pass

def broken(*args, **kwargs):
    raise PanicException('PRIVATE_PANIC_DETAIL')

registry.get_analyzer = broken
mcp_server.main()
"""

    async def scenario(session):
        for tool, arguments in (
            ('reveal_structure', {'path': str(path)}),
            ('reveal_element', {'path': str(path), 'element': 'VALUE'}),
        ):
            result = await asyncio.wait_for(session.call_tool(tool, arguments), timeout=20)
            assert result.is_error
            assert 'PRIVATE_PANIC_DETAIL' not in _text(result)
        # the server survived: a later, ordinary call still answers
        ok = await asyncio.wait_for(session.call_tool('reveal_structure', {'path': str(tmp_path)}), timeout=20)
        assert ok is not None

    _run(tmp_path, scenario, code)
    assert 'PRIVATE_PANIC_DETAIL' in (tmp_path / 'server-stderr.txt').read_text(encoding='utf-8')
