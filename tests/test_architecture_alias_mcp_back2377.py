"""Ordinary architecture alias qualification through the real SDK stdio tool."""

import json
from urllib.parse import quote

import pytest

pytest.importorskip('mcp')

from test_mcp_expected_errors_back1992 import _run, _text  # noqa: E402

pytestmark = [pytest.mark.mcp, pytest.mark.component]


def make_project(root):
    for number in range(7):
        folder = root / f'pkg{number}'
        folder.mkdir(parents=True)
        (folder / 'module.py').write_text('VALUE = 1\n', encoding='utf-8')
    return root


def uri(root, noun='architecture', query=''):
    return f'{noun}://{quote(root.as_posix(), safe="/.:")}' + ('?' + query if query else '')


def retirement_notes(body):
    return [warning for warning in body.get('meta', {}).get('warnings', [])
            if warning.get('code') == 'retired_spelling']


def test_registered_alias_returns_bounded_map_and_one_central_note(tmp_path):
    root = make_project(tmp_path / 'project space & percent%')

    async def scenario(session):
        for top, returned in ((None, 5), (0, 0), (2, 2)):
            query = '' if top is None else f'top={top}'
            response = await session.call_tool('reveal_query', {
                'uri': uri(root, query=query), 'provenance': True})
            assert not response.is_error, _text(response)
            body = json.loads(_text(response))
            assert body['type'] == 'overview' and body['map_status'] == 'complete'
            assert body['scope']['total_code_files'] == 7
            components = body['map']['components']
            assert components['total'] == 7 and components['returned'] == returned
            assert components['omitted'] == 7 - returned
            assert len(components['rows']) == returned
            assert [row['component'] for row in components['rows']] == [f'pkg{n}' for n in range(returned)]
            assert all(body['map'][name]['returned'] <= (5 if top is None else top)
                       for name in ('fan_in', 'entrypoints', 'components', 'cycles'))
            notes = retirement_notes(body)
            assert len(notes) == 1
            assert notes[0]['field'] == 'scheme:architecture'
            assert notes[0]['stage'] == 'note' and 'overview://' in notes[0]['replacement']
            assert 'facts' not in body and 'risks' not in body

        canonical = await session.call_tool('reveal_query', {
            'uri': uri(root, noun='overview'), 'provenance': True})
        assert not canonical.is_error, _text(canonical)
        control = json.loads(_text(canonical))
        assert control['type'] == 'overview' and control['map_status'] == 'complete'
        assert control['map']['components']['total'] == 7
        assert control['map']['components']['returned'] == 5
        assert retirement_notes(control) == []

    _run(tmp_path, scenario)


_LOSS_SERVER = '''
from pathlib import Path
from reveal import mcp_server
from reveal.analyzers.imports import service

original_scope = service.path_scope
original_analyze = service.analyze
original_args = mcp_server._default_args

def scoped(root, **kwargs):
    if Path(root).name.startswith('capped'):
        kwargs['cap'] = 2
    return original_scope(root, **kwargs)

def analyze(scope, **kwargs):
    if Path(scope.root).name.startswith('failed'):
        raise OSError('required graph service unavailable')
    return original_analyze(scope, **kwargs)

def arguments(*args, **kwargs):
    result = original_args(*args, **kwargs)
    # reveal_query has no public fields argument. Exercise the existing final
    # projection through its ordinary Namespace seam, without replacing capture,
    # analysis, answer qualification or SDK conversion.
    if '-fields' in kwargs.get('path', ''):
        result.fields = 'path'
    return result

service.path_scope = scoped
service.analyze = analyze
mcp_server._default_args = arguments
mcp_server.main()
'''


def test_registered_alias_preserves_partial_and_failed_outcomes_after_projection(tmp_path):
    roots = {name: make_project(tmp_path / name)
             for name in ('healthy-fields', 'capped', 'capped-fields', 'failed', 'failed-fields')}

    async def scenario(session):
        async def query(name, parameters='top=0'):
            return await session.call_tool('reveal_query', {
                'uri': uri(roots[name], query=parameters), 'provenance': True})

        healthy = await query('healthy-fields')
        assert not healthy.is_error, _text(healthy)
        selected = json.loads(_text(healthy))
        assert selected['type'] == 'overview' and selected['path'] == roots['healthy-fields'].as_posix()
        assert 'map' not in selected and len(retirement_notes(selected)) == 1

        capped = await query('capped')
        # Useful partial orientation exits incomplete but is not an MCP failure.
        assert not capped.is_error, _text(capped)
        partial = json.loads(_text(capped))
        assert partial['type'] == 'overview' and partial['map_status'] == 'incomplete'
        assert partial['scope']['total_code_files'] == 7
        assert partial['map']['metadata']['scan_budget'] == {
            'scope': 'scan', 'limit': 2, 'total': 3, 'returned': 2, 'exact': False, 'capped': True}
        assert all(partial['map'][name]['rows'] == []
                   for name in ('fan_in', 'entrypoints', 'components', 'cycles'))
        assert any(warning['type'] == 'scan_capped' for warning in partial['meta']['warnings'])
        assert len(retirement_notes(partial)) == 1

        projected = await query('capped-fields')
        assert not projected.is_error, _text(projected)
        selected = json.loads(_text(projected))
        assert selected['type'] == 'overview' and 'map' not in selected
        assert selected['path'] == roots['capped-fields'].as_posix()
        assert any(warning['type'] == 'scan_capped' for warning in selected['meta']['warnings'])
        assert len(retirement_notes(selected)) == 1

        for name in ('failed', 'failed-fields'):
            failure = await query(name)
            assert failure.is_error, (name, _text(failure))
            assert _text(failure).strip()
            assert '"map_status": "complete"' not in _text(failure)
            # Scope-only operation never requested the broken required graph.
            scope_only = await query(name, 'no_imports=true')
            assert not scope_only.is_error, _text(scope_only)
            body = json.loads(_text(scope_only))
            assert body['type'] == 'overview' and len(retirement_notes(body)) == 1
            if not name.endswith('-fields'):
                assert body['map_status'] == 'not_requested' and body['map'] is None

    _run(tmp_path, scenario, code=_LOSS_SERVER)
