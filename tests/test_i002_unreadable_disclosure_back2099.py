"""BACK-2099: I002 says a file it could not read was not read, not that it "parsed with errors".

BACK-2084 added ``ImportGraph.unreadable_files``, the files that failed for an environmental
reason. ``get_scan_disclosures`` still put them in the parse-error line, so a permission problem
read as a syntax problem. A file lost to a dead worker already has its own line (BACK-1753);
an unreadable one now has one that names the error type. A real syntax error keeps its wording.
"""

import json
import os
from pathlib import Path

import pytest

from conftest import _clear_module_caches, _run_reveal_direct
from reveal import base as reveal_base

pytestmark = pytest.mark.integration

POSIX_CHMOD = pytest.mark.skipif(os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                                 reason='chmod 000 does not deny a read on Windows or to root')


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """proj/{a.py: import b, b.py: import a}, so a hidden b.py hides the cycle."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="p"\n', encoding='utf-8')
    (root / 'a.py').write_text('import b\n', encoding='utf-8')
    (root / 'b.py').write_text('import a\n', encoding='utf-8')
    _clear_module_caches()
    yield root.resolve()
    _clear_module_caches()


@pytest.fixture
def deny(monkeypatch):
    """Paths whose read raises PermissionError, the way an unreadable file does."""
    denied = set()
    real = reveal_base.FileAnalyzer._read_file

    def read(self):
        if Path(self.path).resolve() in denied:
            raise PermissionError(13, 'Permission denied', str(self.path))
        return real(self)

    # Reaches extraction under every start method: I002 extracts serially below
    # _GRAPH_PARALLEL_MIN_FILES and the suite sets REVEAL_MAX_WORKERS=1.
    monkeypatch.setattr(reveal_base.FileAnalyzer, '_read_file', read)  # noqa: V036 reviewed: serial
    return denied


def _i002_disclosures(root):
    """The scan disclosures of one CLI `check --select I002` run."""
    result = _run_reveal_direct('check', root, '--select', 'I002', '--format', 'json')
    _clear_module_caches()
    return json.loads(result.stdout)['summary']['scan_disclosures']


def _i002_lines(disclosures):
    return [line for line in disclosures if line.startswith('I002:')]


@POSIX_CHMOD
def test_chmod_000_file_is_disclosed_as_unreadable(proj):
    """The reported reproduction as written: chmod 000 b.py, check --select I002."""
    target = proj / 'b.py'
    os.chmod(target, 0)
    try:
        lines = _i002_lines(_i002_disclosures(proj))
    finally:
        os.chmod(target, 0o644)
    assert len(lines) == 1, lines
    assert 'could not be read' in lines[0] and 'PermissionError' in lines[0], lines[0]
    assert 'parsed with errors' not in lines[0], 'a permission failure was reported as a syntax problem'


def test_denied_read_is_disclosed_as_unreadable(proj, deny):
    deny.add(proj / 'b.py')
    lines = _i002_lines(_i002_disclosures(proj))
    assert len(lines) == 1, lines
    assert 'could not be read' in lines[0] and 'PermissionError' in lines[0], lines[0]
    assert 'parsed with errors' not in lines[0], 'a permission failure was reported as a syntax problem'
    assert '1 file(s)' in lines[0] and str(proj) in lines[0]


def test_syntax_error_keeps_the_parsed_with_errors_wording(proj):
    """Negative control: a file whose content fails to parse is still a parse error."""
    (proj / 'c.py').write_text('def (:\n', encoding='utf-8')
    lines = _i002_lines(_i002_disclosures(proj))
    assert lines == [f'I002: 1 file(s) under {proj} parsed with errors; '
                     'circular-dependency results may be incomplete'], lines


def test_unreadable_and_syntax_error_files_get_one_line_each(proj, deny):
    (proj / 'c.py').write_text('def (:\n', encoding='utf-8')
    deny.add(proj / 'b.py')
    lines = _i002_lines(_i002_disclosures(proj))
    assert len(lines) == 2, lines
    assert sum('parsed with errors' in line and '1 file(s)' in line for line in lines) == 1, lines
    assert sum('could not be read' in line and 'PermissionError' in line and '1 file(s)' in line
               for line in lines) == 1, lines
