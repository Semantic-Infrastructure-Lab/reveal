"""BACK-2079: a Rust ``use`` records its lexical scope through the shared ``edge_scope`` owner.

A ``use`` in a ``fn`` body (free function, ``impl`` or ``trait`` method, nested block, an
inline ``mod`` inside a fn, or a closure inside a fn) is ``local``; one at file, ``mod``,
``impl``-free item level or in a ``const`` initializer block is ``module``. A closure outside
every fn (a ``static``/``const`` initializer) confers no scope here: the statement keeps
``scope=None`` and the edge is disclosed as unclassified. The tag is positional: a Rust
``use`` binds a name at compile time and never runs, so ``local`` is not a load-order claim.

The fixture compiles with rustc (checked by hand when written); an independent ``syn`` 2
inventory of the same source gives the same context for every site.
"""
import json
from dataclasses import asdict

import pytest

from conftest import _run_reveal_direct
from reveal.analyzers.imports import rust
from reveal.analyzers.imports.generic import LuaImportExtractor
from reveal.analyzers.imports.rust import RustExtractor
from reveal.analyzers.imports.types import ImportGraph
from reveal.analyzers.imports.zig import ZigImportExtractor
from reveal.utils.path_utils import to_posix

pytestmark = pytest.mark.component

CARGO = '[package]\nname = "fx"\nversion = "0.1.0"\nedition = "2021"\n'

# One importer, imp.rs, reaches each target from one lexical position.
IMP = '''pub const IMP: i32 = 0;
use crate::t_mod::MOD;
use crate::t_mixed::MIXED;

pub fn free() -> i32 {
    use crate::t_fn::FN;
    FN + MOD
}

pub struct S;
impl S {
    pub fn m(&self) -> i32 {
        use crate::t_method::METHOD;
        METHOD
    }
}

pub trait T {
    fn d() -> i32 {
        use crate::t_trait::TRAIT;
        TRAIT
    }
}

pub fn nested() -> i32 {
    {
        use crate::t_block::BLOCK;
        BLOCK
    }
}

pub fn clos() -> i32 {
    let k = || {
        use crate::t_closure::CLOSURE;
        CLOSURE
    };
    k()
}

pub fn inner_mod() -> i32 {
    mod x {
        use crate::t_inner_mod::INNER_MOD;
        pub fn g() -> i32 { INNER_MOD }
    }
    x::g()
}

pub static K: fn() -> i32 = || {
    use crate::t_static_closure::STATIC_CLOSURE;
    STATIC_CLOSURE
};

pub const CB: i32 = {
    use crate::t_const_block::CONST_BLOCK;
    CONST_BLOCK
};

pub fn mixed() -> i32 {
    use crate::t_mixed::MIXED as M2;
    M2 + MIXED
}

mod tests_like {
    use crate::t_inline_mod::INLINE_MOD;
    pub fn h() -> i32 { INLINE_MOD }
}

macro_rules! via_macro {
    () => {{
        use crate::t_macro::MACRO;
        MACRO
    }};
}

pub fn uses_macro() -> i32 {
    via_macro!()
}
'''

# (line, module_name, imported_names, alias, scope): the full extracted identity of imp.rs.
IMP_STATEMENTS = [
    (2, 'crate::t_mod::MOD', ['MOD'], None, 'module'),
    (3, 'crate::t_mixed::MIXED', ['MIXED'], None, 'module'),
    (6, 'crate::t_fn::FN', ['FN'], None, 'local'),
    (13, 'crate::t_method::METHOD', ['METHOD'], None, 'local'),
    (20, 'crate::t_trait::TRAIT', ['TRAIT'], None, 'local'),
    (27, 'crate::t_block::BLOCK', ['BLOCK'], None, 'local'),
    (34, 'crate::t_closure::CLOSURE', ['CLOSURE'], None, 'local'),
    (42, 'crate::t_inner_mod::INNER_MOD', ['INNER_MOD'], None, 'local'),
    (49, 'crate::t_static_closure::STATIC_CLOSURE', ['STATIC_CLOSURE'], None, None),
    (54, 'crate::t_const_block::CONST_BLOCK', ['CONST_BLOCK'], None, 'module'),
    (59, 'crate::t_mixed::MIXED', ['MIXED as M2'], 'M2', 'local'),
    (64, 'crate::t_inline_mod::INLINE_MOD', ['INLINE_MOD'], None, 'module'),
]
# The macro_rules! body's `use` (t_macro) is a token tree, extracted by no path before or after.

