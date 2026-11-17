"""Rows a request does not sort come in path order on every platform (BACK-2652).

COMMAND_MODEL 'Row order' (Scott 2026-11-16): the one walk is top-down with each directory's
file names and subdirectory names sorted. ``os.walk`` order is whatever the filesystem lists,
so a capped scan kept different files on macOS, Linux and Windows. Each test reverses the
listing order ``os.walk`` reports and asserts the walk's answer does not move.
"""
import os

import pytest

from reveal.utils import path_utils
from reveal.utils.path_utils import ANALYSIS, _walk_code_files, walk_tree, walk_with_causes

pytestmark = [pytest.mark.component]

_real_walk = os.walk


def _reversed_walk(top, *args, **kwargs):
    for root, dirs, files in _real_walk(top, *args, **kwargs):
        dirs.reverse()
        files.reverse()
        yield root, dirs, files


@pytest.fixture
def tree(tmp_path):
    for rel in ('z.py', 'a/x.py', 'a/b.py', 'm.py', 'a/c/d.py', 'b/e.py'):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('X = 1\n', encoding='utf-8')
    return tmp_path


EXPECTED = ['m.py', 'z.py', 'a/b.py', 'a/x.py', 'a/c/d.py', 'b/e.py']


def _rel(paths, root):
    return [p.relative_to(root).as_posix() for p in paths]


@pytest.mark.parametrize('listing', ['native', 'reversed'])
def test_walk_with_causes_is_sorted_walk_order(tree, monkeypatch, listing):
    if listing == 'reversed':
        monkeypatch.setattr(path_utils.os, 'walk', _reversed_walk)
    assert _rel([p for p, _ in walk_with_causes(tree, ANALYSIS)], tree) == EXPECTED


@pytest.mark.parametrize('listing', ['native', 'reversed'])
def test_walk_tree_and_code_files_are_sorted_walk_order(tree, monkeypatch, listing):
    if listing == 'reversed':
        monkeypatch.setattr(path_utils.os, 'walk', _reversed_walk)
    from_tree = [root / name for root, _, files in walk_tree(tree, ANALYSIS) for name in files]
    assert _rel(from_tree, tree) == EXPECTED
    assert _rel(list(_walk_code_files(tree)), tree) == EXPECTED


def test_capped_imports_scan_keeps_the_same_files_whatever_the_listing(tree, monkeypatch):
    from tests.conftest import _run_reveal_in
    import json

    for path in tree.rglob('*.py'):
        path.write_text('import os\n', encoding='utf-8')  # every scanned file then appears in `files`

    def files_kept():
        result = _run_reveal_in(tree, f'imports://{tree.as_posix()}?scan-limit=3', '--format', 'json')
        assert result.returncode == 3, result.stderr  # a capped scan is incomplete
        return sorted(json.loads(result.stdout)['files'])

    native = files_kept()
    assert len(native) == 3  # positive control: the cap kept three of the six files
    monkeypatch.setattr(path_utils.os, 'walk', _reversed_walk)
    assert files_kept() == native
