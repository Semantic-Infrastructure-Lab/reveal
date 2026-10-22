"""Complementary binding features and constructed protocol defenses (BACK-2003)."""
import json
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.testability import TestabilityAdapter as Adapter
from reveal.testability import report

pytestmark = pytest.mark.component


@pytest.fixture
def project(tmp_path):
    src, tests = tmp_path / 'src', tmp_path / 'tests'
    src.mkdir()
    tests.mkdir()
    (src / 'service.py').write_text('def work(x):\n    return x\n', encoding='utf-8')
    (tests / 'test_service.py').write_text('from unittest.mock import patch\npatch("service.work")\n', encoding='utf-8')
    return src, tests


def uri(src, tests):
    return f'testability://{src}?tests={quote(str(tests), safe="")}&min_patches=1&include_unresolved=true'


@pytest.mark.parametrize('mutation', ['plain_list', 'bad_skipped', 'bad_recovered', 'bad_traversal'])
def test_constructed_carrier_protocol_failure_dominates_real_profile(project, monkeypatch, mutation):
    src, tests = project
    real = report.scan_patches
    reached = []
    def malformed(paths, **kwargs):
        rows = real(paths, **kwargs)
        assert rows
        reached.append(len(rows))
        if mutation == 'plain_list':
            return list(rows)
        if mutation == 'bad_skipped':
            rows.skipped = [('test.py', 42)]
        elif mutation == 'bad_recovered':
            rows.recovered_files = 'test.py'
        else:
            rows.traversal_failures = [(42, 'unknown directory')]
        return rows
    monkeypatch.setattr(report, 'scan_patches', malformed)
    response = run(uri(src, tests), '--format', 'json')
    data = json.loads(response.stdout)
    assert reached == [1] and response.returncode == 3
    assert data.get('error') or data.get('meta', {}).get('errors')


@pytest.mark.parametrize('mutation', ['bool_count', 'missing_count', 'bad_ranked', 'bad_collection', 'count_mismatch'])
def test_constructed_report_envelope_is_required_even_with_positive_other_population(project, monkeypatch, mutation):
    src, tests = project
    real = report.build_testability_report
    def malformed(*args, **kwargs):
        data = real(*args, **kwargs)
        assert data['summary']['total_patch_uses'] == data['summary']['total_boundary_profiles'] == 1
        if mutation == 'bool_count':
            data['summary']['total_boundary_profiles'] = True
        elif mutation == 'missing_count':
            del data['summary']['total_patch_uses']
        elif mutation == 'bad_ranked':
            data['patch_hotspots'][0]['score'] = float('nan')
        elif mutation == 'bad_collection':
            # The adapter reauthors tests from resolved roots, so mutate another
            # required public collection rather than that protected field.
            data['boundary_hotspots'] = {'forged': 'rows'}
        else:
            data['summary']['patch_groups_reported'] += 1
        return data
    monkeypatch.setattr(report, 'build_testability_report', malformed)
    response = run(uri(src, tests), '--format', 'json')
    data = json.loads(response.stdout)
    assert response.returncode == 3 and (data.get('error') or data.get('meta', {}).get('errors'))


@pytest.mark.parametrize('tests', [[], [''], [True], ['valid', None]])
def test_typed_empty_or_nonpath_roots_are_usage_errors_before_collection(project, monkeypatch, tests):
    src, _ = project
    calls = []
    monkeypatch.setattr(report, 'scan_patches', lambda *a, **k: calls.append('patches'))
    with pytest.raises((ValueError, TypeError)):
        Adapter(str(src), params={'tests': tests})
    assert calls == []


def test_exact_large_decimal_and_fraction_rejection_use_actual_bound_values(project, monkeypatch):
    src, tests = project
    real = report.build_testability_report
    values = []
    def capture(*args, **kwargs):
        values.append(kwargs['top'])
        return real(*args, **kwargs)
    monkeypatch.setattr(report, 'build_testability_report', capture)
    huge = '900719925474099312345678901234567890'
    good = run(uri(src, tests)+'&top='+huge+'.000', '--format', 'json')
    assert good.returncode == 0 and values == [int(huge)]
    bad = run(uri(src, tests)+'&top='+huge+'.001', '--format', 'json')
    assert bad.returncode == 2 and values == [int(huge)]


def test_artifact_write_failure_preserves_primary_text_and_failure_exit(project, tmp_path):
    src, tests = project
    # A directory is a genuine output write error, independent of analysis.
    response = run(uri(src, tests), '--format', 'text', '--also-json', str(tmp_path))
    assert response.returncode == 3
    assert 'Testability:' in response.stdout and 'Patch uses: 1' in response.stdout


def test_postprocess_cannot_launder_prior_required_failure(project, monkeypatch):
    src, tests = project
    (src / 'service.py').write_text('VALUE=1\n', encoding='utf-8')
    (tests / 'test_service.py').write_text('def broken(:\n', encoding='utf-8')
    real = Adapter.post_process
    called = []
    def launder(self, result, args):
        result = real(self, result, args)
        called.append(1)
        result.pop('error', None)
        result['meta'] = {'warnings': [], 'errors': [], 'confidence': 0.75}
        result['summary']['total_boundary_profiles'] = 1
        return result
    monkeypatch.setattr(Adapter, 'post_process', launder)
    response = run(uri(src, tests), '--max-items', '0', '--format', 'json')
    assert called == [1] and response.returncode == 3
