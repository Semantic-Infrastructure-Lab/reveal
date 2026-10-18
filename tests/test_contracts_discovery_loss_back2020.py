"""Contracts retains actual required traversal loss before rendering and projection."""
import copy
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters import contracts
from reveal.adapters.ast import analysis
from reveal.mcp_server import _ToolFailure, reveal_query
from reveal.utils.results import AnalysisCompleteness


SOURCES = {
    'py': ('from abc import ABC\nclass Hidden(ABC):\n    pass\n', 'VALUE = 1\n'),
    'go': ('package p\ntype Hidden interface { Go() }\n', 'package p\ntype Plain struct { Value int }\n'),
    'rs': ('trait Hidden { fn go(&self); }\n', 'struct Plain;\n'),
}


def make_tree(root, extension='py', survives=True, *, mixed=False, child='included_child'):
    hidden = root / child
    hidden.mkdir(parents=True)
    source, plain = SOURCES[extension]
    (hidden / ('hidden.' + extension)).write_text(source, encoding='utf-8')
    visible = source.replace('Hidden', 'Visible') if survives else plain
    if extension == 'rs' and survives:
        visible = 'struct Visible;\nimpl External for Visible { fn go(&self) {} }\n'
    (root / ('visible.' + extension)).write_text(visible, encoding='utf-8')
    if mixed:
        (root / 'constant.py').write_text('VALUE = 1\n', encoding='utf-8')
    return hidden


