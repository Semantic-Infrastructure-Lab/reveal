"""BACK-1706: Windows path logic, driven on every OS with PureWindowsPath / ntpath inputs.

These test the string/segment LOGIC of ``reveal.utils.path_utils`` (drive letters,
backslashes, UNC, mixed separators), not the filesystem.  Functions that call
``Path.resolve()`` on a real ``Path`` (``to_relative_display`` with a base,
``provenance_for_display_path``) cannot take a ``PureWindowsPath`` on POSIX, so only
their pure halves are covered here: ``to_relative_display`` with no base, and
``classify_path_provenance`` on ``PureWindowsPath.parts``.
``is_unsafe_scan_root`` is driven under a Windows flavour by swapping the module's
``Path`` and ``os.path.realpath`` for ntpath-based stand-ins.
"""
import ntpath
import os
import tempfile
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from reveal.utils import path_utils
from reveal.utils.path_utils import (
    as_spelled,
    classify_path_provenance,
    is_test_path,
    is_unsafe_scan_root,
    to_posix,
    to_relative_display,
)

# BACK-1149: exercises internal functions directly, not CLI/MCP/network surface
pytestmark = pytest.mark.component

W = PureWindowsPath


class TestToPosixWindowsShapes:
    @pytest.mark.parametrize('raw, expected', [
        (r'C:\a\b', 'C:/a/b'),
        (r'c:\Users\Me\proj\x.py', 'c:/Users/Me/proj/x.py'),
        ('C:/a\\b', 'C:/a/b'),                     # mixed separators
        (r'\\srv\share\x\y.py', '//srv/share/x/y.py'),   # UNC
        (r'..\lib\a.py', '../lib/a.py'),
        (r'C:rel\x', 'C:rel/x'),                    # drive-relative
        ('a\\b\\', 'a/b/'),                         # string input keeps a trailing slash
    ])
    def test_string_inputs(self, raw, expected):
        assert to_posix(raw) == expected

    @pytest.mark.parametrize('raw, expected', [
        (r'C:\a\b', 'C:/a/b'),
        (r'\\srv\share\x\y.py', '//srv/share/x/y.py'),
        ('C:/a\\b', 'C:/a/b'),
        (r'.\src\a.py', 'src/a.py'),                # PurePath drops the leading ./
        (r'tests\sub\test_x.py', 'tests/sub/test_x.py'),
    ])
    def test_pure_windows_path_inputs(self, raw, expected):
        assert to_posix(W(raw)) == expected

    def test_string_and_pure_path_agree_on_absolute_paths(self):
        for raw in (r'C:\a\b\c.py', r'D:\x', r'\\srv\share\f'):
            assert to_posix(raw) == to_posix(W(raw))

    def test_no_backslash_survives_any_shape(self):
        for raw in (r'C:\a\b', r'\\srv\share\x', 'C:/a\\b', r'.\a\..\b'):
            assert '\\' not in to_posix(raw)
            assert '\\' not in to_posix(W(raw))

    def test_posix_string_control_is_untouched(self):
        assert to_posix('/usr/lib/x.py') == '/usr/lib/x.py'
        assert to_posix('a/b') == 'a/b'


class TestToRelativeDisplayNoBase:
    @pytest.mark.parametrize('base', [None, ''])
    def test_windows_string_is_posix_without_a_base(self, base):
        assert to_relative_display(r'C:\x\a.py', base) == 'C:/x/a.py'

    def test_pure_windows_path_without_a_base(self):
        assert to_relative_display(W(r'C:\x\a.py'), None) == 'C:/x/a.py'

    def test_unc_without_a_base(self):
        assert to_relative_display(r'\\srv\share\a.py', None) == '//srv/share/a.py'


