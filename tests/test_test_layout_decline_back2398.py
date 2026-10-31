"""Unqualified role filters decline configured selectors at their request boundary."""
import json
import pytest

from conftest import _run_reveal_direct
from reveal.api import query
from reveal.errors import RequestValidationError


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="decline"\n', encoding='utf-8')
    (tmp_path / '.reveal.yaml').write_text('test_layout:\n  additional_paths: [helpers]\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('import os\ndef app():\n    return os.getenv("X")\n', encoding='utf-8')
    (tmp_path / 'helpers').mkdir()
    (tmp_path / 'helpers' / 'probe.py').write_text('from unittest.mock import patch\nwith patch("os.getcwd"):\n    pass\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('scheme,parameters', [('patches', ''), ('testability', ''), ('patches', 'view=pressure')])
def test_qualified_patch_selection_adopts_project_policy(configured, scheme, parameters):
    uri = f'{scheme}://{configured}?{parameters}'
    answer = query(uri)
    assert answer['test_scope']['additional_paths'] == ['helpers']
    assert answer['test_scope']['files_scanned'] == 1
    result = _run_reveal_direct(uri, '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['test_scope'] == answer['test_scope']


def test_unrelated_surface_and_trusted_explicit_suite_remain_usable(configured):
    assert query(f'surface://{configured}')['type'] == 'surface_scan'
    result = query(f'testability://{configured}?tests={configured / "helpers"}')
    assert result['test_scope']['rule'] == 'tests='


def test_stats_invalid_policy_rejects_before_required_file_analysis(configured, monkeypatch):
    from reveal.adapters.stats.adapter import StatsAdapter

    (configured / '.reveal.yaml').write_text('test_layout:\n  additional_paths: [../escape]\n', encoding='utf-8')

    def forbidden(*args, **kwargs):
        raise AssertionError('invalid policy must be validated before scanning')

    monkeypatch.setattr(StatsAdapter, '_collect_filtered_stats', forbidden)
    with pytest.raises(RequestValidationError, match='test_layout'):
        query(f'stats://{configured}?hotspots=true&tests=exclude')


@pytest.mark.parametrize('error', [ValueError('legacy failure'), RequestValidationError('legacy request failure')])
def test_unrelated_legacy_stats_errors_keep_exit_one(configured, monkeypatch, error):
    from reveal.adapters.stats.adapter import StatsAdapter

    def rejected(*args, **kwargs):
        raise error

    monkeypatch.setattr(StatsAdapter, 'get_structure', rejected)
    result = _run_reveal_direct(f'stats://{configured}', '--format', 'json')
    assert result.returncode == 1
