"""Scope rules of reveal's two call walkers, pinned before they are unified (BACK-1309).

The analyzer walker (`TreeSitterAnalyzer._complexity_depth_and_calls`, feeds
structure `calls` / calls://) and the nav walker (`core/nav_calls.range_calls`, feeds
ast:// --calls/--sideeffects/--boundary) find the same call *shapes* (see
test_callee_path_agreement.py) but walk different *scopes*:

| | analyzer | nav |
|---|---|---|
| nested named function | leaf (own entry) | included |
| anonymous callback / lambda | included | included |
| Dart nested function body (sibling of its signature) | occluded | included |
| repeated callee | once, first-seen order | one record per site |
| paren-less Ruby call | appended after the walk | line-ordered with the rest |

A `CallSite` enumerator has to reproduce both from one walk. These tests assert the
current output exactly (ordered), so any refactor that shifts scope, dedupe or order
fails here first. They describe today's behavior, not an endorsement of it -- change an
expectation only as a deliberate, CHANGELOG-noted output change.
"""

import pytest
import tree_sitter_language_pack as ts

from reveal.core import node_children
from reveal.core.nav_calls import range_calls
from reveal.core.node_taxonomy import FUNCTION_TYPES
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root
from reveal.registry import get_analyzer

# BACK-1149: guards an internal invariant/output-contract (registry, schema, or cross-module consistency)
pytestmark = pytest.mark.contract


def _outer_function(root):
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


def _walk(tmp_path, suffix, language, src, from_line=1, to_line=999):
    """({function name: analyzer calls}, [(line, callee, first_arg)] from nav over the first function)."""
    path = tmp_path / f't{suffix}'
    path.write_text(src)
    analyzer = get_analyzer(str(path))(str(path))
    per_function = {f['name']: f['calls'] for f in analyzer.get_structure()['functions']}

    content = src.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser(language), src))
    func_node = _outer_function(root)

    def get_text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    nav = [(c['line'], c['callee'], c['first_arg']) for c in range_calls(
        func_node, from_line, to_line, get_text,
        implicit_nodes=analyzer._implicit_call_nodes(func_node),
    )]
    return per_function, nav


PY_NESTED = (
    "def outer():\n"
    "    def inner():\n"
    "        deep()\n"
    "    top()\n"
    "    inner()\n"
    "    top()\n"
    "    f = lambda: lam()\n"
    "    x = sorted(a, key=lambda z: kc(z))\n"
)


def test_python_nested_named_function_is_a_leaf_for_analyzer_but_walked_by_nav(tmp_path):
    per_function, nav = _walk(tmp_path, '.py', 'python', PY_NESTED)
    # analyzer: inner's `deep` belongs to inner only; lambdas bleed into outer; `top` once.
    assert per_function['outer'] == ['top', 'inner', 'lam', 'sorted', 'kc']
    assert per_function['inner'] == ['deep']
    # nav: `deep` is inside the line range so it is reported; `top` twice (one per site).
    assert nav == [(3, 'deep', None), (4, 'top', None), (5, 'inner', None), (6, 'top', None),
                   (7, 'lam', None), (8, 'sorted', 'a'), (8, 'kc', 'z')]


def test_nav_range_restricts_sites_to_the_requested_lines(tmp_path):
    _, nav = _walk(tmp_path, '.py', 'python', PY_NESTED, from_line=4, to_line=5)
    assert nav == [(4, 'top', None), (5, 'inner', None)]


def test_python_decorator_argument_calls_are_reported_by_both(tmp_path):
    per_function, nav = _walk(tmp_path, '.py', 'python',
                              "@deco(arg())\ndef outer():\n    top()\n")
    assert per_function['outer'] == ['top', 'deco', 'arg']  # body first, decorator after
    assert nav == [(1, 'deco', 'arg()'), (1, 'arg', None), (3, 'top', None)]


def test_js_callbacks_bleed_into_the_enclosing_function_in_both_paths(tmp_path):
    per_function, nav = _walk(
        tmp_path, '.js', 'javascript',
        "function outer(){ function inner(){ deep(); } top(); "
        "[1].map(function(x){ cb(x); }); [1].map(x => arrow(x)); top(); }")
    assert per_function['outer'] == ['top', '[1].map', 'cb', 'arrow']
    assert per_function['inner'] == ['deep']
    assert nav == [(1, 'deep', None), (1, 'top', None),
                   (1, '[1].map', 'function(x){ cb(x); }'), (1, 'cb', 'x'),
                   (1, '[1].map', 'x => arrow(x)'), (1, 'arrow', 'x'), (1, 'top', None)]


