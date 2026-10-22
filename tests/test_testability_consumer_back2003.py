"""Independent native domain/outcome reds; protocol defenses are labeled separately."""
import builtins
import dataclasses
import json
import os
from pathlib import Path

import pytest

import reveal
from conftest import _run_reveal_direct as run
from reveal.testability import report
from reveal.testability.boundaries import collect_boundary_profiles

pytestmark = pytest.mark.component
assert Path(reveal.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1])
PURE = 'def pure(x):\n    return x + 1\n'
PATCH = 'from unittest.mock import patch\npatch("service.work")\n'
BAD_TEST = 'def broken(:\n'


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _project(root, source='constant', tests='bad'):
    src, suite = root / 'src', root / 'tests'
    src.mkdir(parents=True)
    suite.mkdir()
    source_text = {'constant': 'VALUE = 1\n', 'pure': PURE,
                   'recovered_zero': 'VALUE =\n', 'recovered_profile': 'def broken(:\n'}[source]
    _write(src / 'main.py', source_text)
    test_text = {'bad': BAD_TEST, 'zero': 'VALUE = 2\n', 'patch': PATCH,
                 'recovered_patch': 'vi.mock("./service"); const broken=;\n',
                 'recovered_zero': 'const broken=;\n',
                 'unknown_targets': 'from unittest.mock import patch\npatch.object()\nmonkeypatch.setattr("")\n'}[tests]
    filename = 'main.test.ts' if tests.startswith('recovered') else 'test_main.py'
    _write(suite / filename, test_text)
    return src, suite


@pytest.fixture
def evidence(monkeypatch):
    state = {'active': None, 'denied': set(), 'unknown': False, 'read_source': False,
             'read_tests': False, 'mutation': None, 'events': [], 'raw': []}
    real_patches, real_profiles = report.scan_patches, report.collect_boundary_profiles
    real_scandir, real_open, real_read = os.scandir, builtins.open, Path.read_text

    def patches(paths, **kwargs):
        state['active'] = 'tests'
        try:
            uses = real_patches(paths, **kwargs)
            if state['mutation'] == 'patch_line_bool' and uses:
                uses[0] = dataclasses.replace(uses[0], line=True)
            if state['mutation'] == 'child_exception':
                raise RuntimeError('controlled ordinary required patch child failure')
            state['raw'].append(('patches', list(uses), list(uses.skipped),
                                 list(uses.recovered_files), list(uses.traversal_failures)))
            return uses
        finally:
            state['active'] = None

    def profiles(path):
        state['active'] = 'source'
        try:
            rows = real_profiles(path)
            if state['mutation'] == 'profile_line_bool' and rows:
                rows[0] = dataclasses.replace(rows[0], line=True)
            state['raw'].append(('profiles', list(rows), list(rows.skipped),
                                 list(rows.recovered_files), list(rows.traversal_failures)))
            return rows
        finally:
            state['active'] = None

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append((state['active'], Path(path).resolve()))
            if state['unknown']:
                raise PermissionError('actual unlocated required testability directory loss')
            raise PermissionError(13, 'actual required testability directory loss', str(path))
        return real_scandir(path)

    def open_file(path, *args, **kwargs):
        if state['active'] == 'source' and state['read_source'] and str(path).endswith('main.py'):
            state['events'].append(('source_read', Path(path).resolve()))
            raise PermissionError(13, 'actual required source read failure', str(path))
        return real_open(path, *args, **kwargs)

    def read_text(path, *args, **kwargs):
        if state['active'] == 'tests' and state['read_tests'] and path.name == 'test_main.py':
            state['events'].append(('test_read', path.resolve()))
            raise PermissionError(13, 'actual required test read failure', str(path))
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(report, 'scan_patches', patches)
    monkeypatch.setattr(report, 'collect_boundary_profiles', profiles)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(builtins, 'open', open_file)
    monkeypatch.setattr(Path, 'read_text', read_text)
    return state


def _argv(src, suite, spelling='uri'):
    # Thresholds intentionally hide every ranked row; raw observations remain authoritative.
    if spelling == 'command':
        return ['testability', str(src), '--tests', str(suite), '--min-patches', '99',
                '--min-categories', '99', '--top', '1']
    return [f'testability://{src.as_posix()}?tests={suite.as_posix()}&min_patches=99&min_categories=99&top=1']


def _raw(evidence, component):
    rows = [item for item in evidence['raw'] if item[0] == component]
    assert rows
    return rows[-1]


