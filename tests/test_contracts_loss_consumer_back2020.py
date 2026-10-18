"""Independent public Contracts consumers retain producer loss before output cuts."""
import copy
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import contracts
from reveal.adapters.ast import analysis
from reveal.utils.results import AnalysisCompleteness

pytestmark = pytest.mark.component
PYTHON = 'from abc import ABC\nclass Visible(ABC):\n    pass\n'
GO = 'package p\ntype Visible interface { Go() }\n'
RUST = 'struct Visible;\nimpl External for Visible { fn go(&self) {} }\n'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def fixture(root, family='py', useful=True):
    child = root / 'included_child'
    source = GO if family == 'go' else PYTHON
    write(child / ('hidden.' + family), source.replace('Visible', 'Hidden'))
    if useful:
        write(root / ('visible.' + family), source)
    return child


def fault(monkeypatch, child, mode='all', *, unknown=False):
    state = {'stage': None, 'attempts': [], 'shared_calls': 0}
    real_has = contracts._has_files
    real_collect = contracts._collect_files
    real_walk = analysis._walk_code_files
    real_structures = analysis.collect_structures
    real_scandir = os.scandir

    def has(*args, **kwargs):
        previous = state['stage']; state['stage'] = 'activation'
        try:
            return real_has(*args, **kwargs)
        finally:
            state['stage'] = previous

    def collect(*args, **kwargs):
        previous = state['stage']; state['stage'] = 'native'
        try:
            return real_collect(*args, **kwargs)
        finally:
            state['stage'] = previous

    def walk(*args, **kwargs):
        previous = state['stage']; state['stage'] = 'shared'
        try:
            yield from real_walk(*args, **kwargs)
        finally:
            state['stage'] = previous

    def structures(*args, **kwargs):
        state['shared_calls'] += 1
        return real_structures(*args, **kwargs)

    def scandir(path):
        # 'all' covers all source populations; the independent coverage census stays healthy.
        if state['stage'] is not None and Path(path) == child and (mode == 'all' or mode == state['stage']):
            state['attempts'].append(state['stage'])
            if unknown:
                raise PermissionError('controlled unlocated Contracts consumer directory loss')
            raise PermissionError(13, 'controlled Contracts consumer directory loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(contracts, '_has_files', has)
    monkeypatch.setattr(contracts, '_collect_files', collect)
    monkeypatch.setattr(analysis, '_walk_code_files', walk)
    monkeypatch.setattr(analysis, 'collect_structures', structures)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def request(root, transport):
    return ['contracts', str(root)] if transport == 'command' else ['contracts://' + str(root)]


def directory_warning(result):
    warnings = [entry for entry in result['meta']['warnings']
                if entry.get('type') == 'analysis_incomplete' and entry.get('unit') == 'directories']
    assert len(warnings) == 1
    return warnings[0]


@pytest.mark.parametrize('transport', ['command', 'uri'])
@pytest.mark.parametrize('family,mode', [('py', 'activation'), ('py', 'shared'), ('go', 'native'), ('py', 'all')])
@pytest.mark.parametrize('useful', [False, True])
def test_actual_loss_public_json_and_text_keep_domain_outcome(tmp_path, monkeypatch, transport, family, mode, useful):
    root = tmp_path / 'affected'; child = fixture(root, family, useful)
    state = fault(monkeypatch, child, mode)
    response = run(*request(root, transport), '--format', 'json')
    assert state['attempts']
    result = json.loads(response.stdout)
    assert response.returncode == 3
    if mode == 'all':
        assert result['coverage']['total_code_files'] == 1 + int(useful)
    expected = AnalysisCompleteness.INCOMPLETE if useful else AnalysisCompleteness.FAILED
    assert contracts.ContractsAdapter.execution_facts(result).completeness is expected
    assert bool(result.get('error')) is (not useful)
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'ast+tree_sitter'
    directory_warning(result)
    text = run(*request(root, transport))
    assert text.returncode == 3
    combined = text.stdout + text.stderr
    assert combined.count('identified directory enumeration(s) failed') == 1
    assert 'PermissionError' in combined
    assert 'Requested output failed' not in combined
    assert 'No contracts or seams found.' not in combined
    if useful:
        assert 'Visible' in text.stdout


@pytest.mark.parametrize('useful', [False, True])
@pytest.mark.parametrize('transport', ['command', 'uri'])
def test_facts_survive_projection_and_json_artifact(tmp_path, monkeypatch, useful, transport):
    root = tmp_path / 'affected'; child = fixture(root, useful=useful)
    fault(monkeypatch, child)
    projected = run(*request(root, transport), '--format', 'json', '--fields', 'path')
    assert projected.returncode == 3
    assert json.loads(projected.stdout)['path'] == str(root)
    artifact = tmp_path / (transport + '.json')
    text = run(*request(root, transport), '--also-json', str(artifact), '--fail-on', 'none')
    assert text.returncode == 3 and artifact.exists()
    result = json.loads(artifact.read_text(encoding='utf-8'))
    directory_warning(result)
    assert bool(result.get('error')) is (not useful)
    assert 'confidence' not in result['meta']


@pytest.mark.parametrize('provenance', [False, True])
@pytest.mark.parametrize('useful', [False, True])
def test_decorated_generic_query_distinguishes_useful_partial_and_failed(tmp_path, monkeypatch, provenance, useful):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    root = tmp_path / 'affected'; child = fixture(root, useful=useful)
    fault(monkeypatch, child, unknown=True)
    result = reveal_query('contracts://' + str(root), provenance=provenance)
    assert isinstance(result, _ToolFailure) is (not useful)
    if useful:
        assert 'unknown directory' in result
    if useful and provenance:
        data = json.loads(result)
        assert data['execution']['command'].startswith('reveal contracts://')
        assert directory_warning(data)['count'] == 0
        assert 'confidence' not in data['meta']
    elif useful:
        assert 'Visible' in result
    else:
        assert 'reveal error:' in result


@pytest.mark.parametrize('query,expected', [('', AnalysisCompleteness.INCOMPLETE),
                                           ('impls=0', AnalysisCompleteness.INCOMPLETE),
                                           ('abstract_only=true', AnalysisCompleteness.FAILED),
                                           ('implementations=false', AnalysisCompleteness.FAILED)])
def test_zero_total_external_rust_implementer_is_requested_domain_evidence(tmp_path, monkeypatch, query, expected):
    root = tmp_path / 'affected'
    child = root / 'included_child'
    write(child / 'hidden.py', PYTHON)
    write(root / 'visible.rs', RUST)
    fault(monkeypatch, child, 'shared')
    owner = contracts.ContractsAdapter(str(root), query)
    result = owner.get_structure()
    assert result['total_contracts'] == 0
    assert owner.execution_facts(result).completeness is expected
    response = run('contracts://' + str(root) + ('?' + query if query else ''))
    assert response.returncode == 3
    assert 'No contracts or seams found.' not in response.stdout + response.stderr
    if expected is AnalysisCompleteness.INCOMPLETE:
        assert 'Implementing Types' in response.stdout and 'Visible' in response.stdout


@pytest.mark.parametrize('kind', ['bool_line', 'blank_file', 'bases', 'abstract_methods', 'implementations', 'group'])
def test_malformed_actual_scanner_row_dominates_valid_row_without_output_failure(tmp_path, monkeypatch, kind):
    root = tmp_path / 'affected'; child = fixture(root, family='go')
    fault(monkeypatch, child, 'native')
    original = contracts._scan_contracts_go

    def malformed(*args, **kwargs):
        report = original(*args, **kwargs)
        row = copy.deepcopy(report['protocols'][0])
        if kind == 'bool_line':
            row['line'] = True
        elif kind == 'blank_file':
            row['file'] = '  '
        elif kind == 'bases':
            row['bases'] = [7]
        elif kind == 'abstract_methods':
            row['abstract_methods'] = 'wrong shape'
        elif kind == 'implementations':
            row['implementations'] = [{'name': 'Bad', 'file': 'bad.go', 'line': 0}]
        if kind == 'group':
            report['abcs'] = {'wrong': 'list shape'}
        else:
            report['protocols'].append(row)
        return report

    monkeypatch.setattr(contracts, '_scan_contracts_go', malformed)
    # The text boundary must avoid consuming malformed rows after authoring FAILED.
    result = contracts.ContractsAdapter(str(root)).get_structure()
    assert result.get('error')
    assert contracts.ContractsAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED
    assert any(entry.get('code') == 'E_CONTRACTS_DISCOVERY' for entry in result['meta']['errors'])
    response = run('contracts://' + str(root))
    assert response.returncode == 3
    assert 'Requested output failed' not in response.stderr
    assert (response.stdout + response.stderr).count('identified directory enumeration(s) failed') == 1


@pytest.mark.parametrize('kind', ['zero', 'unsupported', 'parse_only', 'excluded', 'noise'])
def test_clean_and_preexisting_non_directory_policies_keep_confidence(tmp_path, monkeypatch, kind):
    root = tmp_path / 'affected'
    if kind == 'unsupported':
        write(root / 'visible.lua', 'local x = 1\n')
    elif kind == 'parse_only':
        write(root / 'visible.py', PYTHON + 'broken = (\n')
    else:
        write(root / 'visible.py', 'VALUE = 1\n')
    child = root / ('node_modules' if kind == 'noise' else 'included_child')
    if kind in {'excluded', 'noise'}:
        write(child / 'hidden.py', PYTHON)
    fault(monkeypatch, child)
    args = request(root, 'command') + ['--format', 'json']
    if kind == 'excluded':
        args += ['--exclude', 'included_child']
    response = run(*args)
    result = json.loads(response.stdout)
    assert result['meta']['confidence'] == 0.7
    assert not any(entry.get('unit') == 'directories' for entry in result['meta']['warnings'])
    assert response.returncode == (3 if kind == 'parse_only' else 0)
