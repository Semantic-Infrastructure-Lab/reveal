"""Cached Ruby classification loss remains required Depends risk with healthy source discovery."""
import errno
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.depends import DependsAdapter
from reveal.analyzers.imports import generic, service
from reveal.analyzers.imports.resolution import ProjectResolver
from reveal.mcp_server import _ToolFailure, reveal_query


def write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000  # request-cache stamps skip files newer than the request; Windows' clock is coarse
    os.utime(path, ns=(aged, aged))
    return path


def tree(root, *, positive=False, requires=None, lock=True):
    (root / '.git').mkdir(parents=True)
    if lock:
        write(root / 'Gemfile.lock', 'GEM\n  specs:\n    external_gem (1.0.0)\n')
    write(root / 'core' / 'core.gemspec', '# manifest filename, no Ruby DSL evaluation\n')
    target = write(root / 'core' / 'lib' / 'spree' / 'existing.rb', 'module Existing\nend\n')
    source = requires if requires is not None else 'require "spree/missing"\nrequire "external_gem"\nrequire "another_unknown"\n'
    if positive:
        target = write(root / 'api' / 'spec' / 'local.rb', 'module Local\nend\n')
        source += 'require_relative "local"\n'
    write(root / 'api' / 'spec' / 'consumer.rb', source)
    return target


@contextmanager
def inventory_fault(root, mode, *, lib_error=PermissionError, denied=None):
    original_manifest = generic.load_path_manifests
    original_scandir, original_iterdir = os.scandir, Path.iterdir
    original_discover = service.discover
    original_load = ProjectResolver._build_load_path_roots
    active = []
    events, discoveries, loads = [], [], []
    denied_path = (denied or root / ('core' if mode == 'manifest' else 'core/lib')).resolve()

    def manifests(*args, **kwargs):
        active.append(True)
        try:
            return original_manifest(*args, **kwargs)
        finally:
            active.pop()

    def scandir(path):
        if mode == 'manifest' and active and Path(path).resolve() == denied_path:
            events.append(('manifest', Path(path)))
            raise PermissionError(errno.EACCES, 'controlled Ruby classification inventory enumeration loss', str(path))
        return original_scandir(path)

    def iterdir(path):
        if mode == 'lib' and path.resolve() == denied_path:
            events.append(('lib', path))
            code = errno.ENOENT if lib_error is FileNotFoundError else errno.ENOTDIR if lib_error is NotADirectoryError else errno.EACCES
            raise lib_error(code, 'controlled attempted Ruby lib enumeration loss', str(path))
        return original_iterdir(path)

    def discover(scope):
        files = original_discover(scope)
        discoveries.append(files)
        return files

    def load(*args, **kwargs):
        result = original_load(*args, **kwargs)
        loads.append(result)
        return result

    with patch.object(generic, 'load_path_manifests', manifests), patch('os.scandir', scandir), \
            patch.object(Path, 'iterdir', iterdir), patch.object(service, 'discover', discover), \
            patch.object(ProjectResolver, '_build_load_path_roots', side_effect=load):
        yield events, discoveries, loads


def request(target):
    answer = reveal_query(f'depends://{target.as_posix()}', provenance=True)
    assert isinstance(answer, str) and not isinstance(answer, _ToolFailure)
    return json.loads(answer)


def without_execution(result):
    # execution.git.dirty reads the process checkout, which other workers write to (BACK-2059)
    return {key: value for key, value in result.items() if key != 'execution'}


def assert_risk(result, discoveries, loads, root, positive=False):
    assert result['_meta']['confidence'] == 'reduced'
    assert result['undercount_possible'] is True
    warnings = [w for w in result.get('meta', {}).get('warnings', []) if w.get('type') == 'analysis_incomplete']
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning['unit'] == 'directories' and warning['count'] == 1
    assert 'missing file population is unknown' in warning['message']
    assert result['warning'].count(warning['message']) == 1
    assert discoveries and all(not files.traversal_failures for files in discoveries)
    expected = 2 + int(positive)
    assert all(len(files.candidates) == expected for files in discoveries)
    assert loads and all(root / 'core' / 'lib' in roots for roots in loads)
    budget = result['metadata']['scan_budget']
    assert budget['total'] == budget['returned'] == expected and budget['exact'] is True
    assert result['metadata']['scan_capped'] is False
    assert result['metadata']['total_import_edges'] == int(positive)
    return warning


@pytest.mark.parametrize('mode', ['manifest', 'lib'])
@pytest.mark.parametrize('positive', [False, True])
def test_actual_cached_inventory_loss_is_required_risk_with_main_and_load_roots_healthy(tmp_path, mode, positive):
    target = tree(tmp_path, positive=positive)
    clean = request(target)
    with inventory_fault(tmp_path, mode) as (events, discoveries, loads):
        lost = request(target)
    assert events and clean['count'] == lost['count'] == int(positive)
    warning = assert_risk(lost, discoveries, loads, tmp_path, positive)
    assert warning['directories'] == ['core' if mode == 'manifest' else 'core/lib']
    assert generic._ruby_gem_inventory.cache_info().misses == 1
    assert generic._ruby_gem_inventory.cache_info().hits >= 2
    assert without_execution(request(target)) == without_execution(clean)


