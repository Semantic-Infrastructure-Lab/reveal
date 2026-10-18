"""Canonical declared analysis/output failures must survive MCP SDK conversion."""
import json

import pytest

from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]

_SERVER = '''
from pathlib import Path
from reveal import mcp_server
from reveal.adapters.surface import SurfaceAdapter
from reveal.rendering.adapters.surface import SurfaceRenderer
from reveal.utils import json_utils

original = SurfaceAdapter.get_structure
original_render = SurfaceRenderer.render_structure
original_json = json_utils.print_json_result

def analyze(self, **kwargs):
    case = Path(self.path).name
    if case == 'analysis_permission':
        raise PermissionError('PUBLIC_ANALYSIS_PERMISSION')
    if case == 'analysis_crash':
        raise RuntimeError('PRIVATE_ANALYSIS_CRASH')
    result = original(self, **kwargs)
    if case == 'returned_failed':
        result['error'] = 'PRIVATE_RETURNED_FAILURE'
        result.setdefault('meta', {})['errors'] = [{'code': 'analysis_failed', 'message': 'PRIVATE_RETURNED_FAILURE'}]
    if case == 'partial':
        result['unparsed_files'] = ['unavailable.py']
    return result

def render(result, *args, **kwargs):
    case = Path(result.get('source', '')).name
    if case in ('render_crash', 'render_permission', 'render_after_stdout'):
        if case == 'render_after_stdout':
            print('BROKEN_PARTIAL_OUTPUT')
        if case == 'render_permission':
            raise PermissionError('PUBLIC_RENDER_PERMISSION')
        raise RuntimeError('PRIVATE_RENDER_CRASH')
    return original_render(result, *args, **kwargs)

def json_render(result, *args, **kwargs):
    case = Path(result.get('source', '')).name
    if case.startswith('render_'):
        if case == 'render_after_stdout':
            print('BROKEN_PARTIAL_OUTPUT')
        if case == 'render_permission':
            raise PermissionError('PUBLIC_RENDER_PERMISSION')
        raise RuntimeError('PRIVATE_RENDER_CRASH')
    return original_json(result, *args, **kwargs)

SurfaceAdapter.get_structure = analyze
SurfaceRenderer.render_structure = staticmethod(render)
json_utils.print_json_result = json_render
mcp_server.main()
'''


@pytest.mark.parametrize('provenance', [False, True])
@pytest.mark.parametrize('case,public,private', [
    ('analysis_permission', 'PUBLIC_ANALYSIS_PERMISSION', ''),
    ('analysis_crash', '', 'PRIVATE_ANALYSIS_CRASH'),
    ('returned_failed', '', 'PRIVATE_RETURNED_FAILURE'),
    ('render_permission', 'PUBLIC_RENDER_PERMISSION', ''),
    ('render_crash', '', 'PRIVATE_RENDER_CRASH'),
    ('render_after_stdout', '', 'PRIVATE_RENDER_CRASH'),
])
def test_declared_failures_are_errors_regardless_of_rendered_body(tmp_path, case, public, private, provenance):
    root = tmp_path / case
    root.mkdir()
    (root / 'demo.py').write_text('VALUE = 1\n', encoding='utf-8')

    async def scenario(session):
        answer = await session.call_tool('reveal_query', {'uri': f'surface://{root}', 'provenance': provenance})
        assert answer.is_error
        assert _text(answer).strip()
        serialized = json.dumps(answer.model_dump(mode='json'))
        if public:
            assert public in _text(answer)
        if private:
            assert private not in serialized
        assert 'BROKEN_PARTIAL_OUTPUT' not in serialized

    _run(tmp_path, scenario, _SERVER)
    if private and case != 'returned_failed':
        assert private in (tmp_path / 'server-stderr.txt').read_text(encoding='utf-8')


def test_partial_analysis_remains_usable_and_explicit(tmp_path):
    root = tmp_path / 'partial'
    root.mkdir()
    (root / 'demo.py').write_text('import os\nTOKEN = os.getenv("APP_TOKEN")\n', encoding='utf-8')

    async def scenario(session):
        answer = await session.call_tool('reveal_query', {'uri': f'surface://{root}'})
        assert not answer.is_error
        assert 'APP_TOKEN' in _text(answer)
        assert 'incomplete' in _text(answer).lower()

    _run(tmp_path, scenario, _SERVER)
