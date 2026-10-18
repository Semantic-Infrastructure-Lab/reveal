"""Calls must follow deep edits across serialized host requests without cache resets."""

import json
import os
import time
from pathlib import Path

import pytest

from reveal.adapters.calls import index
from reveal.mcp_server import reveal_query
from reveal.utils import request_cache


def write(path, source, *, age=60):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    timestamp = time.time_ns() - age * 1_000_000_000
    os.utime(path, ns=(timestamp, timestamp))


def query(root, selector):
    return json.loads(reveal_query(f'calls://{root.as_posix()}?{selector}', provenance=True))


def callers(result):
    return {record['caller'] for level in result['levels'] for record in level['callers']}


def uncalled(result):
    return {entry['name'] for entry in result['entries']}


@pytest.mark.parametrize('change', ['overwrite', 'add', 'delete'])
def test_decorated_host_callers_follow_deep_edit_and_membership(tmp_path, change):
    root = tmp_path / 'affected'
    deep = root / 'included' / 'deep'
    source = deep / 'caller.py'
    write(source, 'def original():\n    return target()\n')
    sibling = tmp_path / 'sibling'
    write(sibling / 'stable.py', 'def stable():\n    return target()\n')
    baseline = reveal_query(f'calls://{sibling.as_posix()}?target=target')
    assert callers(query(root, 'target=target')) == {'original'}
    cheap_key = index._dir_cache_key(root)
    if change == 'overwrite':
        write(source, 'def replacement():\n    return target()\n', age=30)
        expected = {'replacement'}
    elif change == 'add':
        write(deep / 'added.py', 'def added():\n    return target()\n', age=30)
        expected = {'original', 'added'}
    else:
        source.unlink()
        expected = set()
    assert index._dir_cache_key(root) == cheap_key
    assert callers(query(root, 'target=target')) == expected
    assert reveal_query(f'calls://{sibling.as_posix()}?target=target') == baseline


@pytest.mark.parametrize('change', ['overwrite', 'add', 'delete'])
def test_decorated_host_reference_derived_uncalled_follows_deep_changes(tmp_path, change):
    root = tmp_path / 'affected'
    write(root / 'definitions.py', 'def kept():\n    return 1\n\ndef dead():\n    return 2\n')
    reference = root / 'included' / 'deep' / 'references.py'
    write(reference, 'BOUND = 1\n' if change == 'add' else 'BOUND = kept\n')
    expected_initial = {'kept', 'dead'} if change == 'add' else {'dead'}
    assert uncalled(query(root, 'uncalled')) == expected_initial
    cheap_key = index._dir_cache_key(root)
    if change == 'overwrite':
        write(reference, 'BOUND = dead\n', age=30)
        expected = {'kept'}
    elif change == 'add':
        write(reference.parent / 'added.py', 'BOUND = kept\n', age=30)
        expected = {'dead'}
    else:
        reference.unlink()
        expected = {'kept', 'dead'}
    assert index._dir_cache_key(root) == cheap_key
    assert uncalled(query(root, 'uncalled')) == expected


def test_existing_path_key_validated_owner_still_keeps_then_evicts_raw_path(tmp_path, monkeypatch):
    source = tmp_path / 'source.py'
    write(source, 'value = 1\n')
    cache = {}
    evicted = []
    monkeypatch.setattr(request_cache, '_VALIDATED', {})
    monkeypatch.setattr(request_cache, '_STAMPS', {})
    request_cache.register_validated_cache('existing.path.owner', cache, lambda root: evicted.append(root) or cache.pop(root, None))
    started = request_cache.request_started_ns()
    cached = object()
    cache[tmp_path] = cached
    request_cache.seal_request_caches(started)
    request_cache.reset_request_caches()
    assert cache[tmp_path] is cached
    assert not evicted
    write(source, 'value = 2\n', age=30)
    request_cache.reset_request_caches()
    assert not cache
    assert evicted == [tmp_path]
    assert isinstance(evicted[0], Path)


def test_unchanged_host_requests_keep_both_calls_lru_objects(tmp_path):
    write(tmp_path / 'definitions.py', 'def kept():\n    return 1\n\ndef dead():\n    return 2\n')
    write(tmp_path / 'references.py', 'BOUND = kept\n')
    before = query(tmp_path, 'uncalled')
    callers_object = index._INDEX_CACHE[str(tmp_path)][1]
    references_object = index._REFERENCE_CACHE[str(tmp_path)][1]
    after = query(tmp_path, 'uncalled')
    assert before['entries'] == after['entries']
    assert before['meta'] == after['meta']
    assert index._INDEX_CACHE[str(tmp_path)][1] is callers_object
    assert index._REFERENCE_CACHE[str(tmp_path)][1] is references_object


@pytest.fixture
def isolated_owner(monkeypatch):
    monkeypatch.setattr(request_cache, '_RESETTERS', {})
    monkeypatch.setattr(request_cache, '_VALIDATED', {})
    monkeypatch.setattr(request_cache, '_STAMPS', {})
    return request_cache


