"""BACK-2085: the imports whole-graph cache key covers the directories an import can resolve to.

``import pkg`` resolves to a directory (a namespace package), and the key hashed files only:
an empty ``pkg/`` created after a cached run left the cached graph answering "unresolved"
while a cache-off run resolved it. Directories the resolution walk descends are part of the
key now, for imports:// and I002's tree key alike. An unchanged tree is still a hit.
"""

import json

import pytest

from conftest import _MODULE_CACHES, _run_reveal_direct
from reveal.adapters.imports import ImportsAdapter, _candidate_set_fingerprint
from reveal.analyzers.imports import generic, go, javascript, python as py_imports, rust, zig
from reveal.analyzers.imports.file_index import basename_index, resolution_fingerprint

pytestmark = [pytest.mark.integration, pytest.mark.disk_cache]

_SINGLETON_MODULES = (py_imports, javascript, go, rust, zig, generic)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """nd/{a.py: import pkg, b.py}; the cache dir lives beside it, outside the scanned tree."""
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    for module in _SINGLETON_MODULES:
        module._IMPORTS_CACHE.clear()
    root = tmp_path / 'nd'
    root.mkdir()
    (root / 'a.py').write_text('import pkg\n', encoding='utf-8')
    (root / 'b.py').write_text('X = 1\n', encoding='utf-8')
    yield root
    for module in _SINGLETON_MODULES:
        module._IMPORTS_CACHE.clear()


@pytest.fixture
def builds(monkeypatch):
    """How many times the graph was built from extraction, i.e. graph-cache misses."""
    calls = []
    original = ImportsAdapter._process_extracted_files

    def counting(self, *args, **kwargs):
        calls.append(self._target_path)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ImportsAdapter, '_process_extracted_files', counting)
    return calls


def _resolved(root):
    """What `import pkg` in a.py resolved to, through the CLI: None or a path."""
    result = _run_reveal_direct(f'imports://{root}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    (statement,) = json.loads(result.stdout)['files']['a.py']
    return statement['resolved']


def _cache_off_answer(root, monkeypatch):
    """The positive control: the same tree with the disk cache off."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    try:
        return _resolved(root)
    finally:
        monkeypatch.setenv('REVEAL_DISK_CACHE', '1')


def test_fixture_resolves_to_the_directory_without_a_cache(tree, monkeypatch):
    """Positive control: the cache-off answer changes when the directory appears."""
    assert _cache_off_answer(tree, monkeypatch) is None
    (tree / 'pkg').mkdir()
    assert _cache_off_answer(tree, monkeypatch) == 'pkg'


def test_empty_directory_created_after_a_cached_run_is_seen(tree, monkeypatch, builds):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    assert _resolved(tree) is None
    (tree / 'pkg').mkdir()
    expected = _cache_off_answer(tree, monkeypatch)
    assert expected == 'pkg'
    assert _resolved(tree) == expected, 'the graph cached before pkg/ existed was served'


def test_empty_directory_removed_after_a_cached_run_is_seen(tree, monkeypatch, builds):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    (tree / 'pkg').mkdir()
    assert _resolved(tree) == 'pkg'
    (tree / 'pkg').rmdir()
    assert _resolved(tree) is None, 'the graph cached while pkg/ existed was served'


def test_unchanged_tree_is_still_a_hit(tree, monkeypatch, builds):
    """Negative control: with an empty directory present and unchanged, the second run is a hit."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    (tree / 'pkg').mkdir()
    assert _resolved(tree) == 'pkg'
    assert _resolved(tree) == 'pkg'
    assert len(builds) == 1, 'an unchanged tree rebuilt its graph'


def test_i002_tree_key_covers_directories_too(tree):
    """I002's key goes through the same fingerprint: an empty directory changes it."""
    sources = [tree / 'a.py', tree / 'b.py']
    before = resolution_fingerprint(sources, basename_index([tree]), root=tree)
    assert before == resolution_fingerprint(sources, basename_index([tree]), root=tree)
    (tree / 'pkg').mkdir()
    assert resolution_fingerprint(sources, basename_index([tree]), root=tree) != before


def test_adapter_key_covers_directories(tree):
    adapter = ImportsAdapter(resource=str(tree))
    candidates, index = adapter._discover_candidate_files(tree, frozenset({'.py'}), frozenset({'.py'}))
    before = _candidate_set_fingerprint(candidates, index, root=tree)
    (tree / 'pkg').mkdir()
    candidates, index = adapter._discover_candidate_files(tree, frozenset({'.py'}), frozenset({'.py'}))
    assert _candidate_set_fingerprint(candidates, index, root=tree) != before
