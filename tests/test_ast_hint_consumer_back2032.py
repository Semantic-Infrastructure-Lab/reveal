"""AST advisory census loss survives rendering without changing Python analysis."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import capabilities
from reveal.adapters.ast.adapter import AstAdapter
from reveal.utils import path_utils

pytestmark = pytest.mark.component
QUERIES = ['show=dict-heatmap', 'show=dict-schemas', 'reveal_type=cfg']
PYTHON = ''.join(f'def reader_{n}(cfg):\n    return cfg["a"] + cfg["b"] + cfg["c"]\n\n' for n in range(3))


def _write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


def _project(root, children=7):
    _write(root / 'visible.py', PYTHON)
    _write(root / 'visible.js', 'function visible() { return 1; }\n')
    paths = []
    for number in range(children):
        child = root / f'included_{number}'
        _write(child / 'foreign.lua', 'local value=1\n')
        paths.append(child.resolve())
    return paths


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'denied': set(), 'events': [], 'censuses': [], 'later_error': False,
             'nonwalk_errors': 0}
    real_warning, real_scandir = capabilities.python_only_warning, os.scandir
    real_census = path_utils.census_for_path

    def warning(*args, **kwargs):
        state['active'] = True
        try:
            return real_warning(*args, **kwargs)
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append(Path(path).resolve())
            raise PermissionError(13, 'independent actual AST hint enumeration loss', str(path))
        return real_scandir(path)

    def census(*args, **kwargs):
        # Run the actual census first: any callback facts originate in real os.scandir failure.
        result = real_census(*args, **kwargs)
        if state['active']:
            state['censuses'].append(dict(result.per_language))
            if state['later_error']:
                state['nonwalk_errors'] += 1
                raise PermissionError(13, 'separate later nonwalk helper exception', str(Path(args[0]) / 'config'))
        return result

    monkeypatch.setattr(capabilities, 'python_only_warning', warning)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(path_utils, 'census_for_path', census)
    return state


def _body(data):
    return {key: value for key, value in data.items() if key != 'meta'}


def _warning(data):
    entries = [entry for entry in data['meta']['warnings'] if entry.get('unit') == 'directories']
    assert len(entries) == 1, data['meta']
    assert data['meta']['confidence'] == 1.0
    assert not data['meta']['errors']
    return entries[0]


@pytest.mark.parametrize('query', QUERIES)
def test_named_seven_hint_errors_keep_observed_capability_warning_and_grep_channel(tmp_path, fault, query):
    children = _project(tmp_path)
    uri = f'ast://{tmp_path.as_posix()}?{query}'
    owner = AstAdapter(str(tmp_path), query)
    clean = owner.get_structure()
    assert clean['total_results'] > 0
    grep_clean = run(uri, '--format', 'grep')
    assert grep_clean.returncode == 0 and 'W-CAP-1' not in grep_clean.stdout + grep_clean.stderr
    fault['denied'] = set(children)
    result = owner.get_structure()
    assert len(fault['events']) == 7
    assert _body(result) == _body(clean)
    assert fault['censuses'][-1] == {'python': 1, 'javascript': 1}
    warning = _warning(result)
    assert warning['count'] == 7 and len(warning['directories']) == 5
    assert 'and 2 more' in warning['message'] and 'missing file population is unknown' in warning['message']
    assert 'hint' in warning['message'].lower() and 'observed' in warning['message'].lower()
    cap, = [entry for entry in result['meta']['warnings'] if entry.get('code') == 'W-CAP-1']
    assert 'javascript (1)' in cap['message'] and 'lua (7)' not in cap['message']
    grep_lost = run(uri, '--format', 'grep')
    assert grep_lost.returncode == 0 and grep_lost.stdout == grep_clean.stdout
    assert grep_lost.stderr.count('identified directory enumeration(s) failed') == 1
    assert 'W-CAP-1' not in grep_lost.stdout + grep_lost.stderr
    text = run(uri)
    assert text.returncode == 0
    assert (text.stdout + text.stderr).count('W-CAP-1') == 1
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 1
    fault['denied'] = set()
    assert owner.get_structure() == clean


@pytest.mark.parametrize('query', QUERIES)
def test_actual_walk_events_survive_later_separate_nonwalk_exception(tmp_path, fault, query):
    children = _project(tmp_path, children=1)
    owner = AstAdapter(str(tmp_path), query)
    clean = owner.get_structure()
    fault.update(denied=set(children), later_error=True)
    result = owner.get_structure()
    assert len(fault['events']) == 1 and fault['nonwalk_errors'] == 1
    assert fault['censuses'][-1] == {'python': 1, 'javascript': 1}
    assert _body(result) == _body(clean)
    warning = _warning(result)
    assert warning['count'] == 1
    assert 'actual AST hint enumeration loss' in warning['message']
    assert 'later nonwalk helper exception' not in warning['message']
    assert not any(entry.get('code') == 'W-CAP-1' for entry in result['meta']['warnings'])
    fault.update(denied=set(), later_error=False)
    assert owner.get_structure() == clean


def test_hint_disclosure_survives_fields_provenance_artifact_and_sibling_repair(tmp_path, fault):
    root = tmp_path / 'project'
    children = _project(root)
    sibling = tmp_path / 'sibling'
    _project(sibling)
    uri = f'ast://{root.as_posix()}?show=dict-schemas'
    sibling_uri = f'ast://{sibling.as_posix()}?show=dict-schemas'
    sibling_clean = run(sibling_uri, '--format', 'json')
    fault['denied'] = set(children)
    response = run(uri, '--format', 'json', '--fields', 'total_results', '--max-items', '0', '--provenance')
    assert response.returncode == 0
    data = json.loads(response.stdout)
    assert data['total_results'] == 1
    _warning(data)
    assert data['execution']['command'].startswith('reveal ast://')
    artifact = tmp_path / 'answer.json'
    text = run(uri, '--also-json', str(artifact))
    assert text.returncode == 0 and artifact.exists()
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    assert saved['total_results'] == 1
    _warning(saved)
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 1
    sibling_after = run(sibling_uri, '--format', 'json')
    assert sibling_after.returncode == sibling_clean.returncode
    assert sibling_after.stdout == sibling_clean.stdout and sibling_after.stderr == sibling_clean.stderr


def test_ordinary_nonwalk_exception_does_not_manufacture_directory_events(tmp_path, fault):
    _project(tmp_path, children=1)
    fault['later_error'] = True
    result = AstAdapter(str(tmp_path), QUERIES[0]).get_structure()
    assert fault['nonwalk_errors'] == 1 and not fault['events']
    assert result['meta']['warnings'] == [] and result['meta']['confidence'] == 1.0
    assert result['total_results'] == 3


def test_existing_default_two_arguments_missing_and_all_python_empty_prior(tmp_path):
    _write(tmp_path / 'plain.py', 'VALUE = 1\n')
    assert capabilities.python_only_warning('dict-heatmap', tmp_path) is None
    assert capabilities.python_only_warning('dict-heatmap', tmp_path / 'missing') is None
    owner = AstAdapter(str(tmp_path), 'show=dict-heatmap')
    result = owner.get_structure()
    assert result['total_results'] == 0 and result['meta']['confidence'] == 1.0
    assert result['meta']['warnings'] == []
    assert owner.uri_execution_facts(f'{tmp_path}?show=dict-heatmap') is None


def test_clean_mixed_grep_keeps_existing_silent_capability_warning(tmp_path):
    _project(tmp_path, children=1)
    result = run(f'ast://{tmp_path.as_posix()}?show=dict-heatmap', '--format', 'grep')
    assert result.returncode == 0 and result.stdout.strip()
    assert 'W-CAP-1' not in result.stdout + result.stderr
    assert 'directory enumeration' not in result.stdout + result.stderr
