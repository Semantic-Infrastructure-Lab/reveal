"""Unqualified role filters decline configured selectors at their request boundary."""
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


@pytest.mark.parametrize('scheme,parameters', [('stats', 'hotspots=true&tests=exclude'), ('surface', 'source_only=true'), ('patches', ''), ('testability', ''), ('patches', 'view=pressure')])
def test_unqualified_explicit_role_filters_exit_two_and_api_rejects(configured, scheme, parameters):
    uri = f'{scheme}://{configured}?{parameters}'
    with pytest.raises(RequestValidationError, match='test_layout'):
        query(uri)
    result = _run_reveal_direct(uri, '--format', 'json')
    assert result.returncode == 2, result.stderr
    assert 'test_layout' in result.stderr


def test_unrelated_surface_and_trusted_explicit_suite_remain_usable(configured):
    assert query(f'surface://{configured}')['type'] == 'surface_scan'
    result = query(f'testability://{configured}?tests={configured / "helpers"}')
    assert result['test_scope']['rule'] == 'tests='
