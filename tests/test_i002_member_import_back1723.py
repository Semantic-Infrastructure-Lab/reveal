"""BACK-1723: imports:// and I002 see the same file edges as depends://.

An absolute ``from pkg import b`` (b a submodule) runs ``pkg/b.py`` at startup,
so it is a cycle edge. imports:// resolved only the primary target
(``pkg/__init__.py``) and I002 resolved absolute imports with no project-root
search path at all, so both missed a <-> b cycles that depends:// reports.
"""
import pytest

from reveal.adapters.depends import DependsAdapter
from reveal.adapters.imports import ImportsAdapter
from reveal.rules.imports.I002 import I002, _graph_cache

pytestmark = pytest.mark.component


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    _graph_cache.clear()
    yield
    _graph_cache.clear()


def _project(root, files):
    root.mkdir()
    root = root.resolve()  # macOS tmp is /private/var; graph paths are resolved
    (root / 'pyproject.toml').write_text('[project]\nname="probe"\n', encoding='utf-8')
    for rel, text in {'pkg/__init__.py': '', **files}.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    return root


def _rel(root, paths):
    return {p.relative_to(root).as_posix() for p in paths}


def _imports_graph(root):
    adapter = ImportsAdapter(resource=str(root))
    adapter._build_graph(root)
    return adapter.analysis.graph


def _imports_cycles(root):
    return sorted(sorted(_rel(root, group)) for group in _imports_graph(root).find_cycle_groups())


def _i002_cycle_files(root):
    """Files I002 flags, through the rule's real entry point."""
    flagged = set()
    for path in sorted(root.rglob('*.py')):
        detections = I002().check(str(path), None, path.read_text(encoding='utf-8'))
        if detections:
            flagged.add(path.relative_to(root).as_posix())
    return flagged


CYCLES = {
    'member_import': {'pkg/a.py': 'from pkg import b\n', 'pkg/b.py': 'import pkg.a\n'},
    'member_import_both_ways': {'pkg/a.py': 'from pkg import b\n', 'pkg/b.py': 'from pkg import a\n'},
    'dotted_absolute': {'pkg/a.py': 'import pkg.b\n', 'pkg/b.py': 'import pkg.a\n'},
    # positive control for the harness: relative imports were always seen by both
    'relative': {'pkg/a.py': 'from . import b\n', 'pkg/b.py': 'from . import a\n'},
}


@pytest.mark.parametrize('shape', CYCLES)
def test_imports_finds_the_cycle(tmp_path, shape):
    root = _project(tmp_path / shape, CYCLES[shape])
    assert _imports_cycles(root) == [['pkg/a.py', 'pkg/b.py']]


@pytest.mark.parametrize('shape', CYCLES)
def test_i002_finds_the_cycle(tmp_path, shape):
    root = _project(tmp_path / shape, CYCLES[shape])
    assert _i002_cycle_files(root) == {'pkg/a.py', 'pkg/b.py'}


def test_i002_cycle_detection_names_both_files(tmp_path):
    root = _project(tmp_path / 'ctx', CYCLES['member_import'])
    path = root / 'pkg' / 'a.py'
    detections = I002().check(str(path), None, path.read_text(encoding='utf-8'))
    assert len(detections) == 1
    assert 'a.py' in detections[0].context and 'b.py' in detections[0].context


# ---------------------------------------------------------------- negative controls

def test_member_import_of_a_name_gains_no_file_edge(tmp_path):
    """`from pkg import x` with x a NAME in pkg/__init__.py: one edge, to __init__.py."""
    root = _project(tmp_path / 'name', {
        'pkg/__init__.py': 'x = 1\n', 'pkg/a.py': 'from pkg import x\n', 'pkg/b.py': 'import pkg.a\n'})
    graph = _imports_graph(root)
    assert _rel(root, graph.dependencies[root / 'pkg' / 'a.py']) == {'pkg/__init__.py'}
    assert not (root / 'pkg' / 'x.py').exists()
    assert _imports_cycles(root) == []
    assert _i002_cycle_files(root) == set()


def test_one_way_member_import_is_no_cycle(tmp_path):
    root = _project(tmp_path / 'oneway', {'pkg/a.py': 'from pkg import b\n', 'pkg/b.py': 'y = 2\n'})
    graph = _imports_graph(root)
    assert _rel(root, graph.dependencies[root / 'pkg' / 'a.py']) == {'pkg/__init__.py', 'pkg/b.py'}
    assert _imports_cycles(root) == []
    assert _i002_cycle_files(root) == set()


@pytest.mark.parametrize('deferred', [
    'def load():\n    from pkg import b\n',
    'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from pkg import b\n',
])
def test_deferred_member_import_is_not_a_startup_cycle(tmp_path, deferred):
    """Function-body and TYPE_CHECKING imports cannot cause a startup cycle."""
    root = _project(tmp_path / 'deferred', {'pkg/a.py': deferred, 'pkg/b.py': 'import pkg.a\n'})
    assert _imports_cycles(root) == []
    assert _i002_cycle_files(root) == set()


def test_stdlib_named_member_import_stays_external(tmp_path):
    """`from os import path` in a project holding an os/ package is still stdlib (BACK-1080)."""
    root = _project(tmp_path / 'stdlib', {
        'os/__init__.py': '', 'os/path.py': 'import pkg.a\n', 'pkg/a.py': 'from os import path\n'})
    assert _imports_cycles(root) == []
    assert _i002_cycle_files(root) == set()
    dependents = DependsAdapter(str(root / 'os' / 'path.py')).get_structure()['dependents']
    assert [d['file'] for d in dependents] == []