@pytest.mark.parametrize('spelling', ['command', 'uri'])
@pytest.mark.parametrize('source,tests,patch_count,profile_count,read_source', [
    ('constant', 'bad', 0, 0, False),  # Conservative FAILED, not useful clean-file availability.
    ('pure', 'bad', 0, 1, False),  # INCOMPLETE despite no ranked boundary rows.
    ('constant', 'patch', 1, 0, True),  # INCOMPLETE: real patch survives source read loss.
    ('recovered_zero', 'bad', 0, 0, False),
    ('recovered_profile', 'bad', 0, 1, False),  # Real recovered function is a positive.
    ('constant', 'recovered_patch', 1, 0, False),
    ('constant', 'recovered_zero', 0, 0, False),
])
def test_native_required_loss_never_exits_clean_after_ranking_hides_rows(
        tmp_path, evidence, spelling, source, tests, patch_count, profile_count, read_source):
    src, suite = _project(tmp_path / 'project', source, tests)
    evidence['read_source'] = read_source
    response = run(*_argv(src, suite, spelling), '--format', 'json')
    data = json.loads(response.stdout)
    patches, profiles = _raw(evidence, 'patches'), _raw(evidence, 'profiles')
    assert len(patches[1]) == patch_count and len(profiles[1]) == profile_count
    assert patches[2] or patches[3] or profiles[2] or profiles[3]
    assert data['summary']['total_patch_uses'] == patch_count
    assert data['patch_hotspots'] == data['boundary_hotspots'] == []
    assert data['meta']['confidence'] == 0.75 and data['meta']['parse_mode'] == 'python_ast'
    if read_source:
        assert evidence['events'] == [('source_read', (src / 'main.py').resolve())]
    if source in ('pure', 'recovered_profile'):
        assert profiles[1][0].categories == set() and profiles[1][0].line == 1
    assert response.returncode == 3, data


@pytest.mark.parametrize('population', ['source_positive', 'source_zero', 'unknown_tests_root', 'test_read'])
def test_actual_enumeration_and_read_loss_are_required_even_with_zero_identified_directories(
        tmp_path, evidence, population):
    src, suite = _project(tmp_path / 'project', 'pure' if population == 'source_positive' else 'constant', 'zero')
    if population.startswith('source_'):
        hidden = _write(src / 'included' / 'hidden.py', PURE).parent.resolve()
        evidence['denied'] = {hidden}
    elif population == 'unknown_tests_root':
        evidence.update(denied={suite.resolve()}, unknown=True)
    else:
        evidence['read_tests'] = True
    response = run(*_argv(src, suite), '--format', 'json')
    data = json.loads(response.stdout)
    assert len(evidence['events']) == 1
    assert len(_raw(evidence, 'profiles')[1]) == (1 if population == 'source_positive' else 0)
    if population == 'unknown_tests_root':
        warning, = [w for w in data['meta']['warnings'] if w.get('unit') == 'directories']
        assert warning['count'] == 0 and warning['unknown_directory_events'] == 1
    assert response.returncode == 3, data


@pytest.mark.parametrize('mutation', ['patch_line_bool', 'profile_line_bool'])
def test_protocol_defense_malformed_raw_child_is_not_rescued_by_other_real_positive(tmp_path, evidence, mutation):
    src, suite = _project(tmp_path / 'project', 'pure', 'patch')
    hidden = _write(suite / 'included' / 'test_hidden.py', PATCH).parent.resolve()
    evidence.update(denied={hidden}, mutation=mutation)
    response = run(*_argv(src, suite), '--format', 'json')
    data = json.loads(response.stdout)
    patches, profiles = _raw(evidence, 'patches')[1], _raw(evidence, 'profiles')[1]
    assert len(patches) == len(profiles) == 1 and evidence['events']
    malformed, healthy = (patches[0], profiles[0]) if mutation == 'patch_line_bool' else (profiles[0], patches[0])
    assert malformed.line is True and type(healthy.line) is int
    assert response.returncode == 3, data
    assert data.get('error'), 'Malformed required child must be FAILED, not merely partial'


def test_protocol_defense_ordinary_required_child_exception_uses_analysis_failure(tmp_path, evidence):
    src, suite = _project(tmp_path / 'project', 'pure', 'patch')
    assert len(collect_boundary_profiles(str(src))) == 1
    evidence['mutation'] = 'child_exception'
    response = run(*_argv(src, suite), '--format', 'json')
    data = json.loads(response.stdout)
    assert 'controlled ordinary required patch child failure' in data['error']
    assert response.returncode == 3, data


@pytest.mark.parametrize('source,failed', [('constant', True), ('pure', False)])
def test_existing_generic_mcp_consumer_distinguishes_failed_from_useful_partial(tmp_path, evidence, source, failed):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    src, suite = _project(tmp_path / 'project', source, 'bad')
    result = reveal_query(_argv(src, suite)[0], provenance=True)
    assert _raw(evidence, 'patches')[2]
    assert len(_raw(evidence, 'profiles')[1]) == (0 if failed else 1)
    if failed:
        assert isinstance(result, _ToolFailure), result
    else:
        assert type(result) is str
        primary = result.partition('\n[stderr:')[0]
        data = json.loads(primary)
        assert any('usable evidence follows' in w.get('message', '').lower()
                   for w in data['meta']['warnings']), data['meta']