TARGETS = ('t_mod', 't_mixed', 't_fn', 't_method', 't_trait', 't_block', 't_closure', 't_inner_mod',
           't_static_closure', 't_const_block', 't_inline_mod', 't_macro', 't_unused')

MODULE = {'t_mod', 't_mixed', 't_const_block', 't_inline_mod'}
LOCAL = {'t_fn', 't_method', 't_trait', 't_block', 't_closure', 't_inner_mod'}
UNKNOWN = {'t_static_closure'}
BACK = ('src/t_fn.rs', 'src/imp.rs')  # t_fn.rs uses imp.rs at module level: a cycle through a local edge


def _pairs(names):
    return {('src/imp.rs', f'src/{name}.rs') for name in names}


TRUTH = {
    'include': _pairs(MODULE | LOCAL | UNKNOWN) | {BACK},
    'exclude': _pairs(MODULE | UNKNOWN) | {BACK},
    'only': _pairs(LOCAL),
}


def _crate(root):
    root.mkdir()
    root = root.resolve()  # macOS tmp is /private/var
    (root / 'src').mkdir()
    (root / 'Cargo.toml').write_text(CARGO, encoding='utf-8')
    mods = ['imp', *TARGETS]
    (root / 'src' / 'lib.rs').write_text(''.join(f'pub mod {m};\n' for m in mods), encoding='utf-8')
    (root / 'src' / 'imp.rs').write_text(IMP, encoding='utf-8')
    for name in TARGETS:
        const = name[2:].upper()
        (root / 'src' / f'{name}.rs').write_text(f'pub const {const}: i32 = 1;\n', encoding='utf-8')
    (root / 'src' / 't_fn.rs').write_text(
        'pub const FN: i32 = 1;\nuse crate::imp::IMP;\npub fn back() -> i32 { IMP }\n', encoding='utf-8')
    return root


def _query(root, query):
    out = _run_reveal_direct(f'imports://{to_posix(root)}?{query}&scope=path', '--format', 'json')
    return out, json.loads(out.stdout)


def _views(root):
    """{mode: {(importer, target)}} from the public importer summary, and each mode's edge_rule."""
    pairs, rules = {}, {}
    for mode in ('include', 'exclude', 'only'):
        out, answer = _query(root, f'importers&lazy={mode}')
        assert out.returncode == 0, out.stderr
        pairs[mode] = {(importer, row['file']) for row in answer['entries'] for importer in row['importers']}
        rules[mode] = answer['edge_rule']
    return pairs, rules


def test_every_use_keeps_its_identity_and_gains_its_lexical_scope(tmp_path):
    root = _crate(tmp_path / 'fx')
    statements = RustExtractor().extract_imports(root / 'src' / 'imp.rs')
    got = [(s.line_number, s.module_name, s.imported_names, s.alias, s.scope) for s in statements]
    assert sorted(got, key=lambda row: row[0]) == IMP_STATEMENTS
    assert {s.dynamic for s in statements} == {False}
    assert not any('t_macro' in s.module_name for s in statements)


