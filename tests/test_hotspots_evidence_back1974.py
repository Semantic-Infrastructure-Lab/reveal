"""Hotspots retains its existing finding predicate before ranking cuts (BACK-1974)."""
import json
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.hotspots import HotspotsAdapter
from reveal.adapters.stats import metrics
from reveal.adapters.stats.adapter import StatsAdapter
from reveal.rendering.adapters.hotspots import HotspotsRenderer, _render_function_hotspots


def function(name, branches):
    return f'def {name}(x):\n' + ''.join(
        f'    if x == {i}: return {i}\n' for i in range(branches)) + '    return -1\n'


@pytest.fixture
def critical_file(tmp_path):
    file = tmp_path/'ranked.py'
    file.write_text(''.join(function(f'f{n}', n) for n in range(10, 23)), encoding='utf-8')
    return file


def test_real_single_file_hotspots_retains_quality_ranking(critical_file):
    stats = StatsAdapter(str(critical_file)).get_structure(hotspots=True)
    assert stats['summary']['avg_quality_score'] < 70  # real producer prerequisite
    assert len(stats['hotspots']) == 1
    assert stats['hotspots'][0]['quality_score'] == stats['summary']['avg_quality_score']
    result = HotspotsAdapter(str(critical_file), 'files_only=true').get_structure()
    assert len(result['file_hotspots']) == 1
    assert result['summary']['has_findings'] is True


@pytest.mark.parametrize('single', [False, True])
def test_check_rule_failure_disclosed_for_each_stats_resource(tmp_path, single):
    file = tmp_path/'source.py'
    file.write_text(function('small', 0), encoding='utf-8')
    with patch.object(metrics, '_count_local_check_issues', return_value=(
            {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}, ['E501'])):
        result = StatsAdapter(str(file if single else tmp_path)).get_structure(hotspots=True)
    assert result['files'][0]['check_rules_failed'] == ['E501']
    warning, = [w for w in result.get('meta', {}).get('warnings', [])
                 if w.get('type') == 'check_rules_failed']
    assert warning['count'] == 1 and warning['files'] == ['source.py']


def controlled_file_stats(path, *args):
    """Controlled metric records isolate composite ordering; not a real-corpus claim."""
    benign = path.name.startswith('benign')
    return {'file': path.name, 'lines': {'total': 1, 'code': 1, 'empty': 0, 'comments': 0},
            'elements': {'functions': 1, 'classes': 0, 'imports': 0},
            'complexity': {'average': 25 if benign else 0, 'max': 25 if benign else 0,
                           'min': 25 if benign else 0},
            'quality': {'score': 100 if benign else 69, 'long_functions': 0,
                        'deep_nesting': 0, 'avg_function_length': 1, 'local_check_issues': 0},
            'issues': {'long_functions': [], 'deep_nesting': []}}


