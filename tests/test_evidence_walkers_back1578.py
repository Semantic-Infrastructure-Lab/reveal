"""BACK-1578: project-wide evidence comes from the shared walker's evidence walk.

M102 (who imports this module?), T006 (which TypedDicts exist?), I007 (what does the project
import?) and hotspots' test index (which names do tests cover?) judge the files a command
reports on. Narrowing the report with --exclude must not shrink that evidence (BACK-1259), and
noise such as a .venv is not the project's evidence.
"""
import pytest

from conftest import _run_reveal_direct
from reveal.adapters.hotspots import _build_test_name_index
from reveal.rules.maintainability import M102 as m102_module
from reveal.utils.exclusions import exclusion_scope


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "p"\n', encoding='utf-8')
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (tmp_path / 'pkg' / 'util.py').write_text('def helper():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'pkg' / 'orphan.py').write_text('def lonely():\n    return 2\n', encoding='utf-8')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_util.py').write_text(
        'from pkg.util import helper\n\n\ndef test_helper():\n    assert helper()\n',
        encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.setattr(m102_module, '_import_cache', {})
    return tmp_path


def _m102(*args):
    result = _run_reveal_direct('check', '.', '--select', 'M102', *args)
    return result.stdout.replace('\\', '/')  # native separators on Windows (BACK-1366)


def test_m102_exclude_narrows_the_report_not_the_importers(pkg):
    out = _m102('--exclude', 'tests')
    assert 'pkg/orphan.py' in out  # positive control: M102 is running
    assert 'pkg/util.py' not in out  # imported by tests/, which --exclude only hid


def test_m102_an_import_inside_a_venv_is_not_the_projects(pkg):
    venv = pkg / '.venv' / 'lib' / 'site-packages' / 'other'
    venv.mkdir(parents=True)
    (venv / 'm.py').write_text('from pkg import orphan\n', encoding='utf-8')
    assert 'pkg/orphan.py' in _m102()


def test_hotspots_test_index_ignores_exclude_and_vendored_tests(tmp_path):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_core.py').write_text(
        'def test_compute():\n    pass\n', encoding='utf-8')
    vendored = tmp_path / 'vendor' / 'lib' / 'tests'
    vendored.mkdir(parents=True)
    (vendored / 'test_theirs.py').write_text('def test_parse():\n    pass\n', encoding='utf-8')
    with exclusion_scope(tmp_path, ['tests']):
        names = _build_test_name_index(tmp_path)
    assert 'compute' in names
    assert 'parse' not in names
