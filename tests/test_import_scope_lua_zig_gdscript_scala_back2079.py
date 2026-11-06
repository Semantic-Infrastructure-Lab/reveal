"""BACK-2079: Lua, Zig, GDScript and Scala imports record their lexical scope.

The shared owner ``node_taxonomy.edge_scope`` tags each import ``module`` or ``local``
(BACK-2076), as it already does for Python, PHP, JavaScript/TypeScript/TSX, Rust and a Ruby
subset. Before this slice these four languages left ``scope=None``: every edge was disclosed as
unclassified, retained by ``&lazy=include`` and ``exclude`` and dropped by ``only``.

Per language, from the language's own rules:

- Lua: ``require`` is a runtime call, so one in any function body (``local function``, a global
  or ``M:method`` function, an anonymous function in a table) is local and genuinely deferred.
- Zig: ``@import`` in a ``fn`` body is local (positional; Zig resolves it at compile time and
  allows import cycles). A struct-level ``const`` is module scope.
- Scala: an ``import`` in a ``def`` body block is local (positional: it binds names in that
  block). A lambda outside every ``def`` confers no scope here, so that edge stays unclassified.
- GDScript: ``load()`` in a ``func`` or lambda is local and deferred. ``preload()`` is resolved
  when the script is parsed wherever it is written, so one inside a ``func`` is NOT tagged local:
  it stays unclassified and keeps counting in the load-time (``exclude``) view and its cycles.
  A property getter/setter body confers no scope here (unclassified).
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.analyzers.imports.generic import (DartImportExtractor, GDScriptImportExtractor,
                                              LuaImportExtractor, ScalaImportExtractor,
                                              SwiftImportExtractor)
from reveal.analyzers.imports.zig import ZigImportExtractor
from reveal.utils.path_utils import to_posix

pytestmark = pytest.mark.component

LANGS = {
    'lua': {
        'files': {
            'imp.lua': ("local m = require('t_mod')\n"
                        "local function f() return require('t_fn') end\n"
                        "function g() return require('t_global_fn') end\n"
                        "local M = {}\n"
                        "function M:meth() return require('t_method') end\n"
                        "local t = { h = function() return require('t_anon') end }\n"
                        "return M\n"),
            't_fn.lua': "local imp = require('imp')\nreturn {}\n",
        },
        'targets': ['t_mod', 't_fn', 't_global_fn', 't_method', 't_anon'],
        'target_file': '{}.lua',
        'module': {'t_mod'}, 'local': {'t_fn', 't_global_fn', 't_method', 't_anon'}, 'unknown': set(),
        'importer': 'imp.lua', 'dynamic': True, 'extractor': LuaImportExtractor,
    },
    'zig': {
        'files': {
            'imp.zig': ('const m = @import("t_mod.zig");\n'
                        'pub fn f() void {\n    const a = @import("t_fn.zig");\n    _ = a;\n}\n'
                        'const S = struct {\n    const b = @import("t_struct.zig");\n'
                        '    fn meth() void {\n        const c = @import("t_method.zig");\n        _ = c;\n    }\n};\n'),
            't_fn.zig': 'const imp = @import("imp.zig");\npub const x = 1;\n',
        },
        'targets': ['t_mod', 't_fn', 't_struct', 't_method'],
        'target_file': '{}.zig',
        'module': {'t_mod', 't_struct'}, 'local': {'t_fn', 't_method'}, 'unknown': set(),
        'importer': 'imp.zig', 'dynamic': False, 'extractor': ZigImportExtractor,
    },
    'scala': {
        'files': {
            'app/Imp.scala': ('package app\n\nimport pkg.TMod\n\nobject Imp {\n  val x = TMod.v\n'
                              '  def f(): Int = {\n    import pkg.TFn\n    TFn.v\n  }\n'
                              '  val g = (y: Int) => {\n    import pkg.TLambda\n    TLambda.v\n  }\n}\n'
                              'class K {\n  def m(): Int = {\n    import pkg.TMethod\n    TMethod.v\n  }\n}\n'),
            'pkg/TFn.scala': 'package pkg\n\nimport app.Imp\n\nobject TFn {\n  val v = 1\n}\n',
        },
        'targets': ['TMod', 'TFn', 'TLambda', 'TMethod'],
        'target_file': 'pkg/{}.scala',
        'module': {'TMod'}, 'local': {'TFn', 'TMethod'}, 'unknown': {'TLambda'},
        'importer': 'app/Imp.scala', 'dynamic': False, 'extractor': ScalaImportExtractor,
    },
    'gdscript': {
        'files': {
            'imp.gd': ('extends "res://t_base.gd"\n'
                       'const M = preload("res://t_mod.gd")\n'
                       'func f():\n\tvar a = load("res://t_fn.gd")\n'
                       'func g():\n\tvar b = preload("res://t_preload_fn.gd")\n'
                       'var l = func(): return load("res://t_lambda.gd")\n'
                       'var p:\n\tget:\n\t\treturn load("res://t_getter.gd")\n'),
            't_fn.gd': 'extends Node\nconst I = preload("res://imp.gd")\n',
        },
        'targets': ['t_mod', 't_fn', 't_preload_fn', 't_lambda', 't_getter', 't_base'],
        'target_file': '{}.gd',
        'module': {'t_mod', 't_base'}, 'local': {'t_fn', 't_lambda'}, 'unknown': {'t_preload_fn', 't_getter'},
        # `extends` is a declaration (dynamic False); preload/load are loader calls.
        'importer': 'imp.gd', 'dynamic': True, 'declarations': {'t_base'}, 'extractor': GDScriptImportExtractor,
    },
}

_TARGET_SOURCE = {
    'lua': lambda name: 'return {}\n',
    'zig': lambda name: 'pub const x = 1;\n',
    'scala': lambda name: f'package pkg\n\nobject {name} {{\n  val v = 1\n}}\n',
    'gdscript': lambda name: 'extends Node\n',
}


def _project(tmp_path, lang):
    spec = LANGS[lang]
    root = (tmp_path / lang)
    root.mkdir()
    root = root.resolve()  # macOS tmp is /private/var
    for name in spec['targets']:
        path = root / spec['target_file'].format(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_TARGET_SOURCE[lang](name), encoding='utf-8')
    for rel, text in spec['files'].items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


def _truth(lang):
    spec = LANGS[lang]
    pairs = lambda names: {(spec['importer'], spec['target_file'].format(n)) for n in names}  # noqa: E731
    back = (spec['target_file'].format(spec['targets'][1]), spec['importer'])
    return {
        'include': pairs(spec['module'] | spec['local'] | spec['unknown']) | {back},
        'exclude': pairs(spec['module'] | spec['unknown']) | {back},
        'only': pairs(spec['local']),
    }


def _query(root, query):
    out = _run_reveal_direct(f'imports://{to_posix(root)}?{query}&scope=path', '--format', 'json')
    return out, json.loads(out.stdout)


def _views(root):
    pairs, rules = {}, {}
    for mode in ('include', 'exclude', 'only'):
        out, answer = _query(root, f'importers&lazy={mode}')
        assert out.returncode == 0, out.stderr
        pairs[mode] = {(importer, row['file']) for row in answer['entries'] for importer in row['importers']}
        rules[mode] = answer['edge_rule']
    return pairs, rules


@pytest.mark.parametrize('lang', sorted(LANGS))
def test_each_import_gets_its_lexical_scope(tmp_path, lang):
    spec = LANGS[lang]
    root = _project(tmp_path, lang)
    statements = spec['extractor']().extract_imports(root / spec['importer'])
    got = {}
    for stmt in statements:
        name = next(n for n in spec['targets'] if n in stmt.module_name)
        got[name] = stmt.scope
    expected = {**{n: 'module' for n in spec['module']}, **{n: 'local' for n in spec['local']},
                **{n: None for n in spec['unknown']}}
    assert got == expected
    declarations = spec.get('declarations', set())
    dynamic = {next(n for n in spec['targets'] if n in stmt.module_name): stmt.dynamic for stmt in statements}
    assert dynamic == {n: (not spec['dynamic'] if n in declarations else spec['dynamic']) for n in got}


@pytest.mark.parametrize('lang', sorted(LANGS))
def test_public_modes_partition_the_same_union(tmp_path, lang):
    root = _project(tmp_path, lang)
    pairs, rules = _views(root)
    assert pairs == _truth(lang)
    assert pairs['exclude'] | pairs['only'] == pairs['include']
    assert not pairs['exclude'] & pairs['only']
    unknown = len(LANGS[lang]['unknown'])
    for rule in rules.values():
        assert rule['unclassified_edges'] == unknown
        assert rule['unclassified_languages'] == ([lang] if unknown else [])


@pytest.mark.parametrize('lang', sorted(LANGS))
def test_a_cycle_closed_only_by_a_local_import_leaves_the_default_cycle_view(tmp_path, lang):
    root = _project(tmp_path, lang)
    out, default = _query(root, 'circular')
    assert out.returncode == 0, out.stderr
    assert default['count'] == 0
    out, union = _query(root, 'circular&lazy=include')
    assert out.returncode == 0 and union['count'] == 1


def test_check_i002_reads_the_same_load_time_view(tmp_path):
    """A Lua cycle closed only by a require inside a function is not an I002 import cycle."""
    def i002_count(name, b_source):
        root = tmp_path / name  # a separate tree per case: no reuse of a cached graph
        root.mkdir()
        (root / 'a.lua').write_text("local b = require('b')\nreturn {}\n", encoding='utf-8')
        (root / 'b.lua').write_text(b_source, encoding='utf-8')
        out = _run_reveal_direct('check', to_posix(root), '--select', 'I002', '--format', 'json')
        return sum(len(entry.get('detections', [])) for entry in json.loads(out.stdout)['files'])

    assert i002_count('lazy', "local function f() return require('a') end\nreturn {f=f}\n") == 0
    assert i002_count('eager', "local a = require('a')\nreturn {}\n") == 2  # control: module level


def test_a_gdscript_preload_in_a_func_still_closes_a_load_time_cycle(tmp_path):
    """preload() resolves when the script is parsed, so its cycle stays in the default view."""
    root = _project(tmp_path, 'gdscript')
    (root / 't_preload_fn.gd').write_text('extends Node\nconst I = preload("res://imp.gd")\n', encoding='utf-8')
    out, default = _query(root, 'circular')
    assert out.returncode == 0, out.stderr
    assert default['count'] == 1


@pytest.mark.parametrize('lang', sorted(LANGS))
def test_missing_target_still_exits_2_in_each_mode(tmp_path, lang):
    root = _project(tmp_path, lang)
    for mode in ('include', 'exclude', 'only'):
        out = _run_reveal_direct(f'imports://{to_posix(root)}?importers=no_such_file&scope=path&lazy={mode}',
                                 '--format', 'json')
        assert out.returncode == 2, (mode, out.stderr)


def test_languages_outside_the_slice_keep_unknown_scope(tmp_path):
    """Negative control: Dart and Swift are not classified by this slice."""
    dart = tmp_path / 'a.dart'
    dart.write_text("import 'b.dart';\nvoid f() {}\n", encoding='utf-8')
    swift = tmp_path / 'a.swift'
    swift.write_text('import Foundation\nfunc f() {}\n', encoding='utf-8')
    assert {s.scope for s in DartImportExtractor().extract_imports(dart)} == {None}
    assert {s.scope for s in SwiftImportExtractor().extract_imports(swift)} == {None}
