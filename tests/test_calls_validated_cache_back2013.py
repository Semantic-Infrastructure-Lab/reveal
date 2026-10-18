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
