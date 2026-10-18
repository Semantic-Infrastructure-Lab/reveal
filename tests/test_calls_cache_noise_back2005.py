"""Known traversal loss must not survive permission recovery in the callers cache."""

import os
from pathlib import Path

import pytest

from reveal.adapters.ast.analysis import StructureList
from reveal.adapters.calls import index as calls_index


@pytest.fixture(params=['included_child', 'build', 'dist'])
def tree(tmp_path, request):
    child = tmp_path / request.param
    child.mkdir()
    (tmp_path / 'visible.py').write_text(
        'def visible():\n    return target()\n', encoding='utf-8')
    (child / 'hidden.py').write_text(
        'def hidden():\n    return target()\n', encoding='utf-8')
    return tmp_path, child


def deny(context, child):
    real = os.scandir

    def scandir(path):
        if Path(path) == child:
            raise PermissionError(13, 'controlled included child enumeration failure', str(child))
        return real(path)

    context.setattr(os, 'scandir', scandir)


@pytest.mark.parametrize('prior_entry', [False, True])
def test_known_traversal_loss_is_returned_but_not_cached(tree, monkeypatch, prior_entry):
    root, child = tree
    if prior_entry:
        calls_index._INDEX_CACHE[str(root)] = (('older-key',), calls_index.CallersIndex())
    with monkeypatch.context() as context:
        deny(context, child)
        partial = calls_index.build_callers_index(str(root))
    assert [record['caller'] for record in partial['target']] == ['visible']
    assert str(root) not in calls_index._INDEX_CACHE


def test_permission_recovery_rebuilds_without_clearing_cache(tree, monkeypatch):
    root, child = tree
    clean_key = calls_index._dir_cache_key(root)
    with monkeypatch.context() as context:
        deny(context, child)
        assert calls_index._dir_cache_key(root) == clean_key
        partial = calls_index.build_callers_index(str(root))
    assert [record['caller'] for record in partial['target']] == ['visible']
    recovered = calls_index.build_callers_index(str(root))
    assert {record['caller'] for record in recovered['target']} == {'visible', 'hidden'}
    assert calls_index.build_callers_index(str(root)) is recovered


def test_supplied_traversal_loss_evicts_stale_entry(tree):
    root, child = tree
    supplied = StructureList([{'file': str(root / 'visible.py'), 'elements': [
        {'category': 'functions', 'name': 'visible', 'line': 1, 'calls': ['target']},
    ]}])
    supplied.traversal_failures.append((child.as_posix(), 'PermissionError: controlled loss'))
    calls_index._INDEX_CACHE[str(root)] = (('older-key',), calls_index.CallersIndex())
    partial = calls_index.build_callers_index(str(root), supplied)
    assert [record['caller'] for record in partial['target']] == ['visible']
    assert str(root) not in calls_index._INDEX_CACHE


def test_legacy_supplied_collection_without_traversal_attribute_is_cached(tree):
    class LegacyStructures(list):
        skipped = []

    root, _ = tree
    supplied = LegacyStructures([{'file': str(root / 'visible.py'), 'elements': [
        {'category': 'functions', 'name': 'visible', 'line': 1, 'calls': ['target']},
    ]}])
    clean = calls_index.build_callers_index(str(root), supplied)
    assert [record['caller'] for record in clean['target']] == ['visible']
    assert calls_index.build_callers_index(str(root), supplied) is clean
