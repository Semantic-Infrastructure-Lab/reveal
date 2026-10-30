"""Canonical architecture alias paths preserve native and already-POSIX spellings."""
from copy import deepcopy
from pathlib import Path, PureWindowsPath

import pytest

from reveal.adapters import overview
from reveal.adapters.architecture import ArchitectureAdapter

NATIVE = 'pkg\\sub'


@pytest.fixture
def stub_analysis(tmp_path, monkeypatch):
    (tmp_path / 'mod.py').write_text('VALUE=1\n', encoding='utf-8')
    actual = ArchitectureAdapter(str(tmp_path)).get_structure()
    class NativePath(PureWindowsPath):
        def expanduser(self):
            return self
        def stat(self):
            return tmp_path.stat()
        def resolve(self):
            return tmp_path.resolve()
    native = Path
    monkeypatch.setattr(overview, 'Path', lambda value: NativePath(value) if str(value) in (NATIVE, 'pkg/sub') else native(value))
    monkeypatch.setattr(overview, '_run_scope', lambda *_a, **_k: deepcopy(actual['scope']))
    monkeypatch.setattr(overview, '_run_imports_analysis', lambda *_a, **_k: (deepcopy(actual['map']), 'complete'))
    monkeypatch.setattr(overview, '_navigation_exclusions', lambda *_a: [])


@pytest.mark.parametrize('query', ['', 'no_imports=true'])
def test_report_path_and_source_use_forward_slashes(stub_analysis, query):
    result = ArchitectureAdapter(NATIVE, query).get_structure()
    assert result['path'] == result['source'] == 'pkg/sub'
    assert result['type'] == 'overview'


def test_forward_slash_target_is_unchanged(stub_analysis):
    result = ArchitectureAdapter('pkg/sub').get_structure()
    assert result['path'] == result['source'] == 'pkg/sub'


def test_real_directory_report_keeps_its_spelling_and_type(tmp_path):
    (tmp_path / 'mod.py').write_text('VALUE=1\n', encoding='utf-8')
    result = ArchitectureAdapter(str(tmp_path), 'no_imports=true').get_structure()
    assert result['path'] == tmp_path.as_posix()
    assert result['source_type'] == 'directory'


def test_against_request_error_source_uses_forward_slashes(tmp_path, monkeypatch, stub_analysis):
    monkeypatch.chdir(tmp_path)
    result = ArchitectureAdapter(NATIVE, 'against=HEAD').get_structure()
    assert result['type'] == 'overview_diff'
    assert result['meta']['errors'][0]['code'] == 'invalid_request'
    assert result['source'] == 'pkg/sub'
