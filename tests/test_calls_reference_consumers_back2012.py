"""Reference-only required loss must not survive recovery as a clean dead-code claim."""

import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast import analysis
from reveal.adapters.calls import CallsAdapter
from reveal.adapters.calls import index


def make_tree(root, *, partial=False):
    root.mkdir()
    (root / 'definitions.py').write_text(
        'def kept():\n    return 1\n\ndef genuinely_dead():\n    return 1\n', encoding='utf-8')
    reference = root / 'references.py'
    reference.write_text('BOUND = kept\n', encoding='utf-8')
    if partial:
        (root / 'other.py').write_text('OTHER = surviving_reference\n', encoding='utf-8')
    return reference


def names(result):
    return {entry['name'] for entry in result['entries']}


def reference_read_loss(monkeypatch, reference):
    """Fail only the real Python-reference read, preserving structural collection."""
    original_pass = index._python_referenced_names
    original_read = Path.read_text
    active = []
    attempts = []

    def analyze(*args, **kwargs):
        active.append(True)
        try:
            return original_pass(*args, **kwargs)
        finally:
            active.pop()

    def read(path, *args, **kwargs):
        if active and path == reference:
            attempts.append(path)
            raise PermissionError(13, 'controlled reference-only read loss', str(reference))
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(index, '_python_referenced_names', analyze)
    monkeypatch.setattr(Path, 'read_text', read)
    return attempts


