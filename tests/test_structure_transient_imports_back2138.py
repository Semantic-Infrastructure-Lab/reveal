"""BACK-2138: a transient imports-extraction failure is never stored in the structure disk cache.

JS, PHP, Ruby, Go, Lua, Zig and GDScript take their outline imports from the imports://
extractor (``IMPORTS_VIA_EXTRACTOR``). BACK-2136 made the extractor mark a failure that did not
come from the file's content (``ImportExtraction.transient_error``: the analyzer lookup raised,
or the grammar could not be loaded) and kept it out of the imports caches. The extractor does
not raise for it, so the structure built around it carried an empty import list with no
``_imports_failed`` mark and was stored under the file's stat key: every later outline of the
unchanged file lost its imports.
"""

from pathlib import Path

import pytest

from reveal import treesitter as ts_mod
from reveal.analyzers.imports import base as imports_base
from reveal.registry import get_analyzer

pytestmark = [pytest.mark.component, pytest.mark.disk_cache]

SAMPLES = {
    'a.js': "import fs from 'fs';\nimport path from 'path';\nfunction f() { return fs; }\n",
    'a.rb': "require 'json'\nrequire_relative 'b'\nclass A; end\n",
    'a.lua': 'local json = require("cjson")\nlocal M = {}\nreturn M\n',
    'a.go': 'package p\n\nimport (\n\t"fmt"\n\t"os"\n)\n\nfunc f() {}\n',
}


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    ts_mod._get_parse_cache().clear()
    yield
    ts_mod._get_parse_cache().clear()


@pytest.fixture
def lookup_fails_once(monkeypatch):
    """The imports extractor's analyzer lookup raises for the armed path once, then works."""
    armed, fired = set(), []
    real = imports_base.get_analyzer

    def get_analyzer_once(path, *args, **kwargs):
        resolved = Path(str(path)).resolve()
        if resolved in armed:
            armed.discard(resolved)
            fired.append(resolved.name)
            raise RuntimeError('analyzer registry unavailable')
        return real(path, *args, **kwargs)

    monkeypatch.setattr(imports_base, 'get_analyzer', get_analyzer_once)
    return armed, fired


def _structure(path):
    return get_analyzer(str(path))(str(path)).get_structure()


def _write(tmp_path, name):
    path = tmp_path / name
    path.write_text(SAMPLES[name], encoding='utf-8')
    return path


def _cold_copy(tmp_path, name):
    """The sample under a second path: a cold cache entry of its own."""
    path = tmp_path / f'other_{name}'
    path.write_text(SAMPLES[name], encoding='utf-8')
    return path


@pytest.mark.parametrize('name', sorted(SAMPLES))
def test_the_outline_that_hit_a_transient_failure_says_its_imports_are_missing(tmp_path, lookup_fails_once, name):
    armed, fired = lookup_fails_once
    other = _cold_copy(tmp_path, name)
    armed.add(other.resolve())
    first = _structure(other)
    assert fired == [other.name], 'fixture: the failure should hit the extractor once'
    assert first.get('imports', []) == [] and first.get('_imports_failed'), (
        'an empty import list with no mark reads as a file that has no imports')


@pytest.mark.parametrize('name', sorted(SAMPLES))
def test_a_transient_extractor_failure_is_not_served_to_the_next_outline(tmp_path, lookup_fails_once, name):
    armed, fired = lookup_fails_once
    healthy = len(_structure(_write(tmp_path, name)).get('imports', []))
    assert healthy >= 1, 'fixture: the sample should have imports'
    other = _cold_copy(tmp_path, name)
    armed.add(other.resolve())
    _structure(other)
    assert fired == [other.name], 'fixture: the failure should hit the extractor once'
    second = _structure(other)
    assert len(second.get('imports', [])) == healthy and not second.get('_imports_failed'), (
        f'{name}: the structure built while the lookup failed was stored and served again')


def test_a_clean_outline_is_still_served_from_the_cache(tmp_path, monkeypatch):
    """Negative control: a healthy structure is stored and the second outline builds nothing."""
    path = _write(tmp_path, 'a.js')
    first = _structure(path)
    builds = []
    real = ts_mod.TreeSitterAnalyzer._extract_functions
    monkeypatch.setattr(ts_mod.TreeSitterAnalyzer, '_extract_functions',
                        lambda self: builds.append(1) or real(self))
    second = _structure(path)
    assert second['imports'] == first['imports'] and len(first['imports']) == 2
    assert not builds, 'a healthy structure should come from the cache'


def test_an_unreadable_file_at_extraction_is_not_stored_either(tmp_path, monkeypatch):
    """BACK-2083's failure through the same door: the extractor's own read raises an OSError."""
    from reveal import base as reveal_base
    path = _write(tmp_path, 'a.js')
    healthy = len(_structure(path).get('imports', []))
    other = _cold_copy(tmp_path, 'a.js')
    analyzer = get_analyzer(str(other))(str(other))   # reads the content now; armed below
    fired = []
    real = reveal_base.FileAnalyzer._read_file

    def read(self):
        if Path(str(self.path)).resolve() == other.resolve() and not fired:
            fired.append(1)
            raise PermissionError(13, 'Permission denied', str(self.path))
        return real(self)

    monkeypatch.setattr(reveal_base.FileAnalyzer, '_read_file', read)  # noqa: V036 reviewed: serial
    first = analyzer.get_structure()
    assert fired and first.get('imports', []) == [] and first.get('_imports_failed')
    second = _structure(other)
    assert len(second.get('imports', [])) == healthy and not second.get('_imports_failed'), (
        'the structure built while the file was unreadable was stored and served again')
