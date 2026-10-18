"""A supplied real collection with known loss must supersede a warm callers hit."""

import os
from pathlib import Path

import pytest

from reveal.adapters.ast.analysis import collect_structures
from reveal.adapters.calls import index as calls_index


def make_tree(root):
    root.mkdir()
    child = root / 'included_child'
    child.mkdir()
    (root / 'visible.py').write_text('def visible():\n    return target()\n', encoding='utf-8')
    (child / 'hidden.py').write_text('def hidden():\n    return target()\n', encoding='utf-8')
    return child


def callers(index):
    return {record['caller'] for record in index['target']}


@pytest.mark.parametrize('file_path', [False, True])
def test_real_supplied_loss_supersedes_matching_warm_hit(tmp_path, monkeypatch, file_path):
    root = tmp_path / 'affected'
    child = make_tree(root)
    sibling = tmp_path / 'sibling'
    make_tree(sibling)
    path = str(root / 'visible.py' if file_path else root)
    warm = calls_index.build_callers_index(path)
    sibling_warm = calls_index.build_callers_index(str(sibling))
    warm_key = calls_index._INDEX_CACHE[str(root)][0]
    assert callers(warm) == {'visible', 'hidden'}
    assert calls_index.build_callers_index(path) is warm
    real_scandir = os.scandir

    def scandir(directory):
        if Path(directory) == child:
            raise PermissionError(13, 'controlled included child loss', str(child))
        return real_scandir(directory)

    with monkeypatch.context() as context:
        context.setattr(os, 'scandir', scandir)
        supplied = collect_structures(str(root))
        assert len(supplied.traversal_failures) == 1
        failed_directory, cause = supplied.traversal_failures[0]
        assert failed_directory == str(child)
        assert cause.startswith('PermissionError:')
        assert 'controlled included child loss' in cause
        assert calls_index._INDEX_CACHE[str(root)][0] == warm_key
        assert calls_index._dir_cache_key(root) == warm_key[0]
        partial = calls_index.build_callers_index(path, supplied)
        assert callers(partial) == {'visible'}
        assert partial is not warm
        assert str(root) not in calls_index._INDEX_CACHE
        assert callers(calls_index.build_callers_index(path, supplied)) == {'visible'}
        assert str(root) not in calls_index._INDEX_CACHE
        assert calls_index.build_callers_index(str(sibling)) is sibling_warm
        assert callers(sibling_warm) == {'visible', 'hidden'}

    recovered = calls_index.build_callers_index(path)
    assert callers(recovered) == {'visible', 'hidden'}
    assert calls_index.build_callers_index(path) is recovered


@pytest.mark.parametrize('legacy', [False, True])
def test_healthy_supplied_collection_keeps_matching_warm_identity(tmp_path, monkeypatch, legacy):
    root = tmp_path / 'healthy'
    make_tree(root)
    supplied = collect_structures(str(root))
    if legacy:
        class LegacyStructures(list):
            skipped = []
        supplied = LegacyStructures(supplied)
    warm = calls_index.build_callers_index(str(root), supplied)

    def unexpected_collection(*args, **kwargs):
        pytest.fail('a supplied collection must not trigger another collection')

    monkeypatch.setattr(calls_index, 'collect_structures', unexpected_collection)
    assert calls_index.build_callers_index(str(root), supplied) is warm
    assert callers(warm) == {'visible', 'hidden'}
