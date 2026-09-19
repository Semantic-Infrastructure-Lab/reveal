"""End-to-end agreement between reveal's two call extractors (BACK-1279).

The analyzer path (treesitter.py, feeds structure `calls` / calls://) and the
nav path (core/nav_calls.py, feeds ast:// --calls/--sideeffects/--boundary)
extract callees independently. test_callee_dispatch_parity.py pins one node
kind at a time; this runs one realistic function per language through both and
compares the *bare* callee names -- the form calls:// indexes by -- so a call
shape that one path sees and the other misses fails here.

Receiver text may legitimately differ (`a.b().c` vs `.c` for a chained call);
that normalizes away in `_bare_callee_name`. What must not differ is which
calls exist. Found by this probe: Ruby paren-less calls (BACK-1299), Java
`new Foo()`, and a junk `()` callee on every Dart call, all nav-side gaps.
"""

import pytest
import tree_sitter_language_pack as ts

from reveal.adapters.calls.index import _bare_callee_name
from reveal.core.node_taxonomy import FUNCTION_TYPES
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root
from reveal.core import node_children
from reveal.core.nav_calls import range_calls
from reveal.registry import get_analyzer

# BACK-1149: guards an internal invariant/output-contract (registry, schema, or cross-module consistency)
pytestmark = pytest.mark.contract

# suffix, tree-sitter language, source (first function is compared), calls that
# MUST be present in both paths (bare names) -- guards against both paths
# agreeing on an empty set.
CASES = [
    ('.java', 'java', "class A { void f(){ Files.create(p); a.b().c(); helper(); new Foo(1); new Box<Integer>(); } }",
     {'create', 'c', 'helper', 'Foo', 'Box'}),
    ('.rb', 'ruby', "def f\n  helper\n  x.y\n  a.b.c\n  puts 'x'\nend\n",
     {'helper', 'y', 'c', 'puts'}),
    # BACK-1302: pure attribute writes (`r.modes = 1`) are not calls in either path;
    # `r.count += 1` reads first, so it is.
    ('.rb', 'ruby', "def f(r)\n  r.modes = 1\n  self.name = 'x'\n  r.count += 1\n  helper\nend\n",
     {'count', 'helper'}),
    # BACK-1305: parenthesized callees -- comma idiom resolves to the last operand,
    # assignment / inline-function callees have no name (IIFE body calls still count).
    ('.js', 'javascript', "function f(w){ var m; (0, w.x)(1); (m = w.O)(4); (function(){ inner(); })(); w.y(2); }",
     {'x', 'inner', 'y'}),
    ('.js', 'javascript', "function f(){ helper(); new Foo(); a.b.c(); a.b().c(); }",
     {'helper', 'Foo', 'c'}),
    ('.py', 'python', "def f():\n  helper()\n  a.b.c()\n  a.b().c()\n  Foo()\n",
     {'helper', 'c', 'Foo'}),
    ('.go', 'go', "package p\nfunc f(){ helper(); a.B(); a.B().C() }\n",
     {'helper', 'B', 'C'}),
    ('.php', 'php', "<?php function f(){ self::a(); $o->m(); Foo::bar(); new Baz(); helper(); }",
     {'a', 'm', 'bar', 'Baz', 'helper'}),
    ('.cpp', 'cpp', "void f(){ helper(); a.b(); new Foo(); a->c(); }",
     {'helper', 'b', 'Foo', 'c'}),
    ('.rs', 'rust', "fn f(){ helper(); a.b(); Foo::new(); x::<u32>(); }",
     {'helper', 'b', 'new', 'x'}),
    # super./this. receivers: `.member` is a bare sibling, not a `selector` (was `?`).
    ('.dart', 'dart', "void f(){ helper(); a.b(); new Foo(); const Bar(1); a..c(); super.initState(); this.z(); }",
     {'helper', 'b', 'Foo', 'Bar', 'c', 'initState', 'z'}),
    # Swift operators share `infix_expression` with Scala calls but are not calls.
    ('.swift', 'swift', "func f(a: Int, b: Int) { if a != b { g(a) }; let c = a |> h; let d = a >= b; foo(a) }",
     {'g', 'foo'}),
    # Kotlin annotations are `constructor_invocation` nodes (a Dart call kind) but not calls.
    ('.kt', 'kotlin', "@Suppress(\"x\") fun f() { helper(); a.b() }",
     {'helper', 'b'}),
    ('.scala', 'scala', "object O { def f() = { helper(); a.b(1); new Foo(); x foo y } }",
     {'helper', 'b', 'Foo', 'foo'}),
]


def _first_function(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') in FUNCTION_TYPES:
            # Dart's function node is only the signature; the body is a sibling.
            if _zero_arg(node, 'kind') == 'function_signature':
                return _zero_arg(node, 'parent')
            return node
        stack.extend(reversed(node_children(node)))
    raise AssertionError('no function node found')


def _bare(names):
    return {_bare_callee_name(n) for n in names if n}


def _both_paths(tmp_path, suffix, language, src):
    """(analyzer callees, nav callees) for the first function in `src`, raw strings."""
    path = tmp_path / f't{suffix}'
    path.write_text(src)
    analyzer = get_analyzer(str(path))(str(path))
    analyzer_calls = analyzer.get_structure()['functions'][0]['calls']

    content = src.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser(language), src))
    func_node = _first_function(root)

    def get_text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    nav_calls = [c['callee'] for c in range_calls(
        func_node, 1, 999, get_text,
        implicit_nodes=analyzer._implicit_call_nodes(func_node),
    )]
    return analyzer_calls, nav_calls