@pytest.mark.parametrize('failed', [False, True])
@pytest.mark.parametrize('reverse', [False, True])
def test_raw_string_and_path_owners_share_one_stamp_including_none(tmp_path, monkeypatch, isolated_owner, failed, reverse):
    root = tmp_path / 'root'
    if not failed:
        write(root / 'source.py', 'value = 1\n')
    caches = {'string':{str(root):object()}, 'path':{root:object()}}
    evicted = []
    for name in (('path','string') if reverse else ('string','path')):
        def evict(raw, name=name):
            evicted.append((name, raw))
            caches[name].pop(raw, None)
        request_cache.register_validated_cache(name, caches[name], evict)
    real = request_cache._tree_stamp
    stamps = []

    def stamp(path, started_ns=None):
        assert isinstance(path, Path)
        stamps.append((path, started_ns))
        return real(path, started_ns)

    monkeypatch.setattr(request_cache, '_tree_stamp', stamp)
    started = request_cache.request_started_ns()
    request_cache.seal_request_caches(started)
    assert stamps == [(root, started)]
    if not failed:
        assert set(request_cache._STAMPS) == {('string',str(root)), ('path',root)}
    else:
        assert request_cache._STAMPS == {}
    stamps.clear()
    request_cache.reset_request_caches()
    assert stamps == [(root, None)]
    if not failed:
        assert evicted == []
        write(root / 'source.py', 'value = 2\n', age=30)
        request_cache.reset_request_caches()
    assert {name for name,_ in evicted} == {'string','path'}
    assert type(next(raw for name,raw in evicted if name=='string')) is str
    assert isinstance(next(raw for name,raw in evicted if name=='path'), Path)
    assert caches == {'string':{}, 'path':{}}


@pytest.mark.parametrize('reverse', [False, True])
def test_actual_calls_evictions_do_not_remove_other_registration_or_orphan_stamp(tmp_path, monkeypatch, reverse):
    write(tmp_path / 'source.py', 'def visible():\n    return 1\n')
    query(tmp_path, 'uncalled')
    callers_before = index._INDEX_CACHE[str(tmp_path)][1]
    references_before = index._REFERENCE_CACHE[str(tmp_path)][1]
    names = [name for name,(cache,_) in request_cache._VALIDATED.items()
             if cache is index._INDEX_CACHE or cache is index._REFERENCE_CACHE]
    assert len(names) == 2
    reference_name = next(name for name in names if request_cache._VALIDATED[name][0] is index._REFERENCE_CACHE)
    request_cache._STAMPS.pop((reference_name,str(tmp_path)))
    if reverse:
        names.reverse()
    monkeypatch.setattr(request_cache, '_VALIDATED', {name:request_cache._VALIDATED[name] for name in names})
    query(tmp_path, 'uncalled')
    assert index._INDEX_CACHE[str(tmp_path)][1] is callers_before
    assert index._REFERENCE_CACHE[str(tmp_path)][1] is not references_before
    assert (reference_name,str(tmp_path)) in request_cache._STAMPS


def test_externally_built_calls_entries_are_rebuilt_before_host_reuse(tmp_path):
    from reveal.adapters.calls import CallsAdapter

    write(tmp_path / 'source.py', 'def visible():\n    return 1\n')
    result = CallsAdapter(str(tmp_path), 'uncalled').get_structure()
    external_callers = index._INDEX_CACHE[str(tmp_path)][1]
    external_references = index._REFERENCE_CACHE[str(tmp_path)][1]
    actual = query(tmp_path, 'uncalled')
    assert actual['entries'] == result['entries']
    assert index._INDEX_CACHE[str(tmp_path)][1] is not external_callers
    assert index._REFERENCE_CACHE[str(tmp_path)][1] is not external_references


def test_midrequest_changed_entry_is_not_sealed_as_trusted(tmp_path, isolated_owner):
    cache = {}
    request_cache.register_validated_cache('owner', cache, lambda raw: cache.pop(raw, None))
    started = request_cache.request_started_ns()
    write(tmp_path / 'source.py', 'value = 1\n', age=-60)
    cache[str(tmp_path)] = object()
    request_cache.seal_request_caches(started)
    assert not request_cache._STAMPS
    request_cache.reset_request_caches()
    assert not cache


def test_same_request_reuse_and_one_uncalled_structural_collection(tmp_path, monkeypatch):
    write(tmp_path / 'source.py', 'def visible():\n    return 1\n')
    real = index.collect_structures
    collected = []

    def collect(*args, **kwargs):
        collected.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(index, 'collect_structures', collect)
    request_cache.reset_request_caches()
    started = request_cache.request_started_ns()
    try:
        result = index.find_uncalled(str(tmp_path))
        assert {entry['name'] for entry in result['entries']} == {'visible'}
        cached = index._INDEX_CACHE[str(tmp_path)][1]
        assert index.build_callers_index(str(tmp_path)) is cached
        assert len(collected) == 1
    finally:
        request_cache.seal_request_caches(started)


def test_direct_callers_and_reference_lrus_keep_eight_entry_limit(tmp_path):
    roots = [tmp_path / f'root_{number}' for number in range(9)]
    for root in roots:
        write(root / 'source.py', 'def visible():\n    return target()\n')
        index.build_callers_index(str(root))
        index._python_referenced_names(root)
    assert list(index._INDEX_CACHE) == [str(root) for root in roots[1:]]
    assert list(index._REFERENCE_CACHE) == [str(root) for root in roots[1:]]