@pytest.mark.parametrize('view', ['projection', 'artifact'])
def test_positive_uncapped_patch_and_required_source_loss_survive_presentation(tmp_path, evidence, view):
    src, suite = _project(tmp_path / 'project', 'constant', 'patch')
    evidence['read_source'] = True
    artifact = tmp_path / 'answer.json'
    flags = ['--max-items', '0', '--provenance'] if view == 'projection' else ['--max-items', '0', '--also-json', str(artifact)]
    if view == 'projection':
        flags += ['--format', 'json', '--fields', 'patch_hotspots,boundary_hotspots']
    uri = _argv(src, suite)[0].replace('min_patches=99', 'min_patches=1') + '&include_unresolved=true'
    uncut = run(uri, '--format', 'json')
    assert len(json.loads(uncut.stdout)['patch_hotspots']) == 1
    response = run(uri, *flags)
    assert len(_raw(evidence, 'patches')[1]) == 1 and _raw(evidence, 'profiles')[2]
    assert response.returncode == 3, response.stdout
    data = json.loads(response.stdout if view == 'projection' else artifact.read_text(encoding='utf-8'))
    assert data['patch_hotspots'] == data['boundary_hotspots'] == []
    assert any(w.get('type') == 'analysis_failed' for w in data['meta']['warnings'])


def test_actual_source_read_repair_and_healthy_sibling_are_exact_without_clears(tmp_path, evidence):
    src, suite = _project(tmp_path / 'project', 'pure', 'patch')
    sibling_src, sibling_tests = _project(tmp_path / 'sibling', 'pure', 'patch')
    clean = run(*_argv(src, suite), '--format', 'json')
    sibling = run(*_argv(sibling_src, sibling_tests), '--format', 'json')
    evidence['read_source'] = True
    lost = run(*_argv(src, suite), '--format', 'json')
    assert len(_raw(evidence, 'patches')[1]) == 1 and not _raw(evidence, 'profiles')[1]
    assert lost.returncode == 3, lost.stdout
    evidence['read_source'] = False
    repaired = run(*_argv(src, suite), '--format', 'json')
    again = run(*_argv(sibling_src, sibling_tests), '--format', 'json')
    assert repaired.returncode == clean.returncode == 0 and repaired.stdout == clean.stdout
    assert again.returncode == sibling.returncode == 0 and again.stdout == sibling.stdout


@pytest.mark.parametrize('population', ['clean_zero', 'empty_existing_suite', 'advisory_only', 'unknown_empty_targets'])
def test_controls_clean_zero_advisories_and_native_unresolved_rows_remain_valid(tmp_path, evidence, population):
    src, suite = _project(tmp_path / 'project', 'constant', 'unknown_targets' if population == 'unknown_empty_targets' else 'zero')
    if population == 'empty_existing_suite':
        (suite / 'test_main.py').unlink()
    if population == 'advisory_only':
        (suite / 'test_main.py').unlink()
        _write(suite / 'test_native.lua', 'local value = 1\n')
    response = run(*_argv(src, suite), '--format', 'json')
    data = json.loads(response.stdout)
    assert response.returncode == 0 and not data.get('error')
    assert not any(w.get('type') in ('analysis_failed', 'parse_recovered', 'analysis_incomplete')
                   for w in data['meta']['warnings'])
    assert not evidence['events']
    if population == 'unknown_empty_targets':
        patches = _raw(evidence, 'patches')[1]
        assert len(patches) == 2 and {p.target_raw for p in patches} == {'<unknown>', ''}
        assert data['summary']['total_patch_uses'] == 2


def test_control_requested_caps_and_advisory_warnings_do_not_imply_loss(tmp_path, evidence):
    src, suite = _project(tmp_path / 'project', 'pure', 'patch')
    uri = _argv(src, suite)[0].replace('min_patches=99', 'min_patches=1') + '&include_unresolved=true'
    uncut = run(uri, '--format', 'json')
    assert len(json.loads(uncut.stdout)['patch_hotspots']) == 1
    response = run(uri, '--max-items', '0', '--format', 'json')
    data = json.loads(response.stdout)
    assert len(_raw(evidence, 'patches')[1]) == len(_raw(evidence, 'profiles')[1]) == 1
    # Legacy Testability ignores this requested cut; binding harmonization is separate.
    assert isinstance(data['patch_hotspots'], list) and data['boundary_hotspots'] == []
    assert data['summary']['total_patch_uses'] == 1 and response.returncode == 0
    assert not evidence['events']
