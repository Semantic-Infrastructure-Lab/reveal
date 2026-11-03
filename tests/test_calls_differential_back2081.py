"""calls:// answers the same cold, warm and after an edit, cache on and off (BACK-2081, step 5).

The callers and callees views read every file's structure (its functions and their calls) from the
``structure`` disk namespace and import aliases from ``python_imports``; a stale entry is a wrong
call graph (a removed call still reported as a caller). Every view runs as separate processes
through the public path, as in ``test_imports_differential_back2081.py``:

* cache off: the reference, run twice to prove it is deterministic (the control for every compare);
* cache on, cold then warm: both equal the reference, and the warm run visibly rewrites no cache
  file (this does not establish a cache-hit count);
* after each edit (a call added, a call removed, a file added, a file deleted): the cache-on answer
  equals a fresh cache-off answer, and the edit really changed the answer (the positive control).

A long-lived library host (``reveal.api.query``, one host request per call) adds the validated
in-memory indexes (``_INDEX_CACHE``, ``_CALLEE_CACHE``) to the same compare: one process answers
every view after each edit, and each answer must equal a fresh process's. A direct library call
(no host request) after an in-place edit must see the edit too (BACK-2474): outside a request the
index is always built.

An edit that keeps a file's size and mtime is a stat-key design limit and is out of scope here: every
edit below changes the size of the file it rewrites.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cache_differential import assert_complete_answer, cache_entries, cache_env, comparable, run_host, run_reveal

pytestmark = [pytest.mark.disk_cache]

VIEWS = {
    'callers': ['--callers', 'helper'],
    'callers-depth2': ['--callers', 'leaf', '--depth', '2'],
    'callees': ['--callees', 'run'],
    'callees-walk': ['--callees', 'main', '--depth', '3'],
    'rank': ['--rank', 'callers'],
}

# The same requests through a library host, by URI.
HOST_VIEWS = {
    'callers': 'calls://.?callers=helper',
    'callers-depth2': 'calls://.?callers=leaf&depth=2',
    'callees': 'calls://.?callees=run',
    'callees-walk': 'calls://.?callees=main&depth=3',
    'rank': 'calls://.?rank=callers',
}

FILES = {
    'pyproject.toml': '[project]\nname = "proj"\nversion = "0"\n',
    'pkg/__init__.py': '',
    'pkg/a.py': 'from pkg.b import helper\n\n\ndef run():\n    return helper(1)\n\n\ndef other():\n    return run()\n',
    'pkg/b.py': 'def helper(x):\n    return leaf(x)\n\n\ndef leaf(x):\n    return x\n',
    'main.py': 'from pkg.a import run\n\n\ndef main():\n    run()\n',
}

# (name, the view the edit is known to move, relative path, new text or None to delete). The edits
# are a sequence: each starts from the state the previous one left.
EDITS = [
    ('add_call', 'callers', 'main.py',
     'from pkg.a import run\nfrom pkg.b import helper\n\n\ndef main():\n    run()\n    helper(2)\n'),
    ('remove_call', 'callees', 'pkg/a.py', 'def run():\n    return 1\n\n\ndef other():\n    return run()\n'),
    ('add_file', 'callers-depth2', 'pkg/d.py', 'from pkg.b import leaf\n\n\ndef extra():\n    return leaf(3)\n'),
    ('delete_file', 'callers-depth2', 'pkg/d.py', None),
]


def _write_project(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


def _apply(root: Path, rel: str, text) -> None:
    path = root / rel
    if text is None:
        path.unlink()
        return
    before = path.stat().st_size if path.exists() else None
    path.write_text(text, encoding='utf-8')
    assert path.stat().st_size != before, f'{rel}: a same-size edit is the stat-key limit, not this harness'


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    _write_project(root)
    return root


def _answer(root: Path, view, cache_dir: Path, *, cache: bool):
    """One request in its own process, through the public path: (exit code, JSON answer)."""
    answer = run_reveal(['calls', '.', *VIEWS[view], '--format', 'json'], cache_dir,
                        cache=cache, cwd=root, ok_codes=(0,))
    assert_complete_answer(answer[1])
    return answer


@pytest.mark.parametrize('view', sorted(VIEWS))
def test_cold_and_warm_answers_equal_the_cache_off_answer(project, tmp_path, view):
    cache_dir = tmp_path / 'cache'
    reference = _answer(project, view, cache_dir, cache=False)
    assert _answer(project, view, cache_dir, cache=False) == reference, 'cache off is not deterministic'
    assert not cache_entries(cache_dir), 'cache off wrote an entry'
    assert _answer(project, view, cache_dir, cache=True) == reference
    cold = cache_entries(cache_dir)
    assert any('/structure/' in f'/{entry}' for entry in cold), \
        'the cold cache-on run wrote no structure entry; the warm compare proves nothing'
    assert _answer(project, view, cache_dir, cache=True) == reference
    assert cache_entries(cache_dir) == cold, 'the warm run visibly rewrote a cache file'


def test_every_view_after_an_edit_equals_a_fresh_cache_off_answer(project, tmp_path):
    """Keep one edit timeline, reusing the previously verified cache-on map as before."""
    cache_dir = tmp_path / 'cache'
    before = {view: _answer(project, view, cache_dir, cache=True) for view in VIEWS}
    unmoved = []
    stale = []
    for name, moved_view, rel, text in EDITS:
        _apply(project, rel, text)
        after_off = {view: _answer(project, view, cache_dir, cache=False) for view in VIEWS}
        after_on = {view: _answer(project, view, cache_dir, cache=True) for view in VIEWS}
        if after_off[moved_view] == before[moved_view]:
            unmoved.append((name, moved_view))
        stale.extend((name, view) for view in VIEWS if after_on[view] != after_off[view])
        before = after_on
    assert not stale, f'stale views {stale}'
    assert not unmoved, f'unchanged positive-control views {unmoved}'


@pytest.mark.parametrize('disk', [False, True], ids=['disk-off', 'disk-on'])
def test_a_library_host_sees_every_edit_between_requests(project, tmp_path, disk):
    cache_dir = tmp_path / 'cache'
    steps = [[]] + [[(rel, text)] for _name, _view, rel, text in EDITS]
    hosted = run_host(project, HOST_VIEWS, steps, cache_dir, cache=disk)
    # The reference for state k: a fresh process, cache off, over the same root rebuilt to state k.
    fresh = []
    for k in range(len(steps)):
        _write_project(project)
        for _name, _view, rel, text in EDITS[:k]:
            _apply(project, rel, text)
        fresh.append(run_host(project, HOST_VIEWS, [[]], tmp_path / 'off', cache=False)[0])
    _write_project(project)
    assert run_host(project, HOST_VIEWS, [[]], tmp_path / 'off', cache=False)[0] == fresh[0], \
        'a fresh host is not deterministic'
    for k, (name, moved_view, _rel, _text) in enumerate(EDITS, start=1):
        assert fresh[k][moved_view] != fresh[k - 1][moved_view], f'{name} did not change the {moved_view} answer'
    assert hosted[0] == fresh[0]
    stale = [(name, view) for k, (name, _view, _rel, _text) in enumerate(EDITS, start=1)
             for view in HOST_VIEWS if hosted[k][view] != fresh[k][view]]
    assert not stale, f'the host served stale answers {stale}'


# One process asks find_callers, overwrites main.py in place (the root directory's mtime does not
# move), and asks again, inside host requests or as a direct library call with none.
_DIRECT_DRIVER = r'''
import json, sys
from pathlib import Path
from types import SimpleNamespace
from reveal.adapters.calls.index import find_callers
from reveal.utils.request_cache import host_request
hosted = sys.argv[1] == 'host'
def callers():
    if hosted:
        with host_request():
            answer = find_callers('.', 'helper')
    else:
        answer = find_callers('.', 'helper')
    return sorted(c['caller'] for level in answer['levels'] for c in level['callers'])
first = callers()
Path('main.py').write_text(sys.argv[2], encoding='utf-8')
print(json.dumps([first, callers()]))
'''


# BACK-2474: outside a host request the callers index is never read or stored, as callee_source.
@pytest.mark.parametrize('mode', ['host', 'direct'])
def test_a_direct_library_caller_sees_an_in_place_edit(project, tmp_path, mode):
    edited = 'from pkg.a import run\nfrom pkg.b import helper\n\n\ndef main():\n    run()\n    helper(2)\n'
    done = subprocess.run([sys.executable, '-c', _DIRECT_DRIVER, mode, edited], cwd=project, capture_output=True,
                          text=True, encoding='utf-8', env=cache_env(tmp_path / 'cache', cache=False), timeout=120)
    assert done.returncode == 0, done.stderr
    first, second = json.loads(done.stdout)
    assert first == ['run']
    assert second == ['main', 'run'], f'{mode}: the edit added main as a caller; got {second}'


@pytest.mark.parametrize('exit_code,payload', [
    (3, {'callers': []}),
    (0, {'error': 'analysis failed'}),
    (0, {'applicable': False}),
    (0, {'meta': {'errors': [{'message': 'required file unreadable'}]}}),
    (0, {'meta': {'warnings': [{'type': 'analysis_incomplete', 'count': 1}]}}),
    (0, {'meta': {'warnings': [{'type': 'parse_recovered', 'count': 1}]}}),
])
def test_a_failed_or_partial_reference_cannot_qualify_equality(project, tmp_path, monkeypatch,
                                                              exit_code, payload):
    # Two identical failed answers would satisfy equality; the clean fixture must first succeed.
    done = SimpleNamespace(returncode=exit_code, stdout=json.dumps(payload), stderr='')
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: done)
    with pytest.raises(AssertionError):
        _answer(project, 'callers', tmp_path / 'cache', cache=False)


def test_normalization_preserves_semantic_diagnostics():
    answer = {'elapsed_ms': 10, 'meta': {'errors': [{'message': 'missing input'}],
              'warnings': [{'type': 'analysis_incomplete', 'count': 2}]}}
    assert comparable(answer) == {'meta': {'errors': [{'message': 'missing input'}],
           'warnings': [{'type': 'analysis_incomplete', 'count': 2}]}}
