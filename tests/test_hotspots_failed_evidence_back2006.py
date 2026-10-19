"""Required Hotspots loss is usable only when requested observations survived."""

import builtins
import json
from pathlib import Path

import pytest

from reveal.adapters.hotspots import HotspotsAdapter
from reveal.adapters.stats import adapter as stats
from reveal.cli.commands import review
from reveal.utils.results import AnalysisCompleteness


@pytest.fixture
def wire():
    from test_mcp_expected_errors_back1992 import _run, _text
    return _run, _text


def deny_source(monkeypatch):
    original = builtins.open

    def opened(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file).name == 'lost.py':
            raise PermissionError(13, 'controlled required source loss', str(file))
        return original(file, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', opened)


def project(tmp_path, partial=False):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'lost.py').write_text('def lost():\n    return 1\n', encoding='utf-8')
    if partial:
        (root / 'visible.py').write_text('VALUE = 1\n', encoding='utf-8')
    return root


@pytest.mark.parametrize('query', ['files_only=true', '', 'files_only=true&functions_only=true'])
def test_all_required_file_analysis_lost_is_failed(tmp_path, monkeypatch, query):
    root = project(tmp_path)
    deny_source(monkeypatch)
    adapter = HotspotsAdapter(str(root), query)
    result = adapter.get_structure()
    assert result['summary']['total_files'] == 0
    assert result['file_hotspots'] == result['function_hotspots'] == []
    assert adapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED


@pytest.mark.parametrize('query', ['files_only=true', 'files_only=true&functions_only=true'])
def test_clean_zero_remains_complete(tmp_path, query):
    adapter = HotspotsAdapter(str(tmp_path), query)
    result = adapter.get_structure()
    assert result['summary']['total_files'] == 0
    assert adapter.execution_facts(result).completeness is AnalysisCompleteness.COMPLETE


@pytest.mark.parametrize('query', ['files_only=true', 'files_only=true&functions_only=true'])
def test_positive_file_coverage_is_usable_even_with_empty_rankings(tmp_path, monkeypatch, query):
    root = project(tmp_path, partial=True)
    deny_source(monkeypatch)
    adapter = HotspotsAdapter(str(root), query)
    result = adapter.get_structure()
    assert result['summary']['total_files'] == 1
    if 'functions_only=true' in query:
        assert result['file_hotspots'] == result['function_hotspots'] == []
    assert adapter.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE


def test_clean_requested_functions_survive_selective_total_stats_loss(tmp_path, monkeypatch):
    (tmp_path / 'visible.py').write_text('def visible():\n    return 1\n', encoding='utf-8')
    monkeypatch.setattr(stats, '_analyze_file_worker', lambda args: {
        'analysis_failed': 'PermissionError: controlled Stats-only loss', 'path': args[0]})
    adapter = HotspotsAdapter(str(tmp_path), 'functions_only=true&min_complexity=0&top=1')
    result = adapter.get_structure()
    assert result['summary']['total_files'] == 0
    assert result['function_hotspots'][0]['name'] == 'visible'
    assert adapter.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE


def test_clean_ast_without_requested_function_match_does_not_make_loss_usable(tmp_path, monkeypatch):
    (tmp_path / 'visible.py').write_text('def visible():\n    return 1\n', encoding='utf-8')
    monkeypatch.setattr(stats, '_analyze_file_worker', lambda args: {
        'analysis_failed': 'PermissionError: controlled Stats-only loss', 'path': args[0]})
    adapter = HotspotsAdapter(str(tmp_path), 'functions_only=true&min_complexity=10')
    result = adapter.get_structure()
    assert result['summary']['total_files'] == 0
    assert result['function_hotspots'] == []
    assert adapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED


def test_review_required_discovery_warning_marks_analysis_incomplete():
    report = {'meta': {'warnings': [{
        'type': 'analysis_incomplete', 'count': 1, 'unit': 'directories',
        'directories': ['included_child'], 'message': 'hotspots: required directory loss',
    }]}}
    assert review._lost_analysis(report)
    assert review._review_outcome([], [], analysis_incomplete=review._lost_analysis(report)) == ('incomplete', 3)


def test_review_incomplete_analysis_takes_precedence_over_blocking_findings():
    # D6: once analysis begins, lost or capped evidence beats a findings gate (BACK-2051).
    blocking = [{'severity': 'high'}]
    assert review._review_outcome(blocking, [], analysis_incomplete=True) == ('incomplete', 3)
    assert review._review_outcome(blocking, ['x.py: could not be checked']) == ('incomplete', 3)
    assert review._review_outcome(blocking, [], scan_incomplete=True) == ('incomplete', 3)


def test_review_blocking_finding_alone_is_a_finding_not_a_usage_code():
    # Exit 2 means usage rejection everywhere else; a high/critical violation is exit 1.
    for severity in ('high', 'critical'):
        assert review._review_outcome([{'severity': severity}], []) == ('fail', 1)
    assert review._review_outcome([{'severity': 'medium'}], []) == ('warn', 1)


def test_review_optional_churn_warning_does_not_mark_required_analysis_lost():
    report = {'meta': {'warnings': [{'type': 'churn_unavailable', 'message': 'optional history unavailable'}]}}
    assert not review._lost_analysis(report)
    assert review._review_outcome([], [], analysis_incomplete=review._lost_analysis(report)) == ('pass', 0)


@pytest.mark.parametrize('format', ['text', 'json'])
def test_review_actual_stats_directory_loss_returns_incomplete(tmp_path, monkeypatch, format):
    from conftest import _run_reveal_direct
    from test_stats_traversal_back2006 import tree, deny_stats

    child = tree(tmp_path)
    attempts = deny_stats(monkeypatch, {child})
    result = _run_reveal_direct('review', str(tmp_path), '--select', 'C', '--format', format)
    assert attempts, 'the actual Stats collector must encounter the denied directory'
    if format == 'json':
        report = json.loads(result.stdout)
        diagnostic, = [warning for warning in report['meta']['warnings']
                       if warning.get('type') == 'analysis_incomplete']
        assert diagnostic['directories'] == ['included_child']
        assert diagnostic['unit'] == 'directories'
        assert report['overall_status'] == 'incomplete'
    else:
        assert 'included_child' in result.stdout
    assert result.returncode == 3, result.stderr


_SERVER = '''
import builtins
from pathlib import Path
from reveal import mcp_server
original = builtins.open
def opened(file, *args, **kwargs):
    if isinstance(file, (str, Path)) and Path(file).name == 'lost.py':
        raise PermissionError(13, 'controlled required source loss', str(file))
    return original(file, *args, **kwargs)
builtins.open = opened
mcp_server.main()
'''


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [False, True])
def test_mcp_all_loss_is_error_without_usable_evidence_claim(tmp_path, provenance, wire):
    _run, _text = wire
    root = project(tmp_path)

    async def scenario(session):
        result = await session.call_tool('reveal_query', {
            'uri': f'hotspots://{root}?files_only=true', 'provenance': provenance})
        assert result.is_error
        assert 'usable evidence follows' not in _text(result).lower()

    _run(tmp_path, scenario, _SERVER)


@pytest.mark.mcp
def test_mcp_partial_file_observations_remain_usable(tmp_path, wire):
    _run, _text = wire
    root = project(tmp_path, partial=True)

    async def scenario(session):
        result = await session.call_tool('reveal_query', {
            'uri': f'hotspots://{root}?files_only=true', 'provenance': False})
        assert not result.is_error
        assert 'lost.py' in _text(result)
        assert 'incomplete' in _text(result).lower()

    _run(tmp_path, scenario, _SERVER)
