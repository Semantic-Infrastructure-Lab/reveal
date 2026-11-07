"""BACK-2557 / BACK-2558 / BACK-2559 slice 2: Go imports resolve through the scan's package model.

Before, ``GoExtractor.resolve_import`` mapped an import path only into the nearest go.mod's own module,
with a bare ``startswith`` test. A module reached through a go.work ``use`` or a go.mod ``replace => ./dir``
never got an edge (Kubernetes' staging modules: 997 ``pkg/`` importers of ``k8s.io/api/core/v1`` read as
0), and ``k8s.io/apimachinery/...`` counted as inside module ``k8s.io/api``. The package model reads every
go.mod and go.work once per scan; resolution matches the import path against the in-tree modules the
importing module can name, longest first, on a ``/`` boundary.
"""
import json
import textwrap
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal.analyzers.imports import build_cache, go
from reveal.analyzers.imports.go import GoExtractor, go_directives, module_contains
from reveal.analyzers.imports.resolution import ProjectResolver
from reveal.analyzers.imports.types import ImportStatement

STAGING = 'staging/src/example.com'

# A Kubernetes-shaped tree: a root module, staged modules linked by go.work (one level above them) and by
# local replaces, a staged module outside the workspace, and a nested module nobody links.
WORKSPACE = {
    'go.work': f'''
        go 1.22

        use (
        \t.
        \t./{STAGING}/api
        \t./{STAGING}/client
        \t./{STAGING}/sampler // reaches api through this go.work only
        \t./{STAGING}/client/plugins
        )
    ''',
    'go.mod': '''
        module example.com/app

        go 1.22

        replace example.com/app/vendored => ./third_party/vendored
    ''',
    'pkg/app/main.go': '''
        package main

        import (
        \t"fmt"
        \tv1 "example.com/api/core/v1"
        \t"example.com/client/rest"
        \t"example.com/app/pkg/util"
        \t"example.com/app/vendored/lib"
        )
    ''',
    'pkg/util/util.go': 'package util\n',
    # the longest module path wins: example.com/app/vendored is the replace target, not ./vendored
    'third_party/vendored/go.mod': 'module example.com/app/vendored\n\ngo 1.22\n',
    'third_party/vendored/lib/lib.go': 'package lib\n',
    'vendored/lib/decoy.go': 'package lib\n',
    f'{STAGING}/api/go.mod': 'module example.com/api\n\ngo 1.22\n',
    f'{STAGING}/api/core/v1/types.go': 'package v1\n',
    # BACK-2558: example.com/apimachinery is not inside module example.com/api, though api has machinery/pkg
    f'{STAGING}/api/core/v1/conv.go': 'package v1\n\nimport "example.com/apimachinery/pkg"\n',
    f'{STAGING}/api/machinery/pkg/trap.go': 'package pkg\n',
    f'{STAGING}/apimachinery/go.mod': 'module example.com/apimachinery\n\ngo 1.22\n',
    f'{STAGING}/apimachinery/pkg/pkg.go': 'package pkg\n',
    f'{STAGING}/client/go.mod': '''
        module example.com/client

        go 1.22

        replace (
        \texample.com/api v0.0.0 => ../api
        \texample.com/remote => example.com/fork v1.2.3
        )
    ''',
    f'{STAGING}/client/rest/rest.go': 'package rest\n\nimport v1 "example.com/api/core/v1"\n',
    # a module nested in client that client reaches through the go.work above it only
    f'{STAGING}/client/rest/auth.go': 'package rest\n\nimport "example.com/plugins/auth"\n',
    f'{STAGING}/client/plugins/go.mod': 'module example.com/plugins\n\ngo 1.22\n',
    f'{STAGING}/client/plugins/auth/auth.go': 'package auth\n',
    f'{STAGING}/sampler/go.mod': 'module example.com/sampler\n\ngo 1.22\n',
    f'{STAGING}/sampler/sample.go': 'package sampler\n\nimport v1 "example.com/api/core/v1"\n',
    # a nested module neither go.work nor a replace links imports the published root module
    'tools/go.mod': 'module example.com/app/tools\n\ngo 1.22\n',
    'tools/gen/main.go': 'package main\n\nimport "example.com/app/pkg/util"\n',
}

