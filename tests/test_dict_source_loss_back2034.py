"""Actual dict analytical discovery loss is separate from a healthy hint census."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import capabilities
from reveal.adapters.ast.adapter import AstAdapter
from reveal.analyzers import _python_dict_usage as usage
from reveal.utils import path_utils
from reveal.utils.exclusions import exclusion_scope
from reveal.utils.path_utils import EVIDENCE

pytestmark = pytest.mark.component
VISIBLE = 'def visible(cfg):\n    return cfg["visible_a"] + cfg["visible_b"] + cfg["visible_c"]\n'
HIDDEN = ''.join(f'def hidden_{n}(cfg):\n    return cfg["a"] + cfg["b"] + cfg["c"]\n\n' for n in range(2))
MODES = ['dict-heatmap', 'dict-schemas']


def _write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


def _project(root, visible=True, hidden=True, children=1):
    _write(root / 'visible.py', VISIBLE if visible else 'VALUE = 1\n')
    paths = []
    for number in range(children):
        child = root / f'included_{number}'
        _write(child / 'hidden.py', HIDDEN if hidden else 'VALUE = 2\n')
        paths.append(child.resolve())
    return paths


@pytest.fixture
def fault(monkeypatch):
    state = {'active': None, 'stage': 'analysis', 'denied': set(), 'unknown': False,
             'events': [], 'parsed': [], 'hints': []}
    real_collect, real_parse = usage.collect_dict_analysis, usage.parse_file
    real_warning, real_census = capabilities.python_only_warning, path_utils.census_for_path
    real_scandir = os.scandir

    def collect(*args, **kwargs):
        state['active'] = 'analysis'
        try:
            return real_collect(*args, **kwargs)
        finally:
            state['active'] = None

    def parse(*args, **kwargs):
        result = real_parse(*args, **kwargs)
        if state['active'] == 'analysis':
            state['parsed'].append((Path(args[0]).resolve(), result is not None))
        return result

    def warning(*args, **kwargs):
        state['active'] = 'hint'
        try:
            return real_warning(*args, **kwargs)
        finally:
            state['active'] = None

    def census(*args, **kwargs):
        result = real_census(*args, **kwargs)
        if state['active'] == 'hint':
            state['hints'].append(dict(result.per_language))
        return result

    def scandir(path):
        if state['active'] == state['stage'] and Path(path).resolve() in state['denied']:
            state['events'].append((state['active'], Path(path).resolve()))
            if state['unknown']:
                raise PermissionError('actual unlocated dict analytical directory loss')
            raise PermissionError(13, 'actual dict analytical enumeration loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(usage, 'collect_dict_analysis', collect)
    monkeypatch.setattr(usage, 'parse_file', parse)
    monkeypatch.setattr(capabilities, 'python_only_warning', warning)
    monkeypatch.setattr(path_utils, 'census_for_path', census)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _warning(result):
    warnings = [entry for entry in result['meta']['warnings'] if entry.get('unit') == 'directories']
    assert len(warnings) == 1, result['meta']
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'python_ast' and not result['meta']['errors']
    return warnings[0]


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('population', ['partial', 'zero', 'root', 'unknown'])
def test_native_source_loss_disclosed_despite_healthy_independent_hint(tmp_path, fault, mode, population):
    children = _project(tmp_path, visible=population != 'zero')
    owner = AstAdapter(str(tmp_path), 'show=' + mode)
    clean = owner.get_structure()
    assert clean['total_results'] == ((2 if population == 'zero' else 3) if mode == 'dict-heatmap' else 1)
    fault.update(denied={tmp_path.resolve()} if population == 'root' else set(children),
                 unknown=population == 'unknown', parsed=[], hints=[])
    result = owner.get_structure()
    assert fault['events'] and all(stage == 'analysis' for stage, _ in fault['events'])
    assert fault['hints'] == [{'python': 2}]
    assert all(parsed for _, parsed in fault['parsed'])
    expected = 0 if population in ('zero', 'root') or mode == 'dict-schemas' else 1
    assert result['total_results'] == expected
    warning = _warning(result)
    assert warning['count'] == (0 if population == 'unknown' else 1)
    if population == 'unknown':
        assert warning['unknown_directory_events'] == 1
    assert 'dict' in warning['message'].lower()
    assert 'missing file population is unknown' in warning['message']
    assert not any('hint census' in entry['message'] for entry in result['meta']['warnings'])
    fault['denied'] = set()
    assert owner.get_structure() == clean


@pytest.mark.parametrize('mode', MODES)
def test_empty_text_scopes_absence_and_grep_keeps_stdout_clean(tmp_path, fault, mode):
    children = _project(tmp_path, visible=False)
    fault['denied'] = set(children)
    uri = f'ast://{tmp_path.as_posix()}?show={mode}'
    text = run(uri)
    assert text.returncode == 0
    assert 'analyzed portion' in text.stdout and 'incomplete' in text.stdout
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 1
    grep = run(uri, '--format', 'grep')
    assert grep.returncode == 0 and grep.stdout == ''
    assert grep.stderr.count('identified directory enumeration(s) failed') == 1


def test_source_facts_survive_json_projection_provenance_and_text_artifact(tmp_path, fault):
    root = tmp_path / 'project'
    children = _project(root)
    fault['denied'] = set(children)
    uri = f'ast://{root.as_posix()}?show=dict-heatmap'
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


@pytest.mark.parametrize('unknown', [False, True])
def test_seven_actual_source_events_preserve_unknown_population_and_display_cap(tmp_path, fault, unknown):
    children = _project(tmp_path, children=7)
    fault.update(denied=set(children), unknown=unknown)
    result = AstAdapter(str(tmp_path), 'show=dict-heatmap').get_structure()
    assert len(fault['events']) == 7 and result['total_results'] == 1
    assert fault['hints'][-1] == {'python': 8}
    warning = _warning(result)
    assert warning['count'] == (0 if unknown else 7)
    assert len(warning['directories']) == (0 if unknown else 5)
    if unknown:
        assert warning['unknown_directory_events'] == 7
    else:
        assert 'and 2 more' in warning['message']


@pytest.mark.parametrize('mode', MODES)
def test_decorated_mcp_remains_ordinary_with_attributed_source_loss(tmp_path, fault, mode):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    children = _project(tmp_path)
    fault['denied'] = set(children)
    raw = reveal_query(f'ast://{tmp_path.as_posix()}?show={mode}', provenance=True)
    assert type(raw) is str and not isinstance(raw, _ToolFailure)
    result = json.loads(raw)
    _warning(result)
    assert result['total_results'] == (1 if mode == 'dict-heatmap' else 0)


def test_hint_only_loss_retains_prior_and_existing_empty_text(tmp_path, fault):
    children = _project(tmp_path, visible=False, hidden=False)
    uri = f'ast://{tmp_path.as_posix()}?show=dict-heatmap'
    clean = run(uri)
    fault.update(stage='hint', denied=set(children))
    result = AstAdapter(str(tmp_path), 'show=dict-heatmap').get_structure()
    assert fault['events'] and result['total_results'] == 0
    assert result['meta']['confidence'] == 1.0
    assert len(result['meta']['warnings']) == 1 and 'hint census' in result['meta']['warnings'][0]['message']
    text = run(uri)
    assert text.returncode == 0 and text.stdout.startswith(clean.stdout.rstrip())
    assert 'analyzed portion' not in text.stdout


def test_default_tuple_walk_order_and_positional_evidence_purpose_unchanged(tmp_path):
    children = _project(tmp_path)
    result = usage.collect_dict_analysis(str(tmp_path))
    assert type(result) is tuple and len(result) == 2 and all(isinstance(value, list) for value in result)
    with exclusion_scope(tmp_path, ['included_0']):
        ordinary = list(usage.iter_python_files(str(tmp_path)))
        evidence = list(usage.iter_python_files(str(tmp_path), EVIDENCE))
    assert ordinary == [str(tmp_path / 'visible.py')]
    assert [Path(file).resolve() for file in evidence] == [
        (tmp_path / 'visible.py').resolve(), children[0] / 'hidden.py']
    assert usage.has_python_files(str(tmp_path)) and usage.parse_file(str(tmp_path / 'missing.py')) is None


def test_parse_only_fallback_does_not_become_directory_loss(tmp_path):
    _write(tmp_path / 'broken.py', 'def broken(\n')
    assert usage.parse_file(str(tmp_path / 'broken.py')) is None
    result = AstAdapter(str(tmp_path), 'show=dict-heatmap').get_structure()
    assert result['total_results'] == 0 and result['meta']['confidence'] == 1.0
    assert result['meta']['warnings'] == []


def test_explicit_exclusion_noise_single_file_sibling_and_regular_ast_stay_exact(tmp_path, fault):
    root = tmp_path / 'project'
    children = _project(root)
    _write(root / 'node_modules' / 'hidden.py', HIDDEN)
    sibling = tmp_path / 'sibling'
    _project(sibling)
    sibling_owner = AstAdapter(str(sibling), 'show=dict-heatmap')
    sibling_clean = sibling_owner.get_structure()
    regular = AstAdapter(str(root), 'type=function').get_structure()
    single = AstAdapter(str(root / 'visible.py'), 'show=dict-heatmap').get_structure()
    uri = f'ast://{root.as_posix()}?show=dict-heatmap'
    clean = run(uri, '--exclude', 'included_0', '--format', 'json')
    fault['denied'] = {*children, (root / 'node_modules').resolve()}
    excluded = run(uri, '--exclude', 'included_0', '--format', 'json')
    assert excluded.stdout == clean.stdout and excluded.returncode == clean.returncode == 0
    assert not fault['events']
    assert sibling_owner.get_structure() == sibling_clean
    assert AstAdapter(str(root), 'type=function').get_structure() == regular
    assert AstAdapter(str(root / 'visible.py'), 'show=dict-heatmap').get_structure() == single
