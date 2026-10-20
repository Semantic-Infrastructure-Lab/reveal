"""Distinct host consumers and changed-snapshot joins for validated Calls LRUs."""

import json
import os
import time
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.calls import index
from reveal.mcp_server import reveal_query
from reveal.utils import request_cache

pytestmark = pytest.mark.component


def write(path, source, age=60):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    timestamp = time.time_ns() - age * 1_000_000_000
    os.utime(path, ns=(timestamp, timestamp))


def query(path, selector):
    return json.loads(reveal_query(f'calls://{path}?{selector}', provenance=True))


def request(*args):
    request_cache.reset_request_caches()
    started = request_cache.request_started_ns()
    try:
        return run(*args)
    finally:
        request_cache.seal_request_caches(started)


def test_relative_and_absolute_ranking_consumers_keep_spelling_and_follow_edit(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    source = root / 'included' / 'deep' / 'caller.py'
    write(source, 'def caller():\n    return target_old()\n')
    monkeypatch.chdir(tmp_path)
    assert {r['name'] for r in query('project', 'rank=callers&top=0')['entries']} == {'target_old'}
    assert {r['name'] for r in query(root.as_posix(), 'rank=callers&top=0')['entries']} == {'target_old'}
    assert set(index._INDEX_CACHE) == {'project', str(root)}
    relative = index._INDEX_CACHE['project'][1]
    absolute = index._INDEX_CACHE[str(root)][1]
    query('project', 'rank=callers&top=0')
    assert index._INDEX_CACHE['project'][1] is relative
    assert index._INDEX_CACHE[str(root)][1] is absolute
    write(source, 'def caller():\n    return target_new()\n', age=30)
    assert {r['name'] for r in query('project', 'rank=callers&top=0')['entries']} == {'target_new'}
    assert str(root) not in index._INDEX_CACHE
    assert {r['name'] for r in query(root.as_posix(), 'rank=callers&top=0')['entries']} == {'target_new'}
    assert set(index._INDEX_CACHE) == {'project', str(root)}


def test_host_projection_keeps_known_loss_and_does_not_retain_either_lru(tmp_path, monkeypatch):
    root = tmp_path / 'project'; child = root / 'included_child'
    write(root / 'visible.py', 'def visible():\n    return 1\n')
    write(child / 'hidden.py', 'def hidden():\n    return 2\n')
    sibling = tmp_path / 'sibling'
    write(sibling / 'clean.py', 'def clean():\n    return 3\n')
    clean_text = reveal_query(f'calls://{root}?uncalled')
    sibling_text = reveal_query(f'calls://{sibling}?uncalled')
    sibling_index = index._INDEX_CACHE[str(sibling)][1]
    sibling_refs = index._REFERENCE_CACHE[str(sibling)][1]
    real = os.scandir

    def scandir(path):
        if Path(path) == child:
            raise PermissionError(13, 'independent Calls request loss', str(child))
        return real(path)

    with monkeypatch.context() as context:
        context.setattr(os, 'scandir', scandir)
        result = request(f'calls://{root}?uncalled', '--format', 'json',
                         '--fields', 'entries,total_uncalled', '--max-items', '0')
        assert result.returncode == 3, result.stderr  # D6 since calls is declared (BACK-2066): known loss is incomplete analysis, 3
        payload = json.loads(result.stdout)
        assert payload['entries'] == [] and payload['total_uncalled'] == 1
        warnings = [w for w in payload['meta']['warnings'] if w.get('type') == 'analysis_incomplete']
        assert len(warnings) == 1 and warnings[0]['count'] == 1
        assert str(root) not in index._INDEX_CACHE
        assert str(root) not in index._REFERENCE_CACHE
        assert reveal_query(f'calls://{sibling}?uncalled') == sibling_text
        assert index._INDEX_CACHE[str(sibling)][1] is sibling_index
        assert index._REFERENCE_CACHE[str(sibling)][1] is sibling_refs
    assert reveal_query(f'calls://{root}?uncalled') == clean_text


@pytest.mark.parametrize('reverse', [False, True])
def test_actual_mixed_trust_reset_and_changed_seal_remain_registration_local(tmp_path, monkeypatch, reverse):
    write(tmp_path / 'defs.py', 'def kept():\n    return 1\n\ndef dead():\n    return 2\n')
    source = tmp_path / 'included' / 'deep' / 'refs.py'
    write(source, 'BOUND = kept\n')
    query(tmp_path, 'uncalled')
    before_index = index._INDEX_CACHE[str(tmp_path)][1]
    names = [name for name, (cache, _) in request_cache._VALIDATED.items()
             if cache is index._INDEX_CACHE or cache is index._REFERENCE_CACHE]
    references = next(name for name in names if request_cache._VALIDATED[name][0] is index._REFERENCE_CACHE)
    callers = next(name for name in names if name != references)
    original_stamp = request_cache._STAMPS[(callers, str(tmp_path))]
    request_cache._STAMPS.pop((references, str(tmp_path)))
    if reverse:
        names.reverse()
    monkeypatch.setattr(request_cache, '_VALIDATED', {name: request_cache._VALIDATED[name] for name in names})
    request_cache.reset_request_caches()
    assert index._INDEX_CACHE[str(tmp_path)][1] is before_index
    assert str(tmp_path) not in index._REFERENCE_CACHE
    started = request_cache.request_started_ns()
    source.write_text('BOUND = dead\n', encoding='utf-8')
    future = started + 60_000_000_000
    os.utime(source, ns=(future, future))
    result = index.find_uncalled(str(tmp_path))
    assert {r['name'] for r in result['entries']} == {'kept'}
    request_cache.seal_request_caches(started)
    assert request_cache._STAMPS[(callers, str(tmp_path))] == original_stamp
    assert (references, str(tmp_path)) not in request_cache._STAMPS
    # A subsequent request sees the changed tree and safely rebuilds the old callers artifact.
    aged = time.time_ns() - 30_000_000_000
    os.utime(source, ns=(aged, aged))
    assert {r['name'] for r in query(tmp_path, 'uncalled')['entries']} == {'kept'}
    assert index._INDEX_CACHE[str(tmp_path)][1] is not before_index
    assert (references, str(tmp_path)) in request_cache._STAMPS
