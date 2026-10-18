"""Independent Surface consumers preserve native requested evidence and loss facts."""
import copy
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import surface
from reveal.utils.results import AnalysisCompleteness

pytestmark = pytest.mark.component
ENV = 'import os\nx=os.getenv("VISIBLE")\n'
EMPTY_KEYS = {'php': "<?php $x=$_ENV['']; ?>\n", 'swift': 'import Foundation\nlet x=getenv("")\n',
              'rb': "x=ENV['']\n"}


def _write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


def _project(root, source=ENV, suffix='py', children=1):
    _write(root / ('visible.' + suffix), source)
    paths = []
    for number in range(children):
        child = root / f'included_{number}'
        _write(child / 'hidden.py', ENV.replace('VISIBLE', 'HIDDEN'))
        paths.append(child.resolve())
    return paths


@pytest.fixture
def fault(monkeypatch):
    state = {'active': None, 'stage': 'source', 'denied': set(), 'unknown': False,
             'events': [], 'collected': [], 'censuses': []}
    real_collect = surface._collect_source_files
    real_census = surface.census_and_coverage_for_path
    real_scandir = os.scandir

    def collect(*args, **kwargs):
        state['active'] = 'source'
        try:
            result = real_collect(*args, **kwargs)
            state['collected'].append(sum(len(paths) for paths in result.values()))
            return result
        finally:
            state['active'] = None

    def census(*args, **kwargs):
        state['active'] = 'census'
        try:
            result = real_census(*args, **kwargs)
            state['censuses'].append(result[0].total_code_files)
            return result
        finally:
            state['active'] = None

    def scandir(path):
        if state['active'] == state['stage'] and Path(path).resolve() in state['denied']:
            state['events'].append((state['active'], Path(path).resolve()))
            if state['unknown']:
                raise PermissionError('independent unlocated Surface discovery loss')
            raise PermissionError(13, 'independent Surface discovery loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(surface, '_collect_source_files', collect)
    monkeypatch.setattr(surface, 'census_and_coverage_for_path', census)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _warnings(result):
    return [entry for entry in result['meta']['warnings'] if entry.get('unit') == 'directories']


def _loss(result, expected):
    assert _warnings(result), result['meta']
    assert surface.SurfaceAdapter.execution_facts(result).completeness is expected
    assert 'confidence' not in result['meta']
    assert 'confidence' not in result['_meta']


def _args(root, transport, query=''):
    if transport == 'uri':
        return [f'surface://{root.as_posix()}' + ('?' + query if query else '')]
    args = ['surface', str(root)]
    for field in filter(None, query.split('&')):
        name, value = field.split('=')
        args += ['--' + name.replace('_', '-')] + ([] if value == 'true' else [value])
    return args


@pytest.mark.parametrize('suffix', ['php', 'swift', 'rb'])
@pytest.mark.parametrize('stage', ['source', 'census'])
def test_actual_empty_key_name_is_valid_partial_domain_evidence(tmp_path, fault, suffix, stage):
    children = _project(tmp_path, EMPTY_KEYS[suffix], suffix)
    clean = surface.SurfaceAdapter(str(tmp_path), 'type=env').get_structure()
    assert any(row['name'] == '' for row in clean['surfaces']['env'])
    fault.update(stage=stage, denied=set(children))
    response = run(f'surface://{tmp_path.as_posix()}?type=env', '--format', 'json')
    result = json.loads(response.stdout)
    assert fault['events']
    assert any(row['name'] == '' for row in result['surfaces']['env'])
    assert response.returncode == 3
    _loss(result, AnalysisCompleteness.INCOMPLETE)
    assert not result.get('error')
    if stage == 'census':
        assert result['surfaces'] == clean['surfaces']
        assert fault['collected'][-1] == 2 and fault['censuses'][-1] == 1
    else:
        assert fault['collected'][-1] == 1 and fault['censuses'][-1] == 2


@pytest.mark.parametrize('kind', ['wrong_name_type', 'blank_type'])
def test_required_malformed_row_dominates_real_healthy_row_before_rendering(tmp_path, monkeypatch, fault, kind):
    children = _project(tmp_path)
    real_load = surface._load_scanner

    def load(spec):
        scan = real_load(spec)
        def malformed(*args, **kwargs):
            report = scan(*args, **kwargs)
            if report.get('env'):
                row = copy.deepcopy(report['env'][0])
                row['name' if kind == 'wrong_name_type' else 'type'] = None if kind == 'wrong_name_type' else '  '
                report['env'].append(row)
            return report
        return malformed

    monkeypatch.setattr(surface, '_load_scanner', load)
    fault['denied'] = set(children)
    response = run(f'surface://{tmp_path.as_posix()}?type=env', '--format', 'json')
    assert response.returncode == 3
    result = json.loads(response.stdout)
    _loss(result, AnalysisCompleteness.FAILED)
    assert result.get('error')
    text = run(f'surface://{tmp_path.as_posix()}?type=env')
    assert text.returncode == 3
    assert 'Requested output failed' not in text.stderr
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 1


def test_unrequested_malformed_category_does_not_override_valid_requested_rows(tmp_path, monkeypatch, fault):
    children = _project(tmp_path)
    real_load = surface._load_scanner

    def load(spec):
        scan = real_load(spec)
        def unrelated(*args, **kwargs):
            report = scan(*args, **kwargs)
            report['fs'] = {'unrequested': 'not a list'}
            return report
        return unrelated

    monkeypatch.setattr(surface, '_load_scanner', load)
    fault['denied'] = set(children)
    result = surface.SurfaceAdapter(str(tmp_path), 'type=env').get_structure()
    assert result['total'] == 1 and set(result['surfaces']) == {'env'}
    assert not result.get('error')
    _loss(result, AnalysisCompleteness.INCOMPLETE)


@pytest.mark.parametrize('unknown', [False, True])
def test_seven_actual_census_events_keep_bounded_named_or_unknown_evidence(tmp_path, fault, unknown):
    children = _project(tmp_path, children=7)
    clean = surface.SurfaceAdapter(str(tmp_path)).get_structure()
    fault.update(stage='census', denied=set(children), unknown=unknown)
    result = surface.SurfaceAdapter(str(tmp_path)).get_structure()
    assert result['surfaces'] == clean['surfaces'] and result['total'] == 8
    assert len(fault['events']) == 7 and fault['censuses'][-1] == 1
    _loss(result, AnalysisCompleteness.INCOMPLETE)
    warning, = _warnings(result)
    assert warning['count'] == (0 if unknown else 7)
    assert len(warning['directories']) == (0 if unknown else 5)
    if unknown:
        assert warning['unknown_directory_events'] == 7
    else:
        assert 'and 2 more' in warning['message']
    assert 'missing file population is unknown' in warning['message']


@pytest.mark.parametrize('transport', ['command', 'uri'])
@pytest.mark.parametrize('useful', [False, True])
def test_domain_facts_survive_top_zero_fields_and_primary_json_artifact(tmp_path, fault, transport, useful):
    root = tmp_path / 'project'
    children = _project(root)
    fault['denied'] = set(children)
    query = 'type=env&by=dir&top=0' if useful else 'type=fs&by=dir&top=0'
    artifact = tmp_path / 'mirror.json'
    response = run(*_args(root, transport, query), '--format', 'json', '--also-json', str(artifact),
                   '--fields', 'total', '--provenance')
    assert response.returncode == 3
    result = json.loads(response.stdout)
    assert result['total'] == int(useful)
    assert _warnings(result) and 'confidence' not in result['meta']
    assert result['execution']['command'].startswith('reveal ')
    assert bool(result.get('error')) is (not useful)
    # Primary JSON's existing mirror behavior is transport-owned; evidence must survive either route.
    if artifact.exists():
        saved = json.loads(artifact.read_text(encoding='utf-8'))
        assert _warnings(saved) and bool(saved.get('error')) is (not useful)
    text = run(*_args(root, transport, query), '--also-json', str(artifact))
    assert text.returncode == 3 and artifact.exists()
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    _loss(saved, AnalysisCompleteness.INCOMPLETE if useful else AnalysisCompleteness.FAILED)
    assert 'No external surfaces detected.' not in text.stdout + text.stderr
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 1


@pytest.mark.parametrize('stage', ['source', 'census'])
def test_reused_adapter_repairs_exactly_and_sibling_and_source_only_omission_stay_exact(tmp_path, fault, stage):
    root = tmp_path / 'project'
    children = _project(root)
    sibling = tmp_path / 'sibling'
    _project(sibling)
    adapter = surface.SurfaceAdapter(str(root), 'type=env')
    clean = adapter.get_structure()
    sibling_clean = surface.SurfaceAdapter(str(sibling), 'type=env').get_structure()
    fault.update(stage=stage, denied=set(children))
    adapter.get_structure()
    assert surface.SurfaceAdapter(str(sibling), 'type=env').get_structure() == sibling_clean
    fault['denied'] = set()
    assert adapter.get_structure() == clean
    assert clean['meta']['confidence'] == 0.6 and clean['_meta']['confidence'] == 'medium'


def test_source_only_intentional_test_prune_preserves_broader_healthy_census(tmp_path, fault):
    _write(tmp_path / 'app.py', ENV)
    _write(tmp_path / 'tests' / 'test_app.py', ENV)
    clean = surface.SurfaceAdapter(str(tmp_path), 'source_only=true').get_structure()
    fault['denied'] = {(tmp_path / 'tests').resolve()}
    assert surface.SurfaceAdapter(str(tmp_path), 'source_only=true').get_structure() == clean
    assert clean['total'] == 1 and clean['scope']['total_code_files'] == 2
    assert not fault['events'] and not _warnings(clean)


@pytest.mark.parametrize('transport', ['command', 'uri'])
def test_postprocessing_cannot_turn_actual_failed_requested_analysis_into_success(tmp_path, monkeypatch, fault, transport):
    root = tmp_path / 'project'
    _project(root)
    replacement = surface.SurfaceAdapter(str(root)).get_structure()
    assert replacement['total'] == 2
    fault['denied'] = {root.resolve()}

    def apparent_success(self, result, args):
        # Presentation cannot manufacture analysis availability or clear prior owner facts.
        return copy.deepcopy(replacement)

    monkeypatch.setattr(surface.SurfaceAdapter, 'post_process', apparent_success)
    response = run(*_args(root, transport), '--format', 'json')
    assert fault['events'] and fault['collected'][-1] == 0
    assert response.returncode == 3
