"""Real SDK wire controls for canonical trace and its compatibility exception."""
import json

import pytest

from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]

_SERVER = '''
from pathlib import Path
from reveal import mcp_server
from reveal.adapters.trace import TraceAdapter, TraceRenderer
from reveal.utils import json_utils
original = TraceAdapter.get_structure
original_render = TraceRenderer.render_structure
original_json = json_utils.print_json_result

def analyze(self, **kwargs):
    case = Path(self.path).name
    if case == 'permission':
        raise PermissionError('PUBLIC_TRACE_PERMISSION')
    if case == 'crash':
        raise RuntimeError('PRIVATE_TRACE_CRASH')
    result = original(self, **kwargs)
    if case == 'returned':
        result['error'] = 'PRIVATE_RETURNED_TRACE_FAILURE'
    if case == 'partial':
        result.setdefault('meta', {})['warnings'] = [{'type': 'analysis_failed', 'message': 'required input missing'}]
    return result

def render(result, *args, **kwargs):
    case = Path(result.get('path', '')).name
    if case in ('render', 'absent_render'):
        print('BROKEN_TRACE_OUTPUT')
        raise RuntimeError('PRIVATE_TRACE_RENDER')
    return original_render(result, *args, **kwargs)

def json_render(result, *args, **kwargs):
    if Path(result.get('path', '')).name in ('render', 'absent_render'):
        print('BROKEN_TRACE_OUTPUT')
        raise RuntimeError('PRIVATE_TRACE_RENDER')
    return original_json(result, *args, **kwargs)

TraceAdapter.get_structure = analyze
TraceRenderer.render_structure = staticmethod(render)
json_utils.print_json_result = json_render
mcp_server.main()
'''


@pytest.mark.parametrize('tool', ['reveal_trace', 'reveal_query'])
@pytest.mark.parametrize('case,public,private', [
    ('permission', 'PUBLIC_TRACE_PERMISSION', ''),
    ('crash', '', 'PRIVATE_TRACE_CRASH'),
    ('returned', '', 'PRIVATE_RETURNED_TRACE_FAILURE'),
    ('render', '', 'PRIVATE_TRACE_RENDER'),
    ('absent_render', '', 'PRIVATE_TRACE_RENDER'),
])
def test_failed_trace_is_error_even_after_rendered_text(tmp_path, tool, case, public, private):
    root = tmp_path / case
    root.mkdir()
    (root / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    entry = 'absent' if case == 'absent_render' else 'main'

    async def scenario(session):
        arguments = ({'path': str(root), 'entry_point': entry} if tool == 'reveal_trace'
                     else {'uri': f'trace://{root}?from={entry}', 'provenance': True})
        result = await session.call_tool(tool, arguments)
        assert result.is_error
        assert _text(result).strip()
        serialized = json.dumps(result.model_dump(mode='json'))
        assert 'BROKEN_TRACE_OUTPUT' not in serialized
        if public:
            assert public in _text(result)
        if private:
            assert private not in serialized

    _run(tmp_path, scenario, _SERVER)
    if private:
        assert private in (tmp_path / 'server-stderr.txt').read_text(encoding='utf-8')


def test_partial_absent_root_siblings_and_freshness(tmp_path):
    root = tmp_path / 'partial'
    root.mkdir()
    source = root / 'app.py'
    source.write_text('def main():\n    first_call()\n', encoding='utf-8')

    async def scenario(session):
        result = await session.call_tool('reveal_trace', {'path': str(root), 'entry_point': 'main'})
        assert not result.is_error
        assert 'first_call' in _text(result)
        assert 'incomplete' in _text(result).lower()
        source.write_text('def main():\n    second_call()\n', encoding='utf-8')
        after = await session.call_tool('reveal_trace', {'path': str(root), 'entry_point': 'main'})
        assert not after.is_error
        assert 'second_call' in _text(after) and 'first_call' not in _text(after)
        for tool, arguments in (
            ('reveal_trace', {'path': str(tmp_path), 'entry_point': 'absent'}),
            ('reveal_query', {'uri': f'trace://{tmp_path}?from=absent', 'provenance': True}),
            ('reveal_query', {'uri': f'surface://{root}'}),
        ):
            result = await session.call_tool(tool, arguments)
            assert not result.is_error
        missing = await session.call_tool('reveal_trace', {'path': str(tmp_path / 'missing'), 'entry_point': 'main'})
        assert missing.is_error and 'path not found' in _text(missing)

    _run(tmp_path, scenario, _SERVER)


def test_compatible_absence_provenance_is_parseable_json(tmp_path):
    (tmp_path / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')

    async def scenario(session):
        result = await session.call_tool('reveal_query', {
            'uri': f'trace://{tmp_path}?from=absent', 'provenance': True})
        assert not result.is_error
        answer = json.loads(_text(result))
        assert answer['type'] == 'trace'
        assert answer['root'] == 'absent'
        assert answer['error'] and answer['execution']['command']

    _run(tmp_path, scenario)


def test_applied_trace_depth_has_no_false_unused_flag_warning(tmp_path):
    (tmp_path / 'app.py').write_text('def main():\n    helper()\n\ndef helper():\n    third()\n', encoding='utf-8')

    async def scenario(session):
        answer = await session.call_tool('reveal_trace', {'path': str(tmp_path), 'entry_point': 'main', 'depth': 1})
        assert not answer.is_error
        assert 'depth 1' in _text(answer)
        assert '--depth has no effect' not in _text(answer)

    _run(tmp_path, scenario)
