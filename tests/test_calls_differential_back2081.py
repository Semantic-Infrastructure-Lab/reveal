"""calls:// answers the same cold, warm and after an edit, cache on and off (BACK-2081, step 5).

The callers and callees views read every file's structure (its functions and their calls) from the
``structure`` disk namespace and import aliases from ``python_imports``; a stale entry is a wrong
call graph (a removed call still reported as a caller). Every view runs as separate processes
through the public path, as in ``test_imports_differential_back2081.py``:

* cache off: the reference, run twice to prove it is deterministic (the control for every compare);
* cache on, cold then warm: both equal the reference, and the warm run stores nothing (it read back
  every entry it needed);
* after each edit (a call added, a call removed, a file added, a file deleted): the cache-on answer
  equals a fresh cache-off answer, and the edit really changed the answer (the positive control).

A long-lived library host (``reveal.api.query``, one host request per call) adds the validated
in-memory indexes (``_INDEX_CACHE``, ``_CALLEE_CACHE``) to the same compare: one process answers
every view after each edit, and each answer must equal a fresh process's.

An edit that keeps a file's size and mtime is a stat-key design limit and is out of scope here: every
edit below changes the size of the file it rewrites.
"""
import shutil
from pathlib import Path

import pytest

from cache_differential import cache_entries, run_host, run_reveal

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
    return run_reveal(['calls', '.', *VIEWS[view], '--format', 'json'], cache_dir, cache=cache, cwd=root)


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
    assert cache_entries(cache_dir) == cold, 'the warm run re-stored an entry: it missed'


@pytest.mark.parametrize('name,moved_view,rel,text', EDITS, ids=[e[0] for e in EDITS])
def test_every_view_after_an_edit_equals_a_fresh_cache_off_answer(project, tmp_path, name, moved_view, rel, text):
    cache_dir = tmp_path / 'cache'
    for earlier, _view, earlier_rel, earlier_text in EDITS:
        if earlier == name:
            break
        _apply(project, earlier_rel, earlier_text)
    before = {view: _answer(project, view, cache_dir, cache=True) for view in VIEWS}  # fills the cache
    _apply(project, rel, text)
    after_off = {view: _answer(project, view, cache_dir, cache=False) for view in VIEWS}
    assert after_off[moved_view] != before[moved_view], f'{name} did not change the {moved_view} answer'
    stale = [view for view in VIEWS if _answer(project, view, cache_dir, cache=True) != after_off[view]]
    assert not stale, f'{name}: stale views {stale}'


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
