"""Independent Depends manifest-only loss consumers preserve census ownership."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import depends
from reveal.analyzers.imports import service
from reveal.utils.exclusions import exclusion_scope
from reveal.utils.path_utils import to_posix

pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def ruby(root, *, positive=False):
    (root / '.git').mkdir(parents=True)
    write(root / 'core' / 'core.gemspec', '# sibling lib registration uses filename only\n')
    target = write(root / 'core' / 'lib' / 'spree' / 'testing_support' / 'helper.rb', 'module Spree\nend\n')
    write(root / 'api' / 'spec' / 'consumer.rb', 'require "spree/testing_support/helper"\n')
    if positive:
        write(root / 'api' / 'spec' / 'relative.rb', 'require_relative "../../core/lib/spree/testing_support/helper"\n')
    return target


def fault(monkeypatch, root, *, unknown=False, combined=False):
    state = {'manifest': False, 'events': [], 'discoveries': []}
    real_loader = depends.load_path_manifests
    real_scandir = os.scandir
    real_discover = service.discover

    def loader(*args, **kwargs):
        previous = state['manifest']; state['manifest'] = True
        try:
            return real_loader(*args, **kwargs)
        finally:
            state['manifest'] = previous

    def scandir(path):
        manifest_loss = state['manifest'] and Path(path) == root / 'core'
        source_loss = combined and not state['manifest'] and Path(path) == root / 'api' / 'spec'
        if manifest_loss or source_loss:
            state['events'].append(('manifest' if manifest_loss else 'source', str(path)))
            if unknown:
                raise PermissionError('controlled unlocated required manifest consumer loss')
            raise PermissionError(13, 'controlled required manifest consumer loss', str(path))
        return real_scandir(path)

    def discover(scope):
        files = real_discover(scope)
        state['discoveries'].append(files)
        return files

    monkeypatch.setattr(depends, 'load_path_manifests', loader)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(service, 'discover', discover)
    return state


def directory_warning(result):
    entries = [entry for entry in result.get('meta', {}).get('warnings', [])
               if entry.get('type') == 'analysis_incomplete' and entry.get('unit') == 'directories']
    assert len(entries) == 1
    return entries[0]


def healthy_census(state, count):
    assert state['discoveries']
    for files in state['discoveries']:
        assert len(files.candidates) == count and not files.traversal_failures
        assert 'core.gemspec' in files.index and 'helper.rb' in files.index


@pytest.mark.parametrize('positive', [False, True])
def test_real_manifest_loss_keeps_census_exact_and_qualifies_observed_results(tmp_path, monkeypatch, positive):
    root = tmp_path / 'affected'; target = ruby(root, positive=positive)
    owner = depends.DependsAdapter(str(target))
    clean = owner.get_structure(); assert clean['count'] == 1 + int(positive)
    with monkeypatch.context() as context:
        state = fault(context, root)
        result = owner.get_structure()
        healthy_census(state, 2 + int(positive))
        assert result['count'] == int(positive)
        assert result['metadata']['scan_budget'] == clean['metadata']['scan_budget']
        assert result['metadata']['scan_budget']['exact'] is True
        assert owner._graph.traversal_failures
        assert directory_warning(result)['directories'] == ['core']
        assert result['_meta']['confidence'] == 'reduced' and result['undercount_possible']
    assert owner.get_structure() == clean


@pytest.mark.parametrize('view', ['file', 'summary', 'top', 'dot', 'json', 'artifact'])
@pytest.mark.parametrize('positive', [False, True])
def test_public_uri_manifest_diagnostics_survive_existing_views(tmp_path, monkeypatch, view, positive):
    root = tmp_path / 'affected'; target = ruby(root, positive=positive)
    state = fault(monkeypatch, root)
    uri = 'depends://' + str(target if view in {'file', 'json', 'artifact'} else root)
    if view == 'top':
        uri += '?top=1'
    elif view == 'dot':
        uri += '?format=dot'
    flags = ['--format', 'json'] if view == 'json' else []
    artifact = tmp_path / 'manifest.json'
    if view == 'artifact':
        flags += ['--also-json', str(artifact)]
    result = run(uri, *flags)
    assert result.returncode == 0  # BACK-2019 legacy Depends exit policy
    healthy_census(state, 2 + int(positive))
    if view in {'json', 'artifact'}:
        payload = json.loads(result.stdout if view == 'json' else artifact.read_text(encoding='utf-8'))
        assert directory_warning(payload)['count'] == 1
        assert payload['metadata']['scan_budget']['exact'] is True
        assert payload['undercount_possible'] and payload['_meta']['confidence'] == 'reduced'
    else:
        assert result.stdout.count('identified directory enumeration(s) failed') == 1
        assert 'PermissionError' in result.stdout
        assert 'nothing imports this module' not in result.stdout
        assert 'No internal imports found.' not in result.stdout
        if view == 'dot':
            assert result.stdout.startswith('digraph depends {\n')
            assert any(line.lstrip().startswith('//') and 'PermissionError' in line for line in result.stdout.splitlines())
        elif positive:
            assert 'observed' in result.stdout.lower()


@pytest.mark.parametrize('provenance', [False, True])
def test_decorated_mcp_manifest_loss_retains_legacy_result_with_attribution(tmp_path, monkeypatch, provenance):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    root = tmp_path / 'affected'; target = ruby(root)
    state = fault(monkeypatch, root, unknown=True)
    result = reveal_query('depends://' + str(target), provenance=provenance)
    assert type(result) is str and not isinstance(result, _ToolFailure)
    assert 'unknown directory' in result and 'nothing imports this module' not in result
    healthy_census(state, 2)
    if provenance:
        data = json.loads(result)
        assert directory_warning(data)['count'] == 0
        assert directory_warning(data)['unknown_directory_events'] > 0
        assert data['metadata']['scan_budget']['exact'] is True
        assert data['undercount_possible'] and data['_meta']['confidence'] == 'reduced'
        assert data['execution']['command'].startswith('reveal depends://')


def test_main_and_manifest_actual_events_merge_without_fabricating_source_count(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; target = ruby(root)
    state = fault(monkeypatch, root, combined=True)
    owner = depends.DependsAdapter(str(target)); result = owner.get_structure()
    assert {phase for phase, _ in state['events']} == {'source', 'manifest'}
    assert {path for path, _ in owner._graph.traversal_failures} == {to_posix(root / 'core'), to_posix(root / 'api' / 'spec')}
    assert directory_warning(result)['count'] == 2
    assert result['metadata']['scan_budget'] == {'scope': 'scan', 'limit': 5000, 'total': 1, 'returned': 1, 'exact': False}


def test_file_excluded_manifest_remains_required_but_hard_directory_does_not(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; target = ruby(root)
    with exclusion_scope(root, ['core/core.gemspec']):
        assert depends.DependsAdapter(str(target)).get_structure()['count'] == 1
        with monkeypatch.context() as context:
            fault(context, root)
            result = depends.DependsAdapter(str(target)).get_structure()
        assert result['count'] == 0 and directory_warning(result)
    with exclusion_scope(root, ['core']):
        clean = depends.DependsAdapter(str(target)).get_structure()
        with monkeypatch.context() as context:
            state = fault(context, root)
            assert depends.DependsAdapter(str(target)).get_structure() == clean
            assert not state['events']


def test_unrelated_sibling_and_nonruby_do_not_acquire_manifest_loss(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; target = ruby(root)
    sibling_target = ruby(tmp_path / 'sibling')
    sibling = depends.DependsAdapter(str(sibling_target)); clean = sibling.get_structure()
    pyroot = tmp_path / 'python'
    python = write(pyroot / 'target.py', 'VALUE=1\n')
    write(pyroot / 'consumer.py', 'import target\n')
    (pyroot / '.git').mkdir()
    original = depends.load_path_manifests
    calls = []

    def loader(*args, **kwargs):
        calls.append(args[0]); return original(*args, **kwargs)

    with monkeypatch.context() as context:
        fault(context, root)
        assert sibling.get_structure() == clean
    monkeypatch.setattr(depends, 'load_path_manifests', loader)
    assert depends.DependsAdapter(str(python)).get_structure()['count'] == 1
    assert calls == []


def test_project_under_cache_keeps_root_relative_noise_policy_exact(tmp_path, monkeypatch):
    root = tmp_path / '.cache' / 'affected'; target = ruby(root)
    noise = root / 'node_modules'
    write(noise / 'unused' / 'unused.gemspec', '# omitted noise\n')
    owner = depends.DependsAdapter(str(target)); clean = owner.get_structure()
    real = os.scandir
    attempts = []

    def scandir(path):
        if Path(path) == noise:
            attempts.append(path)
            raise PermissionError(13, 'noise must not be enumerated', str(path))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    assert owner.get_structure() == clean and clean['count'] == 1
    assert attempts == []
