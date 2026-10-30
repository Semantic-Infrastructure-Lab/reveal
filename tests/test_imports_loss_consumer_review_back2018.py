"""Independent public consumers preserve required Imports loss before presentation."""

import copy
import json
import os
from pathlib import Path

import pytest

from reveal.analyzers.imports.views import ImportView

from conftest import _run_reveal_direct
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.adapters.deps import DepsAdapter
from reveal.adapters.overview import OverviewAdapter
from reveal.analyzers.imports import file_index
from reveal.mcp_server import _ToolFailure, reveal_query
from reveal.utils.request_cache import reset_request_caches
from reveal.utils.results import AnalysisCompleteness


OWNERS = {'deps':DepsAdapter, 'architecture':ArchitectureAdapter, 'overview':OverviewAdapter}


def write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


def tree(root, kind):
    child = root / 'included_child'
    write(child / 'hidden.py', 'import math\n\ndef hidden():\n    return math.pi\n')
    if kind == 'edges':
        write(root / 'visible.py', 'import stable\n\ndef visible():\n    return stable.VALUE\n')
        write(root / 'stable.py', 'VALUE = 1\n')
    elif kind == 'ast':
        source = 'def complicated(value):\n'
        source += ''.join(f'    if value == {number}:\n        return {number}\n' for number in range(11))
        write(root / 'visible.py', source + '    return -1\n')
    elif kind == 'relative':
        write(root / '__init__.py', 'from . import helper\n')
        write(root / 'helper.py', 'VALUE = 1\n')
    return child


def fail_child(monkeypatch, root, *, resolution_only=False):
    child = root / 'included_child'
    real_scandir = os.scandir
    real_walk = file_index.walk_with_causes
    active = []
    attempts = []

    def walk(*args, **kwargs):
        active.append(True)
        try:
            yield from real_walk(*args, **kwargs)
        finally:
            active.pop()

    def scandir(path):
        if (not resolution_only or active) and Path(path).resolve() == child.resolve():
            attempts.append(Path(path))
            raise PermissionError(13, 'independent required Imports child loss', str(child))
        return real_scandir(path)

    monkeypatch.setattr(file_index, 'walk_with_causes', walk)
    monkeypatch.setattr(os, 'scandir', scandir)
    return attempts


def uri(name, root, query=''):
    if name == 'overview':
        query = '&'.join(part for part in ('', query) if part)
    return f'{name}://{root.as_posix()}' + ('?' + query if query else '')


def invoke(name, root, transport='uri', *extra):
    command = [uri(name, root)] if transport == 'uri' else [name, str(root)]
    return _run_reveal_direct(*command, '--format', 'json', *extra)


@pytest.mark.parametrize('name', OWNERS)
@pytest.mark.parametrize('transport', ['command', 'uri'])
def test_actual_total_required_loss_is_failed_in_both_public_spellings(tmp_path, monkeypatch, name, transport):
    root = tmp_path / 'affected'
    tree(root, 'lost')
    attempts = fail_child(monkeypatch, root)
    response = invoke(name, root, transport)
    result = json.loads(response.stdout)
    assert attempts
    assert response.returncode == 3
    assert OWNERS[name].execution_facts(result).completeness is AnalysisCompleteness.FAILED
    assert any(warning.get('type') == 'analysis_incomplete' for warning in result['meta']['warnings'])


@pytest.mark.parametrize('name', OWNERS)
def test_actual_total_required_loss_is_mcp_failure_not_successful_string(tmp_path, monkeypatch, name):
    root = tmp_path / 'affected'
    tree(root, 'lost')
    attempts = fail_child(monkeypatch, root)
    result = reveal_query(uri(name, root), provenance=True)
    assert attempts
    assert isinstance(result, _ToolFailure)


@pytest.mark.parametrize('name', OWNERS)
def test_valid_surviving_relationships_are_incomplete_and_repair_restores_exact_output(tmp_path, monkeypatch, name):
    root = tmp_path / 'affected'
    tree(root, 'edges')
    baseline = invoke(name, root)
    with monkeypatch.context() as context:
        attempts = fail_child(context, root)
        response = invoke(name, root)
        result = json.loads(response.stdout)
        assert attempts and response.returncode == 3
        assert OWNERS[name].execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE
        assert not isinstance(reveal_query(uri(name, root), provenance=True), _ToolFailure)
    reset_request_caches()  # the repair is a new request; only the MCP host resets, not in-process main()
    repaired = invoke(name, root)
    assert (repaired.returncode, repaired.stdout, repaired.stderr) == (
        baseline.returncode, baseline.stdout, baseline.stderr)


