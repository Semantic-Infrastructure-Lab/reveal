"""imports:// answers the same cold, warm and after an edit, cache on and off (BACK-2081, step 5).

A cache that returns a stale answer is a wrong answer (a removed import still reported as a cycle).
The disk cache (and the host-request memo behind it) must never change what a request returns, so
every view runs as separate processes through the public path:

* cache off: the reference, run twice to prove it is deterministic (the control for every compare);
* cache on, cold then warm: both equal the reference, and the warm one is served from the entry;
* after each edit (a cycle added, a cycle removed, a file added, a file deleted): the cache-on answer
  equals a fresh cache-off answer, and the edit really changed the answer (the positive control).

An edit that keeps a file's size and mtime is a stat-key design limit and is out of scope here.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.disk_cache]

VIEWS = {
    'default': [],
    'circular': ['--circular'],
    'unused': ['--unused'],
    'fan-in': ['--rank', 'fan-in'],
    'entrypoints': ['--entrypoints'],
    'importers': ['--importers'],
}

# The view an edit is known to move; every edit must change at least this answer.
EDITS = [
    ('add_cycle', 'circular', lambda root: (root / 'pkg' / 'b.py').write_text(
        'from pkg import a\nimport os\n', encoding='utf-8')),
    ('remove_cycle', 'circular', lambda root: (root / 'pkg' / 'b.py').write_text(
        'import os\n', encoding='utf-8')),
    ('add_file', 'fan-in', lambda root: (root / 'pkg' / 'd.py').write_text(
        'from pkg import c\nfrom pkg import a\n', encoding='utf-8')),
    ('delete_file', 'fan-in', lambda root: (root / 'pkg' / 'd.py').unlink()),
]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    _write(root / 'pyproject.toml', '[project]\nname = "proj"\nversion = "0"\n')
    _write(root / 'pkg' / '__init__.py', '')
    _write(root / 'pkg' / 'a.py', 'from pkg import c\nimport sys\n')
    _write(root / 'pkg' / 'b.py', 'import os\n')
    _write(root / 'pkg' / 'c.py', 'from pkg import b\n')
    _write(root / 'main.py', 'from pkg import a\n')
    return root


def _answer(root: Path, view, cache_dir: Path, *, cache: bool):
    """One request in its own process, through the public path: (exit code, JSON answer)."""
    env = {**os.environ, 'PYTHONHASHSEED': '0', 'REVEAL_NO_CONFIG': '1',
           'REVEAL_CACHE_DIR': str(cache_dir), 'REVEAL_DISK_CACHE': '1' if cache else '0'}
    done = subprocess.run([sys.executable, '-m', 'reveal', 'imports', str(root), *VIEWS[view],
                           '--format', 'json'], capture_output=True, text=True, encoding='utf-8', env=env, timeout=120)
    assert done.returncode in (0, 3), done.stderr
    return done.returncode, _comparable(json.loads(done.stdout))


def _comparable(value):
    """The answer without what legitimately differs between two runs (timings, cache provenance)."""
    volatile = {'elapsed', 'elapsed_ms', 'duration', 'duration_ms', 'timing', 'timings', 'cache',
                'cache_hit', 'from_cache', 'generated_at', 'perf'}
    if isinstance(value, dict):
        return {k: _comparable(v) for k, v in value.items() if k not in volatile}
    if isinstance(value, list):
        return [_comparable(v) for v in value]
    return value


@pytest.mark.parametrize('view', sorted(VIEWS))
def test_cold_and_warm_answers_equal_the_cache_off_answer(project, tmp_path, view):
    cache_dir = tmp_path / 'cache'
    reference = _answer(project, view, cache_dir, cache=False)
    assert _answer(project, view, cache_dir, cache=False) == reference, 'cache off is not deterministic'
    assert not cache_dir.exists() or not any(cache_dir.rglob('*')), 'cache off wrote an entry'
    assert _answer(project, view, cache_dir, cache=True) == reference
    assert any(cache_dir.rglob('*')), 'the cold cache-on run wrote no entry; the warm compare proves nothing'
    assert _answer(project, view, cache_dir, cache=True) == reference


@pytest.mark.parametrize('name,moved_view,edit', EDITS, ids=[e[0] for e in EDITS])
def test_every_view_after_an_edit_equals_a_fresh_cache_off_answer(project, tmp_path, name, moved_view, edit):
    cache_dir = tmp_path / 'cache'
    # The edits are a sequence: each starts from the state the previous one left.
    for earlier, _view, earlier_edit in EDITS:
        if earlier == name:
            break
        earlier_edit(project)
    before = {view: _answer(project, view, cache_dir, cache=True) for view in VIEWS}  # fills the cache
    edit(project)
    after_off = {view: _answer(project, view, cache_dir, cache=False) for view in VIEWS}
    assert after_off[moved_view] != before[moved_view], f'{name} did not change the {moved_view} answer'
    for view in VIEWS:
        assert _answer(project, view, cache_dir, cache=True) == after_off[view], f'{name}: stale {view}'
