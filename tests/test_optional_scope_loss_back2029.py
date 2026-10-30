"""Canonical maps retain required census loss and isolate composed diagnostics."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import architecture, overview
from reveal.mcp_server import reveal_query
from reveal.utils.exclusions import exclusion_scope
from reveal.utils.results import AnalysisCompleteness

pytestmark = pytest.mark.component
OWNERS = {'architecture': (overview, architecture.ArchitectureAdapter),
          'overview': (overview, overview.OverviewAdapter)}


def project(root, *, empty=False):
    child = root / 'included_child'
    child.mkdir(parents=True)
    if not empty:
        (root / 'visible.py').write_text('def hot(x):\n' + ''.join(
            f'    if x == {n}: return {n}\n' for n in range(12)) + '    return 0\n', encoding='utf-8')
        (child / 'hidden.lua').write_text('local value = 1\n', encoding='utf-8')
    return child


def query(kind):
    return 'top=0'


def owner(kind, root):
    return OWNERS[kind][1](str(root), query(kind))


def uri(kind, root):
    return f'{kind}://{root}?{query(kind)}'


def fault(monkeypatch, kind, paths, *, unknown=False, combined=False, exception=False):
    module = OWNERS[kind][0]
    real_scope, real_scandir = module.scope_dict_for_path, os.scandir
    state = {'active': False, 'events': [], 'enabled': True, 'calls': 0}

    def scope(*args, **kwargs):
        state['calls'] += 1
        if exception and state['enabled']:
            raise RuntimeError('controlled ordinary optional scope failure')
        state['active'] = True
        try:
            return real_scope(*args, **kwargs)
        finally:
            state['active'] = False

    def scandir(path):
        if state['enabled'] and Path(path) in paths and (state['active'] or combined):
            state['events'].append(('scope' if state['active'] else 'analysis', str(path)))
            if unknown:
                raise PermissionError('controlled optional scope unknown directory')
            raise PermissionError(13, 'controlled optional scope directory loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(module, 'scope_dict_for_path', scope)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def directory_warnings(result):
    return [w for w in result.get('meta', {}).get('warnings', [])
            if w.get('type') == 'analysis_incomplete' and w.get('unit') == 'directories']


def required_exception(kind, result):
    assert result['scope'] == {}
    meta = result['meta']
    errors = [e for e in meta['errors'] if e.get('code') == 'E_COMPOSE']
    assert len(errors) == 1
    assert 'scope_dict_for_path' in errors[0]['message']
    assert meta['confidence'] == 0.0
    assert result['map_status'] == 'failed'
    assert OWNERS[kind][1].execution_facts(result).completeness is AnalysisCompleteness.FAILED


def partial_census(kind, result):
    assert result['scope']['complete'] is False
    assert not result.get('meta', {}).get('errors')
    assert OWNERS[kind][1].execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE


@pytest.mark.parametrize('kind', OWNERS)
@pytest.mark.parametrize('empty', [False, True])
@pytest.mark.parametrize('lost', ['root', 'child'])
def test_actual_required_scope_loss_retains_counts_even_empty_and_top_zero(tmp_path, monkeypatch, kind, empty, lost):
    root = tmp_path / 'affected'; child = project(root, empty=empty)
    clean = owner(kind, root).get_structure()
    state = fault(monkeypatch, kind, {root if lost == 'root' else child})
    result = owner(kind, root).get_structure()
    assert state['events'] and all(stage == 'scope' for stage, _ in state['events'])
    assert state['calls'] == 1
    assert result['map'] == clean['map']
    assert result['scope']['total_code_files'] == (0 if empty or lost == 'root' else 1)
    partial_census(kind, result)
    warning, = directory_warnings(result)
    assert warning['count'] == 1 and 'PermissionError' in warning['message']
    assert 'missing file population is unknown' in warning['message']


@pytest.mark.parametrize('kind', OWNERS)
@pytest.mark.parametrize('empty', [False, True])
def test_required_nonwalk_scope_exception_is_failed(tmp_path, monkeypatch, kind, empty):
    root = tmp_path / 'affected'; project(root, empty=empty)
    state = fault(monkeypatch, kind, set(), exception=True)
    result = owner(kind, root).get_structure()
    assert not state['events']
    required_exception(kind, result)
    assert directory_warnings(result) == []


@pytest.mark.parametrize('kind', OWNERS)
def test_unknown_events_survive_without_invented_named_population(tmp_path, monkeypatch, kind):
    root = tmp_path / 'affected'; project(root)
    children = {root / f'part{n}' for n in range(7)}
    for child in children:
        child.mkdir(); (child / 'a.py').write_text('VALUE = 1\n', encoding='utf-8')
    state = fault(monkeypatch, kind, children, unknown=True)
    result = owner(kind, root).get_structure()
    assert len(state['events']) == 7
    partial_census(kind, result)
    warning, = directory_warnings(result)
    assert warning['count'] == 0 and warning['unknown_directory_events'] == 7


@pytest.mark.parametrize('kind', OWNERS)
@pytest.mark.parametrize('view', ['text', 'projection', 'artifact'])
def test_public_views_retain_required_census_loss_and_attributed_disclosure(tmp_path, monkeypatch, kind, view):
    root = tmp_path / 'affected'; project(root)
    state = fault(monkeypatch, kind, {root})
    artifact = tmp_path / 'answer.json'
    flags = ['--provenance']
    if view == 'projection':
        flags += ['--format', 'json', '--fields', 'scope', '--max-items', '0']
    else:
        flags += ['--format', 'text']
        if view == 'artifact':
            flags += ['--also-json', str(artifact)]
    response = run(uri(kind, root), *flags)
    assert state['events']
    assert response.returncode == 3
    if view in {'projection', 'artifact'}:
        result = json.loads(response.stdout if view == 'projection' else artifact.read_text(encoding='utf-8'))
        partial_census(kind, result)
        assert len(directory_warnings(result)) == 1
        assert result['execution']
    else:
        assert 'missing file population is unknown' in response.stdout + response.stderr


@pytest.mark.parametrize('kind', OWNERS)
def test_reused_owner_and_decorated_host_repair_without_manual_clears(tmp_path, monkeypatch, kind):
    root = tmp_path / 'affected'; project(root)
    sibling = tmp_path / 'sibling'; project(sibling)
    adapter = owner(kind, root)
    baseline = adapter.get_structure()
    sibling_clean = owner(kind, sibling).get_structure()
    state = fault(monkeypatch, kind, {root})
    result = adapter.get_structure()
    assert state['events']
    partial_census(kind, result)
    wire = reveal_query(uri(kind, root), provenance=True)
    assert isinstance(wire, str)
    partial_census(kind, json.loads(wire))
    assert owner(kind, sibling).get_structure() == sibling_clean
    state['enabled'] = False
    assert adapter.get_structure() == baseline
    repaired = json.loads(reveal_query(uri(kind, root), provenance=True))
    assert repaired['scope'] == baseline['scope']
    assert not directory_warnings(repaired)


@pytest.mark.parametrize('kind', OWNERS)
def test_real_required_source_failure_remains_failed_with_census_loss(tmp_path, monkeypatch, kind):
    root = tmp_path / 'affected'; project(root)
    state = fault(monkeypatch, kind, {root}, combined=True)
    result = owner(kind, root).get_structure()
    assert {stage for stage, _ in state['events']} == {'analysis', 'scope'}
    assert OWNERS[kind][1].execution_facts(result).completeness is AnalysisCompleteness.FAILED
    assert any(e.get('code') == 'E_OVERVIEW_ANALYSIS'
               for e in result['meta']['errors'])
    assert result['scope']['complete'] is False


def test_overview_explicit_exclusion_does_not_become_failed_scope(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; child = project(root)
    with exclusion_scope(root, ['included_child']):
        clean = owner('overview', root).get_structure()
        state = fault(monkeypatch, 'overview', {child})
        result = owner('overview', root).get_structure()
    assert state['events'] == [] and result == clean
    assert result['scope']['total_code_files'] == 1


def test_required_overview_census_exception_is_failed_and_repairs(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    project(root)
    adapter = owner('overview', root)
    baseline = adapter.get_structure()
    state = fault(monkeypatch, 'overview', set(), exception=True)
    failed = adapter.get_structure()
    assert failed['scope'] == {} and failed['map_status'] == 'failed'
    assert adapter.execution_facts(failed).completeness is AnalysisCompleteness.FAILED
    assert any('scope_dict_for_path' in error['message'] for error in failed['meta']['errors'])
    state['enabled'] = False
    assert adapter.get_structure() == baseline


def test_required_overview_census_loss_retains_surviving_count(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    child = project(root)
    state = fault(monkeypatch, 'overview', {child})
    result = owner('overview', root).get_structure()
    assert state['events'] and result['scope']['total_code_files'] == 1
    assert result['scope']['complete'] is False
    assert overview.OverviewAdapter.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE
    warning, = directory_warnings(result)
    assert warning['count'] == 1 and warning['directories'] == ['included_child']