def test_relative_import_with_empty_module_is_a_real_uncapped_deps_observation(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    tree(root, 'relative')
    fail_child(monkeypatch, root)
    result = DepsAdapter(str(root)).get_structure()
    imports = [entry for entries in result['base']['files'].values() for entry in entries]
    (statement,) = imports
    assert statement['module'] == '' and statement['names'] == ['helper']
    assert statement['is_relative'] is True and statement['line'] == 1
    assert DepsAdapter.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE


def test_actual_top_zero_keeps_authoritative_ast_domain_count_proof(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    tree(root, 'ast')
    fail_child(monkeypatch, root)
    response = _run_reveal_direct(uri('architecture', root, 'top=0'), '--format', 'json')
    result = json.loads(response.stdout)
    assert response.returncode == 3
    assert ArchitectureAdapter.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE
    assert not result.get('error')


@pytest.mark.parametrize('name', OWNERS)
def test_preprojection_failed_facts_survive_manufactured_healthy_postprocessing(tmp_path, monkeypatch, name):
    root, sibling = tmp_path / 'affected', tmp_path / 'sibling'
    tree(root, 'lost')
    tree(sibling, 'edges')
    query = '' if name == 'overview' else ''
    healthy = OWNERS[name](str(sibling), query).get_structure()
    assert OWNERS[name].execution_facts(healthy).completeness is AnalysisCompleteness.COMPLETE
    fail_child(monkeypatch, root)

    def manufacture(self, result, args):
        return copy.deepcopy(healthy)

    monkeypatch.setattr(OWNERS[name], 'post_process', manufacture, raising=False)
    response = invoke(name, root)
    assert response.returncode == 3
    assert isinstance(reveal_query(uri(name, root), provenance=True), _ToolFailure)


@pytest.mark.parametrize('name', OWNERS)
def test_required_loss_survives_fields_artifact_and_provenance(tmp_path, monkeypatch, name):
    root = tmp_path / 'affected'
    tree(root, 'lost')
    fail_child(monkeypatch, root)
    artifact = tmp_path / 'answer.json'
    text = _run_reveal_direct(uri(name, root), '--also-json', str(artifact))
    assert text.returncode == 3
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    assert OWNERS[name].execution_facts(saved).completeness is AnalysisCompleteness.FAILED
    machine = invoke(name, root, 'uri', '--fields', 'type', '--provenance')
    assert machine.returncode == 3
    selected = json.loads(machine.stdout)
    assert selected['type'] == saved['type'] and selected['execution']['command']
    assert selected['meta']['warnings']


@pytest.mark.parametrize('name', OWNERS)
def test_exact_healthy_and_explicitly_excluded_siblings_stay_unchanged(tmp_path, monkeypatch, name):
    root, sibling = tmp_path / 'affected', tmp_path / 'sibling'
    tree(root, 'edges')
    tree(sibling, 'edges')
    baseline = invoke(name, sibling)
    excluded = invoke(name, root, 'uri', '--exclude', 'included_child')
    attempts = fail_child(monkeypatch, root)
    after = invoke(name, sibling)
    after_excluded = invoke(name, root, 'uri', '--exclude', 'included_child')
    assert (baseline.returncode, baseline.stdout, baseline.stderr) == (after.returncode, after.stdout, after.stderr)
    assert (excluded.returncode, excluded.stdout, excluded.stderr) == (
        after_excluded.returncode, after_excluded.stdout, after_excluded.stderr)
    assert attempts == []








@pytest.mark.parametrize('malformation', ['boolean_internal', 'negative_incoming', 'malformed_cycle'])
def test_malformed_relationship_sibling_dominates_real_stats_and_edges(tmp_path, monkeypatch, malformation):
    from reveal.adapters.imports import ImportsAdapter
    root = tmp_path / 'affected'
    tree(root, 'edges')
    original_components = ImportView.components
    original_circular = ImportView.circular

    def components(adapter):
        data = original_components(adapter)
        if malformation != 'malformed_cycle':
            assert data['components']
            data['components'][0]['internal' if malformation == 'boolean_internal' else 'incoming'] = (
                True if malformation == 'boolean_internal' else -1)
        return data

    def circular(adapter):
        data = original_circular(adapter)
        if malformation == 'malformed_cycle':
            data['cycles'] = [['visible.py', 4]]
            data['count'] = 1
        return data

    monkeypatch.setattr(ImportView, 'components', components)
    monkeypatch.setattr(ImportView, 'circular', circular)
    attempts = fail_child(monkeypatch, root)
    response = invoke('overview', root)
    result = json.loads(response.stdout)
    assert attempts
    assert response.returncode == 3
    assert OverviewAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED
