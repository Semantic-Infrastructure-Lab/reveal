"""BACK-2093 R10: the per-file imports memory layer keeps one entry per file, not per edit.

``ImportsDiskCache._mem_cache`` was keyed on ``(abspath, mtime_ns, size)``, so every edit
of one file added an entry and none was ever replaced: 20 edits of one file left 23
entries (manager re-run). A long-lived host resets it per request since BACK-2083, but a
library host or one long CLI run did not. The entry for a path is now replaced when its
stat changes; the stat still decides whether the entry answers.
"""

import os

import pytest

from reveal.analyzers.imports import python as py_imports

pytestmark = pytest.mark.component


@pytest.fixture
def cache(monkeypatch):
    """The Python layer alone: no disk cache behind it."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    py_imports._IMPORTS_CACHE.clear()
    yield py_imports._IMPORTS_CACHE
    py_imports._IMPORTS_CACHE.clear()


def edit(path, i, module='os'):
    """Rewrite *path* with a distinct size and an mtime one second later each time."""
    path.write_text(f'import {module}\nX = {i}\n' + '#' * i, encoding='utf-8')
    stamp = 1_700_000_000_000_000_000 + i * 1_000_000_000
    os.utime(path, ns=(stamp, stamp))


def modules(path):
    extractor = py_imports.PythonExtractor()
    return [stmt.module_name for stmt in extractor.extract_imports(path)]


def test_edits_of_one_file_leave_one_entry(tmp_path, cache):
    path = tmp_path / 'a.py'
    for i in range(20):
        edit(path, i)
        assert modules(path) == ['os']
    assert len(cache._mem_cache) == 1, f'{len(cache._mem_cache)} entries for one file after 20 edits'


# ------------------------------------------------------------- controls

def test_the_entry_still_answers_only_for_the_current_stat(tmp_path, cache):
    """Freshness is unchanged: an edit misses and the next read sees the new content."""
    path = tmp_path / 'a.py'
    edit(path, 1, 'os')
    assert modules(path) == ['os']
    edit(path, 2, 'sys')
    assert modules(path) == ['sys']
    edit(path, 1, 'os')  # back to the first stat: recomputed, not an old entry
    assert modules(path) == ['os']


def test_an_unchanged_file_is_still_a_hit(tmp_path, cache):
    path = tmp_path / 'a.py'
    edit(path, 3)
    assert modules(path) == ['os']
    extractor = py_imports.PythonExtractor()
    extractor._get_tree_analyzer = lambda *_a, **_k: pytest.fail('memory miss for an unchanged file')
    assert [stmt.module_name for stmt in extractor.extract_imports(path)] == ['os']


def test_distinct_files_keep_one_entry_each(tmp_path, cache):
    for name in ('a.py', 'b.py', 'c.py'):
        edit(tmp_path / name, 0)
        modules(tmp_path / name)
    assert len(cache._mem_cache) == 3


def test_edit_timestamps_are_distinct(tmp_path):
    """Fixture guard: each edit moves mtime and size, so the old key really missed."""
    path = tmp_path / 'a.py'
    seen = set()
    for i in range(3):
        edit(path, i)
        st = os.stat(path)
        seen.add((st.st_mtime_ns, st.st_size))
    assert len(seen) == 3