@pytest.mark.parametrize('source,scope', [
    ('use crate::a::{b, c::{d, e as f}};\n', 'module'),
    ('fn g() {\n    use crate::a::{b, c::{d, e as f}};\n}\n', 'local'),
    ('fn g() {\n    let k = |x: i32| { use crate::a::{b, c::{d, e as f}}; x };\n}\n', 'local'),
    ('static G: fn() = || { use crate::a::{b, c::{d, e as f}}; };\n', None),
])
def test_a_grouped_use_gives_every_path_the_same_scope(tmp_path, source, scope):
    path = tmp_path / 'g.rs'
    path.write_text(source, encoding='utf-8')
    statements = RustExtractor().extract_imports(path)
    assert [s.module_name for s in statements] == ['crate::a::b', 'crate::a::c::d', 'crate::a::c::e']
    assert {s.scope for s in statements} == {scope}


def test_scope_annotation_changes_no_other_extracted_field(tmp_path):
    """Control: the slice only adds scope and dynamic; every other field equals the raw parse."""
    root = _crate(tmp_path / 'fx')
    path = root / 'src' / 'imp.rs'
    extractor = RustExtractor()
    annotated = extractor.extract_imports(path)
    analyzer = extractor._get_tree_analyzer(path)
    raw = [s for node in analyzer._find_nodes_by_type('use_declaration')
           for s in extractor._parse_use_declaration(node, path, analyzer)]
    assert len(raw) == len(annotated) == len(IMP_STATEMENTS)
    for old, new in zip(raw, annotated, strict=True):
        old_fields, new_fields = asdict(old), asdict(new)
        assert old_fields.pop('scope') is None and old_fields.pop('dynamic') is None
        new_fields.pop('scope')
        new_fields.pop('dynamic')
        assert old_fields == new_fields


def test_public_modes_partition_the_same_union(tmp_path):
    root = _crate(tmp_path / 'fx')
    pairs, rules = _views(root)
    assert pairs == TRUTH
    assert pairs['exclude'] | pairs['only'] == pairs['include']
    assert not pairs['exclude'] & pairs['only']
    for rule in rules.values():
        assert rule['unclassified_edges'] == 1
        assert rule['unclassified_languages'] == ['rust']
    assert 'Import scope is unknown for 1 edge(s) in rust' in rules['only']['text']


def test_mixed_pair_counts_as_module_and_unknown_is_never_local_only(tmp_path):
    root = _crate(tmp_path / 'fx')
    pairs, _rules = _views(root)
    mixed, unknown = ('src/imp.rs', 'src/t_mixed.rs'), ('src/imp.rs', 'src/t_static_closure.rs')
    assert mixed in pairs['include'] and mixed in pairs['exclude'] and mixed not in pairs['only']
    assert unknown in pairs['include'] and unknown in pairs['exclude'] and unknown not in pairs['only']


def test_truth_sets_reject_an_ignored_filter_and_wrong_scopes():
    """The three expected sets differ, so an ignored &lazy or a one-scope labelling cannot match."""
    assert len({frozenset(pairs) for pairs in TRUTH.values()}) == 3
    every = TRUTH['include']
    assert TRUTH['exclude'] != every and TRUTH['only'] != every
    assert TRUTH['only'] and TRUTH['exclude'] - {BACK}


def test_ignored_filter_mutation_is_caught(tmp_path, monkeypatch):
    root = _crate(tmp_path / 'fx')
    monkeypatch.setattr(ImportGraph, 'edge_view', lambda self, lazy: self)
    pairs, _rules = _views(root)
    assert pairs['include'] == TRUTH['include']
    assert pairs['exclude'] != TRUTH['exclude'] and pairs['only'] != TRUTH['only']


@pytest.mark.parametrize('wrong', ['module', 'local'])
def test_wrong_scope_mutation_keeps_the_union_and_breaks_a_mode(tmp_path, monkeypatch, wrong):
    root = _crate(tmp_path / 'fx')
    monkeypatch.setattr(rust, 'edge_scope', lambda node, **_kw: wrong)
    pairs, _rules = _views(root)
    assert pairs['include'] == TRUTH['include']
    broken = 'only' if wrong == 'module' else 'exclude'
    assert pairs[broken] != TRUTH[broken]


