"""An import that resolved to no file blocks a project definition only where its spelling says the
definition is elsewhere (BACK-2573 follow-up, found by the calls gate's go and rust rows).

BACK-2573 lets a call bound by an import with an unknown verdict reach only a candidate "at the
module's path". The path test was Python's: a module path is a chain of directories ending in a file.
Three layouts read it wrong, and every such call lost its project target (callee) and its caller
(``?callers=``), where the bare-name answer before BACK-2573 had them:

* Go: a package is a directory, and an import path starts with the module path ``go.mod`` declares,
  which is not on disk. ``types.NewPtr`` through ``"example.com/proj/internal/types"`` with no
  ``go.mod`` reached no file (go/depth2 recall 100% -> 81%).
* Rust: ``use write::write_to_db`` spells the item into the module; the item sits in ``write.rs``,
  not in a ``write/write_to_db`` module.
* An import the extractor places in the tree (Rust ``crate::``, any relative import) that resolution
  still could not place was read as one from outside the tree, so it reached nothing at all.

Each test asserts the edge's target or the callers found, not that an answer exists.
"""

from pathlib import Path

from reveal.adapters.calls.adapter import CallsAdapter
from reveal.analyzers.imports import service

from test_callee_import_binding_back2553 import _edges, _target, _tree


def _callers(path: str, name: str):
    result = CallsAdapter(path, f'callers={name}').get_structure()
    return sorted((Path(r['file']).name, r['caller'])
                  for level in result.get('levels') or [] for r in level['callers'])


def _statement(path: str, module: str):
    analysis = service.analyze(service.project_scope(Path(path))).analysis
    return next(s for e in analysis.extractions.values() for s in e.imports if s.module_name == module)


# --- Go: the package directory, under a module path that is not on disk -------------------------

GO_NO_MODFILE = {
    'internal/types/type.go': 'package types\n\nfunc NewPtr(x int) int { return x }\n',
    'cmd/app/main.go': ('package main\n\nimport "example.com/proj/internal/types"\n\n'
                        'func run() int { return types.NewPtr(1) }\n'),
}


def test_go_unplaced_import_reaches_the_package_directory(tmp_path):
    path = _tree(tmp_path, GO_NO_MODFILE)
    assert _target(_edges(path, 'run')['types.NewPtr']) == ('type.go', None)
    assert _callers(path, 'NewPtr') == [('main.go', 'run')]


def test_go_unplaced_import_has_an_unknown_verdict(tmp_path):
    # Positive control for the cause: no go.mod, so the verdict cannot place the module path.
    stmt = _statement(_tree(tmp_path, GO_NO_MODFILE), 'example.com/proj/internal/types')
    assert (stmt.resolved_path, stmt.intra_verdict) == (None, None)


def test_go_unplaced_import_of_another_package_reaches_no_project_definition(tmp_path):
    # Precision control: the package directory must be the one the import path ends with.
    path = _tree(tmp_path, {**GO_NO_MODFILE, 'cmd/app/main.go': (
        'package main\n\nimport "github.com/other/thing/util"\n\nfunc run() int { return util.NewPtr(1) }\n')})
    assert _target(_edges(path, 'run')['util.NewPtr']) == (None, 'external')
    assert _callers(path, 'NewPtr') == []


def test_go_with_a_modfile_a_stdlib_package_never_reaches_a_same_named_directory(tmp_path):
    # Precision control: with go.mod the standard library's verdict is "outside the tree", so the
    # directory rule never applies to it; the project's own errors package is reached by its path.
    path = _tree(tmp_path, {
        'go.mod': 'module example.com/proj\n\ngo 1.22\n',
        'pkg/errors/errors.go': 'package errors\n\nfunc New(s string) error { return nil }\n',
        'cmd/app/main.go': ('package main\n\nimport (\n\t"errors"\n\tmine "example.com/proj/pkg/errors"\n)\n\n'
                            'func run() { errors.New("x"); mine.New("y") }\n')})
    edges = _edges(path, 'run')
    assert _target(edges['errors.New']) == (None, 'external')
    assert _target(edges['mine.New']) == ('errors.go', None)
    assert _callers(path, 'New') == [('main.go', 'run')]


# --- Rust: the item is spelled into the module -------------------------------------------------

RUST_CHILD_MODULE = {
    'Cargo.toml': '[package]\nname = "x"\nversion = "0.1.0"\n',
    'src/lib.rs': 'pub mod idx;\n',
    'src/idx/mod.rs': 'mod write;\nuse write::write_to_db;\n\npub fn run() { write_to_db(); }\n',
    'src/idx/write.rs': 'pub fn write_to_db() {}\n',
    'src/other.rs': 'pub fn write_to_db() {}\n',
}


def test_rust_use_of_a_child_modules_item_reaches_that_module(tmp_path):
    path = _tree(tmp_path, RUST_CHILD_MODULE)
    assert _target(_edges(path, 'run')['write_to_db']) == ('write.rs', None)
    assert _callers(path, 'write_to_db') == [('mod.rs', 'run')]


def test_rust_use_of_a_child_modules_item_is_unplaced(tmp_path):
    # Positive control: resolution does not follow a `use` path through a child `mod` declaration.
    stmt = _statement(_tree(tmp_path, RUST_CHILD_MODULE), 'write::write_to_db')
    assert (stmt.resolved_path, stmt.intra_verdict) == (None, None)


# --- an import placed in the tree that resolution could not place -------------------------------

RUST_NO_MANIFEST = {
    'src/lib.rs': 'pub mod a;\npub mod b;\n',
    'src/a.rs': 'pub fn f() {}\n',
    'src/b.rs': 'use crate::a::f;\n\npub fn run() { f(); }\n',
}


def test_an_in_tree_import_resolution_missed_is_no_claim(tmp_path):
    # No Cargo.toml: `crate::a::f` is in the tree by its spelling, but no crate root places it.
    path = _tree(tmp_path, RUST_NO_MANIFEST)
    assert _target(_edges(path, 'run')['f']) == ('a.rs', None)
    assert _callers(path, 'f') == [('b.rs', 'run')]


def test_an_in_tree_import_resolution_missed_has_an_in_tree_verdict(tmp_path):
    stmt = _statement(_tree(tmp_path, RUST_NO_MANIFEST), 'crate::a::f')
    assert (stmt.resolved_path, stmt.intra_verdict, stmt.is_relative) == (None, True, True)
