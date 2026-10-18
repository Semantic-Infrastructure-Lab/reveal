"""Independent Contracts consumers retain required coverage facts before cuts."""
import copy
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import contracts
from reveal.adapters.ast import analysis
from reveal.utils.path_utils import assess_language_coverage
from reveal.utils.results import AnalysisCompleteness

pytestmark = pytest.mark.component
ABC = 'from abc import ABC\nclass Visible(ABC):\n    pass\n'
RUST = 'struct Visible;\nimpl External for Visible { fn go(&self) {} }\n'
GO = 'package p\ntype Other interface { Go() }\n'


def _write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'denied': set(), 'unknown': False, 'events': [], 'shared': [], 'native': []}
    real_assess, real_scandir = contracts.assess_language_coverage, os.scandir
    real_shared, real_native = analysis.collect_structures, contracts._collect_files

    def assess(*args, **kwargs):
        state['active'] = True
        try:
            return real_assess(*args, **kwargs)
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append(Path(path).resolve())
            if state['unknown']:
                raise PermissionError('independent unlocated Contracts coverage census loss')
            raise PermissionError(13, 'independent Contracts coverage census loss', str(path))
        return real_scandir(path)

    def shared(*args, **kwargs):
        result = real_shared(*args, **kwargs)
        assert not result.traversal_failures and not result.skipped
        state['shared'].append([row['file'] for row in result])
        return result

    def native(*args, **kwargs):
        result = real_native(*args, **kwargs)
        state['native'].append(list(result))
        return result

    monkeypatch.setattr(contracts, 'assess_language_coverage', assess)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(analysis, 'collect_structures', shared)
    monkeypatch.setattr(contracts, '_collect_files', native)
    return state


def _warning(data):
    entries = [entry for entry in data['meta']['warnings'] if entry.get('unit') == 'directories']
    assert len(entries) == 1, data['meta']
    assert 'confidence' not in data['meta']
    return entries[0]


def _domain(data):
    return {key: value for key, value in data.items() if key not in ('coverage', 'meta')}


@pytest.mark.parametrize('query,useful', [('', True), ('implementations=false', False), ('abstract_only=true', False)])
def test_actual_rust_header_zero_requested_rows_control_outcome_before_caps_and_artifact(tmp_path, fault, query, useful):
    root = tmp_path / 'project'
    _write(root / 'visible.rs', RUST)
    unfiltered = contracts.ContractsAdapter(str(root)).get_structure()
    assert unfiltered['total_contracts'] == 0 and contracts._contract_observations(unfiltered)
    clean = contracts.ContractsAdapter(str(root), query).get_structure()
    assert contracts._contract_observations(clean) is useful
    fault['denied'] = {root.resolve()}
    uri = f'contracts://{root.as_posix()}' + ('?' + query if query else '')
    result = run(uri, '--format', 'json', '--fields', 'total_contracts', '--max-items', '0', '--provenance')
    assert result.returncode == 3
    data = json.loads(result.stdout)
    assert data['total_contracts'] == 0
    _warning(data)
    assert bool(data.get('error')) is (not useful)
    assert data['execution']['command'].startswith('reveal contracts://')
    artifact = tmp_path / 'mirror.json'
    text = run(uri, '--also-json', str(artifact))
    assert text.returncode == 3 and artifact.exists()
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    _warning(saved)
    assert contracts.ContractsAdapter.execution_facts(saved).completeness is (
        AnalysisCompleteness.INCOMPLETE if useful else AnalysisCompleteness.FAILED)
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 1
    assert 'No contracts or seams found.' not in text.stdout + text.stderr
    assert 'Requested output failed' not in text.stderr
    if useful:
        assert 'Visible' in text.stdout
    assert fault['native'] and not fault['shared']


