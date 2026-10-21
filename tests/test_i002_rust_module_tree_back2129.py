"""BACK-2129: Rust's module tree is not an import cycle.

A parent module (``mod.rs`` or ``foo.rs`` owning ``foo/``) that uses its child and a child
that names the parent module in a ``crate::`` path is how every Rust crate is laid out; it compiles and is no dependency smell.
I002 and imports://?circular reported it, and printed bare file names, so two ``mod.rs``
in different directories read as one file repeated.  A real cycle between sibling modules
must still be reported, with a path that is a simple cycle.
"""
from pathlib import Path

import pytest

from reveal.adapters.imports import ImportsAdapter
from reveal.analyzers.imports.types import LAZY_EXCLUDE, ImportGraph
from reveal.rules.imports.I002 import I002, _graph_cache

pytestmark = pytest.mark.component


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    _graph_cache.clear()
    yield
    _graph_cache.clear()


def _crate(root, files):
    root.mkdir()
    root = root.resolve()  # macOS tmp is /private/var; graph paths are resolved
    (root / 'Cargo.toml').write_text('[package]\nname = "probe"\nversion = "0.1.0"\n', encoding='utf-8')
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    return root


def _graph(root):
    adapter = ImportsAdapter(resource=str(root))
    adapter._build_graph(root)
    return adapter.analysis.graph


def _cycle_groups(root):
    groups = _graph(root).edge_view(LAZY_EXCLUDE).find_cycle_groups()
    return sorted(sorted(p.relative_to(root).as_posix() for p in group) for group in groups)


def _i002(root):
    """{file: [context, ...]} for every .rs file I002 flags, through the rule's entry point."""
    flagged = {}
    for path in sorted(root.rglob('*.rs')):
        detections = I002().check(str(path), None, path.read_text(encoding='utf-8'))
        if detections:
            flagged[path.relative_to(root).as_posix()] = [d.context for d in detections]
    return flagged


# Parent uses its child and the child uses its parent: the module tree, in each file layout.
TREES = {
    'mod_rs': {
        'src/lib.rs': 'pub mod vector;\n',
        'src/vector/mod.rs': 'mod bulk;\npub use self::bulk::Bulk;\npub struct Settings;\n',
        'src/vector/bulk.rs': 'use crate::vector::Settings;\npub struct Bulk(pub Settings);\n',
    },
    'file_owning_dir': {
        'src/lib.rs': 'pub mod search;\n',
        'src/search.rs': 'mod facet;\npub use crate::search::facet::Facet;\npub struct Query;\n',
        'src/search/facet.rs': 'use crate::search::Query;\npub struct Facet(pub Query);\n',
    },
    'grandchild_to_ancestor': {
        'src/lib.rs': 'pub mod a;\n',
        'src/a/mod.rs': 'pub mod b;\npub use crate::a::b::c::Deep;\npub struct Marker;\n',
        'src/a/b/mod.rs': 'pub mod c;\n',
        'src/a/b/c.rs': 'use crate::a::Marker;\npub struct Deep(pub Marker);\n',
    },
}


@pytest.mark.parametrize('shape', TREES)
def test_module_tree_is_not_a_cycle_in_imports(tmp_path, shape):
    root = _crate(tmp_path / shape, TREES[shape])
    assert _cycle_groups(root) == []


@pytest.mark.parametrize('shape', TREES)
def test_module_tree_is_not_a_cycle_in_i002(tmp_path, shape):
    root = _crate(tmp_path / shape, TREES[shape])
    assert _i002(root) == {}


def test_module_tree_edges_are_still_in_the_graph(tmp_path):
    """Control: the fix is a cycle rule, so the edge set (fan-in, importers) is untouched."""
    root = _crate(tmp_path / 'edges', TREES['mod_rs'])
    graph = _graph(root)
    bulk, mod = root / 'src/vector/bulk.rs', root / 'src/vector/mod.rs'
    assert mod in graph.dependencies[bulk]
    assert bulk in graph.dependencies[mod]


SIBLING_CYCLE = {
    'src/lib.rs': 'pub mod a;\npub mod b;\n',
    'src/a.rs': 'use crate::b::Beta;\npub struct Alpha(pub Beta);\n',
    'src/b.rs': 'use crate::a::Alpha;\npub struct Beta(pub Option<Box<Alpha>>);\n',
}


def test_real_two_file_cycle_is_still_reported(tmp_path):
    root = _crate(tmp_path / 'real', SIBLING_CYCLE)
    assert _cycle_groups(root) == [['src/a.rs', 'src/b.rs']]
    assert sorted(_i002(root)) == ['src/a.rs', 'src/b.rs']


def test_real_cycle_under_a_module_tree_excludes_the_parent(tmp_path):
    """Control: siblings that use each other stay a cycle when their parent also uses both."""
    root = _crate(tmp_path / 'mixed', {
        'src/lib.rs': 'pub mod m;\n',
        'src/m/mod.rs': 'mod a;\nmod b;\npub use self::a::Alpha;\npub use self::b::Beta;\npub struct Shared;\n',
        'src/m/a.rs': 'use super::Shared;\nuse super::b::Beta;\npub struct Alpha(pub Beta, pub Shared);\n',
        'src/m/b.rs': 'use super::a::Alpha;\npub struct Beta(pub Option<Box<Alpha>>);\n',
    })
    assert _cycle_groups(root) == [['src/m/a.rs', 'src/m/b.rs']]


def test_every_reported_cycle_is_simple_and_names_distinct_files(tmp_path):
    """Two ``mod.rs`` in different directories are two nodes; the message must tell them apart."""
    root = _crate(tmp_path / 'twins', {
        'src/lib.rs': 'pub mod x;\npub mod y;\n',
        'src/x/mod.rs': 'use crate::y::Yv;\npub struct Xv(pub Yv);\n',
        'src/y/mod.rs': 'use crate::x::Xv;\npub struct Yv(pub Option<Box<Xv>>);\n',
    })
    graph = _graph(root).edge_view(LAZY_EXCLUDE)
    cycles = graph.find_cycles()
    assert cycles
    for cycle in cycles:
        assert cycle[0] == cycle[-1]
        assert len(set(cycle[:-1])) == len(cycle) - 1, cycle
    flagged = _i002(root)
    assert sorted(flagged) == ['src/x/mod.rs', 'src/y/mod.rs']
    for contexts in flagged.values():
        for context in contexts:
            names = context.removeprefix('Import cycle: ').split(' -> ')
            assert len(set(names[:-1])) == len(names) - 1, context
            assert names[0] == names[-1], context


def test_find_cycles_are_simple_on_a_dense_graph():
    """Control (passes on the old code): the DFS itself never repeats a node."""
    graph = ImportGraph()
    nodes = [Path(f'n{i}') for i in range(6)]
    for node in nodes:
        graph.files[node] = []
    for i, src in enumerate(nodes):
        for dst in nodes[:i] + nodes[i + 1:]:
            graph.add_dependency(src, dst)
    cycles = graph.find_cycles()
    assert cycles
    for cycle in cycles:
        assert len(set(cycle[:-1])) == len(cycle) - 1
