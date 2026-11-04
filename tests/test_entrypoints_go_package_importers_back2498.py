"""A file of an imported Go package is not an entry point (BACK-2498).

Go imports a package, so the resolver makes the edge ``pkg/a/a.go -> pkg/b`` with the directory
``pkg/b`` as its target node and the package's files keep fan-in 0. ``imports://?entrypoints`` listed
every such file as an active entry point (22 of 32 on go-client_golang). The importers of a file are the
importers of the file and of its directory node, the rule ``?importers=FILE`` already uses (BACK-553).
"""
import json
from pathlib import Path

import pytest

from reveal.adapters.imports import ImportsAdapter
from conftest import _run_reveal_direct as run


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


@pytest.fixture
def go_tree(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'go.mod', 'module ex\n\ngo 1.21\n')
    _w(root / 'cmd' / 'main.go', 'package main\n\nimport "ex/pkg/b"\n\nfunc main() { b.B() }\n')
    _w(root / 'pkg' / 'b' / 'b.go', 'package b\n\nimport "ex/pkg/c"\n\nfunc B() int { return c.C() }\n')
    _w(root / 'pkg' / 'c' / 'c.go', 'package c\n\nfunc C() int { return 1 }\n')
    return root.resolve()


def _entries(target: Path) -> dict:
    result = ImportsAdapter(str(target), 'entrypoints').get_structure()
    return {e['file']: e for e in result['entries']}


def test_a_file_of_an_imported_package_is_not_an_entry_point(go_tree):
    entries = _entries(go_tree)
    assert 'cmd/main.go' in entries and not entries['cmd/main.go']['is_test']
    assert 'pkg/b/b.go' not in entries, sorted(entries)


def test_the_cli_agrees_with_the_importers_of_the_same_file(go_tree):
    importers = run('imports://' + str(go_tree) + '?importers=pkg/b/b.go', '--format', 'json')
    assert importers.returncode == 0, importers.stderr
    assert 'cmd/main.go' in importers.stdout
    result = run('imports://' + str(go_tree) + '?entrypoints', '--format', 'json')
    assert result.returncode == 0, result.stderr
    files = [e['file'] for e in json.loads(result.stdout)['entries']]
    assert 'pkg/b/b.go' not in files and 'cmd/main.go' in files


def test_test_only_importers_through_the_package_still_keep_the_file_listed(go_tree):
    """A test file importing the package is evidence of testability, not of a caller (BACK-1263)."""
    _w(go_tree / 'cmd' / 'main.go', 'package main\n\nfunc main() {}\n')
    _w(go_tree / 'cmd' / 'main_test.go',
       'package main\n\nimport (\n\t"testing"\n\n\t"ex/pkg/b"\n)\n\nfunc TestB(t *testing.T) { b.B() }\n')
    entries = _entries(go_tree)
    assert entries['pkg/b/b.go']['test_only_importers'] == 1, entries['pkg/b/b.go']
    assert not entries['pkg/b/b.go']['is_test']


def test_control_a_go_file_nothing_imports_stays_an_entry_point(go_tree):
    _w(go_tree / 'tools' / 'gen.go', 'package main\n\nimport "ex/pkg/c"\n\nfunc main() { c.C() }\n')
    entries = _entries(go_tree)
    assert 'tools/gen.go' in entries and entries['tools/gen.go']['fan_out'] == 1
    assert entries['tools/gen.go']['test_only_importers'] == 0


def test_control_python_entry_points_are_unchanged(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / '__init__.py', '')
    _w(root / 'pkg' / 'lib.py', 'def f():\n    return 1\n')
    _w(root / 'app.py', 'from pkg import lib\n\n\nif __name__ == "__main__":\n    lib.f()\n')
    entries = _entries(root.resolve())
    assert 'app.py' in entries and 'pkg/lib.py' not in entries
