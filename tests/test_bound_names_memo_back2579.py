"""ProjectBindings' pre-check reads a file's bound names once while its project tree is unchanged,
not once per request (BACK-2579).

``?callers=`` applies the import bindings per query (BACK-2567), and ``ProjectBindings.get`` first
asks the file's own import extraction which names it binds (3af89992), so a query whose calls go
through no import never builds the project's analysis. The extraction's in-process layer is emptied
at every host request (BACK-2083) and the disk layer may be off, so every query re-parsed every file
holding a call to the name: go/callers through reveal.api.query took 1.4-2.3 s per query against
0.03 s on 8d0d7b93, nearly all of it tree-sitter. The names are now a validated cache per target
directory (register_validated_cache, as the callers index is kept): kept while that
tree's stamp is unchanged, so a changed file is read again.
"""

import os
import time
from pathlib import Path

import pytest

from reveal.analyzers.imports import bindings
from reveal.analyzers.imports.bindings import ProjectBindings
from reveal.analyzers.imports.go import GoExtractor
from reveal.utils.request_cache import host_request


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    bindings.clear_bound_names()
    (tmp_path / 'go.mod').write_text('module example.com/p\n\ngo 1.22\n', encoding='utf-8')
    app = tmp_path / 'app.go'
    app.write_text('package main\n\nimport "fmt"\n\nfunc run() { fmt.Println(1) }\n', encoding='utf-8')
    # A file written at or after a request's start is never trusted for it (request_cache._tree_stamp).
    # On Windows with Python 3.11 time.time_ns() has the coarse system-clock tick, so a file written
    # just before the first request can carry a later mtime than that request's start and the memo is
    # dropped (the test failed on every windows-3.11 run at 50b22a15, BACK-2582). Age the fixture the
    # way the validated-cache tests do.
    aged = time.time_ns() - 10 * 1_000_000_000
    for path in (tmp_path / 'go.mod', app):
        os.utime(path, ns=(aged, aged))
    calls = []
    original = GoExtractor._extract_imports_uncached

    def counting(self, file_path):
        calls.append(Path(file_path).name)
        return original(self, file_path)

    monkeypatch.setattr(GoExtractor, '_extract_imports_uncached', counting)
    yield tmp_path, app, calls
    bindings.clear_bound_names()


def _names(root: Path, app: Path, name: str):
    with host_request():
        return ProjectBindings(root).get(str(app), name)


def test_an_unchanged_file_is_not_parsed_again_by_the_next_request(tree):
    root, app, calls = tree
    _names(root, app, 'nothing_bound')
    _names(root, app, 'nothing_bound')
    assert calls == ['app.go']


def test_a_changed_file_is_read_again(tree):
    # Freshness control: the second version binds `strings`, which the first did not.
    root, app, calls = tree
    assert _names(root, app, 'strings') is None
    stat = os.stat(app)
    app.write_text('package main\n\nimport "strings"\n\nfunc run() { strings.ToUpper("a") }\n', encoding='utf-8')
    os.utime(app, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert _names(root, app, 'strings') is not None
    assert calls.count('app.go') >= 2


def test_an_extraction_its_content_did_not_decide_is_read_again(tree, monkeypatch):
    # A transient failure (the grammar could not load, BACK-2136) is not the file's answer for its
    # stamp, so it is never remembered (ImportExtraction.cacheable).
    root, app, calls = tree
    counting = GoExtractor._extract_imports_uncached

    def transient(self, file_path):
        result = counting(self, file_path)
        self.analysis.transient_error = 'grammar unavailable'
        return result

    monkeypatch.setattr(GoExtractor, '_extract_imports_uncached', transient)
    _names(root, app, 'nothing_bound')
    _names(root, app, 'nothing_bound')
    assert calls == ['app.go', 'app.go']
