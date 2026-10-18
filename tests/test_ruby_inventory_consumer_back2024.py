"""Cached Ruby classification loss replays once into each Depends consumer."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import depends
from reveal.adapters.imports import ImportsAdapter
from reveal.analyzers.imports import generic, service

pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def ruby(root, *, roots=1):
    (root / '.git').mkdir(parents=True)
    write(root / 'Gemfile.lock', 'GEM\n  specs:\n    external_gem (1.0.0)\n')
    write(root / 'lib' / 'known_local.rb', 'module KnownLocal\nend\n')
    cores = []
    for index in range(roots):
        core = root / ('core' if roots == 1 else f'core{index}')
        write(core / (core.name + '.gemspec'), '# filename inventory, not parsed Ruby DSL\n')
        write(core / 'lib' / f'spree{index}' / 'existing.rb', 'module Existing\nend\n')
        cores.append(core)
    consumer = write(root / 'api' / 'consumer.rb',
                     'require "spree0/missing"\nrequire "external_gem"\n'
                     'require "another_unknown"\nrequire "known_local/missing"\nrequire_relative "local"\n')
    local = write(root / 'api' / 'local.rb', 'module Local\nend\n')
    return consumer, local, cores


def fault(monkeypatch, root, cores, mode, *, unknown=False):
    state = {'manifest': False, 'events': [], 'main': [], 'loads': []}
    real_manifests = generic.load_path_manifests
    real_scandir = os.scandir
    real_iterdir = Path.iterdir
    real_discover = service.discover
    real_load = depends.DependsAdapter._build_load_path_roots

    def manifests(*args, **kwargs):
        previous = state['manifest']; state['manifest'] = True
        try:
            return real_manifests(*args, **kwargs)
        finally:
            state['manifest'] = previous

    def fail(path):
        state['events'].append(str(path))
        if unknown:
            raise PermissionError('controlled unlocated Ruby inventory consumer loss')
        raise PermissionError(13, 'controlled Ruby inventory consumer loss', str(path))

    def scandir(path):
        if mode == 'manifest' and state['manifest'] and Path(path) in cores:
            fail(path)
        return real_scandir(path)

    def iterdir(path):
        if mode == 'lib' and path in {core / 'lib' for core in cores}:
            fail(path)
        return real_iterdir(path)

    def discover(scope):
        files = real_discover(scope)
        state['main'].append(files)
        return files

    def load(*args, **kwargs):
        roots = real_load(*args, **kwargs); state['loads'].append(roots)
        return roots

    monkeypatch.setattr(generic, 'load_path_manifests', manifests)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(Path, 'iterdir', iterdir)
    monkeypatch.setattr(service, 'discover', discover)
    monkeypatch.setattr(depends.DependsAdapter, '_build_load_path_roots', staticmethod(load))
    return state


def warning(result):
    entries = [entry for entry in result.get('meta', {}).get('warnings', [])
               if entry.get('type') == 'analysis_incomplete' and entry.get('unit') == 'directories']
    assert len(entries) == 1
    return entries[0]


def healthy_main(state, cores):
    assert state['main'] and all(not files.traversal_failures for files in state['main'])
    assert state['loads'] and all(set(core / 'lib' for core in cores) <= set(roots) for roots in state['loads'])


@pytest.mark.parametrize('prefill', ['pair_helper', 'imports'])
@pytest.mark.parametrize('mode', ['manifest', 'lib'])
def test_cached_inventory_failure_prefilled_by_another_consumer_reaches_depends(tmp_path, monkeypatch, prefill, mode):
    root = tmp_path / 'affected'; _, target, cores = ruby(root)
    state = fault(monkeypatch, root, cores, mode)
    if prefill == 'pair_helper':
        local, external = generic._ruby_gem_inventory(root)
        assert isinstance(local, frozenset) and isinstance(external, frozenset)
        assert 'external_gem' in external
    else:
        imports = ImportsAdapter(str(root)).get_structure()
        records = [row for rows in imports['files'].values() for row in rows]
        assert next(row for row in records if row['module'] == 'spree0/missing')['classification'] == 'unresolved'
    before = generic._ruby_gem_inventory.cache_info()
    actual_errors = len(state['events']); assert actual_errors == 1
    result = depends.DependsAdapter(str(target)).get_structure()
    after = generic._ruby_gem_inventory.cache_info()
    assert after.misses == before.misses and after.hits > before.hits
    assert len(state['events']) == actual_errors  # only cache hits during Depends classification
    assert result['count'] == 1  # observed relative edge survives
    assert warning(result)['count'] == 1
    assert result['undercount_possible'] and result['_meta']['confidence'] == 'reduced'
    assert result['metadata']['scan_budget']['exact'] is True
    healthy_main(state, cores)


def test_two_real_unknown_events_replay_once_per_root_across_statements_and_builds(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; _, target, cores = ruby(root, roots=2)
    state = fault(monkeypatch, root, cores, 'manifest', unknown=True)
    generic._ruby_gem_inventory(root)
    assert len(state['events']) == 2
    first = depends.DependsAdapter(str(target))
    for owner in (first, first, depends.DependsAdapter(str(target))):
        result = owner.get_structure()
        assert len(state['events']) == 2
        entry = warning(result)
        assert entry['count'] == 0 and entry['unknown_directory_events'] == 2
        assert len(owner._graph.traversal_failures) == 2
        assert all(path is None for path, _ in owner._graph.traversal_failures)
        assert result['metadata']['scan_budget']['exact'] is True
    healthy_main(state, cores)


@pytest.mark.parametrize('view', ['text', 'json', 'dot', 'artifact', 'provenance'])
@pytest.mark.parametrize('mode', ['manifest', 'lib'])
def test_public_inventory_loss_views_retain_risk_and_healthy_source_budget(tmp_path, monkeypatch, view, mode):
    root = tmp_path / 'affected'; _, target, cores = ruby(root)
    state = fault(monkeypatch, root, cores, mode)
    artifact = tmp_path / 'inventory.json'
    uri = 'depends://' + str(root if view == 'dot' else target)
    if view == 'dot':
        uri += '?format=dot'
    flags = []
    if view in {'json', 'provenance'}:
        flags += ['--format', 'json']
    if view == 'provenance':
        flags += ['--provenance']
    if view == 'artifact':
        flags += ['--also-json', str(artifact)]
    response = run(uri, *flags)
    assert response.returncode == 0
    healthy_main(state, cores)
    if view in {'json', 'provenance', 'artifact'}:
        result = json.loads(artifact.read_text(encoding='utf-8') if view == 'artifact' else response.stdout)
        assert warning(result)['count'] == 1
        assert result['metadata']['scan_budget']['exact'] is True
        assert result['undercount_possible'] and result['_meta']['confidence'] == 'reduced'
        if view == 'provenance':
            assert result['execution']['command']
    else:
        assert response.stdout.count('identified directory enumeration(s) failed') == 1
        assert 'PermissionError' in response.stdout
        if view == 'dot':
            assert response.stdout.startswith('digraph depends {\n')
            assert any(line.lstrip().startswith('//') and 'PermissionError' in line for line in response.stdout.splitlines())
        else:
            assert 'observed' in response.stdout


@pytest.mark.parametrize('provenance', [False, True])
def test_normal_decorated_requests_repair_without_clears_and_keep_sibling_exact(tmp_path, monkeypatch, provenance):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    root = tmp_path / 'affected'; _, target, cores = ruby(root)
    _, sibling, _ = ruby(tmp_path / 'sibling')
    uri = 'depends://' + str(target); sibling_uri = 'depends://' + str(sibling)
    def query(path):
        result = reveal_query(path, provenance=provenance)
        assert type(result) is str and not isinstance(result, _ToolFailure)
        return result
    clean = query(uri); baseline_sibling = query(sibling_uri)
    with monkeypatch.context() as context:
        fault(context, root, cores, 'manifest')
        lost = query(uri)
        assert 'directory enumeration' in lost
        assert query(sibling_uri) == baseline_sibling
    assert query(uri) == clean


def test_imports_annotation_scope_stays_explicit_unresolved_without_graph_loss_adoption(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; _, _, cores = ruby(root)
    fault(monkeypatch, root, cores, 'manifest')
    result = ImportsAdapter(str(root)).get_structure()
    records = [row for rows in result['files'].values() for row in rows]
    assert next(row for row in records if row['module'] == 'spree0/missing')['classification'] == 'unresolved'
    assert not any(entry.get('unit') == 'directories' for entry in result.get('meta', {}).get('warnings', []))


def test_absent_marker_keeps_unknown_and_pair_facade_preserves_cache_controls(tmp_path):
    from reveal.analyzers.imports.types import ImportStatement
    root = tmp_path / 'unmarked'; root.mkdir()
    stmt = ImportStatement(root / 'consumer.rb', 1, 'unknown_name', [], False, 'require')
    assert generic.RubyImportExtractor().is_intra_project_import(stmt, root) is None
    pair = generic._ruby_gem_inventory(root)
    assert pair == (frozenset(), frozenset())
    assert pair[0] == frozenset() and pair[1] == frozenset()
    assert generic._ruby_gem_inventory.cache_parameters() == {'maxsize': None, 'typed': False}
    assert callable(generic._ruby_gem_inventory.cache_clear)
