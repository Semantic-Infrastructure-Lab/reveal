"""Contracts URI budgets and evidence survive declared-call adoption in the SDK."""
import json

import pytest

from reveal import api
from test_contracts_api_overlay_back2347 import RUST_SOURCE, SOURCE
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]
_SERVER = '''
import os
from pathlib import Path
from reveal import mcp_server
from reveal.adapters import contracts
scan = contracts._scan_contracts
coverage = contracts.assess_language_coverage
scandir = os.scandir
stage = None

def scanned(*args, **kwargs):
    global stage
    previous, stage = stage, 'source'
    try:
        return scan(*args, **kwargs)
    finally:
        stage = previous

def covered(*args, **kwargs):
    global stage
    previous, stage = stage, 'coverage'
    try:
        return coverage(*args, **kwargs)
    finally:
        stage = previous

def enumerated(path):
    target = Path(path)
    marker_root = target.parent.parent if target.name == 'hidden' else target.parent
    marker = marker_root / ('deny-' + str(stage))
    root_marker = marker_root / 'deny-root-source'
    if ((target.name == 'hidden' and marker.exists()) or
        (target.name == 'project' and stage == 'source' and root_marker.exists())):
        (marker_root / ('observed-' + str(stage))).touch()
        raise PermissionError(13, 'CONTRACTS_' + str(stage).upper() + '_ENUMERATION_DENIED', str(path))
    return scandir(path)

contracts._scan_contracts = scanned
contracts.assess_language_coverage = covered
os.scandir = enumerated
from reveal.rendering.adapters.contracts import ContractsRenderer
render = ContractsRenderer.render_structure

def rendered(result, *args, **kwargs):
    if Path(result.get('source', '')).name == 'output_failure':
        raise PermissionError('CONTRACTS_OUTPUT_DENIED')
    return render(result, *args, **kwargs)

ContractsRenderer.render_structure = staticmethod(rendered)
from reveal.utils import json_utils
json_render = json_utils.print_json_result

def json_rendered(result, *args, **kwargs):
    if Path(result.get('source', '')).name == 'output_failure':
        raise PermissionError('CONTRACTS_OUTPUT_DENIED')
    return json_render(result, *args, **kwargs)

json_utils.print_json_result = json_rendered
mcp_server.main()
'''


@pytest.mark.parametrize('provenance', [False, True])
def test_contracts_budgets_losses_repair_and_siblings_through_stdio(tmp_path, provenance):
    root = tmp_path / 'project'
    root.mkdir()
    source = root / 'contract.py'
    source.write_text(SOURCE, encoding='utf-8')
    hidden = root / 'hidden'
    hidden.mkdir()
    (hidden / 'hidden.py').write_text('from abc import ABC\nclass Hidden(ABC): pass\n', encoding='utf-8')
    output = tmp_path / 'output_failure'
    output.mkdir()
    (output / 'contract.py').write_text(SOURCE, encoding='utf-8')

    implementation_only = tmp_path / 'implementation_only'
    implementation_only.mkdir()
    (implementation_only / 'visible.rs').write_text(RUST_SOURCE, encoding='utf-8')

    async def scenario(session):
        async def query(query_string='', path=root):
            return await session.call_tool('reveal_query', {
                'uri': f'contracts://{path.as_posix()}' + ('?' + query_string if query_string else ''),
                'provenance': provenance})
        useful_zero = await query('impls=1', implementation_only)
        assert not useful_zero.is_error and 'First' in _text(useful_zero) and 'Second' in _text(useful_zero)
        if provenance:
            answer = json.loads(_text(useful_zero))
            assert answer['total_contracts'] == 0 and answer['impls_cap'] == 1
            assert [row['name'] for row in answer['dataclasses']] == ['First', 'Second']
        for control in ('abstract_only=true', 'implementations=false'):
            empty = await query(control, implementation_only)
            assert not empty.is_error and 'incomplete' not in _text(empty).lower()
            if provenance:
                assert json.loads(_text(empty))['dataclasses'] == []
        for cap in (1, 0):
            budget = await query(f'impls={cap}&abstract_only=true')
            assert not budget.is_error and 'Contract' in _text(budget)
            if provenance:
                answer = json.loads(_text(budget))
                expected = api.query(f'contracts://{root.as_posix()}?impls={cap}&abstract_only=true')
                assert answer['type'] == 'contracts' and answer['abcs'] == expected['abcs']
                base = next(row for row in answer['abcs'] if row['name'] == 'Contract')
                assert len(base['implementations']) == 8 and answer['impls_cap'] == cap
            else:
                assert 'Impl0' in _text(budget)
                assert ('Impl7' in _text(budget)) is (cap == 0)
                assert ('and 7 more' in _text(budget)) is (cap == 1)
        for stage in ('source', 'coverage'):
            marker = tmp_path / ('deny-' + stage)
            marker.touch()
            partial = await query()
            assert (tmp_path / ('observed-' + stage)).exists()
            assert not partial.is_error and 'Contract' in _text(partial)
            assert 'incomplete' in _text(partial).lower()
            if provenance:
                warnings = json.loads(_text(partial))['meta']['warnings']
                assert any('CONTRACTS_' + stage.upper() + '_ENUMERATION_DENIED' in entry['message'] for entry in warnings)
                coverage_notes = [entry for entry in warnings if 'language-coverage census' in entry['message']]
                assert bool(coverage_notes) is (stage == 'coverage')
            marker.unlink()
            restored = await query()
            assert not restored.is_error and 'Hidden' in _text(restored)
            assert 'incomplete' not in _text(restored).lower()
        (tmp_path / 'observed-source').unlink()
        marker = tmp_path / 'deny-root-source'
        marker.touch()
        failed = await query()
        assert (tmp_path / 'observed-source').exists()
        assert failed.is_error and _text(failed).strip()
        marker.unlink()
        source.write_text(SOURCE.replace('Contract', 'FreshContract'), encoding='utf-8')
        fresh = await query()
        assert not fresh.is_error and 'FreshContract' in _text(fresh)
        assert 'incomplete' not in _text(fresh).lower()
        for path, query_string in ((root / 'missing', ''), (root, 'impls=-1'), (output, '')):
            failure = await query(query_string, path)
            assert failure.is_error and _text(failure).strip()
        for scheme, query_string in (('surface', 'type=env&top=0'), ('ast', 'name=absent'),
                                     ('ast', 'show=dict-heatmap'), ('ast', 'show=dict-schemas'),
                                     ('ast', 'reveal_type=absent')):
            sibling = await session.call_tool('reveal_query', {
                'uri': f'{scheme}://{root.as_posix()}?{query_string}', 'provenance': provenance})
            assert not sibling.is_error and 'incomplete' not in _text(sibling).lower()

    _run(tmp_path, scenario, _SERVER)
