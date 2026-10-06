"""BACK-1175: the disk cache is documented where users look for REVEAL_* variables.

Pins the claims that can drift from reveal/core/disk_cache.py: the two env vars and
the values that turn the cache off, the default location and layout, the caps, and
the list of cached artifact kinds (one documented name per cache namespace).
"""

import re
from pathlib import Path

import pytest

from reveal.core import disk_cache

pytestmark = pytest.mark.component

GUIDE = Path(__file__).resolve().parent.parent / 'reveal' / 'docs' / 'guides' / 'CONFIGURATION_GUIDE.md'


@pytest.fixture(scope='module')
def guide():
    return GUIDE.read_text(encoding='utf-8')


def _namespaces():
    """Every cache namespace the source declares: `_..._NAMESPACE = "x"` constants and
    `ImportsDiskCache("x")` instances, found by scanning reveal/ so a new one is caught."""
    names = set()
    for path in sorted((GUIDE.parents[2]).rglob('*.py')):
        text = path.read_text(encoding='utf-8')
        names.update(re.findall(r'^_[A-Z_]*NAMESPACE\s*=\s*["\']([\w-]+)["\']', text, flags=re.MULTILINE))
        names.update(re.findall(r'ImportsDiskCache\(\s*["\']([\w-]+)["\']', text))
    return names


def test_env_vars_are_documented(guide):
    for name in ('REVEAL_DISK_CACHE', 'REVEAL_CACHE_DIR', 'REVEAL_STRUCTURE_CACHE_MAX_FILES'):
        assert f'`{name}`' in guide, f'{name} is not documented in CONFIGURATION_GUIDE.md'


def test_every_disabling_value_is_documented(guide):
    for value in sorted(disk_cache._DISABLED_VALUES - {''}):
        assert f'`{value}`' in guide, f'REVEAL_DISK_CACHE={value} is not listed'


def test_default_location_and_layout_match_the_code(guide, monkeypatch, tmp_path):
    monkeypatch.delenv('REVEAL_CACHE_DIR', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    assert disk_cache.cache_root() == tmp_path / '.reveal' / 'cache'
    assert '~/.reveal/cache' in guide
    layout = f'v{disk_cache.CACHE_SCHEMA_VERSION}/<reveal version>-<build>/<namespace>/'
    assert layout in guide


def test_caps_match_the_code(guide):
    assert f'{disk_cache._MAX_BUILDS} most recently used' in guide
    assert f'{disk_cache._MAX_ENTRIES_PER_NAMESPACE} entries' in guide


def test_every_cached_artifact_kind_is_listed(guide):
    missing = sorted(name for name in _namespaces() if f'`{name}`' not in guide)
    assert not missing, f'cache namespaces undocumented: {missing}'


def test_negative_control_the_namespace_scan_sees_a_real_namespace_set():
    """If the scan silently yielded nothing the coverage test would pass vacuously."""
    names = _namespaces()
    assert {'structure', 'churn', 'python_imports', 'import_graph_v3'} <= names
    assert len(names) >= 12
