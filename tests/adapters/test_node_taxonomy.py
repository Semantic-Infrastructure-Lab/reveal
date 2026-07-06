"""Guard-rail tests for reveal.adapters.ast.node_taxonomy (BACK-431 Issue A).

These pin the property the consolidation exists to guarantee: nav_outline.py
(SCOPE_NODES/EXIT_NODES/KEYWORD_LABEL), nav_exits.py (_GATE_NODE_TYPES/
_EXIT_KIND), and nav_varflow.py's if/while/for dispatch all read from the
*same* frozensets in node_taxonomy.py, not independent hand-copies — the
exact drift that caused BACK-427 (if_expression added to two of three
modules) and BACK-430 (while/for/loop/match_expression added to one of
three). If a future edit re-inlines a literal node-kind tuple instead of
importing the shared family, these tests catch it at import/identity time
instead of waiting for a language-specific bug report.
"""

import os
import tempfile
import unittest

import tree_sitter_language_pack as ts

from reveal import complexity, treesitter
from reveal.adapters.ast import node_taxonomy as tax
from reveal.adapters.ast import nav_outline
from reveal.adapters.ast import nav_exits
from reveal.adapters.ast.nav_outline import element_outline, scope_chain
from reveal.adapters.ast.nav_varflow import var_flow
from reveal.analyzers.go import GoAnalyzer
from reveal.analyzers.rust import RustAnalyzer


class TestSharedIdentity(unittest.TestCase):
    """Consumers must reference the taxonomy's objects, not copies of them."""

    def test_nav_outline_scope_nodes_is_taxonomy_scope_nodes(self):
        self.assertIs(nav_outline.SCOPE_NODES, tax.SCOPE_NODES)

    def test_nav_outline_exit_nodes_is_taxonomy_exit_nodes(self):
        self.assertIs(nav_outline.EXIT_NODES, tax.EXIT_NODES)

    def test_nav_outline_function_types_is_taxonomy_function_types(self):
        self.assertIs(nav_outline.FUNCTION_TYPES, tax.FUNCTION_TYPES)

    def test_nav_outline_keyword_label_is_taxonomy_keyword_label(self):
        self.assertIs(nav_outline.KEYWORD_LABEL, tax.KEYWORD_LABEL)

    def test_nav_exits_gate_node_types_is_taxonomy_gate_nodes(self):
        self.assertIs(nav_exits._GATE_NODE_TYPES, tax.GATE_NODES)

    def test_nav_exits_exit_kind_values_match_taxonomy_keyword_label(self):
        for kind, label in nav_exits._EXIT_KIND.items():
            self.assertEqual(
                label, tax.KEYWORD_LABEL[kind],
                f'_EXIT_KIND[{kind!r}] = {label!r} disagrees with '
                f'KEYWORD_LABEL[{kind!r}] = {tax.KEYWORD_LABEL[kind]!r}',
            )

    def test_nav_exits_exit_kind_keys_equal_exit_nodes(self):
        self.assertEqual(frozenset(nav_exits._EXIT_KIND), tax.EXIT_NODES)


class TestFamilyConsistency(unittest.TestCase):
    """Every kind in a per-construct family must carry a KEYWORD_LABEL entry
    and be reachable from the composite sets consumers actually query."""

    def test_every_labeled_kind_used_by_a_composite_has_an_entry(self):
        # This is the same invariant node_taxonomy.py asserts at import time
        # (belt-and-suspenders — a bare `assert` can be stripped with -O).
        composite = tax.SCOPE_NODES | tax.EXIT_NODES | tax.FUNCTION_TYPES
        missing = composite - frozenset(tax.KEYWORD_LABEL)
        self.assertEqual(missing, frozenset(), f'unlabeled node kinds: {missing}')

    def test_gate_nodes_is_subset_of_scope_nodes(self):
        # Anything that can gate a return is, by definition, a scope construct.
        self.assertTrue(tax.GATE_NODES <= tax.SCOPE_NODES)

    def test_if_while_nodes_is_subset_of_gate_and_scope(self):
        self.assertTrue(tax.IF_WHILE_NODES <= tax.GATE_NODES)
        self.assertTrue(tax.IF_WHILE_NODES <= tax.SCOPE_NODES)

    def test_rust_expression_variants_present_in_every_composite(self):
        # Regression pin for BACK-427/430's exact failure shape: a Rust
        # `_expression` kind added to one composite but not the others.
        rust_expression_kinds = {
            'if_expression', 'while_expression', 'for_expression',
            'loop_expression', 'match_expression',
        }
        for kind in rust_expression_kinds:
            self.assertIn(kind, tax.SCOPE_NODES, f'{kind} missing from SCOPE_NODES')
            self.assertIn(kind, tax.GATE_NODES, f'{kind} missing from GATE_NODES')

    def test_bare_break_continue_are_exit_nodes(self):
        # BACK-431: found missing from nav_outline.py's EXIT_NODES despite
        # already being handled by nav_exits.py's old hand-written _EXIT_KIND.
        self.assertIn('break', tax.EXIT_NODES)
        self.assertIn('continue', tax.EXIT_NODES)