EXPECTED = {
    'pkg/app/main.go': {f'{STAGING}/api/core/v1', f'{STAGING}/client/rest', 'pkg/util', 'third_party/vendored/lib'},
    f'{STAGING}/client/rest/rest.go': {f'{STAGING}/api/core/v1'},
    f'{STAGING}/client/rest/auth.go': {f'{STAGING}/client/plugins/auth'},
    f'{STAGING}/sampler/sample.go': {f'{STAGING}/api/core/v1'},
    f'{STAGING}/api/core/v1/conv.go': set(),
    'tools/gen/main.go': set(),
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


def test_workspace_replace_and_own_module_paths_resolve_through_the_public_view(ws):
    resolved = _resolved_by_importer(_default_view(ws))
    for importer, targets in EXPECTED.items():
        assert resolved.get(importer, set()) == targets, importer


def test_importers_of_a_staged_package_include_the_root_module_and_its_siblings(ws):
    result = _run_reveal_in(ws, f'imports://.?importers={STAGING}/api/core/v1/types.go', '--format', 'json')
    assert result.returncode == 0, result.stderr
    importers = {row['file'] for row in json.loads(result.stdout)['importers']}
    assert importers == {'pkg/app/main.go', f'{STAGING}/client/rest/rest.go', f'{STAGING}/sampler/sample.go'}


def test_the_model_reads_go_mod_and_go_work_into_linked_units(ws):
    failures = []
    model = ProjectResolver._build_package_model(sorted(ws.rglob('*.go')), on_error=failures.append)
    assert failures == []
    root = ws.resolve()
    units = {u.name: u for u in model.units}
    assert {name: u.manifest.relative_to(root).as_posix() for name, u in units.items()} == {
        'example.com/app': 'go.mod', 'example.com/app/vendored': 'third_party/vendored/go.mod',
        'example.com/api': f'{STAGING}/api/go.mod', 'example.com/apimachinery': f'{STAGING}/apimachinery/go.mod',
        'example.com/client': f'{STAGING}/client/go.mod', 'example.com/sampler': f'{STAGING}/sampler/go.mod',
        'example.com/plugins': f'{STAGING}/client/plugins/go.mod', 'example.com/app/tools': 'tools/go.mod'}
    names = {name: {spelled for spelled, _ in model.local_units(u.library_root)} for name, u in units.items()}
    workspace = {'example.com/app', 'example.com/api', 'example.com/client', 'example.com/sampler',
                 'example.com/plugins'}
    assert names['example.com/app'] == workspace | {'example.com/app/vendored'}
    assert names['example.com/client'] == workspace                    # go.work and its replace agree
    assert names['example.com/apimachinery'] == {'example.com/apimachinery'}   # not used: links nothing
    assert names['example.com/app/tools'] == {'example.com/app/tools'}
    assert 'example.com/remote' not in names['example.com/client']   # a module replacement is not a directory


def test_a_module_path_contains_a_package_only_on_a_slash_boundary():
    assert module_contains('k8s.io/api', 'k8s.io/api')
    assert module_contains('k8s.io/api', 'k8s.io/api/core/v1')
    assert not module_contains('k8s.io/api', 'k8s.io/apimachinery/pkg')
    assert not module_contains('example.com/foo', 'example.com/foobar/x')


def test_the_boundary_holds_without_a_model_and_in_classification(ws):
    """BACK-2558: calls:// (no model) and the classifier use the same containment test."""
    conv = ws / f'{STAGING}/api/core/v1/conv.go'
    stmt = ImportStatement(conv, 3, 'example.com/apimachinery/pkg', [], False, 'import')
    assert GoExtractor().resolve_import(stmt, conv.parent) is None
    assert GoExtractor().is_intra_project_import(stmt, conv.parent) is False
    own = ImportStatement(conv, 3, 'example.com/api/machinery/pkg', [], False, 'import')
    assert GoExtractor().resolve_import(own, conv.parent) == (ws / f'{STAGING}/api/machinery/pkg').resolve()
    assert GoExtractor().is_intra_project_import(own, conv.parent) is True


def test_without_a_model_only_the_nearest_module_counts(ws):
    """Callers that pass no model keep the nearest-go.mod answer (BACK-2553 moves them)."""
    rest = ws / f'{STAGING}/client/rest/rest.go'
    stmt = ImportStatement(rest, 3, 'example.com/api/core/v1', ['v1'], False, 'import')
    assert GoExtractor().resolve_import(stmt, rest.parent) is None


def test_go_directives_reads_blocks_comments_and_quotes():
    text = 'module "example.com/q" // name\n\nreplace (\n\ta v1 => ../a\n\tb => c v2\n)\nuse\t./x\nuse (\n\t.\n)\n'
    assert go_directives(text) == [('module', ['example.com/q']), ('replace', ['a', 'v1', '=>', '../a']),
                                   ('replace', ['b', '=>', 'c', 'v2']), ('use', ['./x']), ('use', ['.'])]


def test_a_go_work_that_is_not_utf8_declares_nothing(ws):
    (ws / 'go.work').write_bytes(b'go 1.22\nuse ./\xff\n')
    resolved = _resolved_by_importer(_default_view(ws))
    assert resolved[f'{STAGING}/client/rest/rest.go'] == {f'{STAGING}/api/core/v1'}   # its replace still links
    assert resolved.get(f'{STAGING}/sampler/sample.go', set()) == set()           # go.work was its only link
    assert resolved['pkg/app/main.go'] == {'pkg/util', 'third_party/vendored/lib'}


@pytest.mark.skipif(not hasattr(__import__('os'), 'geteuid') or __import__('os').geteuid() == 0,
                    reason='needs a non-root POSIX user for an unreadable file')
def test_an_unreadable_manifest_is_a_recorded_failure(ws):
    manifest = ws / f'{STAGING}/client/go.mod'
    manifest.chmod(0)
    try:
        failures = []
        ProjectResolver._build_package_model(sorted(ws.rglob('*.go')), on_error=failures.append)
        assert [Path(f.filename).name for f in failures] == ['go.mod']
    finally:
        manifest.chmod(0o644)


# --- cache lifetime: a go.work above the scan root is in the graph key (cause 6) ---------------------------

def _client_targets(ws: Path):
    """What client's rest package resolves to when the client module is the scan root (its own go.mod is the
    project marker, so the walk stays inside it): its nested plugins module only through the go.work above."""
    view = _default_view(ws / STAGING / 'client')
    return {s['resolved'] for s in view['rest/auth.go'] if s['resolved']}


def _drop_plugins_from_the_workspace(ws: Path):
    work = ws / 'go.work'
    work.write_text(work.read_text(encoding='utf-8').replace(f'\t./{STAGING}/client/plugins', ''), encoding='utf-8')


@pytest.fixture
def cached(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    go._IMPORTS_CACHE.clear()
    yield
    go._IMPORTS_CACHE.clear()


@pytest.mark.disk_cache
def test_cache_off_answer_moves_with_the_go_work_above_the_root(ws, monkeypatch):
    """Positive control for the cached tests below."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    assert _client_targets(ws) == {'plugins/auth'}
    _drop_plugins_from_the_workspace(ws)
    assert _client_targets(ws) == set()


@pytest.mark.disk_cache
def test_an_edit_to_a_go_work_above_the_scan_root_misses_the_graph_cache(ws, cached):
    assert _client_targets(ws) == {'plugins/auth'}
    assert _client_targets(ws) == {'plugins/auth'}   # warm
    _drop_plugins_from_the_workspace(ws)
    assert _client_targets(ws) == set()


@pytest.mark.disk_cache
def test_without_the_context_manifests_the_cached_graph_goes_stale(ws, cached, monkeypatch):
    """Red control: a key without the manifests above the root serves the old graph after the edit."""
    monkeypatch.setattr(build_cache, '_context_manifests', lambda root: [])
    assert _client_targets(ws) == {'plugins/auth'}
    _drop_plugins_from_the_workspace(ws)
    assert _client_targets(ws) == {'plugins/auth'}


def test_context_manifests_include_the_go_work_above_the_root(ws):
    found = build_cache._context_manifests((ws / STAGING / 'client').resolve())
    assert found == [(ws / STAGING / 'client/go.mod').resolve(), (ws / 'go.mod').resolve(), (ws / 'go.work').resolve()]
