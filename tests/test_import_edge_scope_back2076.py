"""BACK-2076: an import's edge scope comes from one shared, language-neutral helper.

``node_taxonomy.edge_scope(node)`` walks from a node up to the nearest function-like
ancestor: ``DEF_NODES | LAMBDA_NODES`` (``LOCAL_SCOPE_NODES``), not ``FUNCTION_TYPES``,
which also holds the class, struct and impl kinds. A Python class body runs when the module
loads, so an import there is ``module``; a def nested in that class is ``local``. The tag is
positional, not a runtime claim: a Rust fn-local ``use`` is ``local`` without being lazy.

Each grammar below has one snippet. Every ``mod_*`` identifier must read ``module`` and
every ``loc_*`` identifier ``local``. A ``gap_*`` identifier sits in a function body that
``edge_scope`` does not see yet; it is a strict expected failure naming the task. The
grammar-coverage check for function-like kinds is in ``tests/test_grammar_coverage.py``
(``LOCAL_SCOPE_GAPS``).

Python is the first extractor on the helper (``ImportStatement.scope``). ``resolve_graph``
still drops by the old ``is_in_function`` walk, which also calls a *decorated* class body
local; the strict xfails at the end hold that disagreement until it is decided.
"""

import json
import re

import pytest
import tree_sitter_language_pack as ts

from conftest import _run_reveal_direct
from reveal.analyzers.imports.javascript import extract_js_imports
from reveal.analyzers.imports.python import extract_python_imports
from reveal.core import node_children, node_taxonomy
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root
from reveal.utils.path_utils import to_posix

# grammar -> source. Identifiers: mod_* -> 'module', loc_* -> 'local', gap_* -> GAPS.
SNIPPETS = {
    'python': (
        'import mod_a\n'
        'class K:\n'
        '    import mod_b\n'
        '    def m(self):\n'
        '        import loc_a\n'
        '@deco\n'
        'class D:\n'
        '    import mod_c\n'
        '    class Nested:\n'
        '        import mod_d\n'
        '    @staticmethod\n'
        '    def s():\n'
        '        import loc_b\n'
        'def f():\n'
        '    class Inner:\n'
        '        import loc_c\n'
        '    g = lambda: loc_d\n'
        '@deco\n'
        'def h():\n'
        '    import loc_e\n'
    ),
    'javascript': (
        "const a = require('x'); mod_a;\n"
        'function f() { loc_a; }\n'
        'const g = () => loc_b;\n'
        'class K { m() { loc_c; } }\n'
        'function* gen() { loc_d; }\n'
        'const h = function () { gap_a; };\n'
        'const k = function* () { gap_b; };\n'
    ),
    'typescript': (
        "import { x } from './x'; mod_a;\n"
        'function f(): void { loc_a; }\n'
        'const g = (): number => loc_b;\n'
        'class K { m(): void { loc_c; } }\n'
        'const h = function (): void { gap_a; };\n'
        'const k = function* (): Generator<number> { gap_b; };\n'
    ),
    'tsx': (
        "import { x } from './x'; mod_a;\n"
        'function f(): void { loc_a; }\n'
        'const g = (): number => loc_b;\n'
        'class K { m(): void { loc_c; } }\n'
        'const h = function (): void { gap_a; };\n'
        'const k = function* (): Generator<number> { gap_b; };\n'
    ),
    'rust': (
        'use mod_a;\n'
        'struct S { x: i32 }\n'
        'impl S {\n    const C: i32 = mod_b;\n    fn m(&self) { use loc_a; }\n}\n'
        'fn f() { use loc_b; let c = || loc_c; }\n'
        'mod inner { use mod_c; }\n'
        'trait T { fn d() { use loc_d; } }\n'
        'static G: fn() = || { gap_a; };\n'
    ),
    'go': (
        'package main\n'
        'import mod_a "fmt"\n'
        'var v = mod_b\n'
        'func f() { loc_a() }\n'
        'func (s S) m() { loc_b() }\n'
    ),
    'c': (
        'int mod_a;\n'
        'struct S { int mod_b; };\n'
        'void f(void) { loc_a; }\n'
    ),
    'cpp': (
        'int mod_a;\n'
        'class K { int mod_b; void m() { loc_a; } };\n'
        'namespace n { int mod_c; }\n'
        'void f() { loc_b; }\n'
        'auto l = []() { gap_a; };\n'
    ),
    'java': (
        'import mod_a.X;\n'
        'class K {\n  int f = mod_b;\n  void m() { loc_a(); }\n  K() { loc_b(); }\n}\n'
    ),
    'csharp': (
        'using mod_a;\n'
        'namespace N {\n  class K {\n    int f = mod_b;\n    void M() { loc_a(); }\n'
        '    K() { loc_b(); }\n  }\n}\n'
    ),
    'php': (
        '<?php\n'
        'use mod_a;\n'
        'function f() { loc_a(); }\n'
        'class K { const C = mod_b; function m() { loc_b(); } }\n'
        '$g = fn() => loc_c;\n'
        '$h = function () { gap_a(); };\n'
    ),
    'ruby': (
        "require 'x'\n"
        'mod_a\n'
        'class K\n  mod_b\n  def m\n    loc_a\n  end\n  def self.s\n    loc_b\n  end\nend\n'
        'l = -> { loc_c }\n'
        'items.each do\n  gap_a\nend\n'
    ),
    'swift': (
        'import mod_a\n'
        'func f() { loc_a() }\n'
        'class K {\n  var x = mod_b\n  init() { loc_b() }\n  func m() { loc_c() }\n'
        '  deinit { loc_d() }\n}\n'
    ),
    'kotlin': (
        'import mod_a.B\n'
        'fun f() { loc_a }\n'
        'class K {\n    val x = mod_b\n    fun m() { loc_b }\n}\n'
    ),
    'scala': (
        'import mod_a.B\n'
        'object O {\n  val x = mod_b\n  def f(): Int = {\n    import loc_a.C\n    1\n  }\n}\n'
        'class K { def m() = loc_b }\n'
        'val g = (x: Int) => gap_a\n'
    ),
    'dart': (
        "import 'x.dart';\n"
        'var v = mod_a;\n'
        'class K {\n  int x = mod_b;\n  int m() { return gap_a; }\n}\n'
        'void f() { gap_b; }\n'
    ),
    'gdscript': (
        'extends Node\n'
        'const A = mod_a\n'
        'func f():\n\tvar x = loc_a\n'
        'func _init():\n\tvar y = loc_b\n'
        'var l = func(): return loc_c\n'
        'class Inner:\n\tvar z = mod_b\n'
        'var p:\n\tget:\n\t\treturn gap_a\n'
    ),
    'lua': (
        'local a = mod_a\n'
        'local function f() return loc_a end\n'
        'function g() return loc_b end\n'
        'local h = function() return loc_c end\n'
    ),
    'zig': (
        'const a = mod_a;\n'
        'pub fn f() void {\n    _ = loc_a;\n}\n'
        'const S = struct {\n    const b = mod_b;\n'
        '    fn m() void {\n        _ = loc_b;\n    }\n};\n'
    ),
}