class TestComplexityCoversFamilies(unittest.TestCase):
    """complexity.py keeps its own taxonomy (it also counts booleans/ternaries
    and treats infinite `loop` as nesting-but-not-a-decision, so it can't just
    import the nav composites). But its control-flow coverage must not drift
    behind node_taxonomy the way BACK-427/430/431 did — Rust while/loop/match
    and Java/JS for-each were all missing here. These tests fail if a family
    grows a loop/conditional/match kind complexity.py forgot to account for."""

    def test_conditional_and_loop_families_count_as_decisions(self):
        families = (
            tax.IF_NODES | tax.ELIF_NODES | tax.WHILE_NODES | tax.FOR_NODES
            | tax.FOR_EXPRESSION_NODES | tax.FOR_EACH_NAME_VALUE_NODES
            | tax.MATCH_NODES | tax.CASE_NODES | tax.DO_NODES
        )
        missing = families - complexity._DECISION_TYPES
        self.assertEqual(
            missing, frozenset(),
            f'control-flow kinds not counted as complexity decisions: {missing}',
        )

    def test_loop_and_block_families_count_as_nesting(self):
        families = (
            tax.IF_NODES | tax.WHILE_NODES | tax.FOR_NODES
            | tax.FOR_EXPRESSION_NODES | tax.FOR_EACH_NAME_VALUE_NODES
            | tax.LOOP_NODES | tax.DO_NODES | tax.MATCH_NODES
        )
        missing = families - complexity._NESTING_TYPES
        self.assertEqual(
            missing, frozenset(),
            f'control-flow kinds not counted as complexity nesting: {missing}',
        )


def _first_function(lang, code, fn_kinds):
    """Parse and return the first function-like node + a get_text closure."""
    content_bytes = code.encode('utf-8')
    root = ts.get_parser(lang).parse(code).root_node()
    get_text = lambda n: content_bytes[n.start_byte():n.end_byte()].decode('utf-8', 'replace')
    stack = [root]
    while stack:
        n = stack.pop()
        if n.kind() in fn_kinds:
            return n, get_text
        for i in range(n.child_count()):
            stack.append(n.child(i))
    raise AssertionError(f'no function node found in {lang} sample')


class TestForEachVisibility(unittest.TestCase):
    """BACK-431: JS/TS `for_in_statement`, Java `enhanced_for_statement`, and
    the C-style `foreach_statement` were absent from the FOR families, so
    for-each loops were invisible to --outline and their loop variable was
    untracked by --varflow (both confirmed live before the fix)."""

    JAVA = ('class C { int f(int[] items) { int t = 0; '
            'for (int x : items) { if (x > 0) { t += x; } } return t; } }')
    JS = ('function f(items) { let t = 0; '
          'for (const x of items) { if (x > 0) { t += x; } } return t; }')

    def test_java_enhanced_for_appears_in_outline(self):
        node, get_text = _first_function('java', self.JAVA, {'method_declaration'})
        keywords = [i['keyword'] for i in element_outline(node, get_text)]
        self.assertIn('FOR', keywords, 'Java enhanced-for missing from outline')

    def test_js_for_of_appears_in_outline(self):
        node, get_text = _first_function('javascript', self.JS, {'function_declaration'})
        keywords = [i['keyword'] for i in element_outline(node, get_text)]
        self.assertIn('FOR', keywords, 'JS for-of missing from outline')

    def test_java_enhanced_for_loop_var_is_written(self):
        node, get_text = _first_function('java', self.JAVA, {'method_declaration'})
        events = var_flow(node, 'x', node.start_position().row + 1,
                          node.end_position().row + 1, get_text)
        self.assertTrue(
            any(e['kind'] == 'WRITE' for e in events),
            'Java enhanced-for loop variable never recorded as WRITE',
        )

    def test_js_for_of_loop_var_is_written(self):
        node, get_text = _first_function('javascript', self.JS, {'function_declaration'})
        events = var_flow(node, 'x', node.start_position().row + 1,
                          node.end_position().row + 1, get_text)
        self.assertTrue(
            any(e['kind'] == 'WRITE' for e in events),
            'JS for-of loop variable never recorded as WRITE',
        )


class TestClassScopeVisibility(unittest.TestCase):
    """BACK-431 remaining scope (rose-tone-0704 finding #1): node_taxonomy.py's
    CLASS_NODES only knew Python/Java/C#/JS/Ruby's plain class shapes, while
    treesitter.py's separate CLASS_NODE_TYPES (element extraction) already
    covered C++ (`class_specifier`), PHP (`anonymous_class`), and TypeScript
    (`abstract_class_declaration`) — so a method's enclosing class/struct/impl
    was invisible to --scope's ancestor chain for those languages, confirmed
    live before the fix (Python correctly showed CLASS as an ancestor;
    C++/Rust/PHP/TS did not)."""

    CPP_CLASS = 'class Batch { public: void run() { int x = 1; } };'
    CPP_STRUCT = 'struct Foo { void bar() { int x = 1; } };'
    RUST_IMPL = ('struct Batch { total: i32 } '
                 'impl Batch { fn run(&mut self) { let x = 1; } }')
    PHP_ANON_CLASS = '<?php $o = new class { function bar() { $x = 1; } };'
    TS_ABSTRACT_CLASS = 'abstract class Foo { bar() { let x = 1; } }'

    def _chain_keywords(self, lang, code, marker):
        """Parse code and return scope_chain keywords for the line containing marker."""
        content_bytes = code.encode('utf-8')
        get_text = lambda n: content_bytes[n.start_byte():n.end_byte()].decode('utf-8', 'replace')
        root = ts.get_parser(lang).parse(code).root_node()
        line_no = code[:code.index(marker)].count('\n') + 1
        chain = scope_chain(root, line_no, get_text)
        return [item['keyword'] for item in chain]

    def test_cpp_class_specifier_appears_in_scope_chain(self):
        keywords = self._chain_keywords('cpp', self.CPP_CLASS, 'int x = 1')
        self.assertIn('CLASS', keywords, 'C++ class_specifier missing from --scope ancestry')

    def test_cpp_struct_specifier_appears_in_scope_chain(self):
        keywords = self._chain_keywords('cpp', self.CPP_STRUCT, 'int x = 1')
        self.assertIn('STRUCT', keywords, 'C++ struct_specifier missing from --scope ancestry')

    def test_rust_impl_item_appears_in_scope_chain(self):
        keywords = self._chain_keywords('rust', self.RUST_IMPL, 'let x = 1')
        self.assertIn('IMPL', keywords, 'Rust impl_item missing from --scope ancestry')

    def test_php_anonymous_class_appears_in_scope_chain(self):
        keywords = self._chain_keywords('php', self.PHP_ANON_CLASS, '$x = 1')
        self.assertIn('CLASS', keywords, 'PHP anonymous_class missing from --scope ancestry')

    def test_typescript_abstract_class_appears_in_scope_chain(self):
        keywords = self._chain_keywords('typescript', self.TS_ABSTRACT_CLASS, 'let x = 1')
        self.assertIn('CLASS', keywords, 'TS abstract_class_declaration missing from --scope ancestry')


class TestCrossTaxonomyConsistency(unittest.TestCase):
    """BACK-478: treesitter.py keeps its own extraction-side node-kind lists
    (FUNCTION_/CLASS_/STRUCT_/IMPORT_NODE_TYPES) as literal tuples rather than
    importing this module's families directly — a direct import creates a
    circular-import risk (adapters.ast <-> treesitter) that nav_exits.py/
    nav_calls.py already route around via deferred imports for
    CALL_NODE_TYPES. These tests are the guard-rail instead: they pin the two
    taxonomies to the same *content*, so a future edit to one side that
    forgets the other fails a test immediately instead of waiting for a
    language-specific bug report (the exact BACK-462/474/475 pattern)."""

    def test_class_node_types_matches_class_nodes(self):
        self.assertEqual(frozenset(treesitter.CLASS_NODE_TYPES), tax.CLASS_NODES)

    def test_struct_node_types_matches_struct_nodes(self):
        self.assertEqual(frozenset(treesitter.STRUCT_NODE_TYPES), tax.STRUCT_NODES)

    def test_import_node_types_matches_import_nodes(self):
        self.assertEqual(frozenset(treesitter.IMPORT_NODE_TYPES), tax.IMPORT_NODES)

    def test_function_node_types_matches_def_nodes_minus_arrow_function(self):
        # arrow_function is deliberately excluded from the extraction-side
        # list: JS-family arrow functions are extracted via a dedicated path
        # (_extract_arrow_functions / file_handler.py), not this generic
        # node-kind scan, to avoid double-extracting every nested callback
        # arrow expression as a false top-level function.
        self.assertEqual(
            frozenset(treesitter.FUNCTION_NODE_TYPES),
            tax.DEF_NODES - {'arrow_function'},
        )


def _get_structure(analyzer_cls, suffix, code):
    with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8') as f:
        f.write(code)
        f.flush()
        temp_path = f.name
    try:
        return analyzer_cls(temp_path).get_structure()
    finally:
        os.unlink(temp_path)


class TestGoStructVisibility(unittest.TestCase):
    """BACK-478: Go's real struct node kind (`struct_type`, nested inside
    `type_declaration -> type_spec`) was absent from both taxonomies —
    `treesitter.py`'s STRUCT_NODE_TYPES had a `struct_declaration` entry
    labeled "Go" that is actually C#'s node kind (verified via direct
    tree-sitter inspection), so Go structs were entirely invisible to
    get_structure()['structs'] / --outline / --scope."""

    GO_STRUCT = 'package main\n\ntype Foo struct {\n\tX int\n}\n'

    def test_go_struct_appears_in_structure(self):
        structure = _get_structure(GoAnalyzer, '.go', self.GO_STRUCT)
        structs = structure.get('structs') or []
        names = [s['name'] for s in structs]
        self.assertIn('Foo', names, f'Go struct missing from structs: {structs}')

    def test_go_struct_not_misfiled_as_class(self):
        structure = _get_structure(GoAnalyzer, '.go', self.GO_STRUCT)
        classes = structure.get('classes') or []
        self.assertEqual(classes, [], f'Go struct wrongly extracted as class: {classes}')


class TestRustStructNotDoubleCounted(unittest.TestCase):
    """BACK-478: treesitter.py's CLASS_NODE_TYPES included `struct_item`
    ("Rust, treated as class"), so every Rust struct was extracted twice —
    once under 'structs' (correctly) and once under 'classes' (a duplicate,
    mislabeled entry) — confirmed live before the fix."""

    RUST_STRUCT = 'struct Foo { x: i32 }'

    def test_rust_struct_appears_once_under_structs(self):
        structure = _get_structure(RustAnalyzer, '.rs', self.RUST_STRUCT)
        structs = structure.get('structs') or []
        names = [s['name'] for s in structs]
        self.assertEqual(names.count('Foo'), 1, f'expected exactly 1 Foo struct: {structs}')

    def test_rust_struct_does_not_also_appear_under_classes(self):
        structure = _get_structure(RustAnalyzer, '.rs', self.RUST_STRUCT)
        classes = structure.get('classes') or []
        self.assertEqual(classes, [], f'Rust struct double-counted as class: {classes}')


if __name__ == '__main__':
    unittest.main()