@pytest.fixture
def controlled_rank(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path/'proj'
    root.mkdir()
    for name in ('benign.py', 'critical.py'):
        (root/name).write_text(function('small', 0), encoding='utf-8')
    monkeypatch.setattr(metrics, 'calculate_file_stats', controlled_file_stats)
    return root


@pytest.mark.parametrize('top,shown', [(1, 1), (0, 2), (10, 2)])
def test_file_finding_survives_composite_rank_cut(controlled_rank, top, shown):
    result = HotspotsAdapter('proj', f'files_only=true&top={top}').get_structure()
    assert len(result['file_hotspots']) == shown
    assert result['file_hotspots'][0]['quality_score'] == 100
    assert result['summary']['has_findings'] is True
    if top == 1:
        cut, = [w for w in result['meta']['warnings'] if w.get('type') == 'truncated']
        assert (cut['field'], cut['shown'], cut['total']) == ('file_hotspots', 1, 2)
        text = HotspotsRenderer._render_text(result)
        assert 'critical' in text.lower() and 'outside' in text.lower()
        assert 'no critical issues' not in text.lower()


@pytest.mark.parametrize('top', [1, 0])
def test_explicit_findings_gate_uses_uncapped_file_evidence(controlled_rank, top):
    result = run('hotspots', 'proj', '--files-only', '--top', str(top), '--fail-on', 'findings')
    assert result.returncode == 1, result.stderr


@pytest.mark.parametrize('spelling', ['cli', 'uri'])
def test_default_json_policy_reports_without_gate(controlled_rank, spelling):
    argv = ['hotspots', 'proj', '--files-only', '--top', '1'] if spelling == 'cli' else [
        'hotspots://proj?files_only=true&top=1']
    result = run(*argv, '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['summary']['has_findings'] is True


@pytest.mark.parametrize('branches,adverse', [(10, False), (19, False), (20, True), (21, True)])
@pytest.mark.parametrize('top', [1, 0, 10])
def test_actual_function_threshold_and_retained_max(tmp_path, branches, adverse, top):
    (tmp_path/'source.py').write_text(function('ranked', branches), encoding='utf-8')
    adapter = HotspotsAdapter(str(tmp_path), f'functions_only=true&top={top}')
    result = adapter.get_structure()
    assert result['function_hotspots'][0]['complexity'] == branches+1
    assert result['summary']['has_findings'] is adverse
    text = run('hotspots', str(tmp_path), '--functions-only', '--top', str(top), '--fail-on', 'findings')
    assert text.returncode == (1 if adverse else 0)


@pytest.mark.parametrize('query,expected_files,expected_functions,adverse', [
    ('functions_only=true', 0, 13, True), ('files_only=true', 1, 0, True),
    ('functions_only=true&files_only=true', 0, 0, False),
    ('functions_only=true&min_complexity=50', 0, 0, False),
])
def test_only_flags_and_minimum_keep_requested_population(critical_file, query, expected_files, expected_functions, adverse):
    result = HotspotsAdapter(str(critical_file.parent), query+'&top=0').get_structure()
    assert len(result['file_hotspots']) == expected_files
    assert len(result['function_hotspots']) == expected_functions
    assert result['summary']['has_findings'] is adverse
    assert result['summary']['total_files'] == 1


@pytest.mark.parametrize('hint,marker', [(True, '✅'), (False, '⚪'), (None, '❔')])
def test_existing_per_function_hint_renders_without_raw_index(hint, marker):
    result = _render_function_hotspots([{'name': 'ranked', 'complexity': 11,
                                       'file': 'source.py', 'has_test_hint': hint}])
    text = '\n'.join(result)
    assert '(✅ = test found' in text
    assert f' {marker} ranked' in text


def test_legacy_direct_helper_index_fallback_is_preserved():
    entry = {'name': 'ranked', 'complexity': 11, 'file': 'source.py'}
    with_index = '\n'.join(_render_function_hotspots([entry], {'ranked'}))
    without_index = '\n'.join(_render_function_hotspots([entry]))
    assert '✅ ranked' in with_index
    assert 'test found' not in without_index


def test_actual_rank_header_and_coverage_overlay_have_exact_text_parity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for n in range(12):
        (tmp_path/f'benign{n}.py').write_text(function('medium', 10), encoding='utf-8')
    a = run('hotspots', '.', '--top', '20')
    b = run('hotspots://.?top=20')
    assert a.returncode == b.returncode == 0
    assert 'File hotspots (top 12 by severity):' in a.stdout
    assert a.stdout == b.stdout
    assert '(✅ = test found' in a.stdout


@pytest.mark.parametrize('kind', ['clean', 'empty', 'unsupported', 'filtered'])
def test_empty_rankings_only_claim_requested_analyzed_population(tmp_path, kind):
    if kind == 'clean':
        (tmp_path/'source.py').write_text(function('small', 0), encoding='utf-8')
    elif kind == 'unsupported':
        (tmp_path/'source.xyz').write_text('unsupported\n', encoding='utf-8')
    elif kind == 'filtered':
        (tmp_path/'source.py').write_text(function('critical', 22), encoding='utf-8')
    query = 'functions_only=true&min_complexity=50' if kind == 'filtered' else ''
    result = HotspotsAdapter(str(tmp_path), query).get_structure()
    assert result['summary']['has_findings'] is False
    text = HotspotsRenderer._render_text(result)
    assert 'No hotspots found in the requested analyzed population.' in text
    assert 'Code quality looks good' not in text


def test_reused_adapter_clears_failure_and_finding_state(tmp_path):
    (tmp_path/'source.py').write_text(function('small', 0), encoding='utf-8')
    adapter = HotspotsAdapter(str(tmp_path), 'files_only=true')
    with patch.object(StatsAdapter, 'get_structure', side_effect=OSError('required stats unavailable')):
        failed = adapter.get_structure()
    assert failed['meta']['errors']
    restored = adapter.get_structure()
    assert not restored.get('meta', {}).get('errors')
    assert restored['summary']['has_findings'] is False


def test_reused_adapter_clears_previous_adverse_file_evidence(controlled_rank):
    adapter = HotspotsAdapter('proj', 'files_only=true&top=1')
    assert adapter.get_structure()['summary']['has_findings'] is True
    (controlled_rank/'critical.py').unlink()
    assert adapter.get_structure()['summary']['has_findings'] is False


def test_optional_churn_warning_metadata_is_not_a_finding(tmp_path):
    (tmp_path/'source.py').write_text(function('small', 0), encoding='utf-8')
    original = StatsAdapter.get_structure
    def observed(self, **kwargs):
        result = original(self, **kwargs)
        result.setdefault('meta', {}).setdefault('warnings', []).append(
            {'type': 'churn_unavailable', 'message': 'controlled optional churn unavailable'})
        return result
    with patch.object(StatsAdapter, 'get_structure', observed):
        result = HotspotsAdapter(str(tmp_path), 'files_only=true').get_structure()
    assert any(w.get('type') == 'churn_unavailable' for w in result['meta']['warnings'])
    assert result['summary']['has_findings'] is False


def test_single_file_without_hotspots_retains_existing_summary_shape(critical_file):
    result = StatsAdapter(str(critical_file)).get_structure()
    assert result['type'] == 'stats_file'
    assert result['summary']['total_files'] == 1
    assert 'hotspots' not in result


@pytest.mark.parametrize('top', [1, 0, 10])
def test_descending_function_maximum_survives_cut(tmp_path, top):
    (tmp_path/'source.py').write_text(function('medium', 10)+function('critical', 21), encoding='utf-8')
    result = HotspotsAdapter(str(tmp_path), f'functions_only=true&top={top}').get_structure()
    assert result['function_hotspots'][0]['name'] == 'critical'
    assert result['function_hotspots'][0]['complexity'] == 22
    assert len(result['function_hotspots']) == (1 if top == 1 else 2)
    assert result['summary']['has_findings'] is True


def test_legacy_uri_text_policy_stays_unchanged(controlled_rank):
    result = run('hotspots://proj?files_only=true&top=1')
    assert result.returncode == 0


def test_actual_optional_churn_warning_survives_stats_composition(tmp_path):
    (tmp_path/'source.py').write_text(function('small', 0), encoding='utf-8')
    def unavailable(self, stats):
        self._churn_disclosure = 'controlled optional churn unavailable'
        return None
    with patch.object(StatsAdapter, '_compute_churn_counts', unavailable):
        child = StatsAdapter(str(tmp_path)).get_structure(hotspots=True)
        assert child['warnings'][0]['type'] == 'churn_unavailable'
        assert not any(w.get('type') == 'churn_unavailable'
                       for w in child.get('meta', {}).get('warnings', []))
        result = HotspotsAdapter(str(tmp_path), 'files_only=true').get_structure()
    warning, = [w for w in result.get('meta', {}).get('warnings', [])
                 if w.get('type') == 'churn_unavailable']
    assert warning['message'] == 'controlled optional churn unavailable'
    assert result['summary']['has_findings'] is False
