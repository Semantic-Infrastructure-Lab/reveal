"""Existing testability inputs expose root, identity, and required-evidence defects.

Numeric spelling harmonization is explicitly labelled as binding feature adoption.
"""
import json
import os
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.testability import report

pytestmark = pytest.mark.component
SOURCE = 'def run(value):\n    return value + 1\n'
PATCH = 'from unittest.mock import patch\ndef test_use():\n    with patch("bridge.run"):\n        pass\n'


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


@pytest.fixture
def project(tmp_path):
    _write(tmp_path / 'src' / 'bridge.py', SOURCE)
    _write(tmp_path / 'tests' / 'test_bridge.py', PATCH)
    return tmp_path / 'src', tmp_path / 'tests'


@pytest.fixture
def observed(monkeypatch):
    state = {'calls': [], 'builds': [], 'active': None, 'denied': set(), 'events': []}
    real_patches, real_profiles, real_build, real_scandir = (
        report.scan_patches, report.collect_boundary_profiles, report.build_testability_report, os.scandir)

    def collect(kind, function, *args, **kwargs):
        state['active'] = kind
        try:
            value = function(*args, **kwargs)
            state['calls'].append((kind, len(value), list(value.skipped), list(value.traversal_failures)))
            return value
        finally:
            state['active'] = None

    def build(*args, **kwargs):
        state['builds'].append(kwargs.copy())
        return real_build(*args, **kwargs)

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append((state['active'], Path(path).resolve()))
            raise PermissionError(13, 'actual testability required discovery loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(report, 'scan_patches', lambda *a, **k: collect('patches', real_patches, *a, **k))
    monkeypatch.setattr(report, 'collect_boundary_profiles', lambda *a, **k: collect('profiles', real_profiles, *a, **k))
    monkeypatch.setattr(report, 'build_testability_report', build)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _args(src, roots, spelling, query=''):
    if spelling == 'native':
        return ['testability', str(src), '--tests', *map(str, roots)]
    encoded = ','.join(quote(str(root), safe='') for root in roots)
    return [f'testability://{src.as_posix()}?tests={encoded}'+('&'+query if query else '')]


@pytest.mark.parametrize('spelling', ['native', 'uri'])
def test_existing_success_uses_report_owner_identity(project, spelling):
    src, tests = project
    # Plain existing paths avoid folding codec failure into identity proof.
    args = ['testability', str(src), '--tests', str(tests)] if spelling == 'native' else [f'testability://{src}?tests={tests}']
    response = run(*args, '--format', 'json')
    assert response.returncode == 0
    assert json.loads(response.stdout)['type'] == 'testability_report'


@pytest.mark.parametrize('spelling', ['native', 'uri'])
@pytest.mark.parametrize('kind', ['mixed', 'missing', 'explicit-empty'])
def test_explicit_bad_roots_reject_before_either_collector(project, observed, spelling, kind):
    src, tests = project
    missing = src.parent / 'missing'
    roots = [tests, missing] if kind == 'mixed' else ([missing] if kind == 'missing' else [''])
    # These paths contain no encoded characters: isolate preflight from codec behavior.
    args = ['testability', str(src), '--tests', *map(str, roots)] if spelling == 'native' else [f'testability://{src}?tests='+','.join(map(str, roots))]
    response = run(*args, '--format', 'json')
    assert response.returncode == 2, (response.stdout, response.stderr, observed)
    assert observed['calls'] == [] and observed['builds'] == []


@pytest.mark.parametrize('spelling', ['native', 'uri'])
def test_explicit_root_operational_error_is_analysis_failure_before_collectors(project, observed, monkeypatch, spelling):
    src, tests = project
    real_stat = Path.stat
    def stat(path, *args, **kwargs):
        if path == tests and observed['active'] is None:
            raise PermissionError(13, 'actual explicit test-root permission failure', str(path))
        return real_stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    args = ['testability', str(src), '--tests', str(tests)] if spelling == 'native' else [f'testability://{src}?tests={tests}']
    response = run(*args, '--format', 'json')
    assert response.returncode == 3, (response.stdout, response.stderr)
    assert observed['calls'] == [] and observed['builds'] == []
    assert 'PermissionError' in response.stdout + response.stderr or 'permission failure' in response.stdout + response.stderr


@pytest.mark.parametrize('name', ['tests,extra', 'tests&top=0', 'tests with spaces', 'tests%26literal', 'tests+plus=Ω'])
@pytest.mark.parametrize('spelling', ['native', 'uri'])
def test_typed_and_comma_percent_roots_preserve_actual_requested_population(project, observed, name, spelling):
    src, _ = project
    root = src.parent / name
    _write(root / 'test_special.py', PATCH * 3)
    response = run(*_args(src, [root], spelling), '--format', 'json')
    assert response.returncode == 0, (response.stdout, response.stderr)
    result = json.loads(response.stdout)
    assert result['summary']['total_patch_uses'] == 3, result
    assert result['tests'] == [str(root)], result
    assert ('patches', 3) == observed['calls'][0][:2]


@pytest.mark.parametrize('name', ['0', 'true'])
def test_native_typed_relative_numeric_like_test_paths_are_strings(project, monkeypatch, name):
    src, _ = project
    _write(src.parent / name / 'test_special.py', PATCH * 3)
    monkeypatch.chdir(src.parent)
    response = run('testability', 'src', '--tests', name, '--format', 'json')
    assert response.returncode == 0, (response.stdout, response.stderr)
    result = json.loads(response.stdout)
    assert result['summary']['total_patch_uses'] == 3 and result['tests'] == [name]


@pytest.mark.parametrize('population', ['constant-allfailed', 'pure-profile-survives', 'patch-use-survives'])
@pytest.mark.parametrize('spelling', ['native', 'uri'])
def test_actual_required_loss_never_looks_complete_from_empty_ranked_arrays(tmp_path, observed, population, spelling):
    src, tests = tmp_path / 'src', tmp_path / 'tests'
    if population == 'patch-use-survives':
        _write(src / 'bridge.ts', 'const broken = ;\n')
        _write(tests / 'test_bridge.py', PATCH)
    else:
        _write(src / 'bridge.py', 'VALUE=1\n' if population == 'constant-allfailed' else SOURCE)
        _write(tests / 'test_bridge.py', 'def broken(:\n')
    args = ['testability', str(src), '--tests', str(tests)] if spelling == 'native' else [f'testability://{src}?tests={tests}']
    response = run(*args, '--format', 'json')
    assert response.returncode == 3, (response.stdout, response.stderr, observed)
    result = json.loads(response.stdout)
    assert result['patch_hotspots'] == result['boundary_hotspots'] == []
    assert result['meta']['confidence'] == 0.75 and result['meta']['parse_mode'] == 'python_ast'
    raw = {kind: count for kind, count, _, _ in observed['calls']}
    assert raw == {'patches': int(population == 'patch-use-survives'), 'profiles': int(population == 'pure-profile-survives')}
    assert any(w.get('type') in ('analysis_failed', 'parse_recovered') for w in result['meta']['warnings'])


@pytest.mark.parametrize('stage', ['patches', 'profiles'])
def test_actual_directory_loss_is_incomplete_even_with_surviving_hidden_domain_observation(project, observed, stage):
    src, tests = project
    observed['denied'] = {tests if stage == 'patches' else src}
    response = run(f'testability://{src}?tests={tests}&min_patches=99&min_categories=99', '--format', 'json')
    assert observed['events'] == [(stage, tests if stage == 'patches' else src)]
    assert response.returncode == 3, (response.stdout, response.stderr)
    result = json.loads(response.stdout)
    assert result['patch_hotspots'] == result['boundary_hotspots'] == []
    assert any(w.get('unit') == 'directories' for w in result['meta']['warnings'])


@pytest.mark.parametrize('spelling', ['native', 'uri'])
def test_existing_empty_test_directory_is_valid_zero_not_explicit_empty_input(tmp_path, observed, spelling):
    source = tmp_path / 'constant.py'
    _write(source, 'VALUE=1\n')
    tests = tmp_path / 'empty_tests'
    tests.mkdir()
    args = ['testability', str(source), '--tests', str(tests)] if spelling == 'native' else [f'testability://{source}?tests={tests}']
    response = run(*args, '--format', 'json')
    assert response.returncode == 0
    result = json.loads(response.stdout)
    assert result['summary']['total_patch_uses'] == 0
    assert result['patch_hotspots'] == result['boundary_hotspots'] == []
    assert all(count == 0 and not skipped and not errors for _, count, skipped, errors in observed['calls'])


@pytest.mark.parametrize('spelling', ['native', 'uri'])
def test_omitted_no_tests_is_legitimate_nonapplicability_zero(tmp_path, spelling):
    _write(tmp_path / 'src' / 'constant.py', 'VALUE=1\n')
    args = ['testability', str(tmp_path / 'src')] if spelling == 'native' else [f'testability://{tmp_path/"src"}']
    response = run(*args, '--format', 'json')
    assert response.returncode == 0, (response.stdout, response.stderr)


@pytest.mark.parametrize('value', ['1.9', 'true', 'NaN', 'inf', '3e0', '9007199254740993.1'])
def test_numeric_validation_uses_exact_whole_values_and_usage_error(project, observed, value):
    src, tests = project
    response = run(f'testability://{src}?tests={tests}&top={value}', '--format', 'json')
    assert response.returncode == 2, (response.stdout, response.stderr)
    assert observed['calls'] == [] and observed['builds'] == []


@pytest.mark.parametrize('value,expected', [('9007199254740993.0', 9007199254740993), ('-2.0', 0)])
def test_accepted_uri_whole_decimal_normalization_is_exact_and_preserves_clamps(project, observed, value, expected):
    src, tests = project
    response = run(f'testability://{src}?tests={tests}&top={value}', '--format', 'json')
    assert response.returncode == 0
    assert observed['builds'][0]['top'] == expected


@pytest.mark.parametrize('value', ['+3.0', '.0'])
def test_binding_feature_whole_decimal_native_spelling_harmonization(project, observed, value):
    """Feature adoption: old argparse rejects these URI-compatible whole values."""
    src, tests = project
    response = run('testability', str(src), '--tests', str(tests), '--top', value, '--format', 'json')
    assert response.returncode == 0
    assert observed['builds'][0]['top'] == (3 if value == '+3.0' else 0)


@pytest.mark.parametrize('spelling', ['native', 'uri'])
@pytest.mark.parametrize('partial', [False, True])
def test_declared_text_accepts_ranked_top_without_render_failure(project, observed, spelling, partial):
    src, tests = project
    if partial:
        _write(tests / 'test_broken.py', 'def broken(:\n')
    response = run(*_args(src, [tests], spelling), '--format', 'text')
    assert response.returncode == (3 if partial else 0), (response.stdout, response.stderr)
    assert 'Testability:' in response.stdout
    assert 'Production Patch Hotspots' in response.stdout
    assert 'Boundary Fan-Out Hotspots' in response.stdout
    assert 'unexpected keyword' not in response.stdout + response.stderr
    assert [kind for kind, *_ in observed['calls']] == ['patches', 'profiles']
    if partial:
        assert 'missing from the report' in response.stdout


@pytest.mark.parametrize('spelling', ['native', 'uri'])
def test_binding_features_cut_both_lists_before_fields_and_keep_full_artifact(project, spelling, tmp_path):
    src, tests = project
    _write(src / 'bridge.py', 'import requests\nimport os\ndef run():\n    open("data")\n    requests.get("https://example.com")\n    return os.getenv("TOKEN")\n')
    artifact = tmp_path / 'answer.json'
    if spelling == 'native':
        args = _args(src, [tests], spelling) + ['--min-patches', '1', '--min-categories', '1', '--include-unresolved']
    else:
        args = _args(src, [tests], spelling, 'min_patches=1&min_categories=1&include_unresolved=true')
    uncut = run(*args, '--format', 'json')
    data = json.loads(uncut.stdout)
    assert uncut.returncode == 0 and len(data['patch_hotspots']) == len(data['boundary_hotspots']) == 1
    response = run(*args, '--max-items', '0', '--fields', 'patch_hotspots,boundary_hotspots',
                   '--format', 'json', '--provenance')
    data = json.loads(response.stdout)
    assert response.returncode == 0, (response.stdout, response.stderr)
    sidecar = run(*args, '--max-items', '0', '--fields', 'patch_hotspots,boundary_hotspots',
                  '--also-json', str(artifact), '--provenance')
    assert sidecar.returncode == 0, (sidecar.stdout, sidecar.stderr)
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    assert saved['patch_hotspots'] == saved['boundary_hotspots'] == []
    assert saved['summary']['total_patch_uses'] == saved['summary']['total_boundary_profiles'] == 1
    from reveal.utils.results import truncations_of
    assert truncations_of(saved) == truncations_of(data)
    assert data['patch_hotspots'] == data['boundary_hotspots'] == []
    assert 'summary' not in data
    assert len(truncations_of(data)) == 2


@pytest.mark.parametrize('value', [True, False, 1.5, float('inf'), float('nan')])
def test_typed_numeric_controls_reject_boolean_fraction_and_nonfinite(project, value):
    from reveal.adapters.testability import TestabilityAdapter
    src, tests = project
    with pytest.raises(ValueError):
        TestabilityAdapter(str(src), params={'tests': [str(tests)], 'top': value})


@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_verbose_override_keeps_explicit_top_unused_in_ledger(project, observed, output_format):
    src, tests = project
    response = run('testability', str(src), '--tests', str(tests), '--top', '1',
                   '--verbose', '--format', output_format)
    assert response.returncode == 0, (response.stdout, response.stderr)
    assert observed['builds'][0]['top'] > 1
    assert 'top' in response.stderr and 'not' in response.stderr, response.stderr