class TestAsSpelledWindows:
    def test_windows_spelling_and_path_come_back_posix(self):
        out = as_spelled(W(r'C:\x\a.py'), W(r'C:\x'))
        assert '\\' not in out
        assert out.startswith('C:') and out.endswith('x/a.py')

    def test_other_drive_with_absolute_spelling_is_returned_as_given_posix(self):
        out = as_spelled(W(r'D:\other\a.py'), W(r'C:\proj'))
        assert out == 'D:/other/a.py'

    def test_cross_drive_relpath_error_falls_back_to_posix(self, tmp_path, monkeypatch):
        # A relative spelling makes as_spelled call os.path.relpath, which raises
        # ValueError across Windows drives.  Simulate that raise on any OS.
        proj = tmp_path / 'proj'
        proj.mkdir()
        other = tmp_path / 'other' / 'a.py'
        monkeypatch.chdir(proj)
        # control: with a normal relpath the outside path is written relative to the cwd
        assert as_spelled(other, './') == '../other/a.py'

        def other_drive(*_a, **_k):
            raise ValueError('path is on mount "D:", start on mount "C:"')
        monkeypatch.setattr(os.path, 'relpath', other_drive)
        assert as_spelled(other, './') == to_posix(other)


class TestPathClassificationOnWindowsParts:
    def test_test_dir_with_backslash_separator(self):
        assert is_test_path(W(r'tests\sub\test_x.py')) is True
        assert is_test_path(W(r'C:\proj\tests\a.py')) is True

    def test_non_test_control(self):
        assert is_test_path(W(r'C:\proj\src\a.py')) is False

    def test_vendor_and_test_from_pure_windows_parts(self):
        w = W(r'app\vendor\lib\x.js')
        assert classify_path_provenance(w.parts[:-1], w.name) == 'vendor'
        t = W(r'src\tests\a.py')
        assert classify_path_provenance(t.parts[:-1], t.name) == 'test'

    def test_first_party_control(self):
        w = W(r'src\core\a.py')
        assert classify_path_provenance(w.parts[:-1], w.name) is None


class _WinPath(PureWindowsPath):
    """Stand-in for ``Path`` with Windows flavour: pure paths plus ``home()``."""

    @classmethod
    def home(cls):
        return cls(r'C:\Users\Dev')


def _win_realpath(p):
    # What the logic needs from realpath on Windows: normalised, case-folded, no filesystem
    return ntpath.normcase(ntpath.normpath(str(p)))


@pytest.fixture
def windows_flavour(monkeypatch):
    """Run ``is_unsafe_scan_root`` as if on Windows: ntpath realpath, Windows Path/anchor/home/temp."""
    fake_os = SimpleNamespace(path=SimpleNamespace(realpath=_win_realpath))
    monkeypatch.setattr(path_utils, 'os', fake_os)
    monkeypatch.setattr(path_utils, 'Path', _WinPath)
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: r'C:\Users\Dev\AppData\Local\Temp')


class TestIsUnsafeScanRootWindowsFlavour:
    @pytest.mark.parametrize('root', [
        'C:\\',
        'C:/',
        'c:\\',                                     # case-insensitive drive
        'D:\\',
        r'\\srv\share' + '\\',                      # UNC share root is the anchor
        r'C:\Users\Dev',                            # home
        r'c:\users\dev',                            # home, other case
        r'C:\Users\Dev\AppData\Local\Temp',         # temp
        r'C:\Users\Dev\AppData\Local\Temp' + '\\',  # trailing separator
    ])
    def test_roots_are_unsafe(self, windows_flavour, root):
        assert is_unsafe_scan_root(root) is True
        assert is_unsafe_scan_root(W(root)) is True

    @pytest.mark.parametrize('proj', [
        r'C:\Users\Dev\src\proj',
        r'C:\Users\Dev\AppData\Local\Temp\pytest-1\proj',   # a checkout under temp is not temp
        r'D:\work\proj',
        r'\\srv\share\team\proj',
    ])
    def test_project_dirs_are_safe(self, windows_flavour, proj):
        assert is_unsafe_scan_root(proj) is False
        assert is_unsafe_scan_root(W(proj)) is False

    def test_none_is_still_not_a_root(self, windows_flavour):
        assert is_unsafe_scan_root(None) is False