# (grammar, gap identifier) -> why it reads 'module' today. Keep in step with
# tests/test_grammar_coverage.py LOCAL_SCOPE_GAPS.
GAPS = {
    ('javascript', 'gap_a'): 'BACK-2078: function_expression is not in LOCAL_SCOPE_NODES',
    ('typescript', 'gap_a'): 'BACK-2078: function_expression is not in LOCAL_SCOPE_NODES',
    ('tsx', 'gap_a'): 'BACK-2078: function_expression is not in LOCAL_SCOPE_NODES',
    ('javascript', 'gap_b'): 'BACK-2078: generator_function is not in LOCAL_SCOPE_NODES',
    ('typescript', 'gap_b'): 'BACK-2078: generator_function is not in LOCAL_SCOPE_NODES',
    ('tsx', 'gap_b'): 'BACK-2078: generator_function is not in LOCAL_SCOPE_NODES',
    ('gdscript', 'gap_a'): 'BACK-2079: a GDScript 4 property get_body is not in LOCAL_SCOPE_NODES',
    ('rust', 'gap_a'): 'BACK-2079: closure_expression is not in LOCAL_SCOPE_NODES',
    ('cpp', 'gap_a'): 'BACK-2079: lambda_expression is not in LOCAL_SCOPE_NODES',
    ('php', 'gap_a'): 'BACK-2079: anonymous_function is not in LOCAL_SCOPE_NODES',
    ('ruby', 'gap_a'): 'BACK-2079: do_block is not in LOCAL_SCOPE_NODES',
    ('scala', 'gap_a'): 'BACK-2079: lambda_expression is not in LOCAL_SCOPE_NODES',
    # Dart's function_signature is the sibling of its function_body, not its parent, so no
    # walk up from the body meets it. Dart imports are file-level only, so no edge moves
    # (tests/test_grammar_coverage.py lists the kind in NOT_LOCAL_SCOPE for that reason).
    ('dart', 'gap_a'): 'BACK-2079: a Dart method body is the sibling of its signature',
    ('dart', 'gap_b'): 'BACK-2079: a Dart function body is the sibling of its signature',
}

