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
    if case.startswith('returned_failed'):
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

def project(self, result, args):
    case = Path(self.path).name
    if case == 'postprocess_failed':
        result['error'] = 'PRIVATE_POSTPROCESS_FAILURE'
        result.setdefault('meta', {})['errors'] = [{'message': 'PRIVATE_POSTPROCESS_FAILURE'}]
    if case == 'returned_failed_copy':
        return {key: value for key, value in result.items() if key not in ('error', 'meta')}
    if case == 'returned_failed_inplace':
        result.pop('error', None)
        result.pop('meta', None)
    return result

SurfaceAdapter.post_process = project
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
    ('returned_failed_copy', '', 'PRIVATE_RETURNED_FAILURE'),
    ('returned_failed_inplace', '', 'PRIVATE_RETURNED_FAILURE'),
    ('postprocess_failed', '', 'PRIVATE_POSTPROCESS_FAILURE'),
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
    if private:
        assert private in (tmp_path / 'server-stderr.txt').read_text(encoding='utf-8')


@pytest.mark.parametrize('provenance', [False, True])
def test_partial_analysis_remains_usable_and_explicit(tmp_path, provenance):
    root = tmp_path / 'partial'
    root.mkdir()
    (root / 'demo.py').write_text('import os\nTOKEN = os.getenv("APP_TOKEN")\n', encoding='utf-8')

    async def scenario(session):
        answer = await session.call_tool('reveal_query', {'uri': f'surface://{root}', 'provenance': provenance})
        assert not answer.is_error
        assert 'APP_TOKEN' in _text(answer)
        assert 'incomplete' in _text(answer).lower()
        if provenance:
            result = json.loads(_text(answer))
            assert result['type'] == 'surface_scan'
            assert result['execution']['command']
            assert result['unparsed_files'] == ['unavailable.py']

    _run(tmp_path, scenario, _SERVER)


def test_all_declared_consumers_keep_analysis_origin_across_repeated_calls(tmp_path):
    classes = ('architecture.ArchitectureAdapter', 'contracts.ContractsAdapter',
               'deps.DepsAdapter', 'hotspots.HotspotsAdapter',
               'overview.OverviewAdapter', 'surface.SurfaceAdapter')
    code = """
from pathlib import Path
from importlib import import_module
from reveal import mcp_server

def analyze(self, **kwargs):
    if Path(self.path).name == 'permission':
        raise PermissionError('PUBLIC_OPERATION_DETAIL')
    raise RuntimeError('PRIVATE_ANALYSIS_DETAIL')
"""
    for target in classes:
        module, name = target.split('.')
        code += f"getattr(import_module('reveal.adapters.{module}'), '{name}').get_structure = analyze\n"
    code += 'mcp_server.main()\n'
    for case in ('permission', 'crash'):
        (tmp_path / case).mkdir()

    async def scenario(session):
        for target in classes:
            scheme = target.partition('.')[0]
            for case in ('permission', 'crash'):
                for provenance in (False, True):
                    answer = await session.call_tool('reveal_query', {
                        'uri': f'{scheme}://{tmp_path / case}', 'provenance': provenance})
                    assert answer.is_error, (scheme, case, provenance)
                    serialized = json.dumps(answer.model_dump(mode='json'))
                    assert 'PRIVATE_ANALYSIS_DETAIL' not in serialized
                    if case == 'permission':
                        assert 'PUBLIC_OPERATION_DETAIL' in _text(answer)

    _run(tmp_path, scenario, code)


def test_declared_validation_freshness_and_legacy_siblings(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    path = root / 'demo.py'
    path.write_text('import os\nTOKEN = os.getenv("BEFORE_TOKEN")\n', encoding='utf-8')

    async def scenario(session):
        invalid = await session.call_tool('reveal_query', {'uri': f'surface://{tmp_path / "missing"}'})
        assert invalid.is_error
        assert 'Path not found' in _text(invalid)
        before = await session.call_tool('reveal_query', {'uri': f'surface://{root}', 'provenance': True})
        assert not before.is_error
        assert 'BEFORE_TOKEN' in json.dumps(json.loads(_text(before)))
        path.write_text('import os\nTOKEN = os.getenv("AFTER_TOKEN")\n', encoding='utf-8')
        after = await session.call_tool('reveal_query', {'uri': f'surface://{root}', 'provenance': True})
        assert not after.is_error
        assert 'AFTER_TOKEN' in json.dumps(json.loads(_text(after)))
        assert 'BEFORE_TOKEN' not in _text(after)
        legacy = await session.call_tool('reveal_query', {'uri': 'no-such-adapter://x'})
        assert not legacy.is_error
        assert 'Unsupported URI scheme' in _text(legacy)
        absent = await session.call_tool('reveal_trace', {'path': str(root), 'entry_point': 'absent'})
        assert not absent.is_error

    _run(tmp_path, scenario)


def test_required_artifact_failure_reaches_canonical_consumer_without_changing_default_capture(tmp_path):
    from reveal import mcp_server
    from reveal.cli.defaults import _default_args
    from reveal.cli.routing.declared import run_declared_command
    from reveal.utils.results import FailureCause

    (tmp_path / 'demo.py').write_text('VALUE = 1\n', encoding='utf-8')
    answers = []

    def consume(answer):
        answers.append(answer)
        answer.emit()

    # A directory cannot serve as the requested JSON artifact on any platform.
    args = _default_args(path=str(tmp_path), also_json=str(tmp_path))
    captured = mcp_server._run_and_capture(
        run_declared_command, 'surface', args, answer_consumer=consume)
    assert 'Surface:' in captured
    answer = answers[0]
    assert FailureCause.OUTPUT in answer.execution_facts.failures
    assert isinstance(answer.exception, OSError)
    assert isinstance(json.dumps(answer.result), str)
    assert not isinstance(captured, mcp_server._ToolFailure)
    legacy = mcp_server._run_and_capture(
        run_declared_command, 'surface', _default_args(path=str(tmp_path), also_json=str(tmp_path)))
    assert 'Surface:' in legacy
    assert not isinstance(legacy, mcp_server._ToolFailure)
