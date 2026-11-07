"""BACK-2549 / BACK-2559 slice 1: Rust imports resolve through the scan's package model.

Before, ``RustExtractor.resolve_import`` gave up on every use path that did not start with
``crate::``/``super::``/``self::`` and required ``<nearest Cargo.toml>/src``. A workspace crate named
bare (a path dependency, written in place or inherited with ``workspace = true``, renamed or not, or
the package's own library from an integration test) never got an edge, and neither did ``crate::``
inside a ``[[bin]]``/``[[test]]`` target outside ``src/``: every such crate's ``lib.rs`` read zero
importers. The package model (``reveal/analyzers/imports/packages.py``) reads each Cargo.toml once per
scan; resolution asks it which crate a name spells and where the importing target's root is.
"""
import json
import textwrap
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal.analyzers.imports import build_cache, rust
from reveal.analyzers.imports.resolution import ProjectResolver
from reveal.analyzers.imports.rust import RustExtractor
from reveal.analyzers.imports.types import ImportStatement

WORKSPACE = {
    'Cargo.toml': '''
        [package]
        name = "app"
        version = "0.1.0"
        edition = "2021"

        [[bin]]
        name = "app"
        path = "crates/core/main.rs"

        [[test]]
        name = "integration"
        path = "tests/tests.rs"

        [workspace]
        members = ["crates/matcher", "crates/search", "crates/search/inner"]

        [workspace.dependencies]
        matcher = { path = "crates/matcher" }
        inner = { path = "crates/search/inner" }

        [dependencies]
        matcher = { workspace = true }
        search = { path = "crates/search", package = "grep-search" }
        serde = "1"
    ''',
    'crates/core/main.rs': 'mod flags;\nuse matcher::Matcher;\nuse search::sink::Sink;\nuse serde::Serialize;\nfn main() {}\n',
    'crates/core/flags/mod.rs': 'pub mod hi;\npub mod lo;\n',
    'crates/core/flags/hi.rs': 'use crate::flags::lo::Low;\n',
    'crates/core/flags/lo.rs': 'pub struct Low;\n',
    'tests/tests.rs': 'mod util;\nmod feature;\n',
    'tests/util.rs': 'pub struct TestCommand;\n',
    'tests/feature.rs': 'use crate::util::TestCommand;\n',
    'crates/matcher/Cargo.toml': '[package]\nname = "matcher"\nversion = "0.1.0"\nedition = "2021"\n',
    'crates/matcher/src/lib.rs': 'pub struct Matcher;\n',
    'crates/matcher/tests/it.rs': 'use matcher::Matcher;\n',
    'crates/search/Cargo.toml': ('[package]\nname = "grep-search"\nversion = "0.1.0"\nedition = "2021"\n\n'
                                 '[dependencies]\nmatcher = { workspace = true }\ninner = { workspace = true }\n'),
    'crates/search/src/lib.rs': 'pub mod sink;\nuse matcher::Matcher;\nuse inner::Deep;\n',
    'crates/search/inner/Cargo.toml': '[package]\nname = "inner"\nversion = "0.1.0"\nedition = "2021"\n',
    'crates/search/inner/src/lib.rs': 'pub struct Deep;\n',
    'crates/search/src/sink.rs': 'pub struct Sink;\n',
}

# importer -> the files its use paths name in the workspace above
EXPECTED = {
    'crates/core/main.rs': {'crates/matcher/src/lib.rs', 'crates/search/src/sink.rs'},
    'crates/core/flags/hi.rs': {'crates/core/flags/lo.rs'},
    'tests/feature.rs': {'tests/util.rs'},
    'crates/matcher/tests/it.rs': {'crates/matcher/src/lib.rs'},
    'crates/search/src/lib.rs': {'crates/matcher/src/lib.rs', 'crates/search/inner/src/lib.rs'},
}


def write_workspace(root: Path, files=None) -> Path:
    for rel, text in (files or WORKSPACE).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(textwrap.dedent(text).lstrip(), encoding='utf-8')
    return root


@pytest.fixture
def ws(tmp_path):
    return write_workspace(tmp_path / 'ws')


