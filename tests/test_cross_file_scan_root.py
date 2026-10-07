"""A file with no project marker directly in the OS temp dir (or $HOME) must not make a
cross-file rule index that whole directory.

D005, T006 and I002 fall back to the file's own directory when no marker is found. For
``/tmp/x.py`` that directory is the shared temp dir: ``reveal /tmp/x.py --check`` on a
5-line file took 5.8 s (0.49 s for the same file in a clean dir) walking 126k entries,
and ~20 s per test under xdist, where the temp dir is busiest. I002 already refused an
unsafe root; D005 and T006 did not, and the preloads did not either.
"""
import os
import tempfile
from pathlib import Path

import pytest

from reveal.rules.duplicates import D005 as d005_module
from reveal.rules.imports import I002 as i002_module
from reveal.rules.types import T006 as t006_module
from reveal.utils.path_utils import cross_file_scan_root, resolve_project_root

CODE = "EXTS = ['.py', '.js', '.ts', '.rs', '.go']\n"


@pytest.fixture
def file_in_temp_root():
    fd, name = tempfile.mkstemp(suffix='.py', dir=tempfile.gettempdir())
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(CODE)
    path = Path(name).resolve()
    if resolve_project_root(path) is not None:
        path.unlink()
        pytest.skip('the OS temp dir sits inside a project on this machine')
    yield path
    path.unlink()


def _refuse(*_args, **_kwargs):
    raise AssertionError('indexed the OS temp dir as a project')


def test_no_scan_root_for_a_file_directly_in_the_temp_dir(file_in_temp_root):
    assert cross_file_scan_root(file_in_temp_root) is None
    assert d005_module._find_project_root(file_in_temp_root) is None
    assert t006_module._find_project_root(file_in_temp_root) is None
    assert i002_module._find_project_root(file_in_temp_root) is None


def test_marker_less_subdir_still_scopes_to_its_own_directory(tmp_path):
    f = tmp_path / 'lone.py'
    f.write_text(CODE, encoding='utf-8')
    assert cross_file_scan_root(f.resolve()) == tmp_path.resolve()


def test_d005_check_does_not_index_the_temp_dir(file_in_temp_root, monkeypatch):
    d005_module._clear_index()
    monkeypatch.setattr(d005_module, '_build_index', _refuse)
    assert d005_module.D005().check(str(file_in_temp_root), None, CODE) == []


def test_t006_does_not_index_the_temp_dir(file_in_temp_root, monkeypatch):
    monkeypatch.setattr(t006_module, '_build_index', _refuse)
    assert t006_module._project_facts(str(file_in_temp_root)) is t006_module._EMPTY_FACTS


@pytest.mark.parametrize('preload', ['_d005_preload', '_t006_preload', '_i002_preload'])
def test_preload_does_not_index_the_temp_dir(file_in_temp_root, monkeypatch, preload):
    from reveal.rules import scan_caches
    monkeypatch.setattr(d005_module, '_build_index', _refuse)
    monkeypatch.setattr(t006_module, '_build_index', _refuse)
    monkeypatch.setattr(i002_module.I002, '_build_import_graph', _refuse)
    monkeypatch.setattr(scan_caches.logging, 'warning', _refuse)  # the preload swallows errors
    assert getattr(scan_caches, preload)(file_in_temp_root.parent, None, None,
                                         files=[file_in_temp_root]) == {}
