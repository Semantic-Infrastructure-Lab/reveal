"""Required manifest-only loss must not masquerade as healthy Depends resolution."""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.depends import DependsAdapter
from reveal.analyzers.imports import resolution, service
from reveal.analyzers.imports.resolution import ProjectResolver
from reveal.analyzers.imports.file_index import load_path_manifests
from reveal.utils.exclusions import exclusion_scope


@pytest.fixture(autouse=True)
def _cold_build(monkeypatch):
    """The loss is injected between two builds of one tree; a disk-cached clean graph would hide it.
    ci-local.sh runs the cache off and CI on (BACK-2056), and depends builds through the engine's
    disk graph cache since BACK-1054 S6."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


def write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    return path


def tree(root, *, positive_other=False):
    (root / '.git').mkdir(parents=True)
    # Discovery uses the filename and sibling lib; no executable Ruby DSL is parsed.
    manifest = write(root / 'core' / 'core.gemspec', 'not executable or parsed Ruby DSL\n')
    target = write(root / 'core' / 'lib' / 'spree' / 'helper.rb', 'module Spree\nend\n')
    source = 'require "spree/helper"\n'
    if positive_other:
        write(root / 'api' / 'spec' / 'local.rb', 'module Local\nend\n')
        source += 'require_relative "local"\n'
    consumer = write(root / 'api' / 'spec' / 'consumer.rb', source)
    return target, manifest, consumer


@contextmanager
def manifest_fault(root, *, unknown=False, combined=False, denied_path=None):
    real_manifest, real_scandir, real_discover = resolution.load_path_manifests, os.scandir, service.discover
    active = []
    events, discoveries = [], []
    denied = (denied_path or root / 'core').resolve()

    def manifests(*args, **kwargs):
        active.append(True)
        try:
            return real_manifest(*args, **kwargs)
        finally:
            active.pop()

    def scandir(path):
        if (active or combined) and Path(path).resolve() == denied:
            events.append(Path(path))
            if unknown:
                raise PermissionError('controlled unlocated manifest enumeration loss')
            raise PermissionError(13, 'controlled required manifest-only discovery loss', str(path))
        return real_scandir(path)

    def discover(scope):
        files = real_discover(scope)
        discoveries.append(files)
        return files

    with patch.object(resolution, 'load_path_manifests', manifests), patch('os.scandir', scandir), \
            patch.object(service, 'discover', discover):
        yield events, discoveries


def warning(result):
    entries = [entry for entry in result.get('meta', {}).get('warnings', [])
               if entry.get('type') == 'analysis_incomplete']
    assert len(entries) == 1, 'required manifest loss must reach the existing directory-warning owner'
    entry = entries[0]
    assert entry['unit'] == 'directories'
    assert 'missing file population is unknown' in entry['message']
    assert result['warning'].count(entry['message']) == 1
    return entry


def assert_manifest_only_source_population(result, discoveries, expected=2):
    assert discoveries and all(not files.traversal_failures for files in discoveries)
    assert all(len(files.candidates) == expected for files in discoveries)
    accounting = result['metadata']['scan_budget']
    assert accounting['total'] == accounting['returned'] == expected
    assert accounting['exact'] is True
    assert result['metadata']['scan_capped'] is False


@pytest.mark.parametrize('positive_other', [False, True])
@pytest.mark.parametrize('unknown', [False, True])
def test_actual_manifest_loss_is_attributed_without_falsifying_healthy_source_census(tmp_path, positive_other, unknown):
    target, _, _ = tree(tmp_path, positive_other=positive_other)
    owner = DependsAdapter(str(target))
    clean = owner.get_structure()
    with manifest_fault(tmp_path, unknown=unknown) as (events, discoveries):
        lost = owner.get_structure()
    assert clean['count'] == 1 and lost['count'] == 0 and events
    assert lost['metadata']['total_import_edges'] == int(positive_other)
    assert_manifest_only_source_population(lost, discoveries, 2 + int(positive_other))
    entry = warning(lost)
    assert entry['count'] == int(not unknown)
    if unknown:
        assert entry['directories'] == [] and entry['unknown_directory_events'] == 1
    else:
        assert entry['directories'] == ['core']
    assert lost['_meta']['confidence'] == 'reduced' and lost['undercount_possible'] is True
    assert owner._graph.traversal_failures
    assert owner.get_structure() == clean


@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_public_cli_preserves_legacy_exit_and_discloses_missing_manifest_population(tmp_path, output_format):
    target, _, _ = tree(tmp_path)
    with manifest_fault(tmp_path) as (events, discoveries):
        response = run(f'depends://{target}', '--format', output_format, '--provenance')
    assert events and response.returncode == 0
    if output_format == 'json':
        result = json.loads(response.stdout)
        warning(result)
        assert_manifest_only_source_population(result, discoveries)
        assert result['_meta']['confidence'] == 'reduced'
    else:
        assert response.stdout.count('missing file population is unknown') == 1
        assert 'nothing imports this module' not in response.stdout


@pytest.mark.parametrize('provenance', [False, True])
def test_decorated_mcp_retains_normal_legacy_result_with_manifest_disclosure(tmp_path, provenance):
    from reveal.mcp_server import _ToolFailure, reveal_query
    target, _, _ = tree(tmp_path)
    with manifest_fault(tmp_path) as (events, discoveries):
        answer = reveal_query(f'depends://{target}', provenance=provenance)
    assert events and isinstance(answer, str) and not isinstance(answer, _ToolFailure)
    if provenance:
        result = json.loads(answer)
        warning(result)
        assert_manifest_only_source_population(result, discoveries)
    else:
        assert answer.count('missing file population is unknown') == 1


@pytest.mark.parametrize('dot', [False, True])
def test_summary_dot_and_sidecar_keep_surviving_edges_and_single_warning(tmp_path, dot):
    root = tmp_path / 'project'
    tree(root, positive_other=True)
    sidecar = tmp_path / 'answer.json'
    query = 'format=dot&top=1' if dot else 'top=1'
    with manifest_fault(root) as (events, discoveries):
        response = run(f'depends://{root}?{query}', '--provenance', '--also-json', sidecar)
    assert response.returncode == 0 and events
    result = json.loads(sidecar.read_text(encoding='utf-8'))
    warning(result)
    assert_manifest_only_source_population(result, discoveries, 3)
    assert result['total_modules'] == 1 and result['modules'][0]['dependent_count'] == 1
    assert response.stdout.count('missing file population is unknown') == 1
    if dot:
        lines = [line for line in response.stdout.splitlines() if 'missing file population is unknown' in line]
        assert lines[0].lstrip().startswith('//')
        assert '"api/spec/consumer.rb" -> "api/spec/local.rb";' in response.stdout
    else:
        assert 'observed' in response.stdout.lower()


@pytest.mark.parametrize('policy', ['file_excluded', 'gitignored_manifest'])
def test_soft_excluded_manifest_remains_required_resolution_input(tmp_path, policy):
    target, _, _ = tree(tmp_path)
    patterns = ['core/core.gemspec'] if policy == 'file_excluded' else []
    if policy == 'gitignored_manifest':
        write(tmp_path / '.gitignore', 'core/core.gemspec\n')
    with exclusion_scope(tmp_path, patterns):
        clean = DependsAdapter(str(target)).get_structure()
        with manifest_fault(tmp_path) as (events, discoveries):
            lost = DependsAdapter(str(target)).get_structure()
    assert clean['count'] == 1 and lost['count'] == 0 and events
    warning(lost)
    assert_manifest_only_source_population(lost, discoveries)


def test_combined_main_and_manifest_loss_merges_events_without_fake_scan_cap(tmp_path):
    target, _, _ = tree(tmp_path)
    with manifest_fault(tmp_path, combined=True) as (events, discoveries):
        owner = DependsAdapter(str(target))
        result = owner.get_structure()
    assert len(events) >= 2 and discoveries[0].traversal_failures
    entry = warning(result)
    assert entry['count'] == 1 and entry['directories'] == ['core']
    assert len(owner._graph.traversal_failures) >= 2
    assert result['metadata']['scan_budget'] == {'scope':'scan', 'limit':5000, 'total':1, 'returned':1, 'exact':False}
    assert result['metadata']['scan_capped'] is False


def test_real_cap_accounting_is_preserved_when_independent_manifest_walk_fails(tmp_path, monkeypatch):
    target, _, _ = tree(tmp_path)
    monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 1)
    with manifest_fault(tmp_path) as (events, _):
        result = DependsAdapter(str(target)).get_structure()
    assert events and result['metadata']['scan_capped'] is True
    assert result['metadata']['scan_budget'] == {'scope':'scan', 'limit':1, 'total':2, 'returned':1, 'exact':False}
    warning(result)


def test_sibling_repair_and_element_observe_current_manifest_evidence(tmp_path):
    root, sibling = tmp_path / 'affected', tmp_path / 'sibling'
    target, _, _ = tree(root, positive_other=True)
    sibling_target, _, _ = tree(sibling)
    owner = DependsAdapter(str(root))
    clean = owner.get_structure()
    sibling_clean = DependsAdapter(str(sibling_target)).get_structure()
    with manifest_fault(root):
        lost = owner.get_structure()
        warning(lost)
        element = owner.get_element('local.rb')
        assert element is not None and element['count'] == 1
        warning(element)
        assert DependsAdapter(str(sibling_target)).get_structure() == sibling_clean
    assert owner.get_structure() == clean


def test_explicit_directory_policy_omission_is_never_attempted(tmp_path):
    target, _, _ = tree(tmp_path)
    with exclusion_scope(tmp_path, ['core']), manifest_fault(tmp_path) as (events, discoveries):
        result = DependsAdapter(str(target)).get_structure()
    assert events == [] and result['count'] == 0
    assert result['_meta']['confidence'] == 'high' and result['undercount_possible'] is False
    assert_manifest_only_source_population(result, discoveries, 1)
    # No loss warning: the only disclosure is that the policy hid the target (BACK-2075).
    assert [(w['type'], w['causes']) for w in result.get('meta', {}).get('warnings', [])] == [
        ('scope_hidden', ['exclude'])]


def test_reserved_noise_is_relative_to_root_and_never_attempted(tmp_path):
    root = tmp_path / '.cache' / 'project'
    target, _, _ = tree(root)
    write(root / 'node_modules' / 'vendor' / 'vendor.gemspec', '# noise\n')
    clean = DependsAdapter(str(target)).get_structure()
    with manifest_fault(root, denied_path=root / 'node_modules') as (events, _):
        lost = DependsAdapter(str(target)).get_structure()
    assert events == [] and lost == clean and clean['count'] == 1


def test_default_manifest_helpers_keep_list_and_positional_call_contracts(tmp_path):
    target, manifest, consumer = tree(tmp_path)
    assert load_path_manifests(tmp_path, '*.gemspec') == [manifest]
    roots = ProjectResolver._build_load_path_roots([target, consumer], tmp_path)
    assert isinstance(roots, list) and roots == [tmp_path / 'core' / 'lib']


def test_non_ruby_source_does_not_run_manifest_discovery(tmp_path):
    write(tmp_path / 'pyproject.toml', '[project]\nname="python"\n')
    target = write(tmp_path / 'target.py', 'VALUE = 1\n')
    write(tmp_path / 'consumer.py', 'import target\n')
    with patch.object(resolution, 'load_path_manifests', wraps=resolution.load_path_manifests) as manifests:
        result = DependsAdapter(str(target)).get_structure()
    assert result['count'] == 1 and manifests.call_count == 0
