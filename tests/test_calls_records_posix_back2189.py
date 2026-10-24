"""Every ``calls`` record writes '/' in ``file`` on every OS (BACK-1586, BACK-2189).

The walker's structures carry the OS spelling, so on Windows a record built from them said
``pkg\\a.py`` while ``find_callers`` said ``pkg/a.py``. Linux cannot produce that spelling from
a real tree, so each case hands the builder a structure that already spells the file the
Windows way (as ``tests/test_calls_rank_posix_back1586.py`` does for the ranking).
"""

import pytest

from reveal.adapters.calls import index as calls_index

NATIVE = 'pkg\\a.py'


def _structures():
    """One file, as the walker records it on Windows: a function that calls and an unused one."""
    elements = [
        {'name': 'run', 'category': 'functions', 'line': 3, 'calls': ['target'], 'line_count': 2},
        {'name': 'unused', 'category': 'functions', 'line': 9, 'calls': [], 'line_count': 2},
    ]
    return [{'file': NATIVE, 'elements': elements}]


class _Structures(list):
    def __init__(self, items):
        super().__init__(items)
        self.skipped = []
        self.traversal_failures = []


@pytest.fixture
def structures():
    return _Structures(_structures())


def test_callers_index_records_name_their_file_with_forward_slashes(structures):
    index = calls_index.build_callers_index('.', structures)

    assert {rec['file'] for records in index.values() for rec in records} == {'pkg/a.py'}


def test_forward_call_index_records_name_their_file_with_forward_slashes(structures):
    forward = calls_index._build_forward_index(structures, include_builtins=True)

    assert {rec['file'] for records in forward.values() for rec in records} == {'pkg/a.py'}


def test_uncalled_entries_name_their_file_with_forward_slashes(structures, monkeypatch, tmp_path):
    monkeypatch.setattr(calls_index, 'collect_structures', lambda *_a, **_k: structures)

    found = calls_index.find_uncalled(str(tmp_path))

    files = {entry['file'] for entry in found['entries']}
    assert files == {'pkg/a.py'}, found
