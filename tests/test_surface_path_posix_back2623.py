"""surface's answer names its target with '/' on every OS (BACK-2623 B7, the BACK-2188 class).

``str(Path)`` is backslashed on Windows, and surface wrote both ``path`` (``str(display_path)``)
and the envelope ``source`` (the ``str`` of the target) that way. Linux cannot produce a
backslashed relative spelling from a real tree, so the target's spelling is a Windows-flavoured
path object, as in ``tests/test_architecture_path_posix_back2302.py``; the directory it names
really exists (its name holds a backslash on POSIX, nested directories on Windows), so the scan
itself runs unchanged.
"""
from pathlib import Path, PureWindowsPath

import pytest

from reveal.adapters import surface
from reveal.adapters.surface import SurfaceAdapter

NATIVE = 'pkg\\sub'


@pytest.fixture
def native_target(tmp_path, monkeypatch):
    real = tmp_path / NATIVE
    real.mkdir(parents=True)
    (real / 'app.py').write_text("import os\nTOKEN = os.environ['API_TOKEN']\n", encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    class NativePath(PureWindowsPath):
        """The target as Windows spells it: backslashed text, a real directory behind it."""

        def expanduser(self):
            return self

        def is_dir(self):
            return real.is_dir()

    native = Path
    monkeypatch.setattr(surface, 'Path', lambda *parts: (
        NativePath(*parts) if len(parts) == 1 and str(parts[0]) == NATIVE else native(*parts)))
    assert str(NativePath(NATIVE)) == NATIVE  # positive control: the spelling really is backslashed
    return real


def test_path_and_source_use_forward_slashes(native_target):
    result = SurfaceAdapter(NATIVE).get_structure()
    assert (result['path'], result['source']) == ('pkg/sub', 'pkg/sub')
    assert result['source_type'] == 'directory'
    assert [e['file'] for e in result['surfaces']['env']] == ['app.py']  # the scan ran on the real tree


def test_path_and_source_use_forward_slashes_in_the_dir_view(native_target):
    result = SurfaceAdapter(NATIVE, params={'view': 'dir'}).get_structure()
    assert (result['path'], result['source']) == ('pkg/sub', 'pkg/sub')
    assert result['by_dir'] == [{'dir': '.', 'total': 1, 'counts': {'env': 1}}]


def test_a_forward_slash_target_is_unchanged(tmp_path, monkeypatch):
    """Negative control: a POSIX spelling answers exactly as before."""
    (tmp_path / 'pkg' / 'sub').mkdir(parents=True)
    (tmp_path / 'pkg' / 'sub' / 'app.py').write_text("import os\nTOKEN = os.environ['API_TOKEN']\n",
                                                    encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    result = SurfaceAdapter('pkg/sub').get_structure()
    assert (result['path'], result['source']) == ('pkg/sub', 'pkg/sub')
    assert [e['file'] for e in result['surfaces']['env']] == ['app.py']
