"""Independent consumers keep analytical-source and advisory-hint losses distinct."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import capabilities
from reveal.adapters.ast.adapter import AstAdapter
from reveal.analyzers import _python_dict_usage as usage
from reveal.utils import path_utils

pytestmark = pytest.mark.component
MODES = ['dict-heatmap', 'dict-schemas']
VISIBLE = 'def visible(config):\n    return config["one"] + config["two"] + config["three"]\n'
HIDDEN = ''.join(f'def hidden_{i}(config):\n    return config["a"] + config["b"] + config["c"]\n' for i in range(2))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _project(root, children=1, empty=False):
    _write(root / 'visible.py', 'VALUE = 1\n' if empty else VISIBLE)
    paths = []
    for i in range(children):
        child = root / f'included_{i}'
        _write(child / 'hidden.py', 'VALUE = 2\n' if empty else HIDDEN)
        paths.append(child.resolve())
    return paths


@pytest.fixture
def fault(monkeypatch):
    state = {'active': None, 'stages': set(), 'denied': set(), 'unknown': False,
             'events': [], 'parsed': [], 'hints': [], 'walks': 0}
    real_collect, real_hint = usage.collect_dict_analysis, capabilities.python_only_warning
    real_scandir, real_parse, real_census = os.scandir, usage.parse_file, path_utils.census_for_path

    def collect(*args, **kwargs):
        state['walks'] += 1
        state['active'] = 'source'
        try:
            return real_collect(*args, **kwargs)
        finally:
            state['active'] = None

    def hint(*args, **kwargs):
        state['active'] = 'hint'
        try:
            return real_hint(*args, **kwargs)
        finally:
            state['active'] = None

    def census(*args, **kwargs):
        value = real_census(*args, **kwargs)
        if state['active'] == 'hint':
            state['hints'].append(dict(value.per_language))
        return value

    def parse(*args, **kwargs):
        value = real_parse(*args, **kwargs)
        if state['active'] == 'source':
            state['parsed'].append((Path(args[0]).name, value is not None))
        return value

    def scandir(path):
        stage = state['active']
        if stage in state['stages'] and Path(path).resolve() in state['denied']:
            state['events'].append((stage, Path(path).resolve()))
            if state['unknown']:
                raise PermissionError(f'independent {stage} unlocated directory loss')
            raise PermissionError(13, f'independent {stage} directory loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(usage, 'collect_dict_analysis', collect)
    monkeypatch.setattr(capabilities, 'python_only_warning', hint)
    monkeypatch.setattr(path_utils, 'census_for_path', census)
    monkeypatch.setattr(usage, 'parse_file', parse)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _warnings(result):
    return [entry for entry in result['meta']['warnings'] if entry.get('unit') == 'directories']


@pytest.mark.parametrize('mode', MODES)
def test_same_directory_actual_source_and_hint_events_have_distinct_attribution(tmp_path, fault, mode):
    children = _project(tmp_path)
    owner = AstAdapter(str(tmp_path), 'show=' + mode)
    clean = owner.get_structure()
    fault.update(stages={'source', 'hint'}, denied=set(children), parsed=[], events=[])
    result = owner.get_structure()
    assert fault['events'] == [('source', children[0]), ('hint', children[0])]
    assert fault['parsed'] == [('visible.py', True)]
    assert result['total_results'] == (1 if mode == 'dict-heatmap' else 0)
    warnings = _warnings(result)
    assert len(warnings) == 2, result['meta']
    source = next(entry for entry in warnings if 'independent source' in entry['message'])
    hint = next(entry for entry in warnings if 'independent hint' in entry['message'])
    assert source.get('code') and source.get('code') != hint.get('code')
    assert source['count'] == hint['count'] == 1
    assert source['directories'] == hint['directories']
    assert 'hint census' not in source['message'] and 'hint census' in hint['message']
    assert 'confidence' not in result['meta'] and not result['meta']['errors']
    fault['stages'] = set()
    assert owner.get_structure() == clean


@pytest.mark.parametrize('mode', MODES)
def test_hint_only_empty_keeps_original_text_and_confidence(tmp_path, fault, mode):
    children = _project(tmp_path, empty=True)
    uri = f'ast://{tmp_path.as_posix()}?show={mode}'
    clean = run(uri)
    fault.update(stages={'hint'}, denied=set(children))
    answer = AstAdapter(str(tmp_path), 'show=' + mode).get_structure()
    assert answer['total_results'] == 0 and answer['meta']['confidence'] == 1.0
    warning, = _warnings(answer)
    assert 'hint census' in warning['message']
    text = run(uri)
    assert text.returncode == 0 and text.stdout.startswith(clean.stdout.rstrip())
    assert 'analyzed portion' not in text.stdout


@pytest.mark.parametrize('mode', MODES)
def test_root_unknown_source_loss_is_not_repaired_by_healthy_hint_population(tmp_path, fault, mode):
    _project(tmp_path)
    fault.update(stages={'source'}, denied={tmp_path.resolve()}, unknown=True)
    result = AstAdapter(str(tmp_path), 'show=' + mode).get_structure()
    assert fault['hints'] == [{'python': 2}] and fault['parsed'] == []
    assert result['total_results'] == 0 and not result.get('error')
    warnings = _warnings(result)
    assert len(warnings) == 1, result['meta']
    warning = warnings[0]
    assert warning['count'] == 0 and warning['unknown_directory_events'] == 1
    assert 'confidence' not in result['meta']
    text = run(f'ast://{tmp_path.as_posix()}?show={mode}')
    assert text.returncode == 3 and 'analyzed portion' in text.stdout


def test_derived_zero_schema_qualifies_analysis_with_healthy_surviving_usage(tmp_path, fault):
    children = _project(tmp_path)
    fault.update(stages={'source'}, denied=set(children))
    heatmap = AstAdapter(str(tmp_path), 'show=dict-heatmap').get_structure()
    assert heatmap['total_results'] == 1 and heatmap['results'][0]['function'] == 'visible'
    response = run(f'ast://{tmp_path.as_posix()}?show=dict-schemas')
    assert response.returncode == 3 and 'analyzed portion' in response.stdout
    assert 'incomplete' in response.stdout
    assert (response.stdout + response.stderr).count('identified directory enumeration(s) failed') == 1


@pytest.mark.parametrize('mode', MODES)
def test_source_empty_precedes_unsupported_language_claim(tmp_path, fault, mode):
    _write(tmp_path / 'visible.lua', 'local value = 1\n')
    fault.update(stages={'source'}, denied={tmp_path.resolve()})
    result = AstAdapter(str(tmp_path), 'show=' + mode).get_structure()
    assert result['total_results'] == 0 and result['unsupported_language']
    assert fault['events'] and fault['hints'] == [{'lua': 1}]
    response = run(f'ast://{tmp_path.as_posix()}?show={mode}')
    assert response.returncode == 3 and 'analyzed portion' in response.stdout
    assert 'no .py/.pyi files found' not in response.stdout


def test_both_population_warnings_survive_cuts_artifact_and_grep_stdio(tmp_path, fault):
    root = tmp_path / 'project'
    children = _project(root, children=7)
    fault.update(stages={'source', 'hint'}, denied=set(children), unknown=True)
    uri = f'ast://{root.as_posix()}?show=dict-heatmap'
    response = run(uri, '--format', 'json', '--fields', 'results', '--max-items', '0', '--provenance')
    assert response.returncode == 3
    result = json.loads(response.stdout)
    assert result['results'] == []
    warnings = _warnings(result)
    assert len(warnings) == 2, result['meta']
    assert all(entry['count'] == 0 and entry['unknown_directory_events'] == 7 for entry in warnings)
    assert 'confidence' not in result['meta']
    artifact = tmp_path / 'answer.json'
    text = run(uri, '--also-json', str(artifact))
    assert text.returncode == 3 and len(_warnings(json.loads(artifact.read_text(encoding='utf-8')))) == 2
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 2
    grep = run(uri, '--format', 'grep')
    assert grep.returncode == 3 and 'visible' in grep.stdout
    assert 'directory' not in grep.stdout and 'PermissionError' not in grep.stdout
    assert grep.stderr.count('identified directory enumeration(s) failed') == 2


@pytest.mark.parametrize('mode', MODES)
def test_clean_sibling_and_single_file_have_no_source_side_effects(tmp_path, fault, mode):
    root, sibling = tmp_path / 'project', tmp_path / 'sibling'
    _project(root)
    _project(sibling)
    owner = AstAdapter(str(sibling), 'show=' + mode)
    clean = owner.get_structure()
    single = AstAdapter(str(root / 'visible.py'), 'show=' + mode).get_structure()
    fault.update(stages={'source', 'hint'}, denied={root.resolve()})
    assert owner.get_structure() == clean
    assert AstAdapter(str(root / 'visible.py'), 'show=' + mode).get_structure() == single
    assert not fault['events'] and clean['meta']['confidence'] == 1.0


@pytest.mark.parametrize('mode', MODES)
def test_positive_uncapped_observations_hidden_by_cap_are_display_absence_only(tmp_path, fault, mode):
    root = tmp_path / 'project'
    children = _project(root)
    # Both surviving readers share a shape, so both modes have actual positive observations.
    _write(root / 'visible.py', HIDDEN)
    fault.update(stages={'source'}, denied=set(children))
    uncapped = AstAdapter(str(root), 'show=' + mode).get_structure()
    assert uncapped['total_results'] == (2 if mode == 'dict-heatmap' else 1)
    assert uncapped['results'] and fault['parsed'][-1] == ('visible.py', True)
    artifact = tmp_path / 'capped.json'
    response = run(f'ast://{root.as_posix()}?show={mode}', '--max-items', '0', '--also-json', str(artifact))
    assert response.returncode == 3 and artifact.exists()
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    assert saved['results'] == [] and saved['total_results'] == uncapped['total_results']
    assert 'displayed' in response.stdout and 'analyzed portion' in response.stdout
    assert 'analysis is incomplete' in response.stdout
    assert (response.stdout + response.stderr).count('identified directory enumeration(s) failed') == 1
