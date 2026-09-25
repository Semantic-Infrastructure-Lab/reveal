"""The disk cache is keyed on the code that built each value (BACK-1294, BACK-1328).

An edit to reveal's own source in a dev checkout, or a tree-sitter /
language-pack swap, must make every earlier entry unreachable -- the version
string alone stays the same across both.
"""

import os
import sys

import pytest

from reveal.core import disk_cache

pytestmark = pytest.mark.component


@pytest.fixture
def fake_build(tmp_path, monkeypatch):
    """A fingerprint over throwaway packages: `fakereveal` (walked recursively,
    like reveal) and `fakepack` (top level only, like the parser stack)."""
    site = tmp_path / 'site'
    for pkg in ('fakereveal', 'fakepack'):
        (site / pkg / 'sub').mkdir(parents=True)
        (site / pkg / '__init__.py').write_text('', encoding='utf-8')
        (site / pkg / 'sub' / 'mod.py').write_text('x = 1\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(site))
    monkeypatch.setattr(disk_cache, '_BUILD_PACKAGES', (('fakereveal', True), ('fakepack', False)))
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.delenv('REVEAL_DISK_CACHE', raising=False)
    monkeypatch.setattr(disk_cache, '_used_build_dirs', set())
    disk_cache.build_fingerprint.cache_clear()
    yield site
    disk_cache.build_fingerprint.cache_clear()
    for pkg in ('fakereveal', 'fakepack'):
        sys.modules.pop(pkg, None)


def _new_process():
    """The fingerprint is computed once per process; forget it."""
    disk_cache.build_fingerprint.cache_clear()


def _bump_mtime(path):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


def test_unchanged_build_hits(fake_build):
    disk_cache.put('ns', 'k', 'v')
    _new_process()
    assert disk_cache.get('ns', 'k') == 'v'


def test_editing_a_source_file_invalidates(fake_build):
    """BACK-1294: a dev-checkout edit, same __version__."""
    disk_cache.put('ns', 'k', 'built by old extractor')
    (fake_build / 'fakereveal' / 'sub' / 'mod.py').write_text('x = 2  # fixed\n', encoding='utf-8')
    _new_process()
    assert disk_cache.get('ns', 'k') is None


def test_same_size_edit_invalidates_via_mtime(fake_build):
    disk_cache.put('ns', 'k', 'v')
    _bump_mtime(fake_build / 'fakereveal' / 'sub' / 'mod.py')
    _new_process()
    assert disk_cache.get('ns', 'k') is None


def test_dependency_swap_invalidates(fake_build):
    """BACK-1328: a language-pack upgrade replaces its top-level files."""
    disk_cache.put('ns', 'k', 'parsed by old grammar')
    (fake_build / 'fakepack' / '__init__.py').write_text('__version__ = "2"\n', encoding='utf-8')
    _new_process()
    assert disk_cache.get('ns', 'k') is None


def test_dependency_is_fingerprinted_top_level_only(fake_build):
    before = disk_cache.build_fingerprint()
    _bump_mtime(fake_build / 'fakepack' / 'sub' / 'mod.py')
    _new_process()
    assert disk_cache.build_fingerprint() == before


def test_bytecode_does_not_change_the_fingerprint(fake_build):
    before = disk_cache.build_fingerprint()
    cache_dir = fake_build / 'fakereveal' / '__pycache__'
    cache_dir.mkdir()
    (cache_dir / 'mod.cpython-312.pyc').write_bytes(b'\0')
    (fake_build / 'fakereveal' / 'stray.pyc').write_bytes(b'\0')
    _new_process()
    assert disk_cache.build_fingerprint() == before


def test_unknowable_fingerprint_disables_the_cache(fake_build, monkeypatch):
    monkeypatch.setattr(disk_cache, '_package_files', lambda *a: (_ for _ in ()).throw(OSError('gone')))
    _new_process()
    assert disk_cache.build_fingerprint() is None
    disk_cache.put('ns', 'k', 'v')
    assert disk_cache.get('ns', 'k') is None
    assert not (fake_build.parent / 'cache').exists()


def _make_build_dir(schema_dir, name, age):
    path = schema_dir / name / 'ns'
    path.mkdir(parents=True)
    (path / 'k.pkl').write_bytes(b'')
    past = 1_000_000_000 - age
    os.utime(schema_dir / name, (past, past))
    return schema_dir / name


def test_new_build_prunes_to_the_most_recently_used(fake_build, tmp_path):
    schema_dir = tmp_path / 'cache' / f'v{disk_cache.CACHE_SCHEMA_VERSION}'
    legacy = _make_build_dir(schema_dir, '0.127.0', age=500)  # pre-fingerprint layout
    old = [_make_build_dir(schema_dir, f'0.128.0-old{i}', age=100 + i) for i in range(5)]

    disk_cache.put('ns', 'k', 'v')

    remaining = sorted(p.name for p in schema_dir.iterdir())
    assert len(remaining) == disk_cache._MAX_BUILDS
    assert disk_cache._build_dir().name in remaining
    # the newest of the old builds survive; the oldest and the legacy dir go
    assert {'0.128.0-old0', '0.128.0-old1', '0.128.0-old2'} <= set(remaining)
    assert not legacy.exists() and not old[4].exists()


def test_writing_to_an_existing_build_does_not_prune(fake_build, tmp_path):
    disk_cache.put('ns', 'k', 'v')
    schema_dir = tmp_path / 'cache' / f'v{disk_cache.CACHE_SCHEMA_VERSION}'
    others = [_make_build_dir(schema_dir, f'other{i}', age=i) for i in range(6)]
    disk_cache.put('ns', 'k2', 'v2')
    assert all(p.exists() for p in others)


def test_a_build_in_use_is_kept_over_newer_idle_ones(fake_build, tmp_path, monkeypatch):
    """Two installs alternating: using one refreshes it, so dev edits in the
    other (each a new build dir) do not evict it."""
    schema_dir = tmp_path / 'cache' / f'v{disk_cache.CACHE_SCHEMA_VERSION}'
    disk_cache.put('ns', 'k', 'v')
    in_use = disk_cache._build_dir()
    os.utime(in_use, (1, 1))
    for i in range(3):
        _make_build_dir(schema_dir, f'idle{i}', age=10 + i)

    monkeypatch.setattr(disk_cache, '_used_build_dirs', set())  # a later process
    disk_cache.put('ns', 'k', 'v')                             # uses it again
    (fake_build / 'fakereveal' / '__init__.py').write_text('# edit\n', encoding='utf-8')
    _new_process()
    disk_cache.put('ns', 'k', 'v')                             # new build -> prune

    assert in_use.exists()
