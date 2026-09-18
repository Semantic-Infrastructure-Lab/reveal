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
    ('.dart', 'dart', "void f(){ helper(); a.b(); new Foo(); const Bar(1); a..c(); }",
     {'helper', 'b', 'Foo', 'Bar', 'c'}),
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


@pytest.mark.parametrize('suffix,language,src,must_have', CASES, ids=[c[0] for c in CASES])
def test_analyzer_and_nav_paths_find_the_same_calls(tmp_path, suffix, language, src, must_have):
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

    analyzer_bare, nav_bare = _bare(analyzer_calls), _bare(nav_calls)
    assert must_have <= analyzer_bare, f'analyzer lost {must_have - analyzer_bare}'
    assert analyzer_bare == nav_bare, (
        f'paths disagree: only-analyzer={sorted(analyzer_bare - nav_bare)} '
        f'only-nav={sorted(nav_bare - analyzer_bare)}'
    )
    assert '()' not in nav_calls