@pytest.mark.parametrize('positive,unknown', [(True, False), (False, True)])
def test_seven_real_coverage_events_preserve_all_evidence_and_requested_domain(tmp_path, fault, positive, unknown):
    if positive:
        _write(tmp_path / 'visible.py', ABC)
    children = []
    for number in range(7):
        child = tmp_path / f'included_{number}'
        _write(child / 'notes.txt', 'Included directory; missing source population remains unknown.\n')
        children.append(child.resolve())
    adapter = contracts.ContractsAdapter(str(tmp_path))
    clean = adapter.get_structure()
    fault.update(denied=set(children), unknown=unknown)
    result = adapter.get_structure()
    assert len(fault['events']) == 7
    if positive:
        assert _domain(result) == _domain(clean)
    else:
        assert result['total_contracts'] == 0
    warning = _warning(result)
    assert warning['count'] == (0 if unknown else 7)
    assert len(warning['directories']) == (0 if unknown else 5)
    if unknown:
        assert warning['unknown_directory_events'] == 7
    else:
        assert 'and 2 more' in warning['message']
    assert 'missing file population is unknown' in warning['message']
    assert contracts.ContractsAdapter.execution_facts(result).completeness is (
        AnalysisCompleteness.INCOMPLETE if positive else AnalysisCompleteness.FAILED)
    assert 'analysis_skipped' not in result and 'unparsed_files' not in result
    fault['denied'] = set()
    assert adapter.get_structure() == clean


def test_malformed_required_native_group_cannot_be_rescued_by_healthy_python_sibling(tmp_path, monkeypatch, fault):
    _write(tmp_path / 'visible.py', ABC)
    _write(tmp_path / 'other.go', GO)
    child = tmp_path / 'included'
    _write(child / 'notes.txt', 'Included scope.\n')
    real_scan = contracts._scan_contracts_go

    def malformed(*args, **kwargs):
        report = real_scan(*args, **kwargs)
        assert report['protocols']
        report['dataclasses'] = None
        return report

    monkeypatch.setattr(contracts, '_scan_contracts_go', malformed)
    fault['denied'] = {child.resolve()}
    result = contracts.ContractsAdapter(str(tmp_path)).get_structure()
    _warning(result)
    assert result.get('error')
    assert contracts.ContractsAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED
    assert result['by_language']['python']['abcs']
    text = run(f'contracts://{tmp_path.as_posix()}')
    assert text.returncode == 3
    assert 'Requested output failed' not in text.stderr
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 1


@pytest.mark.parametrize('transport', ['command', 'uri'])
def test_presentation_cannot_manufacture_availability_after_real_coverage_zero_failure(tmp_path, monkeypatch, fault, transport):
    root = tmp_path / 'empty'
    root.mkdir()
    sibling = tmp_path / 'healthy'
    _write(sibling / 'visible.py', ABC)
    replacement = contracts.ContractsAdapter(str(sibling)).get_structure()
    assert contracts._contract_observations(replacement)
    fault['denied'] = {root.resolve()}

    def apparent_success(self, result, args):
        return copy.deepcopy(replacement)

    monkeypatch.setattr(contracts.ContractsAdapter, 'post_process', apparent_success)
    args = ['contracts', str(root)] if transport == 'command' else [f'contracts://{root.as_posix()}']
    result = run(*args, '--format', 'json')
    assert fault['events']
    assert result.returncode == 3


def test_reused_adapter_and_sibling_repair_exactly_after_coverage_only_fault(tmp_path, fault):
    root = tmp_path / 'affected'
    _write(root / 'visible.py', ABC)
    _write(root / 'included' / 'foreign.lua', 'local x=1\n')
    sibling = tmp_path / 'sibling'
    _write(sibling / 'visible.rs', RUST)
    owner = contracts.ContractsAdapter(str(root))
    clean = owner.get_structure()
    sibling_clean = contracts.ContractsAdapter(str(sibling)).get_structure()
    fault['denied'] = {(root / 'included').resolve()}
    owner.get_structure()
    assert contracts.ContractsAdapter(str(sibling)).get_structure() == sibling_clean
    fault['denied'] = set()
    assert owner.get_structure() == clean
    assert clean['meta']['confidence'] == 0.7


def test_assess_default_pair_arguments_and_clean_zero_policy_unchanged(tmp_path):
    _write(tmp_path / 'plain.py', 'VALUE = 1\n')
    coverage = assess_language_coverage(tmp_path, {'python'})
    assert coverage.total_code_files == coverage.analyzed_files == 1
    assert coverage.to_scope_dict('contracts')['dominant_language'] == 'Python'
    result = contracts.ContractsAdapter(str(tmp_path)).get_structure()
    assert result['total_contracts'] == 0 and result['meta']['confidence'] == 0.7
    assert contracts.ContractsAdapter.execution_facts(result).completeness is AnalysisCompleteness.COMPLETE
    assert not any(warning.get('unit') == 'directories' for warning in result['meta']['warnings'])