def lose_child(monkeypatch, root, mode, *, unknown=False, child='included_child'):
    active = []
    attempts = []
    real_scandir = os.scandir
    real_shared = analysis._walk_code_files
    real_native = contracts._collect_files
    real_activation = contracts._has_files

    def shared(*args, **kwargs):
        active.append('shared')
        try:
            yield from real_shared(*args, **kwargs)
        finally:
            active.pop()

    def native(*args, **kwargs):
        active.append('native')
        try:
            return real_native(*args, **kwargs)
        finally:
            active.pop()

    def activation(*args, **kwargs):
        active.append('activation')
        try:
            return real_activation(*args, **kwargs)
        finally:
            active.pop()

    def scandir(path):
        if (mode == 'all' or active and active[-1] == mode) and Path(path).resolve() == (root / child).resolve():
            attempts.append((str(path), active[-1] if active else 'other'))
            if unknown:
                raise PermissionError('controlled Contracts unknown directory loss')
            raise PermissionError(13, 'controlled Contracts directory loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(analysis, '_walk_code_files', shared)
    monkeypatch.setattr(contracts, '_collect_files', native)
    monkeypatch.setattr(contracts, '_has_files', activation)
    monkeypatch.setattr(os, 'scandir', scandir)
    return attempts


def directory_warning(result):
    warnings = [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_incomplete']
    assert len(warnings) == 1
    return warnings[0]


@pytest.mark.parametrize('extension,mode', [('py', 'shared'), ('py', 'activation'), ('py', 'all'), ('go', 'native'), ('rs', 'native')])
@pytest.mark.parametrize('survives', [False, True])
def test_actual_owned_loss_classifies_domain_rows_and_same_owner_repairs(tmp_path, monkeypatch, extension, mode, survives):
    root = tmp_path / 'root'
    make_tree(root, extension, survives)
    owner = contracts.ContractsAdapter(str(root))
    clean = owner.get_structure()
    with monkeypatch.context() as context:
        attempts = lose_child(context, root, mode)
        lost = owner.get_structure()
    assert attempts
    expected = AnalysisCompleteness.INCOMPLETE if survives else AnalysisCompleteness.FAILED
    assert owner.execution_facts(lost).completeness is expected
    warning = directory_warning(lost)
    assert warning['count'] == 1 and warning['unit'] == 'directories'
    assert warning['directories'] == ['included_child']
    assert 'missing file population is unknown' in warning['message']
    assert 'confidence' not in lost['meta']
    assert lost['meta']['parse_mode'] == clean['meta']['parse_mode'] == 'ast+tree_sitter'
    assert not any(key.startswith('_traversal') for key in lost)
    assert owner.get_structure() == clean
    assert clean['meta']['confidence'] == 0.7
    if extension == 'rs' and survives:
        assert lost['total_contracts'] == 0
        assert lost['dataclasses'][0]['name'] == 'Visible'


@pytest.mark.parametrize('transport', ['command', 'uri'])
@pytest.mark.parametrize('survives', [False, True])
def test_public_text_json_and_mcp_share_required_loss_policy(tmp_path, monkeypatch, transport, survives):
    root = tmp_path / 'root'
    make_tree(root, 'go', survives)
    attempts = lose_child(monkeypatch, root, 'native')
    argv = ['contracts', str(root)] if transport == 'command' else [f'contracts://{root.as_posix()}']
    machine = _run_reveal_direct(*argv, '--format', 'json', '--provenance')
    result = json.loads(machine.stdout)
    assert machine.returncode == 3
    assert directory_warning(result)['count'] == 1
    assert 'confidence' not in result['meta']
    text = _run_reveal_direct(*argv)
    assert text.returncode == 3
    combined = text.stdout + text.stderr
    assert combined.count('missing file population is unknown') == 1
    assert 'included_child' in combined
    assert 'No contracts or seams found.' not in combined
    response = reveal_query(f'contracts://{root.as_posix()}')
    assert isinstance(response, str if survives else _ToolFailure)
    if survives:
        assert 'Visible' in response
        assert response.count('missing file population is unknown') == 1
    assert attempts


def test_activation_loss_without_any_active_scanner_is_not_clean_zero(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    hidden = root / 'included_child'
    hidden.mkdir(parents=True)
    (hidden / 'hidden.py').write_text(SOURCES['py'][0], encoding='utf-8')
    attempts = lose_child(monkeypatch, root, 'activation')
    result = contracts.ContractsAdapter(str(root)).get_structure()
    assert attempts and result['total_contracts'] == 0
    assert contracts.ContractsAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED
    assert result['error']
    assert directory_warning(result)['count'] == 1


@pytest.mark.parametrize('survives', [False, True])
def test_unknown_directory_event_with_zero_identified_paths_still_loses_confidence(tmp_path, monkeypatch, survives):
    root = tmp_path / 'root'
    make_tree(root, 'py', survives)
    attempts = lose_child(monkeypatch, root, 'shared', unknown=True)
    result = contracts.ContractsAdapter(str(root)).get_structure()
    assert attempts
    warning = directory_warning(result)
    assert warning['count'] == 0 and warning['directories'] == []
    assert warning['unknown_directory_events'] == 1
    assert 'confidence' not in result['meta']
    expected = AnalysisCompleteness.INCOMPLETE if survives else AnalysisCompleteness.FAILED
    assert contracts.ContractsAdapter.execution_facts(result).completeness is expected


@pytest.mark.parametrize('query', ['abstract_only=true', 'implementations=false'])
def test_filtered_out_rust_implementation_does_not_prove_availability(tmp_path, monkeypatch, query):
    root = tmp_path / 'root'
    make_tree(root, 'rs', True)
    attempts = lose_child(monkeypatch, root, 'native')
    result = contracts.ContractsAdapter(str(root), query).get_structure()
    assert attempts and result['dataclasses'] == [] and result['total_contracts'] == 0
    assert contracts.ContractsAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED


@pytest.mark.parametrize('kind', ['name', 'line', 'bases', 'abstract_methods', 'implementations'])
def test_malformed_required_row_dominates_valid_contract_and_failed_text_is_safe(tmp_path, monkeypatch, kind):
    root = tmp_path / 'root'
    make_tree(root, 'py', True)
    original = contracts._scan_contracts_python

    def malformed(*args, **kwargs):
        result = original(*args, **kwargs)
        broken = copy.deepcopy(result['abcs'][0])
        broken.update({'name':'Broken', kind:{'name':' ', 'line':True, 'bases':[3], 'abstract_methods':[None],
                                           'implementations':[{'name':'Bad', 'file':'bad.py', 'line':False}]}[kind]})
        result['abcs'].append(broken)
        result['total_contracts'] += 1
        return result

    monkeypatch.setattr(contracts, '_scan_contracts_python', malformed)
    attempts = lose_child(monkeypatch, root, 'shared')
    response = _run_reveal_direct('contracts', str(root))
    machine = _run_reveal_direct('contracts', str(root), '--format', 'json')
    result = json.loads(machine.stdout)
    assert attempts
    assert response.returncode == machine.returncode == 3
    assert result['error']
    assert contracts.ContractsAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED
    assert 'missing file population is unknown' in response.stdout + response.stderr
    assert 'Traceback' not in response.stdout + response.stderr


@pytest.mark.parametrize('mixed', [False, True])
def test_native_enumeration_keeps_lazy_shared_collection_ownership(tmp_path, monkeypatch, mixed):
    root = tmp_path / 'root'
    make_tree(root, 'go', True)
    if mixed:
        (root / 'contract.py').write_text(SOURCES['py'][0], encoding='utf-8')
        (root / 'contract.ts').write_text('export interface Local { go():void; }\n', encoding='utf-8')
    shared_calls = []
    original = analysis.collect_structures

    def collect(*args, **kwargs):
        shared_calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(analysis, 'collect_structures', collect)
    attempts = lose_child(monkeypatch, root, 'native')
    result = contracts.ContractsAdapter(str(root)).get_structure()
    assert attempts
    assert len(shared_calls) == int(mixed)
    assert directory_warning(result)['count'] == 1


@pytest.mark.parametrize('kind', ['zero', 'unsupported', 'excluded', 'noise', 'sibling'])
def test_exact_policy_and_sibling_controls_stay_clean(tmp_path, monkeypatch, kind):
    root = tmp_path / 'root'
    if kind in ('excluded', 'noise', 'sibling'):
        make_tree(root, child='.git' if kind == 'noise' else 'included_child')
    else:
        root.mkdir()
        (root / ('constant.lua' if kind == 'unsupported' else 'constant.py')).write_text(
            'local value = 1\n' if kind == 'unsupported' else 'VALUE = 1\n', encoding='utf-8')
    argv = ['contracts', str(root), '--format', 'json']
    if kind == 'excluded':
        argv += ['--exclude', 'included_child']
    clean = _run_reveal_direct(*argv)
    target = tmp_path / 'unrelated' if kind in ('zero', 'unsupported', 'sibling') else root
    attempts = lose_child(monkeypatch, target, 'all', child='.git' if kind == 'noise' else 'included_child')
    actual = _run_reveal_direct(*argv)
    assert not attempts
    assert (actual.returncode, actual.stdout, actual.stderr) == (clean.returncode, clean.stdout, clean.stderr)
    result = json.loads(actual.stdout)
    assert contracts.ContractsAdapter.execution_facts(result).completeness is AnalysisCompleteness.COMPLETE
    assert result['meta']['confidence'] == 0.7
