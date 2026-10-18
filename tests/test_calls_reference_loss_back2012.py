"""Incomplete Python reference populations must not become reusable dead-code evidence."""

import os
from pathlib import Path

import pytest

from reveal.adapters.ast.analysis import collect_structures
from reveal.adapters.calls import CallsAdapter
from reveal.adapters.calls import index
from reveal.adapters.calls.adapter import CallsRenderer


def make_tree(root, *, survivors):
    root.mkdir()
    child = root / 'included_child'
    child.mkdir()
    definitions = 'def missing():\n    return 1\n\ndef dead():\n    return 2\n'
    if survivors:
        definitions += '\ndef survivor():\n    return 3\n'
        (root / 'visible_refs.py').write_text('BOUND = survivor\n', encoding='utf-8')
    (root / 'definitions.py').write_text(definitions, encoding='utf-8')
    hidden = child / 'hidden_refs.py'
    hidden.write_text('BOUND = missing\n', encoding='utf-8')
    return child, hidden


def names(result):
    return {entry['name'] for entry in result['entries']}


def reference_phase(monkeypatch):
    phase = {'active': False}
    real = index._python_referenced_names

    def run(*args, **kwargs):
        phase['active'] = True
        try:
            return real(*args, **kwargs)
        finally:
            phase['active'] = False

    monkeypatch.setattr(index, '_python_referenced_names', run)
    return phase


@pytest.mark.parametrize('survivors', [False, True])
@pytest.mark.parametrize('loss', ['read', 'directory'])
def test_reference_only_loss_recovers_without_manual_eviction(tmp_path, monkeypatch, capsys, survivors, loss):
    root, sibling = tmp_path / 'affected', tmp_path / 'sibling'
    child, hidden = make_tree(root, survivors=survivors)
    make_tree(sibling, survivors=True)
    sibling_result = CallsAdapter(str(sibling), 'uncalled').get_structure()
    sibling_refs = index._python_referenced_names(sibling)
    structural = collect_structures(str(root))
    assert not structural.skipped and not structural.traversal_failures
    phase = reference_phase(monkeypatch)
    attempts = []
    real_read, real_scandir = Path.read_text, os.scandir

    def read(path, *args, **kwargs):
        if phase['active'] and path == hidden:
            attempts.append(path)
            raise PermissionError(13, 'controlled reference read loss', str(hidden))
        return real_read(path, *args, **kwargs)

    def scandir(directory):
        if phase['active'] and Path(directory) == child:
            attempts.append(child)
            raise PermissionError(13, 'controlled reference directory loss', str(child))
        return real_scandir(directory)

    with monkeypatch.context() as context:
        if loss == 'read':
            context.setattr(Path, 'read_text', read)
        else:
            context.setattr(os, 'scandir', scandir)
        result = CallsAdapter(str(root), 'uncalled').get_structure()
        assert attempts
        assert names(result) == {'missing', 'dead'}
        assert CallsAdapter(str(sibling), 'uncalled').get_structure() == sibling_result
        assert index._python_referenced_names(sibling) is sibling_refs
        # Check recovery before retention/disclosure assertions: this reproduces the false
        # uncalled answer persisting even after the filesystem has recovered.
    recovered = CallsAdapter(str(root), 'uncalled').get_structure()
    assert names(recovered) == {'dead'}
    assert str(root) not in index._REFERENCE_CACHE or 'missing' in index._REFERENCE_CACHE[str(root)][1]
    warnings = [w for w in result['meta']['warnings']
                if w.get('type') in ('analysis_failed', 'analysis_incomplete')]
    (warning,) = warnings
    assert warning['type'] == ('analysis_failed' if loss == 'read' else 'analysis_incomplete')
    assert 'PermissionError' in warning['message']
    assert warning.get('files', [''])[0].endswith('hidden_refs.py') if loss == 'read' else warning['directories'] == ['included_child']
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'tree_sitter_partial'
    CallsRenderer.render_structure(result)
    output = capsys.readouterr()
    assert output.out.count(warning['message']) == 1


@pytest.mark.parametrize('survivors', [False, True])
@pytest.mark.parametrize('loss', ['read', 'directory'])
def test_direct_legacy_helper_declines_incomplete_reference_cache(tmp_path, monkeypatch, survivors, loss):
    root = tmp_path / 'affected'
    child, hidden = make_tree(root, survivors=survivors)
    real_read, real_scandir = Path.read_text, os.scandir

    def read(path, *args, **kwargs):
        if path == hidden:
            raise PermissionError(13, 'controlled direct read loss', str(hidden))
        return real_read(path, *args, **kwargs)

    def scandir(directory):
        if Path(directory) == child:
            raise PermissionError(13, 'controlled direct directory loss', str(child))
        return real_scandir(directory)

    with monkeypatch.context() as context:
        if loss == 'read':
            context.setattr(Path, 'read_text', read)
        else:
            context.setattr(os, 'scandir', scandir)
        partial = index._python_referenced_names(root)
        assert partial == ({'survivor'} if survivors else set())
        assert str(root) not in index._REFERENCE_CACHE
    assert 'missing' in index._python_referenced_names(root)


def test_actual_syntax_error_is_disclosed_and_not_retained(tmp_path):
    (tmp_path / 'definitions.py').write_text('def missing():\n    return 1\n', encoding='utf-8')
    broken = tmp_path / 'broken.py'
    broken.write_text('BOUND = missing\nbroken = (\n', encoding='utf-8')
    structures = collect_structures(str(tmp_path))
    assert not structures.skipped
    result = CallsAdapter(str(tmp_path), 'uncalled').get_structure()
    assert names(result) == {'missing'}
    assert str(tmp_path) not in index._REFERENCE_CACHE
    (warning,) = [w for w in result['meta']['warnings'] if w.get('type') == 'analysis_failed']
    assert 'SyntaxError' in warning['message']
    assert warning['files'][0].endswith('broken.py')


def test_supplied_structural_directory_loss_supersedes_warm_reference_hit(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    child, hidden = make_tree(root, survivors=True)
    warm = index._python_referenced_names(root)
    assert 'missing' in warm
    phase = reference_phase(monkeypatch)
    real_scandir = os.scandir

    def scandir(directory):
        if not phase['active'] and Path(directory) == child:
            raise PermissionError(13, 'controlled structural directory loss', str(child))
        return real_scandir(directory)

    monkeypatch.setattr(os, 'scandir', scandir)
    result = CallsAdapter(str(root), 'uncalled').get_structure()
    assert names(result) == {'dead'}
    assert str(root) not in index._REFERENCE_CACHE
    assert any(w.get('type') == 'analysis_incomplete' for w in result['meta']['warnings'])


@pytest.mark.parametrize('empty', [False, True])
def test_clean_reference_cache_keeps_set_shape_and_warm_identity(tmp_path, monkeypatch, empty):
    if not empty:
        make_tree(tmp_path / 'source', survivors=True)
        root = tmp_path / 'source'
    else:
        root = tmp_path
    warm = index._python_referenced_names(root)
    assert isinstance(warm, set)
    assert bool(warm) is not empty

    def no_reads(*args, **kwargs):
        pytest.fail('a matching healthy warm hit must not read source again')

    monkeypatch.setattr(Path, 'read_text', no_reads)
    assert index._python_referenced_names(root) is warm