_MARKER = re.compile(r'(?:mod|loc|gap)_[a-z]')


def _text(node, source: bytes) -> str:
    return source[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')


def _markers(grammar: str):
    """{marker: deepest node spelling exactly that marker} for one snippet."""
    src = SNIPPETS[grammar]
    root = tree_root(ts_parse(ts.get_parser(grammar), src))
    source = src.encode('utf-8')
    found = {}
    stack = [root]
    while stack:
        node = stack.pop()
        text = _text(node, source)
        if _MARKER.fullmatch(text):
            found[text] = node  # deeper nodes are popped later and overwrite
        stack.extend(node_children(node))
    return found


def _cases():
    for grammar, src in SNIPPETS.items():
        for marker in sorted(set(_MARKER.findall(src))):
            expected = 'module' if marker.startswith('mod_') else 'local'
            marks = []
            if marker.startswith('gap_'):
                marks.append(pytest.mark.xfail(strict=True, reason=GAPS[(grammar, marker)],
                                               raises=AssertionError))
            yield pytest.param(grammar, marker, expected, id=f'{grammar}-{marker}', marks=marks)


@pytest.mark.parametrize('grammar,marker,expected', list(_cases()))
def test_edge_scope_per_grammar(grammar, marker, expected):
    node = _markers(grammar)[marker]
    assert node_taxonomy.edge_scope(node) == expected


@pytest.mark.parametrize('grammar', sorted(SNIPPETS))
def test_every_snippet_parses_and_has_both_scopes(grammar):
    """Positive control: each snippet parses cleanly and has a module and a local case."""
    root = tree_root(ts_parse(ts.get_parser(grammar), SNIPPETS[grammar]))
    assert not _zero_arg(root, 'has_error'), grammar
    markers = set(_markers(grammar))
    assert {m for m in markers if m.startswith('mod_')}, markers
    assert {m for m in markers if m.startswith(('loc_', 'gap_'))}, markers


def test_every_gap_has_a_snippet():
    for grammar, marker in GAPS:
        assert marker in _markers(grammar), (grammar, marker)


def test_local_scope_nodes_are_defs_and_lambdas_not_containers():
    """The family holds no class, struct or impl kind: those bodies run at load time."""
    assert node_taxonomy.LOCAL_SCOPE_NODES == node_taxonomy.DEF_NODES | node_taxonomy.LAMBDA_NODES
    containers = node_taxonomy.CLASS_NODES | node_taxonomy.STRUCT_NODES | node_taxonomy.IMPL_NODES
    assert not node_taxonomy.LOCAL_SCOPE_NODES & containers


def test_zig_decl_is_local_only_with_a_function_prototype():
    """Zig wraps every top-level declaration in Decl; a const Decl is module scope."""
    markers = _markers('zig')
    decl_parents = []
    node = _zero_arg(markers['mod_a'], 'parent')
    while node is not None:
        decl_parents.append(_zero_arg(node, 'kind'))
        node = _zero_arg(node, 'parent')
    assert 'Decl' in decl_parents, 'positive control: the module-scope const sits in a Decl'
    assert node_taxonomy.edge_scope(markers['mod_a']) == 'module'
    assert node_taxonomy.edge_scope(markers['loc_a']) == 'local'


# ---------------------------------------------------------------------------
# Python: the first extractor on the helper
# ---------------------------------------------------------------------------

PY_SOURCE = (
    'import top\n'
    'from typing import TYPE_CHECKING\n'
    'if TYPE_CHECKING:\n'
    '    import typed\n'
    'class K:\n'
    '    import class_body\n'
    '    def m(self):\n'
    '        import method_body\n'
    '    class Nested:\n'
    '        import nested_class_body\n'
    '@deco\n'
    'class D:\n'
    '    import decorated_class_body\n'
    '    def m(self):\n'
    '        from . import decorated_method_body\n'
    'def f():\n'
    '    import function_body\n'
    '    class Inner:\n'
    '        import class_in_function\n'
    '@deco\n'
    'def g():\n'
    '    from x import decorated_function_body\n'
)
PY_SCOPE = {
    'top': 'module', 'TYPE_CHECKING': 'module', 'typed': 'module',
    'class_body': 'module', 'nested_class_body': 'module', 'decorated_class_body': 'module',
    'method_body': 'local', 'decorated_method_body': 'local', 'function_body': 'local',
    'class_in_function': 'local', 'decorated_function_body': 'local',
}


def _python_imports(tmp_path):
    path = tmp_path / 'scopes.py'
    path.write_text(PY_SOURCE, encoding='utf-8')
    imports = extract_python_imports(path)
    assert len(imports) == len(PY_SCOPE), [s.module_name for s in imports]
    return {stmt.imported_names[0] if stmt.import_type == 'from_import' else stmt.module_name: stmt
            for stmt in imports}


def test_python_import_scope_comes_from_the_helper(tmp_path):
    by_name = _python_imports(tmp_path)
    assert {name: stmt.scope for name, stmt in by_name.items()} == PY_SCOPE


def test_python_scope_is_independent_of_type_checking(tmp_path):
    by_name = _python_imports(tmp_path)
    assert by_name['typed'].is_type_checking and by_name['typed'].scope == 'module'
    assert not by_name['function_body'].is_type_checking


def test_python_import_statements_are_not_dynamic(tmp_path):
    """An ``import`` statement is a declaration; importlib calls are not extracted."""
    assert {stmt.dynamic for stmt in _python_imports(tmp_path).values()} == {False}


def test_python_scope_and_the_resolve_graph_drop_agree_outside_decorated_classes(tmp_path):
    """``is_in_function`` is what resolve_graph drops by; outside a decorated class it is
    exactly ``scope == 'local'``."""
    by_name = _python_imports(tmp_path)
    disagree = {name for name, stmt in by_name.items()
                if stmt.is_in_function != (stmt.scope == 'local')}
    assert disagree == {'decorated_class_body'}


# ---------------------------------------------------------------------------
# JavaScript/TypeScript: the dynamic flag (scope opts in with BACK-2078)
# ---------------------------------------------------------------------------

JS_SOURCE = (
    "import { a } from './static_import';\n"
    "export { b } from './re_export';\n"
    "const c = require('./commonjs_require');\n"
    "require('./side_effect_require');\n"
    "export async function f() { return import('./dynamic_import'); }\n"
)


def test_javascript_dynamic_flag(tmp_path):
    path = tmp_path / 'm.js'
    path.write_text(JS_SOURCE, encoding='utf-8')
    by_name = {stmt.module_name[2:]: stmt for stmt in extract_js_imports(path)}
    assert {name: stmt.dynamic for name, stmt in by_name.items()} == {
        'static_import': False, 're_export': False,
        'commonjs_require': True, 'side_effect_require': True, 'dynamic_import': True,
    }
    assert {stmt.scope for stmt in by_name.values()} == {None}, (
        'JS/TS scope is not recorded yet: resolve_graph would drop its local edges (BACK-2078)')


# ---------------------------------------------------------------------------
# The open decision: resolve_graph still drops a decorated class body's import
# ---------------------------------------------------------------------------

DECORATED = ('BACK-2076: resolve_graph drops by is_in_function, which calls a decorated class '
             'body local')


def _fan_out(root):
    out = _run_reveal_direct(f'imports://{to_posix(root)}?rank=fan-in', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return {to_posix(e['file']): e['fan_out'] for e in json.loads(out.stdout)['entries']}


def _tree(tmp_path, importer_text):
    root = (tmp_path / 'p').resolve()  # macOS tmp is /private/var
    root.mkdir()
    (root / 'b.py').write_text('X = 1\n', encoding='utf-8')
    (root / 'a.py').write_text(importer_text, encoding='utf-8')
    return root


def test_class_body_import_is_an_imports_edge(tmp_path):
    """Control: an undecorated class body's import is kept today."""
    root = _tree(tmp_path, 'class K:\n    import b\n')
    assert _fan_out(root)['a.py'] == 1


@pytest.mark.xfail(strict=True, reason=DECORATED, raises=AssertionError)
def test_decorated_class_body_import_is_an_imports_edge(tmp_path):
    root = _tree(tmp_path, 'def deco(c):\n    return c\n@deco\nclass K:\n    import b\n')
    assert _fan_out(root)['a.py'] == 1


def test_function_body_import_is_still_dropped(tmp_path):
    """Negative control: BACK-445's drop of a function-body import is unchanged."""
    root = _tree(tmp_path, 'def f():\n    import b\n')
    assert _fan_out(root)['a.py'] == 0
