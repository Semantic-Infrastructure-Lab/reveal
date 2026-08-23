"""Nav feature tests: deps/varflow coverage across languages.

Split from test_ast_nav_probe_features.py (BACK-1151) -- covers
collect_deps/all_var_flow/render_deps and the per-language varflow/deps
regressions (--deps/--flowto/varflow surface).
"""

"""Tests for probe-inspired nav features added in BACK-156 through BACK-160.

Covers:
  collect_exits()    -- BACK-156/159 (--exits / --flowto)
  all_var_flow()     -- BACK-160 foundation
  collect_deps()     -- BACK-160 (--deps)
  collect_mutations()-- BACK-160 (--mutations)
  render_branchmap() -- BACK-158 (--ifmap / --catchmap)
  render_exits()     -- BACK-159
  render_deps()      -- BACK-160
  render_mutations() -- BACK-160

Also covers flat-file behaviour (Change A: root_node fallback) indirectly
through the nav functions accepting root_node as scope_node.
"""

import textwrap
import unittest

import tree_sitter_language_pack as ts

import pytest
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root

# BACK-1149: component-layer test -- single adapter/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


# ---------------------------------------------------------------------------
# Parse helpers (shared with test_ast_nav.py pattern)
# ---------------------------------------------------------------------------

def _parse_python(code: str):
    """Parse Python code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('python')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _find_func(root, get_text, name: str):
    """Find a function_definition node by name."""
    stack = [root.child(i) for i in range(_zero_arg(root, 'child_count'))]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') == 'function_definition':
            for child in [node.child(i) for i in range(_zero_arg(node, 'child_count'))]:
                if _zero_arg(child, 'kind') == 'identifier' and get_text(child) == name:
                    return node
        stack.extend(reversed([node.child(i) for i in range(_zero_arg(node, 'child_count'))]))
    return None


# ===========================================================================
# collect_exits
# ===========================================================================

def _parse_php(code: str):
    """Parse PHP code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('php')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _parse_swift(code: str):
    """Parse Swift code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('swift')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _parse_kotlin(code: str):
    """Parse Kotlin code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('kotlin')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _parse_scala(code: str):
    """Parse Scala code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('scala')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _parse_lua(code: str):
    """Parse Lua code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('lua')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _parse_ruby(code: str):
    """Parse Ruby code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('ruby')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _parse_tsx(code: str):
    """Parse TSX code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('tsx')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


class TestAllVarFlow(unittest.TestCase):

    def setUp(self):
        code = """
        def process(data, limit):
            result = []
            count = 0
            for item in data:
                if count >= limit:
                    break
                result.append(item)
                count += 1
            return result
        """
        self._tree, self._root, self._get_text, _ = _parse_python(code)
        self._func = _find_func(self._root, self._get_text, 'process')

    def _all_flow(self, from_line, to_line):
        from reveal.adapters.ast.nav import all_var_flow
        return all_var_flow(self._func, from_line, to_line, self._get_text)

    def test_returns_dict(self):
        result = self._all_flow(1, 999)
        self.assertIsInstance(result, dict)

    def test_result_includes_known_vars(self):
        result = self._all_flow(1, 999)
        # 'result' and 'count' are definitely in scope
        self.assertIn('result', result)
        self.assertIn('count', result)

    def test_each_value_is_list_of_events(self):
        result = self._all_flow(1, 999)
        for var_name, events in result.items():
            self.assertIsInstance(events, list)
            for ev in events:
                self.assertIn('kind', ev)
                self.assertIn('line', ev)

    def test_range_limits_which_vars_are_found(self):
        # With a very narrow range we get fewer variables
        all_result = self._all_flow(1, 999)
        narrow_result = self._all_flow(1, 2)
        self.assertLessEqual(len(narrow_result), len(all_result))

    def test_events_sorted_by_line_per_var(self):
        result = self._all_flow(1, 999)
        for var_name, events in result.items():
            lines = [e['line'] for e in events]
            self.assertEqual(lines, sorted(lines), f'Events for {var_name!r} not sorted')

    def test_works_on_root_node(self):
        from reveal.adapters.ast.nav import all_var_flow
        result = all_var_flow(self._root, 1, 999, self._get_text)
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)


# ===========================================================================
# collect_deps
# ===========================================================================

class TestCollectDeps(unittest.TestCase):

    def setUp(self):
        # A function where 'data' and 'limit' flow in (params),
        # and 'result' is written inside (not a dep).
        code = """
        def process(data, limit):
            result = []
            count = 0
            for item in data:
                if count >= limit:
                    break
                result.append(item)
                count += 1
            return result
        """
        self._tree, self._root, self._get_text, _ = _parse_python(code)
        self._func = _find_func(self._root, self._get_text, 'process')

    def _deps(self, from_line=1, to_line=999):
        from reveal.adapters.ast.nav import collect_deps
        return collect_deps(self._func, from_line, to_line, self._get_text)

    def test_returns_list(self):
        self.assertIsInstance(self._deps(), list)

    def test_deps_have_required_fields(self):
        deps = self._deps()
        for d in deps:
            self.assertIn('var', d)
            self.assertIn('first_read_line', d)
            self.assertIn('first_write_line', d)

    def test_sorted_by_first_read_line(self):
        deps = self._deps()
        lines = [d['first_read_line'] for d in deps]
        self.assertEqual(lines, sorted(lines))

    def test_data_param_is_dep(self):
        """'data' is read before any write in the function body — it's a dep."""
        deps = self._deps()
        names = [d['var'] for d in deps]
        self.assertIn('data', names)

    def test_result_is_not_dep(self):
        """'result' is written first (result = []), not a dep."""
        deps = self._deps()
        names = [d['var'] for d in deps]
        self.assertNotIn('result', names)

    def test_first_write_line_present_when_written(self):
        """limit is read as a dep but also written to (count >= limit pattern)."""
        deps = self._deps()
        limit_dep = next((d for d in deps if d['var'] == 'limit'), None)
        if limit_dep:
            # limit is only read (not reassigned) — first_write_line should be None
            self.assertIsNone(limit_dep['first_write_line'])

    def test_empty_when_no_deps(self):
        """A function that writes all vars before reading them has no deps."""
        code = """
        def f():
            x = 1
            y = x + 1
            return y
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func(root, get_text, 'f')
        from reveal.adapters.ast.nav import collect_deps
        deps = collect_deps(func, 1, 999, get_text)
        # x is written first, y is written first — neither is a dep
        dep_names = [d['var'] for d in deps]
        self.assertNotIn('x', dep_names)
        self.assertNotIn('y', dep_names)

    def test_range_limits_analysis(self):
        """A narrow range produces fewer or equal deps than the full function."""
        all_deps = self._deps()
        # Use first 2 lines — very few variables in scope
        narrow_deps = self._deps(from_line=1, to_line=2)
        self.assertLessEqual(len(narrow_deps), len(all_deps))


class TestCollectDepsBack402(unittest.TestCase):
    """BACK-402: own name and dotted-attribute segments must not appear as deps."""

    def _deps_for(self, code, func_name):
        _, root, get_text, _ = _parse_python(code)
        func = _find_func(root, get_text, func_name)
        from reveal.adapters.ast.nav import collect_deps
        return collect_deps(func, 1, 999, get_text)

    def test_own_name_excluded(self):
        code = """
        def pick(n):
            if n > 0:
                return Color.RED
            return Color.BLUE
        """
        names = [d['var'] for d in self._deps_for(code, 'pick')]
        self.assertNotIn('pick', names)

    def test_dotted_attribute_segment_excluded(self):
        """Only the base object of Color.RED/Color.BLUE is a dep, not RED/BLUE."""
        code = """
        def pick(n):
            if n > 0:
                return Color.RED
            return Color.BLUE
        """
        names = [d['var'] for d in self._deps_for(code, 'pick')]
        self.assertIn('Color', names)
        self.assertNotIn('RED', names)
        self.assertNotIn('BLUE', names)

    def test_nested_attribute_chain_only_base_object(self):
        code = """
        def f():
            return a.b.c
        """
        names = [d['var'] for d in self._deps_for(code, 'f')]
        self.assertIn('a', names)
        self.assertNotIn('b', names)
        self.assertNotIn('c', names)


class TestVarFlowBack411(unittest.TestCase):
    """BACK-411: declaration-with-initializer must classify as WRITE, not READ,
    across languages whose grammar uses a distinct declarator/declaration node
    shape instead of Python's plain `assignment` (C#, Java, Go, Rust, TS/JS).
    Also covers compound-assignment (+=) READ+WRITE pairing where the grammar
    unifies `=`/`+=`/etc. into one node kind (C#, Go)."""

    @staticmethod
    def _parse(code: str, lang: str):
        parser = ts.get_parser(lang)
        src = textwrap.dedent(code).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')

        return root, get_text

    def _kinds_for(self, code, lang, var_name):
        from reveal.adapters.ast.nav_varflow import var_flow
        root, get_text = self._parse(code, lang)
        events = var_flow(root, var_name, 1, 999, get_text)
        return [(e['kind'], e['line']) for e in events]

    def test_csharp_declaration_is_write(self):
        code = """
        class C {
            void M() {
                var x = Foo();
                x += Bar();
                Console.WriteLine(x);
            }
        }
        """
        kinds = self._kinds_for(code, 'c_sharp', 'x')
        self.assertEqual(kinds[0][0], 'WRITE')  # declaration
        self.assertIn(('READ', kinds[1][1]), kinds)  # += reads before writing
        self.assertIn(('WRITE', kinds[1][1]), kinds)

    def test_csharp_plain_assignment_still_write(self):
        code = """
        class C {
            void M() {
                y = Baz();
            }
        }
        """
        kinds = self._kinds_for(code, 'c_sharp', 'y')
        self.assertEqual(kinds, [('WRITE', 3)])

    def test_java_declaration_is_write(self):
        code = """
        class C {
            void m() {
                int x = foo();
                x += bar();
            }
        }
        """
        kinds = self._kinds_for(code, 'java', 'x')
        self.assertEqual(kinds[0][0], 'WRITE')
        self.assertIn(('READ', kinds[1][1]), kinds)
        self.assertIn(('WRITE', kinds[1][1]), kinds)

    def test_go_short_var_declaration_is_write(self):
        code = """
        package main
        func m() {
            x := foo()
            x += bar()
            y = baz()
        }
        """
        x_kinds = self._kinds_for(code, 'go', 'x')
        self.assertEqual(x_kinds[0][0], 'WRITE')  # x := foo()
        self.assertIn(('READ', x_kinds[1][1]), x_kinds)  # x += bar()
        self.assertIn(('WRITE', x_kinds[1][1]), x_kinds)

        y_kinds = self._kinds_for(code, 'go', 'y')
        self.assertEqual(y_kinds, [('WRITE', y_kinds[0][1])])  # plain y = baz()

    def test_rust_let_declaration_is_write(self):
        code = """
        fn m() {
            let x = foo();
            x += bar();
        }
        """
        kinds = self._kinds_for(code, 'rust', 'x')
        self.assertEqual(kinds[0][0], 'WRITE')
        self.assertIn(('READ', kinds[1][1]), kinds)
        self.assertIn(('WRITE', kinds[1][1]), kinds)

    def test_typescript_lexical_declaration_is_write(self):
        code = """
        function m() {
            let x = foo();
            x += bar();
        }
        """
        kinds = self._kinds_for(code, 'typescript', 'x')
        self.assertEqual(kinds[0][0], 'WRITE')
        self.assertIn(('READ', kinds[1][1]), kinds)
        self.assertIn(('WRITE', kinds[1][1]), kinds)

    def test_kotlin_reassignment_target_is_write(self):
        # Kotlin's `x = ...` reassignment parses as an `assignment` node whose
        # target/value are POSITIONAL children (directly_assignable_expression,
        # '=', <expr>) with no 'left'/'right' fields — so resolve_assignment_
        # sides returned (None, None) and both `x` identifiers fell through to
        # READ. The declaration (`var x = ...`) already worked via _DECL_SHAPES;
        # only the bare reassignment was blind (BACK-476).
        code = """
        fun m(): Int {
            var x = foo()
            x = x * 2
            return x
        }
        """
        kinds = self._kinds_for(code, 'kotlin', 'x')
        self.assertEqual(kinds[0][0], 'WRITE')            # var x = foo()  (decl)
        self.assertIn(('WRITE', kinds[1][1]), kinds)      # x = x * 2      (reassign target)
        self.assertIn(('READ', kinds[1][1]), kinds)       # x = x * 2      (rhs read)

    def test_swift_reassignment_target_is_write(self):
        # Swift shares Kotlin's exact `assignment` shape (positional
        # directly_assignable_expression / '=' / <expr>, no fields) — same
        # BACK-476 fix covers both.
        code = """
        func m() -> Int {
            var x = foo()
            x = x * 2
            return x
        }
        """
        kinds = self._kinds_for(code, 'swift', 'x')
        self.assertEqual(kinds[0][0], 'WRITE')
        self.assertIn(('WRITE', kinds[1][1]), kinds)
        self.assertIn(('READ', kinds[1][1]), kinds)


# ===========================================================================
# collect_mutations
# ===========================================================================

class TestRenderDeps(unittest.TestCase):

    def test_empty_deps(self):
        from reveal.adapters.ast.nav import render_deps
        result = render_deps([], 10, 50)
        self.assertIn('No dependencies', result)
        self.assertIn('L10', result)
        self.assertIn('L50', result)

    def test_dep_without_write(self):
        from reveal.adapters.ast.nav import render_deps
        deps = [{'var': 'data', 'first_read_line': 3, 'first_write_line': None}]
        result = render_deps(deps, 1, 20)
        self.assertIn('data', result)
        self.assertIn('PARAM', result)
        self.assertIn('never written', result)

    def test_dep_with_write(self):
        from reveal.adapters.ast.nav import render_deps
        deps = [{'var': 'limit', 'first_read_line': 5, 'first_write_line': 8}]
        result = render_deps(deps, 1, 20)
        self.assertIn('limit', result)
        self.assertIn('L5', result)
        self.assertIn('L8', result)

    def test_multiple_deps_present(self):
        from reveal.adapters.ast.nav import render_deps
        deps = [
            {'var': 'a', 'first_read_line': 2, 'first_write_line': None},
            {'var': 'b', 'first_read_line': 4, 'first_write_line': 6},
        ]
        result = render_deps(deps, 1, 10)
        self.assertIn('a', result)
        self.assertIn('b', result)


class TestCollectIdentifierNames(unittest.TestCase):

    def test_finds_identifiers_in_range(self):
        code = """
        x = 1
        y = x + 2
        z = y + 3
        """
        _, root, get_text, _ = _parse_python(code)
        from reveal.adapters.ast.nav import _collect_identifier_names
        names = _collect_identifier_names(root, 1, 999, get_text)
        self.assertIn('x', names)
        self.assertIn('y', names)
        self.assertIn('z', names)

    def test_range_limits_names(self):
        code = """
        alpha = 1
        beta = 2
        gamma = 3
        """
        _, root, get_text, _ = _parse_python(code)
        from reveal.adapters.ast.nav import _collect_identifier_names
        # Only look at line 1 (alpha = 1)
        names_narrow = _collect_identifier_names(root, 1, 1, get_text)
        names_all = _collect_identifier_names(root, 1, 999, get_text)
        self.assertLessEqual(len(names_narrow), len(names_all))

    def test_returns_frozenset(self):
        code = "x = 1"
        _, root, get_text, _ = _parse_python(code)
        from reveal.adapters.ast.nav import _collect_identifier_names
        result = _collect_identifier_names(root, 1, 999, get_text)
        self.assertIsInstance(result, frozenset)

    def test_empty_range_returns_empty(self):
        code = "x = 1"
        _, root, get_text, _ = _parse_python(code)
        from reveal.adapters.ast.nav import _collect_identifier_names
        result = _collect_identifier_names(root, 999, 1000, get_text)
        self.assertEqual(result, frozenset())


# ---------------------------------------------------------------------------
# BACK-199: --sideeffects taxonomy classifier
# ---------------------------------------------------------------------------

class TestPhpVarflow(unittest.TestCase):

    def setUp(self):
        code = """\
<?php
function process($data) {
    $count = 0;
    foreach ($data as $k => $row) {
        if ($row > 0) {
            $count += $row;
        }
    }
    return $count;
}
"""
        self._tree, self._root, self._get_text, _ = _parse_php(code)

    def test_collect_identifier_names_finds_php_vars(self):
        from reveal.adapters.ast.nav import _collect_identifier_names
        names = _collect_identifier_names(self._root, 1, 999, self._get_text)
        self.assertIn('$count', names)
        self.assertIn('$data', names)
        self.assertIn('$row', names)
        self.assertIn('$k', names)

    def test_var_flow_tracks_php_write(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, '$count', 1, 999, self._get_text)
        self.assertTrue(len(events) > 0)
        kinds = [e['kind'] for e in events]
        self.assertIn('WRITE', kinds)

    def test_var_flow_tracks_php_read(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, '$count', 1, 999, self._get_text)
        kinds = [e['kind'] for e in events]
        self.assertIn('READ', kinds)

    def test_var_flow_write_before_read(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, '$count', 1, 999, self._get_text)
        write_lines = [e['line'] for e in events if e['kind'] == 'WRITE']
        read_lines = [e['line'] for e in events if e['kind'] == 'READ']
        self.assertTrue(min(write_lines) < max(read_lines))

    def test_augmented_assignment_produces_read_and_write(self):
        from reveal.adapters.ast.nav import var_flow
        # $count += $row is both READ and WRITE
        events = var_flow(self._root, '$count', 1, 999, self._get_text)
        line6_events = [e for e in events if e['line'] == 6]
        event_kinds = {e['kind'] for e in line6_events}
        self.assertIn('WRITE', event_kinds)
        self.assertIn('READ', event_kinds)

    def test_var_flow_not_empty_for_php(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, '$count', 1, 999, self._get_text)
        self.assertGreater(len(events), 0)


# ---------------------------------------------------------------------------
# BACK-431 Issue G smoke-tier audit: Swift varflow — simple_identifier /
# property_declaration node-shape fix
# ---------------------------------------------------------------------------

class TestSwiftVarflow(unittest.TestCase):
    """Swift identifiers parse as `simple_identifier`, not `identifier`/
    `variable_name` — nav_varflow.py's read/write matcher never recognized
    that node kind, so --varflow found zero references for every Swift
    variable (silent, not a crash). Its `var`/`let` declarations also use a
    `property_declaration` node whose 'name' field wraps the identifier in
    an extra `pattern` node, a shape none of the declarator dispatch cases
    matched. Found via the BACK-431 Issue G smoke-tier audit."""

    def setUp(self):
        code = """\
        func run(order: String?) -> String? {
            var upper = order
            while upper != nil {
                upper = nil
            }
            return upper
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_swift(code)

    def test_collect_identifier_names_finds_swift_vars(self):
        from reveal.adapters.ast.nav import _collect_identifier_names
        names = _collect_identifier_names(self._root, 1, 999, self._get_text)
        self.assertIn('upper', names)
        self.assertIn('order', names)

    def test_var_flow_tracks_swift_declaration_write(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'upper', 1, 999, self._get_text)
        kinds = [e['kind'] for e in events]
        self.assertIn('WRITE', kinds)

    def test_var_flow_tracks_swift_read(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'upper', 1, 999, self._get_text)
        kinds = [e['kind'] for e in events]
        self.assertIn('READ', kinds)

    def test_var_flow_not_empty_for_swift(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'upper', 1, 999, self._get_text)
        self.assertGreater(len(events), 0)


# ---------------------------------------------------------------------------
# BACK-431 Issue G smoke-tier audit: Kotlin varflow — property_declaration
# with no exposed fields (`val x = f()` mislabeled READ instead of WRITE)
# ---------------------------------------------------------------------------

class TestKotlinVarflow(unittest.TestCase):
    """Kotlin's `property_declaration` (`val x = f()`) exposes no 'name'/
    'value' fields at all (unlike Swift's node of the same name) — the
    declared identifier is a positional `variable_declaration` child. Without
    recognizing that shape, the name fell through to the generic
    "unprocessed children are READ" branch and every Kotlin declaration was
    silently mislabeled as a read instead of a write. Found via the BACK-431
    Issue G smoke-tier audit."""

    def setUp(self):
        code = """\
        fun run(order: String?): String? {
            val result = order
            return result
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_kotlin(code)

    def test_var_flow_tracks_kotlin_declaration_write(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'result', 1, 999, self._get_text)
        kinds = [e['kind'] for e in events]
        self.assertIn('WRITE', kinds)

    def test_var_flow_write_before_read_kotlin(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'result', 1, 999, self._get_text)
        write_lines = [e['line'] for e in events if e['kind'] == 'WRITE']
        read_lines = [e['line'] for e in events if e['kind'] == 'READ']
        self.assertTrue(write_lines and read_lines)
        self.assertTrue(min(write_lines) < max(read_lines))


class TestKotlinDepsAndBoundary(unittest.TestCase):
    """BACK-431 feature-breadth pass (--deps/--boundary, real-corpus dogfood
    on tivi's markSeasonWatched): Kotlin's `navigation_expression` (obj.member
    / obj.method()) was absent from nav_varflow's `_MEMBER_ACCESS_KINDS`, so
    every method/property name in a call chain was misread as an independent
    undefined variable — a `.filter().map().toList()` chain alone produced 3
    bogus "PARAM" entries. Separately, Kotlin's `function_declaration` has
    neither a 'name' nor a 'declarator' field, so `_declared_name_node`
    (used to exclude a scope's own name from its dep list) always returned
    None — every function's own name showed up as a dependency on itself."""

    def setUp(self):
        code = """\
        fun run(x: Int): Int {
            val y = bar.baz(x)
            return y
        }
        """
        from reveal.core import node_children
        self._tree, root, self._get_text, _ = _parse_kotlin(code)
        # collect_deps runs against the resolved function node in production
        # (ctx.func_node), not the source_file root — descend to it here too.
        self._func_node = node_children(root)[0]

    def test_deps_excludes_member_access_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        deps = collect_deps(self._func_node, 1, 999, self._get_text)
        names = {d['var'] for d in deps}
        self.assertNotIn('baz', names)
        self.assertIn('bar', names)

    def test_deps_excludes_own_function_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        deps = collect_deps(self._func_node, 1, 999, self._get_text)
        names = {d['var'] for d in deps}
        self.assertNotIn('run', names)


class TestVarflowExcludesOwnDeclarationSiteButKeepsRecursiveReference(unittest.TestCase):
    """BACK-431 feature-breadth pass (--varflow, real-corpus dogfood on
    three.js's WebGLRenderer.checkMaterialsReady): a direct --varflow query
    goes straight to var_flow()/VarFlowWalker, which — unlike
    _collect_identifier_names's skip_positions — never excluded a scope's
    own declaration-site name at all. A function that legitimately
    references its own name for recursion (`setTimeout(checkThing, 10)`)
    showed TWO reads: the real recursive reference, plus a bogus one at the
    `function checkThing()` declaration line itself. Confirmed
    language-agnostic (reproduces in plain Python, not just JS) since the
    gap was in the shared walker, not any per-language taxonomy."""

    def test_python_recursive_self_reference(self):
        from reveal.adapters.ast.nav import var_flow
        _, root, get_text, _ = _parse_python("""\
        def check_thing():
            do_later(check_thing)
        """)
        func = _find_func(root, get_text, 'check_thing')
        events = var_flow(func, 'check_thing', 1, 999, get_text)
        read_lines = [e['line'] for e in events if e['kind'] == 'READ']
        self.assertEqual(read_lines, [2])

    def test_javascript_recursive_self_reference(self):
        from reveal.adapters.ast.nav import var_flow
        from reveal.core import node_children
        parser = ts.get_parser('javascript')
        src = textwrap.dedent("""\
        function checkThing() {
          setTimeout(checkThing, 10);
        }
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        root = tree_root(ts_parse(parser, src))
        # var_flow runs against the resolved function node in production
        # (ctx.func_node), not the source_file root — descend to it here too
        # (_declared_name_node needs the function node itself to find 'name').
        func = node_children(root)[0]

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')

        events = var_flow(func, 'checkThing', 1, 999, get_text)
        read_lines = [e['line'] for e in events if e['kind'] == 'READ']
        self.assertEqual(read_lines, [2])


# ---------------------------------------------------------------------------
# BACK-431 Issue G smoke-tier audit: Scala varflow (val_definition/
# var_definition) and --exits/--returns (throw_expression)
# ---------------------------------------------------------------------------

class TestScalaVarflow(unittest.TestCase):
    """Scala's `val_definition`/`var_definition` ('pattern'/'value' fields,
    the same shape as Rust's `let_declaration`) had no dispatch case at all —
    every Scala declaration fell into the same silent WRITE-as-READ
    mislabeling Kotlin's property_declaration had. Found via the BACK-431
    Issue G smoke-tier audit."""

    def setUp(self):
        code = """\
        object Sample {
          def run(order: String): String = {
            val result = order
            result
          }
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_scala(code)

    def test_var_flow_tracks_scala_declaration_write(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'result', 1, 999, self._get_text)
        kinds = [e['kind'] for e in events]
        self.assertIn('WRITE', kinds)


class TestScalaForComprehensionEnumerator(unittest.TestCase):
    """Scala's for-comprehension `enumerator` (`x <- expr` generator
    binding, `x = expr` value binding, or a bare `if cond` guard) has no
    AST fields at all and had no dispatch case — the bound name fell
    through to the generic recursion and was mislabeled READ instead of
    WRITE at its own binding site. Found via real gitbucket source
    (WebHookService.scala's callIssuesWebHook): `repoOwner <- users.get(...)`
    (BACK-431 tier A real-corpus dogfood audit)."""

    def setUp(self):
        code = """\
        object Sample {
          def run(users: Map[String, String]): Option[String] = {
            for {
              repoOwner <- users.get("a")
              if repoOwner.nonEmpty
              x = repoOwner.trim
            } yield {
              x
            }
          }
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_scala(code)

    def test_generator_binding_is_write(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'repoOwner', 1, 999, self._get_text)
        kinds_by_line = {e['line']: e['kind'] for e in events}
        # Binding site (the `<-` line) is a WRITE; the guard's use and the
        # `x = repoOwner.trim` use are READs.
        binding_line = min(kinds_by_line)
        self.assertEqual(kinds_by_line[binding_line], 'WRITE')
        self.assertIn('READ', kinds_by_line.values())

    def test_value_binding_is_write(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'x', 1, 999, self._get_text)
        kinds = [e['kind'] for e in events]
        self.assertIn('WRITE', kinds)
        self.assertIn('READ', kinds)


class TestScalaThrowExpression(unittest.TestCase):
    """Scala's grammar is expression-oriented like Rust's: `throw` parses as
    `throw_expression`, not `throw_statement` — absent from THROW_NODES it
    was totally invisible to --exits/--returns (BACK-431 Issue G smoke-tier
    audit, the same failure shape BACK-430 found for Rust)."""

    def setUp(self):
        code = """\
        object Sample {
          def validate(order: Option[String]): String = order match {
            case None => throw new IllegalArgumentException("empty")
            case Some(o) => o
          }
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_scala(code)

    def test_collect_gate_chains_finds_throw_expression(self):
        from reveal.adapters.ast.nav import collect_gate_chains
        chains = collect_gate_chains(self._root, 1, 999, self._get_text)
        kinds = {c['kind'] for c in chains}
        self.assertIn('THROW', kinds)


class TestScalaNamedArgumentNotWrite(unittest.TestCase):
    """BACK-431 feature-breadth pass (--deps, real-corpus dogfood on
    gitbucket's WebHookService.scala callIssuesWebHook): Scala's named
    call argument (`f(x = value)`) parses as `assignment_expression` —
    structurally identical to a real reassignment statement `x = value` —
    so the generic WRITE-detection walker misread the argument label as a
    write to a same-named local/parameter. `WebHookIssuesPayload(repository
    = ApiRepository(repository, ...), ...)` made --deps report the
    `repository` parameter as reassigned inside the function body, when it
    never is — the label and the parameter merely share a name."""

    def setUp(self):
        code = """\
        object Sample {
          def run(repository: Int): Unit = {
            val x = Bar(repository = ApiRepository(repository))
          }
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_scala(code)

    def test_var_flow_has_no_write_for_named_argument_label(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'repository', 1, 999, self._get_text)
        kinds = [e['kind'] for e in events]
        self.assertNotIn('WRITE', kinds)
        self.assertIn('READ', kinds)

    def test_deps_reports_no_write_for_named_argument_label(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        deps = collect_deps(self._root, 1, 999, self._get_text)
        by_var = {d['var']: d for d in deps}
        self.assertIn('repository', by_var)
        self.assertIsNone(by_var['repository']['first_write_line'])


# ---------------------------------------------------------------------------
# BACK-200: --returns gate-chain walker
# ---------------------------------------------------------------------------

class TestLuaDottedFunctionNameNav(unittest.TestCase):
    """Lua `function table.name(...)` (BACK-431 Issue G tier B dogfood
    finding, via real Kong source kong/concurrency.lua) — the name is a
    `dot_index_expression`, a kind absent from every check in
    TreeSitterAnalyzer._get_node_name, so the function had no resolvable
    name at all and every nav flag (not just --varflow) was blind to it."""

    def test_get_node_name_returns_final_segment(self):
        from reveal.registry import get_analyzer
        import tempfile
        code = "function concurrency.with_worker_mutex(opts, fn)\n  return fn(opts)\nend\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = f.name
        try:
            cls = get_analyzer(path)
            analyzer = cls(path)
            nodes = analyzer._find_nodes_by_type('function_declaration')
            self.assertEqual(len(nodes), 1)
            self.assertEqual(analyzer._get_node_name(nodes[0]), 'with_worker_mutex')
        finally:
            import os
            os.unlink(path)


class TestLuaColonMethodFunctionNameNav(unittest.TestCase):
    """Lua `function table:name(...)` (BACK-722 Lua sideeffects-recall-oracle
    pre-flight, via real Kong source e.g. kong/db/dao/init.lua's
    `function DAO:insert(...)`/`function DAO:select(...)`) — the colon-method
    idiom, Lua's closest equivalent to a receiver method (implicitly takes
    `self`). The name is a `method_index_expression`, a kind that was absent
    from every check in TreeSitterAnalyzer._get_node_name (only its sibling
    `dot_index_expression`, the BACK-431 fix above, was handled) — so a
    colon-defined method had no resolvable name at all: entirely missing
    from --outline and erroring outright on a direct bare-name lookup, even
    though it is the DOMINANT method-definition idiom in Kong's DAO/plugin-
    handler layers, more common in this corpus than the dot form."""

    def test_get_node_name_returns_final_segment(self):
        from reveal.registry import get_analyzer
        import tempfile
        code = "function connector:query(sql)\n  return self:execute(sql)\nend\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = f.name
        try:
            cls = get_analyzer(path)
            analyzer = cls(path)
            nodes = analyzer._find_nodes_by_type('function_declaration')
            self.assertEqual(len(nodes), 1)
            self.assertEqual(analyzer._get_node_name(nodes[0]), 'query')
        finally:
            import os
            os.unlink(path)

    def test_outline_includes_colon_method(self):
        """End-to-end: --outline/get_structure() now surfaces the colon
        method by name (previously silently absent)."""
        from reveal.registry import get_analyzer
        import tempfile
        code = (
            "local M = {}\n"
            "function M.dotform(x)\n  return x\nend\n"
            "function M:colonform(y)\n  return y\nend\n"
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = f.name
        try:
            cls = get_analyzer(path)
            analyzer = cls(path)
            structure = analyzer.get_structure()
            names = {fn['name'] for fn in structure.get('functions', [])}
            self.assertIn('dotform', names)
            self.assertIn('colonform', names)
        finally:
            import os
            os.unlink(path)


class TestLuaDepsExcludesMemberAndMethodNames(unittest.TestCase):
    """BACK-431 feature-breadth pass (--deps, real-corpus dogfood on Kong's
    concurrency.lua with_worker_mutex): neither of Lua's two member-access
    node kinds — `dot_index_expression` (`obj.field`) and
    `method_index_expression` (`obj:method()`, colon-call syntax) — was in
    `_MEMBER_ACCESS_KINDS`, so every field/method name in the function
    (`opts.name`, `rlock:lock(...)`, `rlock.dict:ttl(...)`, `rlock:unlock(...)`)
    read as its own independent undefined variable."""

    def setUp(self):
        self._tree, self._root, self._get_text, _ = _parse_lua("""\
        function run(opts, rlock)
          local x = opts.name
          rlock:lock(x)
          rlock.dict:ttl(x)
        end
        """)

    def test_deps_excludes_dot_and_method_index_names(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        deps = collect_deps(self._root, 1, 999, self._get_text)
        names = {d['var'] for d in deps}
        self.assertNotIn('name', names)
        self.assertNotIn('lock', names)
        self.assertNotIn('ttl', names)
        self.assertNotIn('dict', names)  # also a member name (rlock.dict), not a var
        self.assertIn('opts', names)
        self.assertIn('rlock', names)  # the real base of rlock.dict:ttl(...)


class TestLuaVarflowMemberNameCollision(unittest.TestCase):
    """BACK-431 feature-breadth pass (--varflow, same Kong dogfood): a
    direct --varflow query bypasses `_collect_identifier_names` and goes
    straight to `var_flow()`'s `VarFlowWalker`, which had no member-access
    exclusion at all (a gap pre-dating this session, present for every
    language, not just Lua) — so a real local variable whose name happened
    to collide with an unrelated member-access name elsewhere in the same
    function (`opts.timeout` vs. `local timeout = ...`) picked up a bogus
    extra READ event from the unrelated dotted access."""

    def test_varflow_ignores_unrelated_dotted_member_of_same_name(self):
        from reveal.adapters.ast.nav import var_flow
        tree, root, get_text, _ = _parse_lua("""\
        function run(opts)
          local x = opts.timeout
          local timeout = 60
          return timeout
        end
        """)
        events = var_flow(root, 'timeout', 1, 999, get_text)
        read_lines = [e['line'] for e in events if e['kind'] == 'READ']
        write_lines = [e['line'] for e in events if e['kind'] == 'WRITE']
        self.assertNotIn(2, read_lines)  # opts.timeout must not count
        self.assertEqual(write_lines, [3])
        self.assertIn(4, read_lines)

    def test_varflow_no_double_read_for_table_field_shorthand_collision(self):
        """`{timeout = timeout}` (Lua table-constructor named field) must
        count as exactly one READ of the value, not two (label + value)."""
        from reveal.adapters.ast.nav import var_flow
        tree, root, get_text, _ = _parse_lua("""\
        function run(opts)
          local timeout = opts.timeout
          local t = new("x", {
            timeout = timeout,
          })
        end
        """)
        events = var_flow(root, 'timeout', 1, 999, get_text)
        read_lines = [e['line'] for e in events if e['kind'] == 'READ']
        self.assertEqual(read_lines, [4])

    def test_varflow_still_tracks_positional_and_computed_key_fields(self):
        """Positional (`{x}`) and computed-key (`{[k] = x}`) table fields
        have no label to exclude — every identifier there is a genuine
        read, unlike the named-key form above."""
        from reveal.adapters.ast.nav import var_flow
        tree, root, get_text, _ = _parse_lua("""\
        function run(k)
          local x = 1
          local t = {x, [k] = x}
        end
        """)
        events = var_flow(root, 'x', 1, 999, get_text)
        read_lines = [e['line'] for e in events if e['kind'] == 'READ']
        self.assertEqual(len(read_lines), 2)


class TestRubyDepsExcludesMethodNames(unittest.TestCase):
    """BACK-431 feature-breadth pass (--deps, real-corpus dogfood on
    Discourse's User#unread_notifications): Ruby's `call` node
    (`receiver.method(args)`) was entirely absent from
    `_MEMBER_ACCESS_KINDS`-style handling — unlike every other supported
    language's member-access node, it exposes 'receiver'/'method'/
    'arguments' as direct fields rather than nesting them in a shared
    member-access node, so it needed its own branch. Without it, every
    method name in a call chain (`DB.query_single(...)[0].to_i`) read as an
    independent undefined variable — 5 bogus PARAM entries from one line."""

    def setUp(self):
        self._tree, self._root, self._get_text, _ = _parse_ruby("""\
        def run(x)
          y = DB.query_single(x)[0].to_i
          y
        end
        """)

    def test_deps_excludes_chained_method_names(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        deps = collect_deps(self._root, 1, 999, self._get_text)
        names = {d['var'] for d in deps}
        self.assertNotIn('query_single', names)
        self.assertNotIn('to_i', names)
        self.assertIn('x', names)

    def test_deps_still_tracks_bare_call_name(self):
        """A receiver-less call (`puts(x)`) has no member name to strip —
        its own callee is itself an undefined read, same as Python's
        `sum(x)` — so it must still show up, unlike the chained case above."""
        from reveal.adapters.ast.nav_exits import collect_deps
        _, root, get_text, _ = _parse_ruby("""\
        def run(x)
          puts(x)
        end
        """)
        deps = collect_deps(root, 1, 999, get_text)
        names = {d['var'] for d in deps}
        self.assertIn('puts', names)


class TestRubyCallsShowsMethodName(unittest.TestCase):
    """BACK-431 feature-breadth pass (--calls, same Discourse dogfood):
    Ruby's `call` node holds 'receiver'/'method'/'arguments' as direct
    fields, not nested inside a shared member-access wrapper the way
    JS/Kotlin/C# do — the generic `_extract_callee` fallback grabbed only
    `child(0)` (the receiver), dropping the method name entirely.
    `DB.query_single(sql)` rendered as the nonsensical `DB(sql)` — as if
    the receiver constant itself were being called with the method's args."""

    def test_extract_callee_keeps_method_name(self):
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        _, root, get_text, _ = _parse_ruby("""\
        def run(x)
          DB.query_single(x)
        end
        """)
        calls = range_calls(root, 1, 999, get_text, CALL_NODE_TYPES)
        callees = [c['callee'] for c in calls]
        self.assertIn('DB.query_single', callees)

    def test_extract_callee_collapses_chained_call_to_dotted_form(self):
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        _, root, get_text, _ = _parse_ruby("""\
        def run(x)
          DB.query_single(x).to_i
        end
        """)
        calls = range_calls(root, 1, 999, get_text, CALL_NODE_TYPES)
        callees = [c['callee'] for c in calls]
        self.assertIn('DB.query_single', callees)
        self.assertIn('.to_i', callees)


class TestTsxDepsExcludesLowercaseJsxTags(unittest.TestCase):
    """BACK-431 feature-breadth pass (--deps, real-corpus dogfood on
    excalidraw's Actions.tsx SelectedShapeActions): a lowercase JSX tag
    (`<div>`, `<fieldset>`) is an HTML intrinsic — a string-like element
    name, not a variable — but it parses as a bare `identifier` with no
    distinguishing node kind from a real reference, same as everything
    else. `<div className="...">...</div>` alone produced 2 bogus PARAM
    entries. An uppercase tag (`<MyComponent>`) IS a real component
    reference and must still be tracked — JSX's own lowercase/uppercase
    convention is the only signal available."""

    def test_deps_excludes_lowercase_tag_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        _, root, get_text, _ = _parse_tsx("""\
        function run(x: number) {
          return (
            <div className="wrap">
              <fieldset>{x}</fieldset>
            </div>
          );
        }
        """)
        deps = collect_deps(root, 1, 999, get_text)
        names = {d['var'] for d in deps}
        self.assertNotIn('div', names)
        self.assertNotIn('fieldset', names)
        self.assertIn('x', names)

    def test_deps_excludes_self_closing_lowercase_tag(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        _, root, get_text, _ = _parse_tsx("""\
        function run(x: number) {
          return <div style={{ width: x }} />;
        }
        """)
        deps = collect_deps(root, 1, 999, get_text)
        names = {d['var'] for d in deps}
        self.assertNotIn('div', names)
        self.assertIn('x', names)

    def test_deps_still_tracks_uppercase_component_reference(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        _, root, get_text, _ = _parse_tsx("""\
        function run(x: number) {
          return <MyComponent value={x} />;
        }
        """)
        deps = collect_deps(root, 1, 999, get_text)
        names = {d['var'] for d in deps}
        self.assertIn('MyComponent', names)
        self.assertIn('x', names)

    def test_varflow_ignores_lowercase_tag_matching_unrelated_variable(self):
        """A direct --varflow query bypasses collect_deps's candidate pass
        and goes straight to var_flow()/VarFlowWalker — a separate walker
        that needed its own copy of this exclusion. Without it, a real
        variable whose name happens to match a JSX tag elsewhere in scope
        (rare, but the same class of collision Lua's `timeout` bug hit)
        would pick up bogus READ events from the tag occurrences."""
        from reveal.adapters.ast.nav import var_flow
        _, root, get_text, _ = _parse_tsx("""\
        function run() {
          const div = 1;
          return <div>{div}</div>;
        }
        """)
        events = var_flow(root, 'div', 1, 999, get_text)
        read_lines = [e['line'] for e in events if e['kind'] == 'READ']
        # Only the real `{div}` expression reference is a read — not the
        # opening/closing <div> tag-name occurrences.
        self.assertEqual(read_lines, [3])


# ─── BACK-638: Java/C# constructor_declaration missing from FUNCTION_NODE_TYPES
# / DEF_NODES / KEYWORD_LABEL ──────────────────────────────────────────────
# A Java constructor's name equals its enclosing class name, and
# `constructor_declaration` was absent from every function-node taxonomy —
# so element/nav lookups by that name fell through _find_element_node's
# 'function' pass entirely and matched the class_declaration node instead
# (same string name), silently returning the WHOLE CLASS BODY as the
# constructor's range. `--sideeffects`/`--boundary` on a constructor then
# attributed sibling methods' effects to it. Found via the Java
# sideeffects-recall-oracle loop (BACK-547 third language) on real
# Elasticsearch source: `RecoveryMetricsCollector` and `ElasticsearchIndexWriter`
# constructors both leaked a `logger.warn(...)` call from an unrelated,
# much-later method into their own --sideeffects output.

class TestSwiftDepsAndBoundary(unittest.TestCase):
    """BACK-431 feature-breadth pass (--deps/--boundary, real-corpus dogfood
    on ios-oss's AppDelegateViewModel.navigation(fromPushEnvelope:)): two
    distinct false-positive sources in Swift, both invisible to --varflow
    (which only tests one already-known variable at a time) but glaring in
    --deps/--boundary (which enumerate every identifier in range).

    1. A parameter's external argument label (`fromPushEnvelope` in
       `func f(fromPushEnvelope envelope: T)`) is a call-site-only label,
       never bound inside the function body — only the internal name
       (`envelope`) is a real variable. Swift's grammar exposes it as a
       distinct `external_name` field, previously never checked.
    2. Swift's leading-dot implicit-member shorthand (`.someCase`) — used
       both as a bare enum-case switch pattern and as an inferred-type
       static member reference — parses as `pattern`/`prefix_expression`
       wrapping a literal '.' token plus the member-name identifier; the
       identifier was read as an ordinary variable. A 7-case switch over
       `activity.category` alone produced 7 bogus PARAM entries.
    """

    def setUp(self):
        code = """\
        func navigate(fromEnvelope envelope: Int) -> String? {
            switch envelope {
            case .backing:
                return .project(.id(envelope))
            case .other:
                return nil
            }
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_swift(code)

    def test_deps_excludes_external_argument_label(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        deps = collect_deps(self._root, 1, 999, self._get_text)
        names = {d['var'] for d in deps}
        self.assertNotIn('fromEnvelope', names)
        self.assertIn('envelope', names)

    def test_deps_excludes_leading_dot_enum_case_and_member(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        deps = collect_deps(self._root, 1, 999, self._get_text)
        names = {d['var'] for d in deps}
        self.assertNotIn('backing', names)
        self.assertNotIn('other', names)
        self.assertNotIn('project', names)
        self.assertNotIn('id', names)


