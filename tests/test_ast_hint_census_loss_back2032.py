"""AST capability hints disclose their own census loss without changing analysis policy."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import capabilities
from reveal.adapters.ast.adapter import AstAdapter
from reveal.mcp_server import reveal_query
from reveal.utils import path_utils

pytestmark = pytest.mark.component
MODES = ['show=dict-heatmap', 'show=dict-schemas', 'reveal_type=cfg']
PYTHON = ''.join(f'def consumer_{n}(cfg):\n    return cfg["a"] + cfg["b"] + cfg["c"]\n\n' for n in range(3))


def project(root, *, python=True, foreign=True, pure=False):
    root.mkdir(parents=True)
    if python:
        (root / 'visible.py').write_text('VALUE = 1\n' if pure else PYTHON, encoding='utf-8')
    child = root / 'included_child'
    if foreign:
        child.mkdir()
        for n in range(3):
            (child / f'hidden{n}.lua').write_text('local value = 1\n', encoding='utf-8')
    return child


def fault(monkeypatch, paths, *, unknown=False):
    real_warning, real_scandir = capabilities.python_only_warning, os.scandir
    state = {'active': False, 'events': [], 'enabled': True, 'calls': 0}

    def warning(*args, **kwargs):
        state['calls'] += 1
        state['active'] = True
        try:
            return real_warning(*args, **kwargs)
        finally:
            state['active'] = False

    def scandir(path):
        if state['enabled'] and state['active'] and Path(path) in paths:
            state['events'].append(str(path))
            if unknown:
                raise PermissionError('controlled AST capability census unknown directory')
            raise PermissionError(13, 'controlled AST capability census directory loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(capabilities, 'python_only_warning', warning)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def body(result):
    return {key: value for key, value in result.items() if key != 'meta'}


def directory_warning(result):
    warnings = [w for w in result['meta']['warnings']
                if w.get('type') == 'analysis_incomplete' and w.get('unit') == 'directories']
    assert len(warnings) == 1
    warning = warnings[0]
    message = warning['message'].lower()
    assert 'capability' in message and 'census' in message
    assert 'missing file population is unknown' in message
    assert 'python rows' not in message and 'failed parsing' not in message
    return warning


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('lost', ['child', 'root'])
def test_actual_hint_census_loss_preserves_healthy_analysis_and_domain_prior(tmp_path, monkeypatch, mode, lost):
    root = tmp_path / 'affected'; child = project(root)
    clean = AstAdapter(str(root), mode).get_structure()
    assert clean['total_results'] == (1 if mode == 'show=dict-schemas' else 3)
    state = fault(monkeypatch, {root if lost == 'root' else child})
    result = AstAdapter(str(root), mode).get_structure()
    assert state['events'] and state['calls'] == 1
    assert body(result) == body(clean)
    assert result['meta']['confidence'] == 1.0
    assert result['meta']['parse_mode'] == clean['meta']['parse_mode']
    assert not result.get('error') and result['meta']['errors'] == []
    warning = directory_warning(result)
    assert warning['count'] == 1 and 'PermissionError' in warning['message']


@pytest.mark.parametrize('mode', MODES)
def test_foreign_observations_and_hint_uncertainty_coexist(tmp_path, monkeypatch, mode):
    root = tmp_path / 'affected'; child = project(root)
    (root / 'visible.lua').write_text('local kept = 1\n', encoding='utf-8')
    state = fault(monkeypatch, {child})
    result = AstAdapter(str(root), mode).get_structure()
    assert state['events']
    warning, = [w for w in result['meta']['warnings'] if w.get('code') == 'W-CAP-1']
    assert '1 file(s)' in warning['message'] and 'lua (1)' in warning['message']
    directory_warning(result)


@pytest.mark.parametrize('profile', ['python_zero', 'unsupported'])
def test_unknown_events_are_advisory_even_when_domain_rows_are_empty(tmp_path, monkeypatch, profile):
    root = tmp_path / 'affected'
    project(root, python=profile != 'unsupported', foreign=profile == 'unsupported', pure=True)
    children = {root / f'part{n}' for n in range(7)}
    for child in children:
        child.mkdir(); (child / 'a.lua').write_text('local x = 1\n', encoding='utf-8')
    clean = AstAdapter(str(root), MODES[0]).get_structure()
    assert clean['total_results'] == 0
    state = fault(monkeypatch, children, unknown=True)
    result = AstAdapter(str(root), MODES[0]).get_structure()
    assert len(state['events']) == 7 and body(result) == body(clean)
    assert result['meta']['confidence'] == 1.0 and not result.get('error')
    warning = directory_warning(result)
    assert warning['count'] == 0 and warning['unknown_directory_events'] == 7


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('format', ['text', 'grep'])
def test_native_human_and_grep_channels_disclose_hint_loss_once(tmp_path, monkeypatch, mode, format):
    root = tmp_path / 'affected'; child = project(root)
    uri = f'ast://{root}?{mode}'
    clean = run(uri, '--format', format)
    state = fault(monkeypatch, {child})
    response = run(uri, '--format', format)
    assert state['events'] and response.returncode == clean.returncode == 0
    combined = response.stdout + response.stderr
    assert combined.count('missing file population is unknown') == 1
    assert 'capability' in combined.lower()
    if format == 'grep':
        assert response.stdout == clean.stdout
        assert 'missing file population is unknown' in response.stderr
        assert 'directory' not in response.stdout


@pytest.mark.parametrize('mode,view', list(zip(MODES, ['json', 'projection', 'artifact'])))
def test_json_projection_and_artifact_keep_disclosure_and_prior(tmp_path, monkeypatch, mode, view):
    root = tmp_path / 'affected'; project(root)
    state = fault(monkeypatch, {root})
    artifact = tmp_path / 'answer.json'
    flags = ['--provenance']
    if view == 'artifact':
        flags += ['--format', 'text', '--also-json', str(artifact)]
    else:
        flags += ['--format', 'json']
        if view == 'projection':
            flags += ['--fields', 'results,total_results', '--max-items', '0']
    response = run(f'ast://{root}?{mode}', *flags)
    assert state['events'] and response.returncode == 0
    result = json.loads(artifact.read_text(encoding='utf-8') if view == 'artifact' else response.stdout)
    assert result['meta']['confidence'] == 1.0 and result['execution']
    directory_warning(result)
    if view == 'projection':
        assert result['results'] == [] and result['total_results'] == 1


@pytest.mark.parametrize('mode', MODES)
def test_same_adapter_and_decorated_requests_repair_and_sibling_without_clears(tmp_path, monkeypatch, mode):
    root = tmp_path / 'affected'; child = project(root)
    sibling = tmp_path / 'sibling'; project(sibling)
    adapter = AstAdapter(str(root), mode)
    clean = adapter.get_structure()
    sibling_uri = f'ast://{sibling}?{mode}'
    sibling_clean = reveal_query(sibling_uri, provenance=True)
    state = fault(monkeypatch, {child})
    lost = adapter.get_structure()
    assert state['events'] and body(lost) == body(clean)
    directory_warning(lost)
    wire = reveal_query(f'ast://{root}?{mode}', provenance=True)
    assert type(wire) is str
    data = json.loads(wire)
    assert data['meta']['confidence'] == 1.0
    directory_warning(data)
    assert reveal_query(sibling_uri, provenance=True) == sibling_clean
    state['enabled'] = False
    assert adapter.get_structure() == clean
    repaired = json.loads(reveal_query(f'ast://{root}?{mode}', provenance=True))
    assert repaired['meta'] == clean['meta']


def test_default_two_positional_helper_missing_and_all_python_remain_none(tmp_path):
    root = tmp_path / 'python'; project(root, foreign=False)
    assert capabilities.python_only_warning('dict-heatmap', root) is None
    assert capabilities.python_only_warning('dict-heatmap', tmp_path / 'missing') is None


def test_nonwalk_oserror_keeps_optional_fallback_without_directory_events(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; project(root)
    def nonwalk(*args, **kwargs):
        raise PermissionError(13, 'controlled nonwalk hint prerequisite', str(root / 'config'))
    monkeypatch.setattr(path_utils, 'census_for_path', nonwalk)
    assert capabilities.python_only_warning('dict-heatmap', root) is None
    result = AstAdapter(str(root), MODES[0]).get_structure()
    assert result['total_results'] == 3 and result['meta']['warnings'] == []
    assert result['meta']['confidence'] == 1.0


@pytest.mark.parametrize('format', ['text', 'grep'])
def test_clean_python_result_has_no_new_diagnostics(tmp_path, format):
    root = tmp_path / 'python'; project(root, foreign=False)
    result = AstAdapter(str(root), MODES[0]).get_structure()
    assert result['meta']['warnings'] == []
    response = run(f'ast://{root}?{MODES[0]}', '--format', format)
    assert response.returncode == 0
    assert 'W-CAP' not in response.stdout + response.stderr
    assert 'directory' not in response.stdout + response.stderr
