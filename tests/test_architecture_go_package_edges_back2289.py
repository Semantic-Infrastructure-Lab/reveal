"""A Go package import counts as incoming at the package's component (BACK-2289).

Go imports a package, not a file, so the resolver makes the edge ``pkg/a/a.go -> pkg/b`` with the
directory ``pkg/b`` as its target node (``imports://?rank=fan-in`` ranks ``pkg/b`` at fan-in 1). The
component counts only looked at the edges of scanned files, so the directory node belonged to no
component: ``pkg/a`` showed outgoing 1 and ``pkg/b`` incoming 0, and an external test package
(``package b_test`` in ``pkg/b``) importing its own package counted as outgoing. A directory node now
belongs to that directory's component, in ``imports://?components``, ``overview`` and ``architecture``.
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
    _w(root / 'pkg' / 'a' / 'a.go', 'package a\n\nimport "ex/pkg/b"\n\nfunc A() int { return b.B() }\n')
    _w(root / 'pkg' / 'b' / 'b.go', 'package b\n\nfunc B() int { return 1 }\n')
    return root.resolve()


def _components(target: Path) -> dict:
    result = ImportsAdapter(str(target), 'components').get_structure()
    return {c['component']: c for c in result['components']}


def _fan_in(target: Path) -> dict:
    result = ImportsAdapter(str(target), 'rank=fan-in').get_structure()
    return {e['file']: e['fan_in'] for e in result['entries']}


def _counts(row: dict) -> tuple:
    return row['files'], row['internal'], row['outgoing'], row['incoming']


def test_a_package_import_is_outgoing_at_the_importer_and_incoming_at_the_package(go_tree):
    comps = _components(go_tree)
    assert _counts(comps['pkg/a']) == (1, 0, 1, 0)
    assert _counts(comps['pkg/b']) == (1, 0, 0, 1), comps['pkg/b']
    # the same edge imports://?rank=fan-in counts: one importer of the package node pkg/b
    assert _fan_in(go_tree)['pkg/b'] == comps['pkg/b']['incoming'] == 1


def test_overview_and_architecture_components_agree_with_imports(go_tree):
    expected = {name: _counts(row) for name, row in _components(go_tree).items()}
    assert expected == {'pkg/a': (1, 0, 1, 0), 'pkg/b': (1, 0, 0, 1)}
    for command in ('overview', 'architecture'):
        result = run(command, str(go_tree), '--format', 'json')
        assert result.returncode == 0, (command, result.stderr)
        rows = json.loads(result.stdout)['map']['components']['rows']
        assert {r['component']: _counts(r) for r in rows} == expected, command


def test_importers_outside_the_requested_package_count_as_incoming(go_tree):
    """imports://repo/pkg/b climbs to go.mod: pkg/a/a.go is not a row, its edge still arrives."""
    comps = _components(go_tree / 'pkg' / 'b')
    assert [_counts(row) for row in comps.values()] == [(1, 0, 0, 1)]


def test_an_external_test_package_importing_its_own_package_is_internal(go_tree):
    _w(go_tree / 'pkg' / 'b' / 'b_ext_test.go',
       'package b_test\n\nimport (\n\t"testing"\n\n\t"ex/pkg/b"\n)\n\n'
       'func TestB(t *testing.T) { _ = b.B() }\n')
    comps = _components(go_tree)
    assert _counts(comps['pkg/b']) == (2, 1, 0, 1), comps['pkg/b']
    assert comps['pkg/b']['top_bridge'] is None


def test_control_a_go_package_importing_only_the_standard_library_stays_zero(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'go.mod', 'module ex\n\ngo 1.21\n')
    _w(root / 'pkg' / 'c' / 'c.go', 'package c\n\nimport (\n\t"fmt"\n\t"strings"\n)\n\n'
       'func C() { fmt.Println(strings.ToUpper("c")) }\n')
    comps = _components(root.resolve())
    assert _counts(comps['pkg/c']) == (1, 0, 0, 0)
    assert comps['pkg/c']['top_bridge'] is None


def test_control_python_package_component_counts_are_unchanged(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / '__init__.py', '')
    _w(root / 'pkg' / 'a.py', 'from pkg import b\n\n\ndef a():\n    return b.b()\n')
    _w(root / 'pkg' / 'b.py', 'def b():\n    return 1\n')
    _w(root / 'other.py', 'from pkg import a\n\n\ndef o():\n    return a.a()\n')
    # values observed before the fix: `from pkg import b` is an edge to pkg/__init__.py and to pkg/b.py
    comps = _components(root.resolve())
    assert comps['pkg'] == {'component': 'pkg', 'files': 3, 'internal': 2, 'outgoing': 0,
                            'incoming': 2, 'cohesion': 1.0, 'top_bridge': None}
    assert comps['.'] == {'component': '.', 'files': 1, 'internal': 0, 'outgoing': 2,
                          'incoming': 0, 'cohesion': 0.0, 'top_bridge': 'other.py'}
