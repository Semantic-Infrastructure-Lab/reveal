"""Actual stdio and direct MCP requests observe included-directory loss."""
import json
import os
from pathlib import Path

import pytest

pytest.importorskip('mcp')
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]

_SERVER = '''
import os
from pathlib import Path
from reveal import mcp_server
real = os.scandir

def scandir(path):
    target = Path(path)
    if target.name == 'included_child' and (target.parent / 'deny').exists():
        raise PermissionError(13, 'controlled included child enumeration failure', str(target))
    return real(path)

os.scandir = scandir
mcp_server.main()
'''


def project(tmp_path):
    root = tmp_path / 'project'
    child = root / 'included_child'
    child.mkdir(parents=True)
    (root / 'visible.py').write_text('def visible():\n    return 1\n', encoding='utf-8')
    (child / 'hidden.py').write_text('def hidden():\n    return 2\n', encoding='utf-8')
    return root, child


def arguments(tool, root, entry):
    return ({'path': str(root), 'entry_point': entry} if tool == 'reveal_trace'
            else {'uri': f'trace://{root}?from={entry}', 'provenance': True})


@pytest.mark.parametrize('tool', ['reveal_trace', 'reveal_query'])
def test_stdio_clean_loss_repair_and_unaffected_sibling(tmp_path, tool):
    root, child = project(tmp_path)
    marker = root / 'deny'

    async def scenario(session):
        for entry in ('visible', 'hidden'):
            clean = await session.call_tool(tool, arguments(tool, root, entry))
            assert not clean.is_error
        sibling = await session.call_tool('reveal_element', {'path': str(root / 'visible.py'), 'element': 'visible'})
        marker.write_text('deny', encoding='utf-8')
        partial = await session.call_tool(tool, arguments(tool, root, 'visible'))
        assert not partial.is_error
        assert 'controlled included child enumeration failure' in _text(partial)
        assert 'incomplete' in _text(partial).lower()
        if tool == 'reveal_query':
            answer = json.loads(_text(partial))
            warning, = [w for w in answer['meta']['warnings'] if w.get('unit') == 'directories']
            assert warning['count'] == 1 and warning['directories'] == [child.as_posix()]
        failed = await session.call_tool(tool, arguments(tool, root, 'hidden'))
        assert failed.is_error  # Cannot use clean absence's historical MCP exception.
        after = await session.call_tool('reveal_element', {'path': str(root / 'visible.py'), 'element': 'visible'})
        assert after.model_dump() == sibling.model_dump()
        marker.unlink()
        repaired = await session.call_tool(tool, arguments(tool, root, 'hidden'))
        assert not repaired.is_error
        assert 'controlled included child enumeration failure' not in _text(repaired)
        assert 'incomplete' not in _text(repaired).lower()

    _run(tmp_path, scenario, _SERVER)


@pytest.mark.parametrize('tool', ['reveal_trace', 'reveal_query'])
def test_direct_mcp_partial_and_failed_trace_are_distinct(tmp_path, monkeypatch, tool):
    from reveal import mcp_server
    root, child = project(tmp_path)
    real = os.scandir

    def denied(path):
        if Path(path) == child:
            raise PermissionError(13, 'controlled included child enumeration failure', str(child))
        return real(path)

    fn = getattr(mcp_server, tool)
    with monkeypatch.context() as context:
        context.setattr(os, 'scandir', denied)
        partial = fn(**arguments(tool, root, 'visible'))
        assert not isinstance(partial, mcp_server._ToolFailure)
        assert 'controlled included child enumeration failure' in partial
        failed = fn(**arguments(tool, root, 'hidden'))
        assert isinstance(failed, mcp_server._ToolFailure)
    repaired = fn(**arguments(tool, root, 'hidden'))
    assert not isinstance(repaired, mcp_server._ToolFailure)
    assert 'incomplete' not in repaired.lower()