@pytest.mark.parametrize('suffix,language,src,must_have', CASES, ids=[c[0] for c in CASES])
def test_analyzer_and_nav_paths_find_the_same_calls(tmp_path, suffix, language, src, must_have):
    analyzer_calls, nav_calls = _both_paths(tmp_path, suffix, language, src)
    analyzer_bare, nav_bare = _bare(analyzer_calls), _bare(nav_calls)
    assert must_have <= analyzer_bare, f'analyzer lost {must_have - analyzer_bare}'
    assert analyzer_bare == nav_bare, (
        f'paths disagree: only-analyzer={sorted(analyzer_bare - nav_bare)} '
        f'only-nav={sorted(nav_bare - analyzer_bare)}'
    )
    assert '()' not in nav_calls


def test_ruby_attribute_writes_are_not_calls_in_either_path(tmp_path):
    path = tmp_path / 't.rb'
    path.write_text("def f(r)\n  r.modes = 1\n  self.name = 'x'\n  r.count += 1\nend\n")
    calls = get_analyzer(str(path))(str(path)).get_structure()['functions'][0]['calls']
    assert _bare(calls) == {'count'}


def test_unnameable_parenthesized_callees_emit_no_junk(tmp_path):
    path = tmp_path / 't.js'
    path.write_text("function f(w){ var m; (0, w.x)(1); (m = w.O)(4); (function(){ inner(); })(); }")
    calls = get_analyzer(str(path))(str(path)).get_structure()['functions'][0]['calls']
    assert calls == ['w.x', 'inner']


def test_prefix_operators_and_implicit_members_name_the_operand_in_both_paths(tmp_path):
    # BACK-1279: Swift `!isRunning(x)` / `.init(x)` and Scala `!a.b(x)` parse the callee as
    # prefix_expression; nav used to keep the operator ('!f', '.init') while the analyzer
    # already named the operand. Both now go through core/callees/generic.py.
    an, nav = _both_paths(tmp_path, '.swift', 'swift', "func f() { if !isRunning(1) { g() }; let v = T.init(2) }")
    assert 'isRunning' in an and 'isRunning' in nav
    assert not [c for c in nav if c.startswith(('!', '.'))]
    an, nav = _both_paths(tmp_path, '.scala', 'scala', "object O { def f() = { if (!a.b(1)) g() } }")
    assert 'a.b' in an and 'a.b' in nav


def test_chained_call_receiver_policy_is_the_only_intended_difference(tmp_path):
    # BACK-415: the index keeps the whole receiver (`a.b().c`); nav collapses it to `.c`
    # because the inner call is already its own edge. Everything else is shared.
    an, nav = _both_paths(tmp_path, '.js', 'javascript', "function f(){ a.b().c(); x.y(); }")
    assert 'a.b().c' in an and '.c' in nav
    assert 'x.y' in an and 'x.y' in nav


def test_java_generic_method_calls_keep_the_receiver_in_both_paths(tmp_path):
    # BACK-1279: `svc.<T>run(x)` puts type_arguments between '.' and the name; the nav-only
    # positional form lost the receiver ('run'). Named fields keep `svc.run` in both paths.
    an, nav = _both_paths(tmp_path, '.java', 'java', "class A { void f(){ svc.<String>run(1); new ArrayList<String>(); } }")
    assert 'svc.run' in an and 'svc.run' in nav
    assert 'new ArrayList' in an and 'new ArrayList' in nav  # generic suffix normalised in both


def test_php_dynamic_and_anonymous_class_instantiation_emit_no_junk(tmp_path):
    # `new $cls()` has no static name and `new class { ... }` used to emit its whole body as the
    # callee in the analyzer path; neither is a nameable call in either path now.
    an, nav = _both_paths(tmp_path, '.php', 'php', "<?php function f($cls){ new $cls(); $o = new class { public $x; }; new Real(); }")
    assert 'new Real' in an and 'new Real' in nav
    assert not [c for c in an + nav if c.startswith('new ') and c != 'new Real']


def test_cpp_new_names_the_class_in_both_paths(tmp_path):
    # BACK-1279: one C++ `new` extractor. Qualified and templated types collapse to the trailing
    # class name; non-class types (`new int[8]`) are allocations, not constructor calls.
    src = "void f(){ new Foo(1); new ns::Bar(2); new std::vector<int>(3); int* p = new int[8]; Baz obj(4); }"
    an, nav = _both_paths(tmp_path, '.cpp', 'cpp', src)
    for calls in (an, nav):
        assert {'new Foo', 'new Bar', 'new vector', 'Baz'} <= set(calls), calls
        assert 'new int' not in calls