@pytest.mark.parametrize('mode', ['include', 'exclude', 'only'])
def test_empty_target_and_missing_target_in_each_mode(tmp_path, mode):
    root = _crate(tmp_path / 'fx')
    out, empty = _query(root, f'importers=src/t_unused.rs&lazy={mode}')
    assert out.returncode == 0, out.stderr
    assert empty['count'] == 0 and empty['importers'] == []
    out, macro = _query(root, f'importers=src/t_macro.rs&lazy={mode}')
    assert out.returncode == 0 and macro['importers'] == []
    missing = _run_reveal_direct(f'imports://{to_posix(root)}?importers=src/missing.rs&scope=path&lazy={mode}',
                                 '--format', 'json')
    assert missing.returncode == 2


@pytest.mark.parametrize('mode', ['include', 'exclude', 'only'])
def test_partial_input_stays_incomplete(tmp_path, mode):
    root = _crate(tmp_path / 'fx')
    (root / 'src' / 'broken.rs').write_text('fn broken( {{{\n', encoding='utf-8')
    out, partial = _query(root, f'importers&lazy={mode}')
    assert out.returncode == 3, out.stderr
    assert partial['metadata']['files_failed_count'] == 1


def test_a_cycle_closed_only_by_a_fn_local_use_leaves_the_default_cycle_view(tmp_path):
    """`?circular` reads the module-scope view (BACK-2077): the imp <-> t_fn cycle runs through the
    fn-local `use crate::t_fn::FN`, so only &lazy=include still reports it."""
    root = _crate(tmp_path / 'fx')
    out, default = _query(root, 'circular')
    assert out.returncode == 0, out.stderr
    assert default['count'] == 0
    out, union = _query(root, 'circular&lazy=include')
    assert out.returncode == 0 and union['count'] == 1


def test_a_module_scope_back_edge_is_still_a_cycle(tmp_path):
    """Control for the control: the same back-edge at module scope closes a cycle in the default view."""
    root = _crate(tmp_path / 'fx')
    imp = root / 'src' / 'imp.rs'
    imp.write_text('use crate::t_fn::FN;\n' + IMP, encoding='utf-8')
    out, default = _query(root, 'circular')
    assert out.returncode == 0, out.stderr
    assert default['count'] == 1


def test_other_bespoke_and_generic_extractors_keep_unknown_scope(tmp_path):
    """Negative control: Zig and Lua (still BACK-2079) are not classified by the Rust slice."""
    zig = tmp_path / 'a.zig'
    zig.write_text('pub fn f() void {\n    const a = @import("b.zig");\n    _ = a;\n}\n', encoding='utf-8')
    lua = tmp_path / 'a.lua'
    lua.write_text("local function f() return require('b') end\n", encoding='utf-8')
    assert {s.scope for s in ZigImportExtractor().extract_imports(zig)} == {None}
    assert {s.scope for s in LuaImportExtractor().extract_imports(lua)} == {None}


@pytest.mark.disk_cache
def test_scope_survives_cache_layers_and_file_edit(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    path = tmp_path / 'source.rs'
    path.write_text('fn f() {\n    use crate::a::B;\n}\n', encoding='utf-8')
    real = RustExtractor._extract_imports_uncached
    calls = []

    def counted(self, *args):
        calls.append(1)
        return real(self, *args)

    monkeypatch.setattr(RustExtractor, '_extract_imports_uncached', counted)
    cold = RustExtractor().extract_imports(path)
    cold[0].scope = 'poison'
    warm = RustExtractor().extract_imports(path)
    rust._IMPORTS_CACHE.clear()
    disk = RustExtractor().extract_imports(path)
    assert len(calls) == 1
    assert warm[0].scope == disk[0].scope == 'local'
    rust._IMPORTS_CACHE.clear()
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    cache_off = RustExtractor().extract_imports(path)
    assert len(calls) == 2 and asdict(cache_off[0]) == asdict(warm[0])
    path.write_text('use crate::a::B;\nfn f() {}\n', encoding='utf-8')
    edited = RustExtractor().extract_imports(path)
    assert len(calls) == 3 and edited[0].scope == 'module'
