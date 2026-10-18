"""Independent public consumers preserve required Imports loss before presentation."""

import copy
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.adapters.deps import DepsAdapter
from reveal.adapters.overview import OverviewAdapter
from reveal.analyzers.imports import file_index
from reveal.mcp_server import _ToolFailure, reveal_query
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
        query = '&'.join(part for part in ('no_git=true', query) if part)
    return f'{name}://{root.as_posix()}' + ('?' + query if query else '')


def invoke(name, root, transport='uri', *extra):
    command = [uri(name, root)] if transport == 'uri' else [name, str(root)]
    if transport == 'command' and name == 'overview':
        command.append('--no-git')
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
    query = 'no_git=true' if name == 'overview' else ''
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


def test_actual_stats_read_failure_is_not_file_inventory_proof(tmp_path, monkeypatch):
    import builtins
    from reveal.adapters.stats import StatsAdapter

    root = tmp_path / 'affected'
    tree(root, 'lost')
    visible = root / 'visible.py'
    write(visible, 'VALUE = 1\n')
    fail_child(monkeypatch, root)
    real_stats = StatsAdapter.get_structure
    real_open = builtins.open
    active = []
    reads = []
    observed_stats = []

    def stats(self, *args, **kwargs):
        active.append(True)
        try:
            result = real_stats(self, *args, **kwargs)
            observed_stats.append(copy.deepcopy(result))
            return result
        finally:
            active.pop()

    def open_file(path, *args, **kwargs):
        if active and isinstance(path, (str, Path)) and Path(path).resolve() == visible.resolve():
            reads.append(path)
            raise PermissionError(13, 'independent Stats-only read denial', str(visible))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(StatsAdapter, 'get_structure', stats)
    monkeypatch.setattr(builtins, 'open', open_file)
    response = invoke('overview', root)
    result = json.loads(response.stdout)
    assert reads
    assert observed_stats[0]['files'] == [] and observed_stats[0]['summary']['total_files'] == 0
    assert response.returncode == 3
    assert OverviewAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED


@pytest.mark.parametrize('malformed', ['missing_lines', 'boolean_total', 'bad_partition'])
def test_stats_path_or_invalid_measurements_do_not_rescue_directory_loss(tmp_path, monkeypatch, malformed):
    from reveal.adapters.stats import StatsAdapter

    root = tmp_path / 'affected'
    tree(root, 'lost')
    write(root / 'visible.py', 'VALUE = 1\n')
    fail_child(monkeypatch, root)
    real_stats = StatsAdapter.get_structure

    def stats(self, *args, **kwargs):
        result = real_stats(self, *args, **kwargs)
        (entry,) = result['files']
        if malformed == 'missing_lines':
            entry.pop('lines')
        elif malformed == 'boolean_total':
            entry['lines']['total'] = True
        else:
            entry['lines']['total'] += 1
        return result

    monkeypatch.setattr(StatsAdapter, 'get_structure', stats)
    response = invoke('overview', root)
    result = json.loads(response.stdout)
    assert response.returncode == 3
    assert OverviewAdapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED


def test_actual_degraded_stats_retains_useful_physical_line_observation(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    tree(root, 'lost')
    write(root / 'broken.py', 'def broken(\n')
    fail_child(monkeypatch, root)
    response = invoke('overview', root)
    result = json.loads(response.stdout)
    (entry,) = result['stats']['files']
    assert entry['parse_degraded'] is True
    lines = entry['lines']
    assert lines['total'] == lines['code'] + lines['empty'] + lines['comments']
    assert response.returncode == 3
    assert OverviewAdapter.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE
