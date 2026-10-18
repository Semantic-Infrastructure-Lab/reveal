"""Required Hotspots loss is usable only when requested observations survived."""

import builtins
from pathlib import Path

import pytest

from reveal.adapters.hotspots import HotspotsAdapter
from reveal.adapters.stats import adapter as stats
from reveal.utils.results import AnalysisCompleteness
from test_mcp_expected_errors_back1992 import _run, _text


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
def test_mcp_all_loss_is_error_without_usable_evidence_claim(tmp_path, provenance):
    root = project(tmp_path)

    async def scenario(session):
        result = await session.call_tool('reveal_query', {
            'uri': f'hotspots://{root}?files_only=true', 'provenance': provenance})
        assert result.is_error
        assert 'usable evidence follows' not in _text(result).lower()

    _run(tmp_path, scenario, _SERVER)


@pytest.mark.mcp
def test_mcp_partial_file_observations_remain_usable(tmp_path):
    root = project(tmp_path, partial=True)

    async def scenario(session):
        result = await session.call_tool('reveal_query', {
            'uri': f'hotspots://{root}?files_only=true', 'provenance': False})
        assert not result.is_error
        assert 'visible.py' in _text(result)
        assert 'incomplete' in _text(result).lower()

    _run(tmp_path, scenario, _SERVER)