@pytest.mark.parametrize('module', ['retained/missing', 'external_gem', 'unknown_name'])
def test_inventory_facts_are_consumed_independently_of_observed_verdict(tmp_path, module):
    target = tree(tmp_path, requires=f'require "{module}"\n')
    write(tmp_path / 'lib' / 'retained' / 'entry.rb', 'module Retained\nend\n')
    # Keep the extra real source in the expected source census for this focused case.
    with inventory_fault(tmp_path, 'manifest') as (events, discoveries, loads):
        owner = DependsAdapter(str(target))
        result = owner.get_structure()
    assert events
    assert result['_meta']['confidence'] == 'reduced' and result['undercount_possible'] is True
    entries = [w for w in result.get('meta', {}).get('warnings', []) if w.get('type') == 'analysis_incomplete']
    assert len(entries) == 1
    assert owner._graph.traversal_failures
    assert discoveries and all(not files.traversal_failures for files in discoveries)
    assert result['metadata']['scan_budget']['exact'] is True
    assert result['metadata']['scan_budget']['total'] == 3
    assert all(tmp_path / 'core' / 'lib' in roots for roots in loads)


@pytest.mark.parametrize('error_class', [PermissionError, FileNotFoundError, NotADirectoryError])
def test_every_oserror_from_actual_existing_lib_iteration_is_known_loss(tmp_path, error_class):
    target = tree(tmp_path)
    assert (tmp_path / 'core' / 'lib').is_dir()
    with inventory_fault(tmp_path, 'lib', lib_error=error_class) as (events, discoveries, loads):
        result = request(target)
    assert events
    assert_risk(result, discoveries, loads, tmp_path)
    assert any(error_class.__name__ in cause for cause in result['meta']['warnings'][0]['causes'])


@pytest.mark.parametrize('output_format', ['json', 'text'])
def test_public_depends_keeps_legacy_exit_and_reports_inventory_risk(tmp_path, output_format):
    target = tree(tmp_path)
    with inventory_fault(tmp_path, 'manifest') as (events, discoveries, loads):
        answer = run(f'depends://{target.as_posix()}', '--format', output_format, '--provenance')
    assert answer.returncode == 0 and events
    if output_format == 'json':
        assert_risk(json.loads(answer.stdout), discoveries, loads, tmp_path)
    else:
        assert answer.stdout.count('missing file population is unknown') == 1
        assert 'nothing imports this module' not in answer.stdout


@pytest.mark.parametrize('control', ['missing_lib', 'non_directory_lib', 'missing_lock', 'noise'])
def test_intentional_absence_and_noise_keep_exact_clean_behavior(tmp_path, control):
    target = tree(tmp_path, lock=control != 'missing_lock')
    denied = tmp_path / 'lib'
    mode = 'lib'
    if control == 'non_directory_lib':
        write(denied, 'not a lib directory\n')
    if control == 'noise':
        denied = tmp_path / 'node_modules'
        write(denied / 'vendor' / 'vendor.gemspec', '# ignored noise\n')
        mode = 'manifest'
    if control == 'missing_lock':
        denied = tmp_path / 'core'
        mode = 'manifest'
    clean = request(target)
    with inventory_fault(tmp_path, mode, denied=denied) as (events, _, _):
        actual = request(target)
    assert not events and without_execution(actual) == without_execution(clean)


def test_current_inventory_pair_and_default_cache_controls_are_preserved(tmp_path):
    tree(tmp_path)
    pair = generic._ruby_gem_inventory(tmp_path)
    local, external = pair
    assert type(local) is type(external) is frozenset
    assert pair[0] == local and pair[1] == external and len(pair) == 2
    assert 'spree' in local and 'external_gem' in external
    before = generic._ruby_gem_inventory.cache_info()
    assert generic._ruby_gem_inventory(tmp_path) == pair
    assert generic._ruby_gem_inventory.cache_info().hits == before.hits + 1
    assert generic._ruby_gem_inventory.cache_parameters() == {'maxsize':None, 'typed':False}
    generic._ruby_gem_inventory.cache_clear()
    assert generic._ruby_gem_inventory.cache_info().currsize == 0


def test_existing_import_annotations_remain_honest_and_repair_normally(tmp_path):
    tree(tmp_path, positive=True)

    def annotations():
        answer = reveal_query(f'imports://{tmp_path.as_posix()}', provenance=True)
        result = json.loads(answer)
        return {row['module']:row['classification'] for rows in result['files'].values() for row in rows}

    clean = annotations()
    with inventory_fault(tmp_path, 'manifest') as (events, _, _):
        lost = annotations()
    assert events
    assert clean['spree/missing'] == 'intra_project' and lost['spree/missing'] == 'unresolved'
    assert clean['external_gem'] == lost['external_gem'] == 'unresolved'
    assert clean['another_unknown'] == lost['another_unknown'] == 'unresolved'
    assert clean['local'] == lost['local'] == 'intra_project'
    assert annotations() == clean


def test_frozen_fact_cache_and_historical_pair_controls_share_one_build(tmp_path):
    from dataclasses import FrozenInstanceError

    tree(tmp_path)
    with inventory_fault(tmp_path, 'manifest') as (events, _, _):
        facts = generic._ruby_inventory_facts(tmp_path)
        pair = generic._ruby_gem_inventory(tmp_path)
        repeated = generic._ruby_inventory_facts(tmp_path)
    assert len(events) == 1 and repeated is facts
    assert pair == (facts.local_names, facts.external_names)
    assert facts.root == tmp_path and isinstance(facts.traversal_failures, tuple)
    assert Path(facts.traversal_failures[0][0]).resolve() == (tmp_path / 'core').resolve()
    info = generic._ruby_gem_inventory.cache_info()
    assert info.misses == 1 and info.hits == 2 and info.currsize == 1
    with pytest.raises(FrozenInstanceError):
        setattr(facts, 'traversal_failures', ())
    generic._ruby_gem_inventory.cache_clear()
    assert generic._ruby_inventory_facts.cache_info().currsize == 0