def _default_view(cwd: Path, target: str = '.'):
    result = _run_reveal_in(cwd, f'imports://{target}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)['files']


def _resolved_by_importer(view):
    return {file: {s['resolved'] for s in stmts if s['resolved']} for file, stmts in view.items()}


def test_every_cargo_shape_resolves_through_the_public_view(ws):
    """Workspace-inherited, renamed and own-library crate names, and crate:: in [[bin]]/[[test]] targets."""
    resolved = _resolved_by_importer(_default_view(ws))
    for importer, targets in EXPECTED.items():
        assert resolved.get(importer, set()) == targets, importer


def test_a_registry_dependency_and_std_stay_unresolved(ws):
    view = _default_view(ws)
    unresolved = {s['module'] for s in view['crates/core/main.rs'] if not s['resolved']}
    assert unresolved == {'serde::Serialize'}


def test_importers_of_a_library_name_every_crate_that_uses_it(ws):
    result = _run_reveal_in(ws, 'imports://.?importers=crates/matcher/src/lib.rs', '--format', 'json')
    assert result.returncode == 0, result.stderr
    importers = {row['file'] for row in json.loads(result.stdout)['importers']}
    assert importers == {'crates/core/main.rs', 'crates/matcher/tests/it.rs', 'crates/search/src/lib.rs'}


def test_the_model_reads_each_manifest_once_into_units(ws):
    files = sorted(ws.rglob('*.rs'))
    failures = []
    model = ProjectResolver._build_package_model(files, on_error=failures.append)
    assert failures == []
    assert {u.name: u.manifest.relative_to(ws.resolve()).as_posix() for u in model.units} == {
        'app': 'Cargo.toml', 'matcher': 'crates/matcher/Cargo.toml', 'grep_search': 'crates/search/Cargo.toml',
        'inner': 'crates/search/inner/Cargo.toml'}
    core = (ws / 'crates/core/flags/hi.rs').resolve()
    assert model.target_root_for(core) == (ws / 'crates/core').resolve()
    assert model.target_root_for((ws / 'tests/feature.rs').resolve()) == (ws / 'tests').resolve()
    assert model.named_unit(core.parent, 'search').name == 'grep_search'   # renamed: code spells the key
    assert model.named_unit(core.parent, 'grep_search') is None              # ... not the package name
    assert model.named_unit(core.parent, 'serde') is None                    # not in-tree


def test_without_a_model_the_src_convention_is_unchanged(ws):
    """calls:// and other callers that pass no model keep today's answers (BACK-2553 moves them)."""
    hi = ws / 'crates/core/flags/hi.rs'
    stmt = ImportStatement(hi, 1, 'crate::flags::lo::Low', ['Low'], True, 'import')
    assert RustExtractor().resolve_import(stmt, hi.parent) is None
    bare = ImportStatement(ws / 'crates/search/src/lib.rs', 2, 'matcher::Matcher', ['Matcher'], False, 'import')
    assert RustExtractor().resolve_import(bare, bare.file_path.parent) is None


def test_a_manifest_that_is_not_toml_declares_nothing(ws):
    (ws / 'crates/matcher/Cargo.toml').write_text('[package\nname = ', encoding='utf-8')
    resolved = _resolved_by_importer(_default_view(ws))
    assert 'crates/matcher/src/lib.rs' not in resolved.get('crates/core/main.rs', set())
    assert resolved['crates/core/flags/hi.rs'] == {'crates/core/flags/lo.rs'}   # the rest still resolves


@pytest.mark.skipif(not hasattr(__import__('os'), 'geteuid') or __import__('os').geteuid() == 0,
                    reason='needs a non-root POSIX user for an unreadable file')
def test_an_unreadable_manifest_is_a_recorded_failure(ws):
    manifest = ws / 'crates/matcher/Cargo.toml'
    manifest.chmod(0)
    try:
        failures = []
        ProjectResolver._build_package_model(sorted(ws.rglob('*.rs')), on_error=failures.append)
        assert [Path(f.filename).name for f in failures] == ['Cargo.toml']
    finally:
        manifest.chmod(0o644)


# --- cache lifetime: a manifest above the scan root is in the graph key (cause 6) -------------------------

def _search_targets(ws: Path):
    """What crates/search/src/lib.rs resolves to when crates/search is the scan root (its own Cargo.toml is
    the package marker): `inner` is a path dependency only through the workspace manifest above it."""
    view = _default_view(ws / 'crates/search')
    return {s['resolved'] for s in view['src/lib.rs'] if s['resolved']}


@pytest.fixture
def cached(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    rust._IMPORTS_CACHE.clear()
    yield
    rust._IMPORTS_CACHE.clear()


def _unpath_inner(ws: Path):
    """The workspace manifest (above the scan root) makes `inner` a registry dependency instead."""
    root = ws / 'Cargo.toml'
    root.write_text(root.read_text(encoding='utf-8').replace('inner = { path = "crates/search/inner" }',
                                                             'inner = "1.0.0"'), encoding='utf-8')


@pytest.mark.disk_cache
def test_cache_off_answer_moves_with_the_workspace_manifest(ws, monkeypatch):
    """Positive control for the cached tests below."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    assert _search_targets(ws) == {'inner/src/lib.rs'}
    _unpath_inner(ws)
    assert _search_targets(ws) == set()


@pytest.mark.disk_cache
def test_an_edit_to_a_manifest_above_the_scan_root_misses_the_graph_cache(ws, cached):
    assert _search_targets(ws) == {'inner/src/lib.rs'}
    assert _search_targets(ws) == {'inner/src/lib.rs'}   # warm
    _unpath_inner(ws)
    assert _search_targets(ws) == set()


@pytest.mark.disk_cache
def test_without_the_context_manifests_the_cached_graph_goes_stale(ws, cached, monkeypatch):
    """Red control: a key without the manifests above the root serves the old graph after the edit."""
    monkeypatch.setattr(build_cache, '_context_manifests', lambda root: [])
    assert _search_targets(ws) == {'inner/src/lib.rs'}
    _unpath_inner(ws)
    assert _search_targets(ws) == {'inner/src/lib.rs'}


def test_a_path_dependency_outside_the_scan_is_not_read(ws):
    """Scanning one crate reads its own manifest and those above it, never a sibling's: no edge leaves for
    ../matcher, and the cache key needs only the manifests at and above the root."""
    view = _default_view(ws / 'crates/search')
    assert [s['resolved'] for s in view['src/lib.rs'] if s['module'] == 'matcher::Matcher'] == [None]
    assert {s['module'] for s in view['src/lib.rs'] if s['resolved']} == {'inner::Deep'}


def test_context_manifests_are_the_cargo_tomls_at_and_above_the_root(ws):
    found = build_cache._context_manifests((ws / 'crates/search').resolve())
    assert found == [(ws / 'crates/search/Cargo.toml').resolve(), (ws / 'Cargo.toml').resolve()]