def test_go_function_literal_is_not_a_leaf_in_either_path(tmp_path):
    per_function, nav = _walk(tmp_path, '.go', 'go',
                              "package p\nfunc outer(){ top(); func(){ lit() }(); top() }\n")
    assert per_function['outer'] == ['top', 'func(){ lit() }', 'lit']
    assert nav == [(2, 'top', None), (2, 'func(){ lit() }', None), (2, 'lit', None), (2, 'top', None)]


def test_ruby_implicit_calls_are_appended_by_analyzer_but_line_ordered_by_nav(tmp_path):
    per_function, nav = _walk(
        tmp_path, '.rb', 'ruby',
        "def outer\n  top\n  [1].each { |x| blk(x) }\n  def inner; deep; end\n  top\nend\n")
    # Paren-less `top` is an implicit call: the analyzer appends implicit calls after the walk.
    assert per_function['outer'] == ['[1].each', 'blk', 'top']
    assert per_function['inner'] == ['deep']
    # Nav interleaves it by line; the nested def's own bare `deep` is not an implicit call of outer.
    assert nav == [(2, 'top', None), (3, '[1].each', None), (3, 'blk', 'x'), (5, 'top', None)]


def test_dart_nested_function_body_is_occluded_for_analyzer_but_walked_by_nav(tmp_path):
    per_function, nav = _walk(
        tmp_path, '.dart', 'dart',
        "void outer(){ top(); void inner(){ deep(); } inner(); a..c(); top(); }")
    # BACK-760: inner's body is a sibling of its signature; outer must not see `deep`.
    assert per_function['outer'] == ['top', 'inner', 'c']
    assert per_function['inner'] == ['deep']
    # Nav reports it, and spells the cascade call with only the member (chain-receiver policy).
    assert nav == [(1, 'top', None), (1, 'deep', None), (1, 'inner', None), (1, '.c', None), (1, 'top', None)]


# Walker-level shapes: one call spread across sibling nodes, so neither path can name it
# from a single node kind. These are what BACK-1309 folds into the enumerator.

def test_zig_suffix_expr_calls_in_both_paths(tmp_path):
    per_function, nav = _walk(
        tmp_path, '.zig', 'zig',
        'fn outer() void {\n    top();\n    a.b.c(1);\n    std.debug.print("x", .{});\n    top();\n}\n')
    assert per_function['outer'] == ['top', 'a.b.c', 'std.debug.print']
    # first_arg: Zig's `FnCallArguments` is the argument list itself (was never recognised).
    assert nav == [(2, 'top', None), (3, 'a.b.c', '1'), (4, 'std.debug.print', '"x"'), (5, 'top', None)]


def test_gdscript_attribute_calls_in_both_paths(tmp_path):
    per_function, nav = _walk(
        tmp_path, '.gd', 'gdscript',
        "func outer():\n\ttop()\n\tself.m(1)\n\tobj.n()\n\tFoo.new()\n\ttop()\n")
    assert per_function['outer'] == ['top', 'self.m', 'obj.n', 'Foo.new']
    assert nav == [(2, 'top', None), (3, 'self.m', '1'), (4, 'obj.n', None), (5, 'Foo.new', None), (6, 'top', None)]


def test_dart_selector_chains_differ_only_in_receiver_form(tmp_path):
    per_function, nav = _walk(
        tmp_path, '.dart', 'dart',
        "void outer(){ a.b(1).c(2); x.y.z(); top(); top(); }")
    # Both paths agree on the calls. Receivers differ: the analyzer names `c` and `z` bare, nav
    # names `.c` (chain-receiver policy) and `x.y.z` (full receiver).
    assert per_function['outer'] == ['a.b', 'c', 'z', 'top']
    assert nav == [(1, 'a.b', '1'), (1, '.c', '2'), (1, 'x.y.z', None), (1, 'top', None), (1, 'top', None)]


@pytest.mark.parametrize('suffix, language, src', [
    ('.kt', 'kotlin', "fun outer() { foo(1, 2)\n  a.b(x) }\n"),
    ('.swift', 'swift', "func outer() { foo(1, 2)\n  a.b(x) }\n"),
])
def test_kotlin_and_swift_nav_report_the_first_argument(tmp_path, suffix, language, src):
    """`call_expression > call_suffix > value_arguments` sits one level below where
    `_extract_first_arg` looked, so nav reported no first arg for every Kotlin/Swift call
    (1350/1350 and 1408/1408 sites over the 60-file corpus sample)."""
    _, nav = _walk(tmp_path, suffix, language, src)
    assert [(c, a) for _, c, a in nav] == [('foo', '1'), ('a.b', 'x')]