@pytest.mark.parametrize('partial', [False, True])
@pytest.mark.parametrize('file_request', [False, True])
def test_reference_only_read_loss_is_disclosed_and_recovers_without_manual_eviction(
        tmp_path, monkeypatch, partial, file_request):
    root = tmp_path / 'affected'
    reference = make_tree(root, partial=partial)
    sibling = tmp_path / 'sibling'
    make_tree(sibling)
    clean = CallsAdapter(str(sibling), 'uncalled').get_structure()
    path = root / 'definitions.py' if file_request else root
    adapter = CallsAdapter(str(path), 'uncalled')
    with monkeypatch.context() as context:
        attempts = reference_read_loss(context, reference)
        result = adapter.get_structure()
        assert attempts == [reference]
        assert names(result) == {'kept', 'genuinely_dead'}
        assert str(root) not in index._REFERENCE_CACHE
        (warning,) = [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_failed']
        assert warning['count'] == 1
        assert Path(warning['files'][0]).name == reference.name
        assert 'PermissionError' in warning['message']
        assert 'confidence' not in result['meta']
        assert result['meta']['parse_mode'] == 'tree_sitter_partial'
        assert CallsAdapter(str(sibling), 'uncalled').get_structure() == clean
    repaired = adapter.get_structure()
    assert names(repaired) == {'genuinely_dead'}
    assert repaired['meta'] == clean['meta']


@pytest.mark.parametrize('partial', [False, True])
def test_reference_parser_failure_recovers_after_real_source_repair(tmp_path, partial):
    root = tmp_path / 'affected'
    reference = make_tree(root, partial=partial)
    reference.write_text('BOUND = kept\nif (\n', encoding='utf-8')
    result = CallsAdapter(str(root), 'uncalled').get_structure()
    assert names(result) == {'kept', 'genuinely_dead'}
    assert str(root) not in index._REFERENCE_CACHE
    (warning,) = [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_failed']
    assert warning['count'] == 1
    assert 'SyntaxError' in warning['message']
    reference.write_text('BOUND = kept\n', encoding='utf-8')
    repaired = CallsAdapter(str(root), 'uncalled').get_structure()
    assert names(repaired) == {'genuinely_dead'}
    assert not [w for w in repaired['meta']['warnings'] if w.get('type') == 'analysis_failed']


@pytest.mark.parametrize('partial', [False, True])
def test_direct_existing_helper_does_not_retain_failed_backing_without_sink(tmp_path, monkeypatch, partial):
    root = tmp_path / 'affected'
    reference = make_tree(root, partial=partial)
    with monkeypatch.context() as context:
        reference_read_loss(context, reference)
        found = index._python_referenced_names(root)
        assert ('surviving_reference' in found) is partial
        assert 'kept' not in found
        assert str(root) not in index._REFERENCE_CACHE
    assert 'kept' in index._python_referenced_names(root)


def test_reference_loss_in_empty_structural_collection_reaches_envelope(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    root.mkdir()
    reference = root / 'references.py'
    reference.write_text('BOUND = kept\n', encoding='utf-8')
    real = analysis.create_element_dict

    def skip(path, *args, **kwargs):
        if Path(path) == reference:
            raise ValueError('controlled structural loss')
        return real(path, *args, **kwargs)

    monkeypatch.setattr(analysis, 'create_element_dict', skip)
    reference_read_loss(monkeypatch, reference)
    result = CallsAdapter(str(root), 'uncalled').get_structure()
    assert result['total_defined'] == 0
    assert str(root) not in index._REFERENCE_CACHE
    (warning,) = [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_failed']
    assert warning['count'] == 1, 'one file lost in two passes must remain one missing file'
    assert len(warning['files']) == 1
    assert 'ValueError' in warning['message']


def test_supplied_structural_traversal_loss_prevents_retention_even_if_reference_walk_recovers(
        tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    make_tree(root)
    child = root / 'included_child'
    child.mkdir()
    (child / 'callback.py').write_text('BOUND = kept\n', encoding='utf-8')
    real_collect = index.collect_structures
    real_scandir = os.scandir

    def collect(*args, **kwargs):
        def scandir(path):
            if Path(path) == child:
                raise PermissionError(13, 'controlled structural traversal loss', str(child))
            return real_scandir(path)
        with monkeypatch.context() as context:
            context.setattr(os, 'scandir', scandir)
            return real_collect(*args, **kwargs)

    monkeypatch.setattr(index, 'collect_structures', collect)
    result = CallsAdapter(str(root), 'uncalled').get_structure()
    assert names(result) == {'genuinely_dead'}
    assert any(w.get('type') == 'analysis_incomplete' for w in result['meta']['warnings'])
    assert str(root) not in index._REFERENCE_CACHE


def test_cli_text_discloses_reference_only_read_loss_once_and_preserves_exit(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    reference = make_tree(root)
    reference_read_loss(monkeypatch, reference)
    result = _run_reveal_direct(f'calls://{root.as_posix()}?uncalled')
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert combined.count('1 file(s) could not be analyzed completely (PermissionError)') == 1
    assert 'confidence above' not in combined
    assert 'Zero callers found is not proof of dead code.' in combined


def test_clean_warm_reference_reuse_and_single_structural_collection(tmp_path, monkeypatch):
    root = tmp_path / 'clean'
    make_tree(root)
    first = index._python_referenced_names(root)
    real_read = Path.read_text
    reads = []

    def read(path, *args, **kwargs):
        reads.append(path)
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read)
    assert index._python_referenced_names(root) is first
    assert not reads
    real_collect = index.collect_structures
    collections = []

    def collect(*args, **kwargs):
        collections.append(args)
        return real_collect(*args, **kwargs)

    monkeypatch.setattr(index, 'collect_structures', collect)
    assert names(CallsAdapter(str(root), 'uncalled').get_structure()) == {'genuinely_dead'}
    assert len(collections) == 1


@pytest.mark.parametrize('unknown_directory', [False, True])
def test_reference_only_discovery_loss_preserves_attribution_and_recovers(
        tmp_path, monkeypatch, unknown_directory):
    root = tmp_path / 'affected'
    reference = make_tree(root)
    child = root / 'included_child'
    child.mkdir()
    reference.rename(child / reference.name)
    original_pass = index._python_referenced_names
    original_scandir = os.scandir
    active = []

    def analyze(*args, **kwargs):
        active.append(True)
        try:
            return original_pass(*args, **kwargs)
        finally:
            active.pop()

    def scandir(path):
        if active and Path(path) == child:
            if unknown_directory:
                raise PermissionError('controlled unknown directory')
            raise PermissionError(13, 'controlled reference-only discovery loss', str(child))
        return original_scandir(path)

    with monkeypatch.context() as context:
        context.setattr(index, '_python_referenced_names', analyze)
        context.setattr(os, 'scandir', scandir)
        result = CallsAdapter(str(root), 'uncalled').get_structure()
        assert names(result) == {'kept', 'genuinely_dead'}
        assert str(root) not in index._REFERENCE_CACHE
        (warning,) = [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_incomplete']
        assert warning['count'] == (0 if unknown_directory else 1)
        assert warning.get('unknown_directory_events', 0) == int(unknown_directory)
        assert warning['directories'] == ([] if unknown_directory else ['included_child'])
        assert 'PermissionError' in warning['message']
        assert 'confidence' not in result['meta']
    assert names(CallsAdapter(str(root), 'uncalled').get_structure()) == {'genuinely_dead'}


def test_excluded_reference_is_policy_and_scope_change_rebuilds_cleanly(tmp_path):
    from reveal.utils.exclusions import exclusion_scope

    root = tmp_path / 'clean'
    make_tree(root)
    with exclusion_scope(root, ['references.py']):
        result = CallsAdapter(str(root), 'uncalled').get_structure()
        assert names(result) == {'kept', 'genuinely_dead'}
        assert not [w for w in result['meta']['warnings'] if w.get('type') in ('analysis_failed', 'analysis_incomplete')]
        assert 'confidence' in result['meta']
        assert str(root) in index._REFERENCE_CACHE
    assert names(CallsAdapter(str(root), 'uncalled').get_structure()) == {'genuinely_dead'}


def test_existing_unsafe_parent_policy_is_not_required_loss(tmp_path, monkeypatch):
    root = tmp_path / 'clean'
    make_tree(root)
    monkeypatch.setattr(index, 'is_unsafe_scan_root', lambda path: path == root)
    found = index._python_referenced_names(root)
    assert found == set()
    assert index._python_referenced_names(root) is found
    assert str(root) in index._REFERENCE_CACHE
