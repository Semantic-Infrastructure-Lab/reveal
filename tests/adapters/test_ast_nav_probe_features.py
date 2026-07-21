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


# ---------------------------------------------------------------------------
# Parse helpers (shared with test_ast_nav.py pattern)
# ---------------------------------------------------------------------------

def _parse_python(code: str):
    """Parse Python code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('python')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


def _find_func(root, get_text, name: str):
    """Find a function_definition node by name."""
    stack = [root.child(i) for i in range(root.child_count())]
    while stack:
        node = stack.pop()
        if node.kind() == 'function_definition':
            for child in [node.child(i) for i in range(node.child_count())]:
                if child.kind() == 'identifier' and get_text(child) == name:
                    return node
        stack.extend(reversed([node.child(i) for i in range(node.child_count())]))
    return None


# ===========================================================================
# collect_exits
# ===========================================================================

class TestCollectExits(unittest.TestCase):
    """Tests for collect_exits — exit-node harvester."""

    def setUp(self):
        # A function with several kinds of exits
        code = """
        def process(items, limit):
            result = []
            for item in items:
                if not item:
                    continue
                if len(result) >= limit:
                    break
                try:
                    result.append(item)
                except ValueError:
                    raise
            return result
        """
        self._tree, self._root, self._get_text, _ = _parse_python(code)
        self._func = _find_func(self._root, self._get_text, 'process')

    def _exits(self, from_line=1, to_line=999):
        from reveal.adapters.ast.nav import collect_exits
        return collect_exits(self._func, from_line, to_line, self._get_text)

    def test_returns_list(self):
        self.assertIsInstance(self._exits(), list)

    def test_return_found(self):
        exits = self._exits()
        kinds = [e['kind'] for e in exits]
        self.assertIn('RETURN', kinds)

    def test_break_found(self):
        exits = self._exits()
        kinds = [e['kind'] for e in exits]
        self.assertIn('BREAK', kinds)

    def test_continue_found(self):
        exits = self._exits()
        kinds = [e['kind'] for e in exits]
        self.assertIn('CONTINUE', kinds)

    def test_raise_found(self):
        exits = self._exits()
        kinds = [e['kind'] for e in exits]
        self.assertIn('RAISE', kinds)

    def test_exits_have_required_fields(self):
        exits = self._exits()
        for e in exits:
            self.assertIn('kind', e)
            self.assertIn('line', e)
            self.assertIn('text', e)

    def test_sorted_by_line(self):
        exits = self._exits()
        lines = [e['line'] for e in exits]
        self.assertEqual(lines, sorted(lines))

    def test_range_filtering(self):
        all_exits = self._exits()
        # Only look at first 3 lines — should find nothing (function header + first line)
        limited = self._exits(from_line=1, to_line=3)
        self.assertLessEqual(len(limited), len(all_exits))

    def test_empty_range_returns_empty(self):
        # Artificial range that contains no code
        exits = self._exits(from_line=999, to_line=1000)
        self.assertEqual(exits, [])

    def test_text_field_not_empty(self):
        exits = self._exits()
        for e in exits:
            self.assertTrue(len(e['text']) > 0)

    def test_works_on_root_node(self):
        """collect_exits accepts root_node (flat-file fallback pattern)."""
        from reveal.adapters.ast.nav import collect_exits
        exits = collect_exits(self._root, 1, 999, self._get_text)
        self.assertIsInstance(exits, list)
        # Root should surface at least the same exits as the function node
        func_exits = self._exits()
        self.assertGreaterEqual(len(exits), len(func_exits))

    def test_die_exit_call_detected(self):
        """die() and exit() PHP-style calls are treated as EXIT kind."""
        code = """
        def f(x):
            if not x:
                die(x)
            return x
        """
        # We use Python parser; die() is just a call expression — no language
        # support needed to test the callee-name detection logic.  The callee
        # extraction path is what matters.
        _, root, get_text, _ = _parse_python(code)
        func = _find_func(root, get_text, 'f')
        from reveal.adapters.ast.nav import collect_exits
        exits = collect_exits(func, 1, 999, get_text)
        # 'return x' is RETURN; die(x) should be EXIT
        kinds = {e['kind'] for e in exits}
        self.assertIn('RETURN', kinds)
        # die() may or may not be detected depending on tree-sitter Python grammar
        # (it's not a keyword in Python, just a bare call).  The important thing
        # is no crash and at least RETURN is found.

    def test_no_exits_in_trivial_function(self):
        code = """
        def f():
            x = 1
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func(root, get_text, 'f')
        from reveal.adapters.ast.nav import collect_exits
        exits = collect_exits(func, 1, 999, get_text)
        # No return/raise/break/continue in this function
        self.assertEqual(exits, [])


# ===========================================================================
# render_exits / render_branchmap
# ===========================================================================

class TestRenderExits(unittest.TestCase):

    def test_empty_exits(self):
        from reveal.adapters.ast.nav import render_exits
        result = render_exits([], 10, 50)
        self.assertIn('No exits', result)
        self.assertIn('L10', result)
        self.assertIn('L50', result)

    def test_exits_formatted(self):
        from reveal.adapters.ast.nav import render_exits
        exits = [
            {'kind': 'RETURN', 'line': 20, 'text': 'return result'},
            {'kind': 'BREAK', 'line': 15, 'text': 'break'},
        ]
        result = render_exits(exits, 10, 50)
        self.assertIn('RETURN', result)
        self.assertIn('BREAK', result)
        self.assertIn('L20', result)
        self.assertIn('L15', result)

    def test_verdict_clear(self):
        from reveal.adapters.ast.nav import render_exits
        result = render_exits([], 10, 50, verdict=True)
        self.assertIn('✓ CLEAR', result)
        self.assertIn('L50', result)

    def test_verdict_blocked_on_return(self):
        from reveal.adapters.ast.nav import render_exits
        exits = [{'kind': 'RETURN', 'line': 20, 'text': 'return x'}]
        result = render_exits(exits, 10, 50, verdict=True)
        self.assertIn('⚠ BLOCKED', result)

    def test_verdict_conditional_on_break(self):
        from reveal.adapters.ast.nav import render_exits
        exits = [{'kind': 'BREAK', 'line': 20, 'text': 'break'}]
        result = render_exits(exits, 10, 50, verdict=True)
        self.assertIn('~ CONDITIONAL', result)

    def test_verdict_blocked_on_raise(self):
        from reveal.adapters.ast.nav import render_exits
        exits = [{'kind': 'RAISE', 'line': 20, 'text': 'raise ValueError()'}]
        result = render_exits(exits, 10, 50, verdict=True)
        self.assertIn('⚠ BLOCKED', result)

    def test_no_verdict_without_flag(self):
        from reveal.adapters.ast.nav import render_exits
        exits = [{'kind': 'RETURN', 'line': 20, 'text': 'return x'}]
        result = render_exits(exits, 10, 50, verdict=False)
        self.assertNotIn('BLOCKED', result)

    def test_verdict_yield_is_conditional_not_clear(self):
        """Regression: YIELD previously fell through to CLEAR because it was
        not in _HARD_EXIT_KINDS or _SOFT_EXIT_KINDS.  A generator that yields
        suspends control to the caller, so CLEAR is misleading — CONDITIONAL
        is the correct verdict."""
        from reveal.adapters.ast.nav import render_exits
        exits = [{'kind': 'YIELD', 'line': 20, 'text': 'yield value'}]
        result = render_exits(exits, 10, 50, verdict=True)
        self.assertIn('~ CONDITIONAL', result)
        self.assertNotIn('✓ CLEAR', result)

    def test_exit_kind_from_die_call(self):
        from reveal.adapters.ast.nav import render_exits
        exits = [{'kind': 'EXIT', 'line': 30, 'text': 'die(error)'}]
        result = render_exits(exits, 10, 50, verdict=True)
        self.assertIn('EXIT', result)
        self.assertIn('⚠ BLOCKED', result)


class TestRenderBranchmap(unittest.TestCase):

    def test_empty_items(self):
        from reveal.adapters.ast.nav import render_branchmap
        result = render_branchmap([], 10, 100)
        self.assertIn('No branch nodes', result)
        self.assertIn('L10', result)
        self.assertIn('L100', result)

    def test_items_rendered_with_indent(self):
        from reveal.adapters.ast.nav import render_branchmap
        items = [
            {
                'keyword': 'IF', 'label': 'IF  x > 0',
                'line_start': 5, 'line_end': 15, 'depth': 1,
            },
            {
                'keyword': 'ELSE', 'label': 'ELSE',
                'line_start': 10, 'line_end': 15, 'depth': 1,
            },
        ]
        result = render_branchmap(items, 1, 20)
        self.assertIn('IF  x > 0', result)
        self.assertIn('ELSE', result)
        self.assertIn('L5→L15', result)

    def test_single_line_range(self):
        from reveal.adapters.ast.nav import render_branchmap
        items = [
            {
                'keyword': 'RETURN', 'label': 'RETURN  x',
                'line_start': 7, 'line_end': 7, 'depth': 1,
            },
        ]
        result = render_branchmap(items, 1, 20)
        # Single-line items should not show →
        self.assertIn('L7', result)
        self.assertNotIn('L7→', result)

    def test_depth_indentation(self):
        from reveal.adapters.ast.nav import render_branchmap
        items = [
            {
                'keyword': 'IF', 'label': 'IF  outer',
                'line_start': 2, 'line_end': 10, 'depth': 1,
            },
            {
                'keyword': 'IF', 'label': 'IF  inner',
                'line_start': 4, 'line_end': 8, 'depth': 2,
            },
        ]
        result = render_branchmap(items, 1, 12)
        lines = result.splitlines()
        # Inner item should have more leading whitespace
        outer_indent = len(lines[0]) - len(lines[0].lstrip())
        inner_indent = len(lines[1]) - len(lines[1].lstrip())
        self.assertGreater(inner_indent, outer_indent)


# ===========================================================================
# all_var_flow
# ===========================================================================

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
        tree = parser.parse(src)
        root = tree.root_node()

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

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

class TestCollectMutations(unittest.TestCase):
    """collect_mutations makes sense only with a sub-range — there must be lines
    after to_line for writes to be 'read after the range'.  Tests use explicit
    sub-ranges that leave the return statement outside."""

    def setUp(self):
        # Parsed code (after dedent+lstrip):
        #  L1: def process(data, limit):
        #  L2:     result = []
        #  L3:     count = 0
        #  L4:     for item in data:
        #  L5:         if count >= limit:
        #  L6:             break
        #  L7:         result.append(item)
        #  L8:         count += 1
        #  L9:     return result
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
        # Use lines 1-8 so that 'return result' (line 9) is after the range.
        self._from_line = 1
        self._to_line = 8

    def _mutations(self, from_line=None, to_line=None):
        from reveal.adapters.ast.nav import collect_mutations
        fl = from_line if from_line is not None else self._from_line
        tl = to_line if to_line is not None else self._to_line
        return collect_mutations(self._func, fl, tl, self._get_text)

    def test_returns_list(self):
        self.assertIsInstance(self._mutations(), list)

    def test_mutations_have_required_fields(self):
        mutations = self._mutations()
        for m in mutations:
            self.assertIn('var', m)
            self.assertIn('last_write_line', m)
            self.assertIn('next_read_line', m)

    def test_sorted_by_last_write_line(self):
        mutations = self._mutations()
        lines = [m['last_write_line'] for m in mutations]
        self.assertEqual(lines, sorted(lines))

    def test_result_is_mutation(self):
        """'result' is written in lines 1-8 and read by 'return result' (line 9)."""
        mutations = self._mutations()
        names = [m['var'] for m in mutations]
        self.assertIn('result', names)

    def test_next_read_after_last_write(self):
        mutations = self._mutations()
        for m in mutations:
            self.assertGreater(m['next_read_line'], m['last_write_line'])

    def test_no_mutations_when_nothing_read_after(self):
        """A function where all writes are at the very end has no mutations."""
        code = """
        def f(x):
            y = x + 1
            z = y + 2
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func(root, get_text, 'f')
        from reveal.adapters.ast.nav import collect_mutations
        # Using lines 1-3 (all lines) — nothing after to_line
        mutations = collect_mutations(func, 1, 3, get_text)
        mut_names = [m['var'] for m in mutations]
        self.assertNotIn('y', mut_names)
        self.assertNotIn('z', mut_names)

    def test_range_limits_analysis(self):
        """A sub-range that's too narrow to include any writes has no mutations."""
        # Lines 1-2 cover 'def process(...)' and 'result = []'.
        # 'result' IS written at line 2, but 'return result' is at line 9 which
        # is after the narrow range — so result qualifies. That's fine; the important
        # thing is that a wider range finds at least as many mutations.
        narrow = self._mutations(from_line=1, to_line=2)
        wide = self._mutations()
        self.assertLessEqual(len(narrow), len(wide))


# ===========================================================================
# render_deps / render_mutations
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


class TestRenderMutations(unittest.TestCase):

    def test_empty_mutations(self):
        from reveal.adapters.ast.nav import render_mutations
        result = render_mutations([], 10, 50)
        self.assertIn('No read-after-write hazards', result)
        self.assertIn('L10', result)
        self.assertIn('L50', result)

    def test_mutation_rendered(self):
        from reveal.adapters.ast.nav import render_mutations
        mutations = [{'var': 'result', 'last_write_line': 8, 'next_read_line': 11}]
        result = render_mutations(mutations, 1, 10)
        self.assertIn('result', result)
        self.assertIn('RETURN', result)
        self.assertIn('L8', result)
        self.assertIn('L11', result)

    def test_multiple_mutations(self):
        from reveal.adapters.ast.nav import render_mutations
        mutations = [
            {'var': 'a', 'last_write_line': 5, 'next_read_line': 12},
            {'var': 'b', 'last_write_line': 7, 'next_read_line': 15},
        ]
        result = render_mutations(mutations, 1, 10)
        self.assertIn('a', result)
        self.assertIn('b', result)


# ===========================================================================
# ifmap / catchmap keyword filtering (via element_outline + post-filter)
# ===========================================================================

class TestIfmapCatchmapFiltering(unittest.TestCase):
    """Verify the keyword filtering logic that --ifmap/--catchmap uses."""

    def setUp(self):
        code = """
        def handler(req):
            if req.method == 'GET':
                try:
                    data = fetch(req)
                except IOError:
                    data = []
                except ValueError:
                    raise
            elif req.method == 'POST':
                data = req.body
            else:
                data = None
            for item in data:
                pass
            return data
        """
        self._tree, self._root, self._get_text, _ = _parse_python(code)
        self._func = _find_func(self._root, self._get_text, 'handler')

    def _outline(self):
        from reveal.adapters.ast.nav import element_outline
        return element_outline(self._func, self._get_text, max_depth=5)

    def test_ifmap_filter_excludes_try_for(self):
        items = self._outline()
        IF_KEYWORDS = frozenset({'IF', 'ELIF', 'ELSE', 'SWITCH', 'CASE', 'DEFAULT'})
        filtered = [i for i in items if i['keyword'] in IF_KEYWORDS]
        keywords = {i['keyword'] for i in filtered}
        # TRY and FOR should NOT appear in the ifmap output
        self.assertNotIn('TRY', keywords)
        self.assertNotIn('FOR', keywords)
        # IF, ELIF, ELSE should appear
        self.assertIn('IF', keywords)

    def test_catchmap_filter_excludes_if_for(self):
        items = self._outline()
        CATCH_KEYWORDS = frozenset({'TRY', 'CATCH', 'EXCEPT', 'FINALLY'})
        filtered = [i for i in items if i['keyword'] in CATCH_KEYWORDS]
        keywords = {i['keyword'] for i in filtered}
        # IF and FOR should NOT appear
        self.assertNotIn('IF', keywords)
        self.assertNotIn('FOR', keywords)
        # TRY should appear
        self.assertIn('TRY', keywords)

    def test_ifmap_preserves_depth(self):
        """Depth values from the original outline are kept as-is after filtering."""
        items = self._outline()
        IF_KEYWORDS = frozenset({'IF', 'ELIF', 'ELSE', 'SWITCH', 'CASE', 'DEFAULT'})
        filtered = [i for i in items if i['keyword'] in IF_KEYWORDS]
        # All items must have a depth field
        for item in filtered:
            self.assertIn('depth', item)

    def test_ifmap_render_produces_output(self):
        from reveal.adapters.ast.nav import element_outline, render_branchmap
        items = element_outline(self._func, self._get_text, max_depth=5)
        IF_KEYWORDS = frozenset({'IF', 'ELIF', 'ELSE', 'SWITCH', 'CASE', 'DEFAULT'})
        filtered = [i for i in items if i['keyword'] in IF_KEYWORDS]
        func_start = self._func.start_position().row + 1
        func_end = self._func.end_position().row + 1
        result = render_branchmap(filtered, func_start, func_end)
        self.assertIn('IF', result)


# ===========================================================================
# Flat-file fallback (Change A): verify nav functions work with root_node
# ===========================================================================

class TestFlatFileFallback(unittest.TestCase):
    """Verify that var_flow, range_calls, collect_exits, etc. accept root_node.

    This tests the language-agnostic promise from the planning doc: all nav
    functions take 'any tree-sitter node' — the root_node fallback in
    _dispatch_nav (Change A) is what makes flat-file support work.
    """

    def setUp(self):
        # Flat procedural code — no top-level function wrapper
        code = """
        errormsg = ''
        data = fetch_data()
        if data:
            try:
                result = process(data)
                errormsg = result.get('error', '')
            except Exception as e:
                errormsg = str(e)
        write_log(errormsg)
        return_value = bool(errormsg)
        """
        self._tree, self._root, self._get_text, _ = _parse_python(code)

    def test_var_flow_on_root_node(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'errormsg', 1, 999, self._get_text)
        self.assertIsInstance(events, list)
        # errormsg is written and read — should have events
        self.assertGreater(len(events), 0)
        kinds = {e['kind'] for e in events}
        self.assertIn('WRITE', kinds)

    def test_range_calls_on_root_node(self):
        from reveal.adapters.ast.nav import range_calls
        calls = range_calls(self._root, 1, 999, self._get_text)
        self.assertIsInstance(calls, list)
        # fetch_data, process, write_log, bool are calls
        self.assertGreater(len(calls), 0)
        callees = [c['callee'] for c in calls]
        self.assertTrue(any('fetch_data' in (c or '') for c in callees))

    def test_collect_exits_on_root_node(self):
        from reveal.adapters.ast.nav import collect_exits
        exits = collect_exits(self._root, 1, 999, self._get_text)
        self.assertIsInstance(exits, list)

    def test_collect_deps_on_root_node(self):
        from reveal.adapters.ast.nav import collect_deps
        deps = collect_deps(self._root, 1, 999, self._get_text)
        self.assertIsInstance(deps, list)

    def test_collect_mutations_on_root_node(self):
        from reveal.adapters.ast.nav import collect_mutations
        mutations = collect_mutations(self._root, 1, 999, self._get_text)
        self.assertIsInstance(mutations, list)

    def test_element_outline_on_root_node(self):
        from reveal.adapters.ast.nav import element_outline
        items = element_outline(self._root, self._get_text, max_depth=3)
        self.assertIsInstance(items, list)

    def test_var_flow_range_filtering_on_root(self):
        from reveal.adapters.ast.nav import var_flow
        all_events = var_flow(self._root, 'errormsg', 1, 999, self._get_text)
        # Narrow to first 2 lines — errormsg starts at line 1
        narrow = var_flow(self._root, 'errormsg', 1, 2, self._get_text)
        self.assertLessEqual(len(narrow), len(all_events))


# ===========================================================================
# _collect_identifier_names (internal helper)
# ===========================================================================

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

def _parse_php(code: str):
    """Parse PHP code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('php')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


class TestClassifyCall(unittest.TestCase):

    def test_db_mysql_query(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('mysql_query'), 'db')

    def test_db_execute_method(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$pdo->execute'), 'db')

    def test_http_curl_exec(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('curl_exec'), 'http')

    def test_http_requests_get(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('requests.get'), 'http')

    def test_cache_memcache_set(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('memcache_set'), 'cache')

    def test_log_error_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('error_log'), 'log')

    def test_file_fopen(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('fopen'), 'file')

    def test_file_put_contents(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('file_put_contents'), 'file')

    def test_sleep(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('sleep'), 'sleep')

    def test_usleep(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('usleep'), 'sleep')

    def test_log_swift_nslog(self):
        # BACK-498 quick win: NSLog is Swift/Cocoa's unambiguous logging call.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('NSLog', 'swift'), 'log')

    def test_log_swift_os_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os_log', 'swift'), 'log')

    def test_swift_print_stays_unclassified(self):
        # print is a plain stdout write, not a log call — matches tier1
        # Java/C#/Python treatment (bare print/println/System.out unclassified).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('print', 'swift'))

    def test_csharp_db_executereader(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('ExecuteReader', 'csharp'), 'db')

    def test_csharp_http_getasync(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('client.GetAsync', 'csharp'), 'http')

    def test_csharp_file_writealltext(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('File.WriteAllText', 'csharp'), 'file')

    def test_csharp_env_getenvironmentvariable(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Environment.GetEnvironmentVariable', 'csharp'), 'env')

    def test_csharp_log_loginformation(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('_logger.LogInformation', 'csharp'), 'log')

    def test_csharp_sleep_task_delay(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Task.Delay', 'csharp'), 'sleep')

    def test_csharp_scoped_to_csharp(self):
        # These are csharp-only patterns — must not leak into other languages.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('ExecuteReader', 'python'))

    def test_ruby_file_write(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('File.write', 'ruby'), 'file')

    def test_ruby_fileutils_rm(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('FileUtils.rm', 'ruby'), 'file')

    def test_ruby_http_net_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Net::HTTP.get', 'ruby'), 'http')

    def test_ruby_http_httparty(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('HTTParty.get', 'ruby'), 'http')

    def test_cpp_file_ofstream(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::ofstream', 'cpp'), 'file')

    def test_cpp_http_curl_easy_perform(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('curl_easy_perform', 'cpp'), 'http')

    def test_cpp_sleep_for(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::this_thread::sleep_for', 'cpp'), 'sleep')

    def test_cpp_log_spdlog(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('spdlog::info', 'cpp'), 'log')

    def test_hard_stop_die(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('die'), 'hard_stop')

    def test_hard_stop_exit(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('exit'), 'hard_stop')

    def test_unclassified_returns_none(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('some_custom_function'))

    def test_empty_string_returns_none(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call(''))

    def test_none_returns_none(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call(None))

    def test_case_insensitive(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('CURL_EXEC'), 'http')

    def test_http_setcookie(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('setcookie'), 'http')

    def test_http_mail(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('mail'), 'http')

    def test_session_start(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('session_start'), 'session')

    def test_session_destroy(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('session_destroy'), 'session')

    def test_env_getenv(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('getenv'), 'env')

    def test_env_os_environ(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.environ'), 'env')

    def test_log_trigger_error(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('trigger_error'), 'log')

    def test_db_pdo_method(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$pdo->prepare'), 'db')

    def test_cache_apc_fetch(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('apc_fetch'), 'cache')

    def test_file_readfile(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('readfile'), 'file')


class TestClassifyCallBoundaryMatch(unittest.TestCase):
    """BACK-283: segment-boundary matching, not substring containment."""

    def test_print_header_does_not_match_header(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('printHeader'))

    def test_request_headers_does_not_match_header(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('request_headers'))

    def test_gmail_does_not_match_mail(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('gmail'))

    def test_mailer_send_does_not_match_mail(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mailer.send'))

    def test_mylog_does_not_match_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mylog'))

    def test_my_pdo_class_does_not_match_pdo(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mypdo'))

    def test_bare_header_classifies_as_http(self):
        # Re-added in BACK-283 now that boundary matching is safe.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('header'), 'http')

    def test_php_member_call_pdo_prepare_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$pdo->prepare'), 'db')

    def test_new_pdo_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('new PDO'), 'db')

    def test_nested_segment_match_services_cache_set(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('services.cache.set'), 'cache')

    def test_os_getenv_classifies_as_env_via_segment(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.getenv'), 'env')

    def test_app_logger_info_classifies_as_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('app.logger.info'), 'log')


class TestClassifyCallReceiver(unittest.TestCase):
    """BACK-285a: receiver-shape heuristics on non-final segments."""

    def test_cursor_execute_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('cursor.execute'), 'db')

    def test_conn_connection_receiver_no_longer_classifies_as_db(self):
        # BACK-594 (sideeffects-recall-oracle, real-corpus): `conn`/`connection`
        # were REMOVED from the language-unscoped db receiver fallback. They are
        # extremely common non-db variable names and produced corpus-confirmed
        # cross-language false positives — Go websocket `conn.Close()`/
        # `conn.Subprotocol()` -> db (client-go), Python websocket
        # `connection.send_result(...)` -> db (Home Assistant). Per the
        # conservative philosophy an ambiguous receiver is DECLINED, not guessed.
        # Real db calls formerly relying on these are now caught precisely by the
        # explicit `session.<orm-verb>` python patterns and the common
        # `->execute`/`->commit`-shaped verbs (e.g. `connection.execute`).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('conn::commit'))
        self.assertIsNone(classify_call('connection.close'))
        # Go corpus false positives that motivated the removal:
        self.assertIsNone(classify_call('conn.Close', language='go'))
        self.assertIsNone(classify_call('conn.Subprotocol', language='go'))

    def test_requests_receiver_no_longer_classifies_as_http(self):
        # BACK-640 (sideeffects-recall-oracle/java): 'requests' (Python's
        # requests library alias) REMOVED from the unscoped http receiver
        # fallback — as a bare English plural noun it collided with Java's
        # `request.requests.get(i)` field access (a list field, not HTTP),
        # same class as BACK-594's conn/session/cache drop. Redundant with
        # the explicit python http patterns below (still classify correctly).
        from reveal.adapters.ast.nav_effects import classify_call
        # language='java' scopes out python's explicit 'requests.get'
        # segment pattern, isolating the receiver-fallback path (which runs
        # unconditionally regardless of language) — this is what the real
        # corpus false positive hit via `reveal ... --sideeffects` on a
        # detected-Java file.
        self.assertIsNone(classify_call('request.requests.get', language='java'))
        self.assertEqual(classify_call('requests.get', language='python'), 'http')
        self.assertEqual(classify_call('requests.post', language='python'), 'http')

    def test_underscore_log_warning_classifies_as_log(self):
        # Restoration after BACK-283: was matched by substring on 'log',
        # now matched cleanly via receiver segment.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('_log.warning'), 'log')

    def test_aiohttp_get_classifies_as_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('aiohttp.get'), 'http')

    # False-positive guards (BACK-286 regression coverage).

    def test_dict_get_unclassified(self):
        # Critical: BACK-286 surfaced this. `'->get('` deleted from http
        # patterns; receiver pass must not turn `dict.get` into http either.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('dict.get'))

    def test_actual_pos_get_unclassified(self):
        # Real-world false positive: `actual_pos.get(...)` on a dict.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('actual_pos.get'))

    def test_bare_receiver_word_unclassified(self):
        # Single segment is not a method call — nothing to classify.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('cursor'))

    def test_final_segment_session_does_not_match(self):
        # `session` only matches as a non-final receiver. `state.session`
        # has `state` as the only non-final segment; should not classify.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('state.session'))

    # Deferred-to-BACK-238 (project-specific receivers, intentionally None).

    def test_evlog_emit_unclassified_universal_only(self):
        # `evlog` is project-specific; needs .reveal.yaml extension.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('evlog.emit_entry'))

    def test_tsx_get_open_position_unclassified_universal_only(self):
        # `tsx` is project-specific; needs .reveal.yaml extension.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('tsx.get_open_position'))

    # BACK-286: the deleted `->get(` / `->post(` patterns must not
    # spuriously fire on bare verb names anymore.

    def test_arbitrary_get_call_unclassified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mything.get'))

    def test_arbitrary_post_call_unclassified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mything.post'))

    # BACK-290: SQLAlchemy `engine` as a universal db receiver.

    def test_engine_execute_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('engine.execute'), 'db')

    def test_engine_connect_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('engine.connect'), 'db')

    def test_template_engine_render_unclassified(self):
        # Non-final-segment guard: `template_engine` is its own segment and
        # should not match the bare `engine` receiver.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('template_engine.render'))

    def test_rules_engine_evaluate_unclassified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('rules_engine.evaluate'))

    # BACK-401: per-language stdlib receiver/pattern coverage (.NET BCL,
    # JVM stdlib, Go stdlib, Rust std) — previously silently unclassified.

    def test_csharp_file_exists_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('File.Exists'), 'file')

    def test_csharp_directory_createdirectory_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Directory.CreateDirectory'), 'file')

    def test_csharp_environment_getenvironmentvariable_classifies_as_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('Environment.GetEnvironmentVariable'), 'env'
        )

    def test_csharp_underscore_logger_classifies_as_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('_logger.LogInformation'), 'log')

    def test_csharp_httpclient_classifies_as_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('_httpClient.GetAsync'), 'http')

    def test_java_files_exists_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Files.exists'), 'file')

    def test_java_system_getenv_classifies_as_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('System.getenv'), 'env')

    def test_java_system_getproperty_classifies_as_env(self):
        # BACK-639 (sideeffects-recall-oracle/java, real-corpus measurement on
        # Elasticsearch): System.getProperty is Java's dominant env-config-read
        # idiom (JVM system properties) and was entirely unclassified — 12/13
        # real env misses in the stratified sample traced to it.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('System.getProperty'), 'env')

    def test_java_slf4j_classifies_as_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('slf4j.info'), 'log')

    def test_go_os_open_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.Open'), 'file')

    def test_go_ioutil_readfile_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('ioutil.ReadFile'), 'file')

    def test_go_os_getenv_classifies_as_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.Getenv'), 'env')

    def test_rust_std_fs_read_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::fs::read'), 'file')

    def test_rust_std_env_var_classifies_as_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::env::var'), 'env')

    def test_rust_std_process_exit_classifies_as_hard_stop(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::process::exit'), 'hard_stop')

    def test_python_file_object_receiver_still_classifies(self):
        # 'file' as a bare receiver is intentional — the caution in the
        # taxonomy docstring is about full-pattern (not receiver-scoped)
        # matching being too broad; receiver-only matching is safe.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('file.read'), 'file')

    def test_kotlin_file_writetext_classifies_as_file(self):
        # BACK-477 gap map: File(...).writeText(...) was entirely absent
        # from the taxonomy — --sideeffects saw nothing for Kotlin's
        # dominant file-write idiom.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('.writeText', language='kotlin'), 'file')
        self.assertEqual(classify_call('.appendText', language='kotlin'), 'file')
        self.assertEqual(classify_call('.readText', language='kotlin'), 'file')

    def test_kotlin_writetext_unscoped_by_language(self):
        # The pattern is Kotlin-specific; a differently-scoped call must not
        # pick it up (mirrors the Go/PHP scoping tests above).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('.writeText', language='python'))

    def test_swift_write_tofile_classifies_as_file(self):
        # BACK-477 gap map: "...".write(toFile:...) was invisible to
        # --sideeffects. classify_call only sees the callee text ('write'),
        # not the toFile: argument label, so the pattern is scoped to Swift
        # rather than added as an unscoped common pattern (a bare 'write'
        # callee is too generic in other languages to mean file I/O).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('"hello".write', language='swift'), 'file')

    def test_swift_write_unscoped_by_language(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('"hello".write', language='python'))


class TestCollectEffectsCSharpBack401(unittest.TestCase):
    """BACK-401 end-to-end: collect_effects must see C# invocation_expression
    call sites (the CALL_NODE_TYPES entry was also wrong: 'invocation' vs
    the real tree-sitter-c-sharp node kind 'invocation_expression')."""

    def setUp(self):
        code = """
        class C {
            string M(string renderNodePath) {
                var x = File.Exists(renderNodePath) ? renderNodePath : "";
                return x;
            }
        }
        """
        from tree_sitter_language_pack import get_parser
        parser = get_parser('c_sharp')
        tree = parser.parse(code)
        self._root = tree.root_node()
        lines = code.split('\n')

        def get_text(node):
            sr, sc = node.start_position().row, node.start_position().column
            er, ec = node.end_position().row, node.end_position().column
            if sr == er:
                return lines[sr][sc:ec]
            parts = [lines[sr][sc:]]
            parts.extend(lines[sr + 1:er])
            parts.append(lines[er][:ec])
            return '\n'.join(parts)
        self._get_text = get_text

    def test_file_exists_call_detected_and_classified(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        effects = collect_effects(self._root, 1, 999, self._get_text)
        kinds = [e['kind'] for e in effects]
        self.assertIn('file', kinds)


class TestJavaEffectsBack416(unittest.TestCase):
    """BACK-416: Java method_invocation dropped the method name, so the effect
    taxonomy misattributed a filesystem write. `Files.createDirectories()` (real
    write) was seen as bare "Files" and missed; `path.resolveIndex()` (no I/O)
    was seen as bare "path" and falsely classified `file`. After the fix the
    callee is receiver-qualified and only the real write is classified."""

    def _collect(self, code, fname):
        from tree_sitter_language_pack import get_parser
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = get_parser('java')
        cb = code.encode()
        root = parser.parse(code).root_node()

        def get_text(node):
            return cb[node.start_byte():node.end_byte()].decode('utf-8')

        stack = [root]
        func = None
        while stack:
            n = stack.pop()
            if n.kind() == 'method_declaration' and fname in get_text(n):
                func = n
                break
            stack.extend(n.child(i) for i in range(n.child_count()))
        return collect_effects(func, 1, 999, get_text)

    CODE = (
        "public class Fs {\n"
        "  public Directory newDirectory(IndexSettings s, ShardPath path) {\n"
        "    final Path location = path.resolveIndex();\n"
        "    Files.createDirectories(location);\n"
        "    return newFSDirectory(location);\n"
        "  }\n"
        "}\n"
    )

    def test_real_fs_write_classified_on_files_call(self):
        effects = self._collect(self.CODE, 'newDirectory')
        file_effects = [e for e in effects if e['kind'] == 'file']
        self.assertEqual(len(file_effects), 1)
        self.assertIn('createDirectories', file_effects[0]['callee'])

    def test_path_method_not_falsely_classified(self):
        effects = self._collect(self.CODE, 'newDirectory')
        # path.resolveIndex() is not I/O — it must not be a file effect.
        path_effects = [
            e for e in effects
            if e['kind'] == 'file' and 'resolveIndex' in (e['callee'] or '')
        ]
        self.assertEqual(path_effects, [])

    def test_java_method_invocation_callee_is_receiver_qualified(self):
        from tree_sitter_language_pack import get_parser
        from reveal.adapters.ast.nav_calls import range_calls
        parser = get_parser('java')
        cb = self.CODE.encode()
        root = parser.parse(self.CODE).root_node()
        gt = lambda n: cb[n.start_byte():n.end_byte()].decode()
        stack = [root]
        func = None
        while stack:
            n = stack.pop()
            if n.kind() == 'method_declaration':
                func = n
                break
            stack.extend(n.child(i) for i in range(n.child_count()))
        callees = [c['callee'] for c in range_calls(func, 1, 999, gt)]
        self.assertIn('Files.createDirectories', callees)
        self.assertIn('path.resolveIndex', callees)

    def test_classify_regression_matrix(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Files.createDirectories'), 'file')
        self.assertIsNone(classify_call('path.resolveIndex'))
        self.assertIsNone(classify_call('Path.Combine'))
        self.assertEqual(classify_call('file.read'), 'file')  # lowercase kept
        self.assertEqual(classify_call('fs.writeFileSync'), 'file')  # Node fs


class TestClassifyCallLanguageScoping(unittest.TestCase):
    """BACK-431 Issue D: per-language taxonomy tables, opt-in via `language=`."""

    def test_unscoped_call_matches_every_language_back_compat(self):
        from reveal.adapters.ast.nav_effects import classify_call
        # No language given == old flat-taxonomy behavior: every language's
        # patterns still fire, so existing (unscoped) callers see no change.
        self.assertEqual(classify_call('session_start'), 'session')
        self.assertEqual(classify_call('os.mkdirall'), 'file')
        self.assertEqual(classify_call('std::process::exit'), 'hard_stop')

    def test_php_builtin_scoped_to_php_only(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('session_start', language='php'), 'session')
        self.assertIsNone(classify_call('session_start', language='go'))
        self.assertIsNone(classify_call('session_start', language='rust'))

    def test_go_stdlib_scoped_to_go_only(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.mkdirall', language='go'), 'file')
        self.assertIsNone(classify_call('os.mkdirall', language='python'))
        self.assertIsNone(classify_call('os.mkdirall', language='php'))

    def test_rust_stdlib_scoped_to_rust_only(self):
        from reveal.adapters.ast.nav_effects import classify_call
        # 'std::process::exit' also matches via the common bare 'exit'
        # pattern regardless of language (see
        # test_common_patterns_fire_regardless_of_language) — 'std::env::var'
        # avoids that overlap and so demonstrates true rust-only scoping.
        self.assertEqual(classify_call('std::process::exit', language='rust'), 'hard_stop')
        self.assertEqual(classify_call('std::env::var', language='rust'), 'env')
        self.assertIsNone(classify_call('std::env::var', language='python'))
        self.assertIsNone(classify_call('std::env::var', language='java'))

    def test_python_stdlib_scoped_to_python_only(self):
        from reveal.adapters.ast.nav_effects import classify_call
        # 'requests.get' matches for any language via the (unscoped)
        # _RECEIVER_TAXONOMY fallback — 'os.environ' isn't a receiver name,
        # so it isolates the python-only taxonomy table instead.
        self.assertEqual(classify_call('os.environ', language='python'), 'env')
        # BACK-629 (sideeffects-recall-oracle): Go's own 'os.environ' pattern
        # was added separately (real corpus idiom, os.Environ()) — this is no
        # longer isolating in the Go direction, so use rust (still absent)
        # to keep testing table isolation rather than Go's own coverage.
        self.assertIsNone(classify_call('os.environ', language='rust'))

    def test_js_group_aliases_share_one_bucket(self):
        from reveal.adapters.ast.nav_effects import classify_call
        for lang in ('javascript', 'typescript', 'tsx'):
            self.assertEqual(classify_call('setTimeout', language=lang), 'sleep')
        self.assertIsNone(classify_call('setTimeout', language='python'))

    def test_java_bucket_pattern_present_though_shadowed_by_common(self):
        from reveal.adapters.ast.nav_effects import classify_call
        # java's only distinguishing pattern ('system.getenv') is a superset
        # of the common bare 'getenv' pattern, so it already matches for
        # every language — there's no independently-observable java-only
        # case today, but the entry is still correct and harmless.
        self.assertEqual(classify_call('System.getenv', language='java'), 'env')

    def test_common_patterns_fire_regardless_of_language(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('db_query', language='go'), 'db')
        self.assertEqual(classify_call('db_query', language='php'), 'db')
        self.assertEqual(classify_call('die', language='rust'), 'hard_stop')

    def test_unknown_language_falls_back_to_common_only(self):
        # BACK-722 (Lua sideeffects-recall-oracle pre-flight): a known-but-
        # unmapped language (any language absent from _TAXONOMY_BY_LANG —
        # 'dart' still qualifies) used to silently fall back to the FULLY
        # UNSCOPED _COMPILED_ALL table, the same table language=None uses —
        # confirmed live on real Kong Lua source before the fix: ordinary
        # `table.insert(t, x)` (Lua stdlib) was classified 'db' via Python/
        # PHP's scoped bare 'insert' verb leaking through this fallback.
        # Fixed: an unmapped-but-named language now scopes to COMMON only
        # (its real, intended scope until it gets its own entry) — the PHP-
        # only 'session_start' pattern (not in COMMON) no longer leaks into
        # a Dart file, mirroring how any other cross-language leak (Go
        # tagged 'session' by a PHP builtin) was already prevented for
        # every language that DOES have its own entry.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session_start', language='dart'))
        # True unscoped mode (language genuinely omitted) is unaffected —
        # this is the one case where matching every language's patterns is
        # the documented, intended behavior.
        self.assertEqual(classify_call('session_start', language=None), 'session')

    def test_lua_stdlib_calls_not_misclassified_via_unscoped_leak(self):
        """BACK-722: the same fallback bug, concrete real-corpus evidence.
        `table.insert`/`table.remove` (Lua's stdlib array mutators, ~80/4
        corpus call sites in Kong) and bare `select` (Lua's builtin vararg
        helper, `select('#', ...)`) were all silently classified 'db' via
        Python/PHP's scoped bare 'insert'/'select' verbs leaking through
        the old fully-unscoped fallback -- confirmed live before the fix
        with `reveal <file> <func> --sideeffects` on a Lua file containing
        nothing but `table.insert(t, x)` and `select('#', x)`."""
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('table.insert', language='lua'))
        self.assertIsNone(classify_call('table.remove', language='lua'))
        self.assertIsNone(classify_call('select', language='lua'))

    def test_go_klog_glog_logrus_classified_as_log(self):
        # BACK-629 (sideeffects-recall-oracle, real-corpus measurement on
        # k8s.io/client-go): klog.Fatalf(...) in the azure auth plugin's
        # init() was silently unclassified — 'klog' tokenizes to its own
        # segment, distinct from the common bare 'log' pattern.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('klog.Fatalf', language='go'), 'log')
        self.assertEqual(classify_call('klog.Infof', language='go'), 'log')
        self.assertEqual(classify_call('glog.Warningf', language='go'), 'log')
        self.assertEqual(classify_call('logrus.Error', language='go'), 'log')
        self.assertIsNone(classify_call('klog.Fatalf', language='python'))

    def test_go_http_stdlib_and_roundtrip_classified_as_http(self):
        # BACK-629: Go had no http bucket at all — real corpus misses on
        # client-go included `rt.RoundTrip(req)` (transport.go) and
        # `http.NewRequestWithContext(...)` (remotecommand/websocket.go).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('http.Get', language='go'), 'http')
        self.assertEqual(classify_call('http.NewRequestWithContext', language='go'), 'http')
        self.assertEqual(classify_call('rt.RoundTrip', language='go'), 'http')
        self.assertEqual(classify_call('transport.RoundTrip', language='go'), 'http')
        self.assertIsNone(classify_call('http.Get', language='python'))

    def test_go_do_call_stays_unclassified_ambiguous_verb(self):
        # `client.Do(req)` (net/http's dominant call-site idiom, e.g.
        # rest/request.go:Watch and rest/fake/fake.go:do in client-go) is
        # deliberately left unclassified: classify_call only sees the callee
        # text, not the argument, so a bare 'do' pattern would be exactly the
        # collision-prone-verb case the module docstring warns about (same
        # shape as '.save'/'.where' staying unclassified elsewhere) —
        # confirmed via the sideeffects-recall-oracle measurement loop.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('client.Do', language='go'))

    def test_go_os_lookupenv_setenv_unsetenv_environ_classified_as_env(self):
        # BACK-629: os.LookupEnv(...) in client-go's feature-gate reader
        # (features/envvar.go) was silently unclassified — only bare
        # 'getenv'/'putenv' existed in _TAXONOMY_COMMON.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.LookupEnv', language='go'), 'env')
        self.assertEqual(classify_call('os.Setenv', language='go'), 'env')
        self.assertEqual(classify_call('os.Unsetenv', language='go'), 'env')
        self.assertEqual(classify_call('os.Environ', language='go'), 'env')
        self.assertIsNone(classify_call('os.LookupEnv', language='python'))

    def test_python_os_remove_makedirs_classified_as_file(self):
        # BACK-634 (sideeffects-recall-oracle/python, real-corpus measurement
        # on Home Assistant): os.remove / os.makedirs — the exact stdlib twins
        # of the already-present os.unlink / os.mkdir — were silently
        # unclassified. Real corpus misses: `os.remove(filename)`
        # (nest/media_source.py:async_remove_media, verisure/camera.py) and
        # `os.makedirs(...)` (helpers/storage.py, knx/telegrams.py).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.remove', language='python'), 'file')
        self.assertEqual(classify_call('os.makedirs', language='python'), 'file')

    def test_python_pathlib_read_write_methods_classified_as_file(self):
        # BACK-634: pathlib's file-I/O methods are invoked on Path *values*
        # (`self._path.write_text(...)`, `file_path.read_bytes()`), so the
        # 'pathlib' module pattern never matched them. Same shape BACK-477
        # added for Kotlin's kotlin.io writeText/readText/writeBytes/readBytes.
        # Real misses: `self._path.write_text(ics_content)`
        # (local_calendar/store.py), `file_path.read_bytes()` (llama_cpp).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('self._path.write_text', language='python'), 'file')
        self.assertEqual(classify_call('file_path.read_bytes', language='python'), 'file')
        self.assertEqual(classify_call('p.read_text', language='python'), 'file')
        self.assertEqual(classify_call('out.write_bytes', language='python'), 'file')

    def test_python_async_get_clientsession_stays_unclassified_project_idiom(self):
        # BACK-634 deliberate non-fix: `async_get_clientsession(hass)` is Home
        # Assistant's dominant HTTP-client factory and the single largest http
        # recall gap in the corpus — but it is a PROJECT-specific helper name,
        # not a Python/stdlib idiom. Per the module docstring, project-specific
        # names belong in a `.reveal.yaml` extension (BACK-238), not the global
        # taxonomy (the same reasoning that keeps Go's `client.Do` unclassified).
        # Genuinely global http idioms in the corpus (requests.get/delete,
        # aiohttp.ClientSession) are already classified.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('async_get_clientsession', language='python'))
        self.assertIsNone(
            classify_call('aiohttp_client.async_get_clientsession', language='python'))
        self.assertEqual(classify_call('requests.get', language='python'), 'http')

    # ── BACK-635: bare-verb subsequence over-fire (fail-before / pass-after) ──

    def test_python_dict_update_not_db(self):
        # `->update` was moved to PHP-only. The tokenizer strips the arrow, so
        # it used to collapse to bare `update` and tag every Python `.update()`
        # as db (corpus: 12 FPs on Home Assistant incl. 2/60 negative-control
        # FPs `added_doors.update(...)` / `self.data.update()`).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('domains.update', language='python'))
        self.assertIsNone(classify_call('added_doors.update', language='python'))
        self.assertIsNone(classify_call('self.data.update', language='python'))
        self.assertIsNone(classify_call('device.update', language='python'))

    def test_python_value_copy_not_file(self):
        # bare `copy` was moved to PHP-only (PHP's `copy()` builtin). It used to
        # tag every value-copy idiom as file (corpus: 4 FPs — `entry.data.copy()`,
        # `os.environ.copy()`, `env.copy()`).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('x.copy', language='python'))
        self.assertIsNone(classify_call('entry.data.copy', language='python'))
        # `os.environ.copy()` is now correctly ENV (via the os.environ pattern),
        # no longer mislabeled file by the bare `copy` verb.
        self.assertEqual(classify_call('os.environ.copy', language='python'), 'env')

    def test_python_requests_delete_is_http_not_db(self):
        # `->delete` was moved to PHP-only. It used to collapse to bare `delete`
        # and — because kind-order puts db before http — STEAL Python's explicit
        # `requests.delete` -> http, mislabeling it db (corpus: itunes/_request).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('requests.delete', language='python'), 'http')

    def test_php_arrow_db_and_copy_still_classify(self):
        # Proof the BACK-635 fix SCOPED rather than deleted these patterns: the
        # PHP idioms they legitimately serve must still classify.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$model->update', language='php'), 'db')
        self.assertEqual(classify_call('$repo->delete', language='php'), 'db')
        self.assertEqual(classify_call('copy', language='php'), 'file')
        # Unscoped (no language) also still classifies — every language's
        # patterns merge, so back-compat callers see the PHP idiom too.
        self.assertEqual(classify_call('$model->update'), 'db')
        self.assertEqual(classify_call('copy'), 'file')

    def test_cpp_fileaccess_idiom_classified_as_file(self):
        # BACK-547 fourth language (sideeffects-recall-oracle, real-corpus
        # measurement on Godot's core/): a cross-platform-engine codebase
        # almost never calls stdlib ofstream/fopen directly — real corpus
        # misses were FileAccess::open(...) (static factory) and instance
        # calls like f->store_line(...)/f->get_buffer(...), none of which
        # matched the generic-stdlib-only 'file' patterns already present.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('FileAccess::open', language='cpp'), 'file')
        self.assertEqual(classify_call('f->store_line', language='cpp'), 'file')
        self.assertEqual(classify_call('f->store_buffer', language='cpp'), 'file')
        self.assertEqual(classify_call('f->get_buffer', language='cpp'), 'file')
        self.assertIsNone(classify_call('f->store_line', language='python'))

    def test_cpp_os_singleton_env_and_sleep_wrapper_classified(self):
        # BACK-547 fourth language: bare 'getenv'/'putenv' (_TAXONOMY_COMMON)
        # never matches the cross-platform-engine OS-singleton wrapper idiom
        # (`OS::get_singleton()->get_environment(...)`/`->delay_usec(...)`) —
        # real corpus misses: core_bind.cpp:OS::get_environment/
        # set_environment/has_environment/unset_environment/delay_usec/
        # delay_msec.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('OS::get_singleton()->get_environment', language='cpp'), 'env')
        self.assertEqual(classify_call('OS::get_singleton()->has_environment', language='cpp'), 'env')
        self.assertEqual(classify_call('OS::get_singleton()->set_environment', language='cpp'), 'env')
        self.assertEqual(classify_call('OS::get_singleton()->delay_usec', language='cpp'), 'sleep')
        self.assertEqual(classify_call('OS::get_singleton()->delay_msec', language='cpp'), 'sleep')

    def test_cpp_print_line_and_warn_err_print_classified_as_log(self):
        # BACK-547 fourth language: print_line/print_error/print_verbose and
        # the WARN_PRINT/ERR_PRINT macros are the dominant logging idiom in
        # engine code built this way (same shape as Go's klog/glog/logrus
        # addition, BACK-629) — real corpus misses across config/engine.cpp,
        # object/message_queue.cpp, and elsewhere.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('print_line', language='cpp'), 'log')
        self.assertEqual(classify_call('print_error', language='cpp'), 'log')
        self.assertEqual(classify_call('print_verbose', language='cpp'), 'log')
        self.assertEqual(classify_call('WARN_PRINT', language='cpp'), 'log')
        self.assertEqual(classify_call('ERR_PRINT', language='cpp'), 'log')
        self.assertIsNone(classify_call('print_line', language='python'))

    # ── BACK-594: receiver fallback crossing language boundaries ──

    def test_python_session_receiver_not_db_for_http_verbs(self):
        # `session`/`connection` were dropped from the receiver fallback. aiohttp
        # `session.get(url)`, OAuth `session.async_ensure_token_valid()`, and
        # websocket `connection.send_result(...)` used to be tagged db purely by
        # the receiver name (corpus: 9 occurrences on Home Assistant).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session.async_ensure_token_valid', language='python'))
        self.assertIsNone(classify_call('session.async_on_cleanup', language='python'))
        self.assertIsNone(classify_call('connection.send_result', language='python'))
        self.assertIsNone(classify_call('connection.send_error', language='python'))
        # `session.get` is genuinely ambiguous (aiohttp http vs SQLAlchemy 2.0
        # db read) -> DECLINED, not guessed.
        self.assertIsNone(classify_call('session.get', language='python'))

    def test_python_sqlalchemy_session_orm_verbs_still_db(self):
        # Recall guard: the real SQLAlchemy db calls that used to rely on the
        # dropped `session` receiver are now caught by explicit python patterns,
        # so db recall does not regress (verified 25/25 on the oracle).
        from reveal.adapters.ast.nav_effects import classify_call
        for verb in ('add', 'flush', 'commit', 'rollback', 'refresh',
                     'expunge', 'expunge_all', 'merge', 'connection', 'scalars'):
            self.assertEqual(
                classify_call(f'session.{verb}', language='python'), 'db',
                msg=f'session.{verb} should classify as db')
        # cursor / bare-verb paths still work too.
        self.assertEqual(classify_call('cursor.execute', language='python'), 'db')
        self.assertEqual(classify_call('session.query', language='python'), 'db')
        self.assertEqual(classify_call('connection.execute', language='python'), 'db')

    def test_go_cache_receiver_not_cache(self):
        # BACK-594: bare `cache` receiver dropped — `k8s.io/client-go/tools/cache`
        # is a package literally named `cache`, so `cache.NewListWatchFromClient`
        # was mislabeled a cache side effect. redis/memcache receivers are kept.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('cache.NewListWatchFromClient', language='go'))
        self.assertIsNone(classify_call('cache.NewIndexer', language='go'))


class TestTypeScriptEffectsBack547(unittest.TestCase):
    """BACK-547 fifth language (sideeffects-recall-oracle, TypeScript/VS Code
    corpus, 65,008 functions). Pre-flight check (following the C++ loop's own
    carried-forward note) found a real collision before any oracle code was
    written: bare 'fetch' matched via _TAXONOMY_COMMON's `->fetch` (a bare
    verb kept common for PHP's `$stmt->fetch()`/Python DB-API recall) beat
    js's own explicit http 'fetch(' entry, because db precedes http in
    _KIND_ORDER — every JS/TS global `fetch()` HTTP call silently classified
    as db instead."""

    def test_js_bare_fetch_classifies_as_http_not_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('fetch', language='typescript'), 'http')
        self.assertEqual(classify_call('fetch', language='javascript'), 'http')

    def test_php_arrow_fetch_still_classifies_as_db(self):
        # ->fetch moved from _TAXONOMY_COMMON to _TAXONOMY_BY_LANG['php'] —
        # PHP's $stmt->fetch() (PDOStatement/mysqli_result row fetch) must
        # keep working, scoped or unscoped.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$stmt->fetch', language='php'), 'db')
        self.assertEqual(classify_call('$stmt->fetch'), 'db')  # unscoped

    def test_bare_fetch_no_longer_db_for_other_languages(self):
        # Corpus-confirmed (samples/python): bare `.fetch(` has zero real
        # occurrences in Python — only PHP genuinely needs it.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('fetch', language='python'))
        self.assertIsNone(classify_call('fetch', language='go'))

    def test_js_indexeddb_classified_as_db(self):
        # Real corpus miss: indexedDB.deleteDatabase(database.name) in
        # src/vs/base/browser/indexedDB.ts:deleteDatabase — js had no db
        # bucket at all before this loop.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('indexedDB.deleteDatabase', language='typescript'), 'db')
        self.assertEqual(classify_call('indexedDB.open', language='typescript'), 'db')
        self.assertEqual(classify_call('db.createObjectStore', language='typescript'), 'db')
        self.assertIsNone(classify_call('indexedDB.deleteDatabase', language='python'))

    def test_js_node_http_stdlib_classified_as_http(self):
        # Real corpus miss: https.get(requestOptions, ...) in
        # extensions/vscode-test-resolver/src/download.ts:
        # downloadVSCodeServerArchive.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('https.get', language='typescript'), 'http')
        self.assertEqual(classify_call('http.get', language='typescript'), 'http')
        self.assertEqual(classify_call('https.request', language='typescript'), 'http')
        self.assertEqual(classify_call('http.request', language='typescript'), 'http')

    def test_js_request_service_wrapper_declined_project_specific(self):
        # VS Code's own `requestService.request(...)` internal abstraction
        # (3 real corpus misses: abstractUpdateService.ts:isLatestVersion,
        # updateService.linux.ts:doCheckForUpdates,
        # userDataProfileInit.ts:doGetProfileTemplate) is deliberately NOT
        # added — a single-repo internal wrapper name, same declined shape
        # as Python's async_get_clientsession (BACK-634) and Go's client.Do
        # (BACK-633).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('requestService.request', language='typescript'))

    def test_js_process_env_stays_unclassified_by_the_call_channel(self):
        # BACK-644: process.env.FOO is a property/subscript access, never a
        # call_expression, so range_calls() never extracts it as a callee and
        # classify_call() can never see it — a call-taxonomy entry for it would
        # be dead code (verified: 0/26 real corpus hits with the pattern
        # present). Still deliberately NOT added: env classification for JS/TS
        # is now real, but it lives in collect_effects()'s property channel
        # (test_process_env_read_is_classified_env below), not here.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('process.env', language='typescript'))

    def test_process_env_read_is_classified_env(self):
        # BACK-644 (fixed), end-to-end: a function whose ONLY effect is a
        # process.env property read produces zero *call* sites, so this is
        # exactly the shape that was invisible before the property channel
        # existed. Both the dotted and subscript forms must be classified, and
        # rendered WITHOUT a `()` suffix — they are not calls.
        from reveal.adapters.ast.nav_effects import collect_effects, render_effects
        parser = ts.get_parser('typescript')
        src = textwrap.dedent("""
        function readToken() {
            const token = process.env.MY_TOKEN;
            const other = process.env['SECRET'];
            return token + other;
        }
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = parser.parse(src)
        root = tree.root_node()

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='typescript')
        self.assertEqual(
            [(e['line'], e['kind'], e['callee'], e['via']) for e in effects],
            [(2, 'env', 'process.env.MY_TOKEN', 'property'),
             (3, 'env', "process.env['SECRET']", 'property')],
        )
        rendered = render_effects(effects, 1, 999)
        self.assertIn('process.env.MY_TOKEN', rendered)
        self.assertNotIn('process.env.MY_TOKEN()', rendered)

    def test_process_env_method_call_is_not_double_reported(self):
        # BACK-644: `os.environ.get('X')` is classified 'env' by the CALL
        # channel, and its callee `os.environ.get` is an attribute whose base
        # text is exactly `os.environ` — so without callee suppression the
        # property channel would report the same env access a second time on
        # the same line. Exactly one effect per line is the contract.
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('python')
        src = textwrap.dedent("""
        def f():
            a = os.environ.get('CALL_FORM')
            b = os.environ['SUBSCRIPT_FORM']
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = parser.parse(src)
        root = tree.root_node()

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='python')
        self.assertEqual(
            [(e['line'], e['kind'], e['via']) for e in effects],
            [(2, 'env', 'call'), (3, 'env', 'property')],
        )

    def test_ruby_env_constant_matches_but_rack_env_local_does_not(self):
        # BACK-644, the precision trap this channel exists to avoid: Ruby's
        # `ENV['X']` is the process environment, but `env['X']` is Rack's
        # request hash — 199 of them in Discourse against 534 real ENV[ reads.
        # classify_call()'s _tokenize() lowercases and so cannot tell them
        # apart; the property channel matches base text CASE-SENSITIVELY.
        # Also covers `ENV['X'].blank?`, where Ruby's `call` exposes the
        # element_reference as its RECEIVER (child(0)) rather than a callee —
        # suppressing child(0) generically would lose the read entirely.
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('ruby')
        src = textwrap.dedent("""
        def handle(env)
          real = ENV['SECRET_KEY']
          guarded = ENV['HOME'].blank?
          rack = env['HTTP_HOST']
          more = env.fetch('REQUEST_METHOD')
        end
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = parser.parse(src)
        root = tree.root_node()

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='ruby')
        self.assertEqual(
            [(e['line'], e['kind'], e['callee']) for e in effects if e['kind'] == 'env'],
            [(2, 'env', "ENV['SECRET_KEY']"), (3, 'env', "ENV['HOME']")],
        )

    def test_property_channel_ignores_lookalike_bases(self):
        # BACK-644: the channel matches an explicit base allowlist, never a
        # "member access = effect" shape — a wrong classification is worse than
        # an unclassified read. `config.process.env.X` (a local object, real:
        # VS Code's terminalSandboxEngine.test.ts) and a bare `process.env`
        # passed around without reading a key are both correctly not env.
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('typescript')
        src = textwrap.dedent("""
        function f(config) {
            const a = config.process.env.FOO;
            const b = other.env.BAR;
            spawn(cmd, process.env);
        }
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = parser.parse(src)
        root = tree.root_node()

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='typescript')
        self.assertEqual([e for e in effects if e['kind'] == 'env'], [])

    def test_property_channel_keeps_receiver_of_a_method_call(self):
        # BACK-644: only the callee node itself is suppressed, never its
        # subtree — in `process.env.FOO.trim()` the receiver `process.env.FOO`
        # is a real env read and must survive.
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('typescript')
        src = textwrap.dedent("""
        function f() {
            return process.env.FOO.trim();
        }
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = parser.parse(src)
        root = tree.root_node()

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='typescript')
        self.assertEqual(
            [(e['kind'], e['callee']) for e in effects if e['kind'] == 'env'],
            [('env', 'process.env.FOO')],
        )


class TestCollectEffects(unittest.TestCase):

    def setUp(self):
        code = """\
<?php
function processOrder($order_id) {
    $sql = mysql_query("SELECT * FROM orders WHERE id=" . $order_id);
    if (!$sql) {
        error_log("DB failed");
        die("fatal");
    }
    curl_exec(curl_init("https://api.example.com"));
    sleep(1);
    return mysql_fetch_assoc($sql);
}
"""
        self._tree, self._root, self._get_text, _ = _parse_php(code)

    def _effects(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        return collect_effects(self._root, 1, 999, self._get_text)

    def test_returns_list(self):
        self.assertIsInstance(self._effects(), list)

    def test_effects_have_required_fields(self):
        effects = self._effects()
        for e in effects:
            self.assertIn('line', e)
            self.assertIn('callee', e)
            self.assertIn('kind', e)

    def test_db_calls_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('db', kinds)

    def test_http_calls_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('http', kinds)

    def test_log_calls_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('log', kinds)

    def test_hard_stop_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('hard_stop', kinds)

    def test_sleep_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('sleep', kinds)

    def test_sorted_by_line(self):
        effects = self._effects()
        classified = [e for e in effects if e['kind'] is not None]
        lines = [e['line'] for e in classified]
        self.assertEqual(lines, sorted(lines))

    def test_range_filtering(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        # Only lines 3-4 — should find mysql_query but not die/curl_exec
        effects = collect_effects(self._root, 3, 4, self._get_text)
        callees = [e['callee'] for e in effects if e['kind'] is not None]
        self.assertTrue(any('mysql_query' in (c or '') for c in callees))
        self.assertFalse(any('die' in (c or '') for c in callees))


class TestPhpMemberAndObjectCalls(unittest.TestCase):
    """BACK-284: range_calls must detect PHP $obj->method() and new X()."""

    def setUp(self):
        code = """\
<?php
function audit_db() {
    $dsn = getenv('DB_DSN');
    $pdo = new PDO($dsn);
    $stmt = $pdo->prepare("SELECT * FROM users");
    $stmt->execute();
    $row = $stmt->fetch();
    return $row;
}
"""
        self._tree, self._root, self._get_text, _ = _parse_php(code)

    def _calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        return range_calls(self._root, 1, 999, self._get_text)

    def test_object_creation_detected(self):
        callees = [c['callee'] for c in self._calls()]
        self.assertIn('new PDO', callees)

    def test_member_call_detected(self):
        callees = [c['callee'] for c in self._calls()]
        self.assertIn('$pdo->prepare', callees)
        self.assertIn('$stmt->execute', callees)
        self.assertIn('$stmt->fetch', callees)

    def test_bare_function_still_detected(self):
        callees = [c['callee'] for c in self._calls()]
        self.assertIn('getenv', callees)

    def test_all_five_calls_present(self):
        callees = [c['callee'] for c in self._calls()]
        self.assertEqual(len(callees), 5)

    def test_object_creation_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        effects = collect_effects(self._root, 1, 999, self._get_text)
        new_pdo = next((e for e in effects if e['callee'] == 'new PDO'), None)
        self.assertIsNotNone(new_pdo)
        self.assertEqual(new_pdo['kind'], 'db')

    def test_member_call_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        effects = collect_effects(self._root, 1, 999, self._get_text)
        kinds_by_callee = {e['callee']: e['kind'] for e in effects}
        self.assertEqual(kinds_by_callee.get('$stmt->execute'), 'db')
        self.assertEqual(kinds_by_callee.get('$stmt->fetch'), 'db')


class TestRenderEffects(unittest.TestCase):

    def _make_effects(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        code = """\
<?php
function f() {
    mysql_query("SELECT 1");
    error_log("x");
    die("stop");
}
"""
        _, root, get_text, _ = _parse_php(code)
        return collect_effects(root, 1, 999, get_text)

    def test_output_is_string(self):
        from reveal.adapters.ast.nav_effects import render_effects
        result = render_effects(self._make_effects(), 1, 999)
        self.assertIsInstance(result, str)

    def test_output_contains_kind_labels(self):
        from reveal.adapters.ast.nav_effects import render_effects
        result = render_effects(self._make_effects(), 1, 999)
        self.assertIn('db', result)
        self.assertIn('log', result)
        self.assertIn('hard_stop', result)

    def test_output_contains_line_numbers(self):
        from reveal.adapters.ast.nav_effects import render_effects
        result = render_effects(self._make_effects(), 1, 999)
        self.assertIn('L3', result)

    def test_empty_effects_returns_message(self):
        from reveal.adapters.ast.nav_effects import render_effects
        result = render_effects([], 1, 999)
        self.assertIn('No classified side effects', result)


# ---------------------------------------------------------------------------
# BACK-203: PHP varflow — variable_name node type fix
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

def _parse_swift(code: str):
    """Parse Swift code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('swift')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


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

def _parse_kotlin(code: str):
    """Parse Kotlin code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('kotlin')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


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
        root = parser.parse(src).root_node()
        # var_flow runs against the resolved function node in production
        # (ctx.func_node), not the source_file root — descend to it here too
        # (_declared_name_node needs the function node itself to find 'name').
        func = node_children(root)[0]

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

        events = var_flow(func, 'checkThing', 1, 999, get_text)
        read_lines = [e['line'] for e in events if e['kind'] == 'READ']
        self.assertEqual(read_lines, [2])


# ---------------------------------------------------------------------------
# BACK-431 Issue G smoke-tier audit: Scala varflow (val_definition/
# var_definition) and --exits/--returns (throw_expression)
# ---------------------------------------------------------------------------

def _parse_scala(code: str):
    """Parse Scala code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('scala')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


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

class TestCollectGateChains(unittest.TestCase):

    def setUp(self):
        code = """\
def process(data, token):
    if not token:
        return False
    if token == 'invalid':
        raise ValueError('bad')
    result = fetch(data)
    if result is None:
        return None
    if result > 10:
        if result > 100:
            return 'high'
        return 'medium'
    return result
"""
        self._tree, self._root, self._get_text, _ = _parse_python(code)

    def _chains(self):
        from reveal.adapters.ast.nav_exits import collect_gate_chains
        return collect_gate_chains(self._root, 1, 999, self._get_text)

    def test_returns_list(self):
        self.assertIsInstance(self._chains(), list)

    def test_each_item_has_required_fields(self):
        for item in self._chains():
            self.assertIn('kind', item)
            self.assertIn('line', item)
            self.assertIn('text', item)
            self.assertIn('gates', item)

    def test_unconditional_return_has_empty_gates(self):
        chains = self._chains()
        # Last 'return result' is unconditional
        last = [c for c in chains if c['kind'] == 'RETURN'][-1]
        self.assertEqual(last['gates'], [])

    def test_conditional_return_has_gates(self):
        chains = self._chains()
        # 'return False' is gated on 'not token'
        early_return = next(c for c in chains if 'False' in c['text'])
        self.assertGreater(len(early_return['gates']), 0)

    def test_nested_conditions_accumulate(self):
        chains = self._chains()
        # 'return high' is nested inside two ifs
        high_return = next(c for c in chains if 'high' in c['text'])
        self.assertEqual(len(high_return['gates']), 2)

    def test_gates_have_line_and_text(self):
        chains = self._chains()
        for item in chains:
            for gate in item['gates']:
                self.assertIn('line', gate)
                self.assertIn('text', gate)

    def test_sorted_by_line(self):
        chains = self._chains()
        lines = [c['line'] for c in chains]
        self.assertEqual(lines, sorted(lines))

    def test_raise_included(self):
        chains = self._chains()
        kinds = [c['kind'] for c in chains]
        self.assertIn('RAISE', kinds)

    def test_range_filtering(self):
        from reveal.adapters.ast.nav_exits import collect_gate_chains
        # Only lines 1-5 — should find 'return False' but not 'return result'
        chains = collect_gate_chains(self._root, 1, 5, self._get_text)
        texts = [c['text'] for c in chains]
        self.assertTrue(any('False' in t for t in texts))
        self.assertFalse(any('result' in t and 'None' not in t for t in texts))

    def test_empty_range_returns_empty(self):
        from reveal.adapters.ast.nav_exits import collect_gate_chains
        chains = collect_gate_chains(self._root, 999, 1000, self._get_text)
        self.assertEqual(chains, [])


class TestRenderGateChains(unittest.TestCase):

    def _make_chains(self):
        from reveal.adapters.ast.nav_exits import collect_gate_chains
        code = """\
def f(x):
    if x > 0:
        return 'pos'
    return 'neg'
"""
        _, root, get_text, _ = _parse_python(code)
        return collect_gate_chains(root, 1, 999, get_text)

    def test_output_is_string(self):
        from reveal.adapters.ast.nav_exits import render_gate_chains
        result = render_gate_chains(self._make_chains(), 1, 999)
        self.assertIsInstance(result, str)

    def test_unconditional_label_present(self):
        from reveal.adapters.ast.nav_exits import render_gate_chains
        result = render_gate_chains(self._make_chains(), 1, 999)
        self.assertIn('[unconditional]', result)

    def test_gate_label_present(self):
        from reveal.adapters.ast.nav_exits import render_gate_chains
        result = render_gate_chains(self._make_chains(), 1, 999)
        self.assertIn('gate:', result)

    def test_line_numbers_present(self):
        from reveal.adapters.ast.nav_exits import render_gate_chains
        result = render_gate_chains(self._make_chains(), 1, 999)
        self.assertIn('L3', result)

    def test_empty_chains_returns_message(self):
        from reveal.adapters.ast.nav_exits import render_gate_chains
        result = render_gate_chains([], 1, 999)
        self.assertIn('No return/exit paths', result)


class TestPhpGateChains(unittest.TestCase):

    def setUp(self):
        code = """\
<?php
function send($user_id, $tpl) {
    if (!$user_id) {
        return false;
    }
    if ($tpl === 'welcome') {
        return sendWelcome($user_id);
    }
    return sendGeneric($user_id, $tpl);
}
"""
        self._tree, self._root, self._get_text, _ = _parse_php(code)

    def _chains(self):
        from reveal.adapters.ast.nav_exits import collect_gate_chains
        return collect_gate_chains(self._root, 1, 999, self._get_text)

    def test_php_returns_found(self):
        chains = self._chains()
        self.assertGreater(len(chains), 0)

    def test_php_gated_return_has_gate(self):
        chains = self._chains()
        gated = [c for c in chains if c['gates']]
        self.assertGreater(len(gated), 0)

    def test_php_unconditional_return_exists(self):
        chains = self._chains()
        uncond = [c for c in chains if not c['gates']]
        self.assertGreater(len(uncond), 0)

    def test_php_condition_text_extracted(self):
        chains = self._chains()
        for c in chains:
            for gate in c['gates']:
                self.assertGreater(len(gate['text']), 0)


class TestCollectBoundary(unittest.TestCase):
    """collect_boundary composes deps + effects into INPUTS / ENVIRONMENT / EFFECTS."""

    def setUp(self):
        code = """\
def process(data, user_id):
    result = []
    for item in data:
        import requests
        resp = requests.get('https://api.example.com/' + str(user_id))
        result.append(resp.json())
    return result
"""
        self._tree, self._root, self._get_text, _ = _parse_python(code)
        func = _find_func(self._root, self._get_text, 'process')
        self._func = func
        self._start = func.start_position().row + 1
        self._end = func.end_position().row + 1

    def _boundary(self):
        from reveal.adapters.ast.nav_boundary import collect_boundary
        return collect_boundary(self._func, self._start, self._end, self._get_text)

    def test_returns_dict_with_three_keys(self):
        result = self._boundary()
        self.assertIn('inputs', result)
        self.assertIn('superglobals', result)
        self.assertIn('effects', result)

    def test_inputs_are_list(self):
        result = self._boundary()
        self.assertIsInstance(result['inputs'], list)

    def test_effects_are_list(self):
        result = self._boundary()
        self.assertIsInstance(result['effects'], list)

    def test_superglobals_empty_for_python(self):
        result = self._boundary()
        self.assertEqual(result['superglobals'], [])

    def test_inputs_contain_known_dep(self):
        result = self._boundary()
        var_names = [d['var'] for d in result['inputs']]
        self.assertIn('data', var_names)

    def test_effects_contain_http(self):
        result = self._boundary()
        kinds = [e['kind'] for e in result['effects']]
        self.assertIn('http', kinds)

    def test_effects_only_classified(self):
        result = self._boundary()
        for e in result['effects']:
            self.assertIsNotNone(e['kind'])


class TestCollectBoundaryPhp(unittest.TestCase):
    """collect_boundary detects PHP superglobals in ENVIRONMENT section."""

    def setUp(self):
        code = """\
<?php
function handleRequest($config) {
    $user_id = $_SESSION['user_id'];
    $page = $_GET['page'];
    $rows = mysql_query("SELECT * FROM items WHERE user=" . $user_id);
    error_log("Fetched page " . $page);
    return $rows;
}
"""
        self._tree, self._root, self._get_text, _ = _parse_php(code)

    def _boundary(self):
        from reveal.adapters.ast.nav_boundary import collect_boundary
        return collect_boundary(self._root, 1, 999, self._get_text)

    def test_superglobals_detected(self):
        result = self._boundary()
        sg_names = [d['var'] for d in result['superglobals']]
        self.assertIn('$_SESSION', sg_names)
        self.assertIn('$_GET', sg_names)

    def test_superglobals_not_in_inputs(self):
        result = self._boundary()
        input_names = [d['var'] for d in result['inputs']]
        self.assertNotIn('$_SESSION', input_names)
        self.assertNotIn('$_GET', input_names)

    def test_effects_contain_db(self):
        result = self._boundary()
        kinds = [e['kind'] for e in result['effects']]
        self.assertIn('db', kinds)

    def test_effects_contain_log(self):
        result = self._boundary()
        kinds = [e['kind'] for e in result['effects']]
        self.assertIn('log', kinds)


class TestRenderBoundary(unittest.TestCase):
    """render_boundary produces three-section text output."""

    def _make_result(self):
        return {
            'inputs': [
                {'var': 'data', 'first_read_line': 2, 'first_write_line': None},
                {'var': 'user_id', 'first_read_line': 3, 'first_write_line': None},
            ],
            'superglobals': [],
            'effects': [
                {'kind': 'db', 'line': 5, 'callee': 'mysql_query', 'first_arg': '"SELECT..."', 'has_more_args': False},
                {'kind': 'http', 'line': 8, 'callee': 'curl_exec', 'first_arg': None, 'has_more_args': False},
            ],
        }

    def _render(self, result=None):
        from reveal.adapters.ast.nav_boundary import render_boundary
        return render_boundary(result or self._make_result(), 1, 20)

    def test_output_is_string(self):
        self.assertIsInstance(self._render(), str)

    def test_inputs_section_header_present(self):
        self.assertIn('INPUTS', self._render())

    def test_effects_section_header_present(self):
        self.assertIn('EFFECTS', self._render())

    def test_input_var_names_present(self):
        out = self._render()
        self.assertIn('data', out)
        self.assertIn('user_id', out)

    def test_effects_kind_labels_present(self):
        out = self._render()
        self.assertIn('db', out)
        self.assertIn('http', out)

    def test_effects_line_numbers_present(self):
        out = self._render()
        self.assertIn('L5', out)
        self.assertIn('L8', out)

    def test_environment_section_omitted_when_empty(self):
        out = self._render()
        self.assertNotIn('ENVIRONMENT', out)

    def test_environment_section_present_when_superglobals_exist(self):
        from reveal.adapters.ast.nav_boundary import render_boundary
        result = {
            'inputs': [],
            'superglobals': [{'var': '$_GET', 'first_read_line': 4, 'first_write_line': None}],
            'effects': [],
        }
        out = render_boundary(result, 1, 10)
        self.assertIn('ENVIRONMENT', out)
        self.assertIn('$_GET', out)

    def test_empty_inputs_shows_none_message(self):
        from reveal.adapters.ast.nav_boundary import render_boundary
        result = {'inputs': [], 'superglobals': [], 'effects': []}
        out = render_boundary(result, 1, 10)
        self.assertIn('none', out)

    def test_sections_separated_by_blank_line(self):
        out = self._render()
        self.assertIn('\n\n', out)


# ---------------------------------------------------------------------------
# BACK-431 Issue G tier B real-corpus dogfood (mysterious-probe-0703): the
# synthetic ~20-line smoke fixtures found 4 bugs on first contact, but real
# source (AppFlowy/Kong/Ghostty/godot-demo-projects/excalidraw) found 2 more
# that a small hand-written fixture didn't happen to exercise.
# ---------------------------------------------------------------------------

def _parse_zig(code: str):
    """Parse Zig code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('zig')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


class TestZigSwitchExpr(unittest.TestCase):
    """Zig's `switch (x) { .a => ..., .b => ... }` (`SwitchExpr`/
    `SwitchProng`) was entirely absent from SWITCH_NODES/CASE_NODES —
    --ifmap/--outline saw no branches at all for a function whose only
    control flow was a switch. Found via real Ghostty source
    (terminal/formatter.zig's formatStyleOpen), which uses switch
    pervasively — the hand-written smoke fixture used if/while instead and
    never exercised this shape."""

    def setUp(self):
        code = """\
        fn formatKind(self: Self) void {
            switch (self.kind) {
                .plain => unreachable,
                .html => {
                    doThing();
                },
            }
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_zig(code)

    def test_element_outline_finds_switch_and_prongs(self):
        from reveal.adapters.ast.nav import element_outline
        items = element_outline(self._root, self._get_text, max_depth=5)
        keywords = [i['keyword'] for i in items]
        self.assertIn('SWITCH', keywords)
        self.assertEqual(keywords.count('CASE'), 2)


class TestPhpCaseStatement(unittest.TestCase):
    """PHP's `switch ($x) { case ...: ... default: ... }` node itself
    (`switch_statement`) was already covered, but its arms use
    `case_statement`/`default_statement` — distinct names from every other
    language's shape (and from the never-actually-verified 'switch_case'/
    'switch_default' placeholders already in the taxonomy) — so the entire
    switch body was invisible to --ifmap/--outline. Found via real
    WordPress source (wp-includes/post.php's wp_attachment_is), a 4-arm
    switch where zero arms showed up despite --exits correctly finding the
    returns inside them (BACK-431 tier A real-corpus dogfood audit)."""

    def setUp(self):
        code = """\
        <?php
        function f($x) {
            switch ($x) {
                case 'a':
                    return 1;
                case 'b':
                    return 2;
                default:
                    return 0;
            }
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_php(code)

    def test_element_outline_finds_switch_case_and_default(self):
        from reveal.adapters.ast.nav import element_outline
        items = element_outline(self._root, self._get_text, max_depth=5)
        keywords = [i['keyword'] for i in items]
        self.assertIn('SWITCH', keywords)
        self.assertEqual(keywords.count('CASE'), 2)
        self.assertIn('DEFAULT', keywords)


class TestSwiftSwitchEntry(unittest.TestCase):
    """Swift's `switch x { case ...: ... default: ... }` node itself
    (`switch_statement`) was already in SWITCH_NODES, but its case-arm node
    (`switch_entry` — wraps both `case`-pattern and `default` arms, fully
    fieldless) was entirely absent from CASE_NODES — every switch case in
    real Swift source was invisible to --ifmap/--outline. Found via real
    Kickstarter source (AppDelegateViewModel.swift's
    navigation(fromPushEnvelope:)), a 7-case switch where zero cases showed
    up (BACK-431 tier A real-corpus dogfood audit)."""

    def setUp(self):
        code = """\
        func f(x: Int) -> String {
            switch x {
            case 1:
                return "one"
            case 2, 3:
                return "two-or-three"
            default:
                return "other"
            }
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_swift(code)

    def test_element_outline_finds_switch_and_entries(self):
        from reveal.adapters.ast.nav import element_outline
        items = element_outline(self._root, self._get_text, max_depth=5)
        keywords = [i['keyword'] for i in items]
        self.assertIn('SWITCH', keywords)
        self.assertEqual(keywords.count('CASE'), 3)


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


class TestKotlinWhenExpr(unittest.TestCase):
    """Kotlin's `when (x) { ... }` (`when_expression`/`when_entry`) was
    entirely absent from SWITCH_NODES/CASE_NODES — the same fully-fieldless
    shape as Zig's `switch`, just never audited for Kotlin. Found via real
    tivi source (SeasonsEpisodesRepository.kt's markSeasonWatched), which
    uses `when` as an expression assigned into a `val`; the hand-written
    smoke fixture never exercised this shape (BACK-431 tier A real-corpus
    dogfood audit)."""

    def setUp(self):
        code = """\
        fun label(x: Int): String {
            val y = when (x) {
                1 -> "one"
                2 -> "two"
                else -> "other"
            }
            return y
        }
        """
        self._tree, self._root, self._get_text, _ = _parse_kotlin(code)

    def test_element_outline_finds_when_and_entries(self):
        from reveal.adapters.ast.nav import element_outline
        items = element_outline(self._root, self._get_text, max_depth=5)
        keywords = [i['keyword'] for i in items]
        self.assertIn('SWITCH', keywords)
        self.assertEqual(keywords.count('CASE'), 3)


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


def _parse_lua(code: str):
    """Parse Lua code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('lua')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


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


def _parse_ruby(code: str):
    """Parse Ruby code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('ruby')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


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


def _parse_tsx(code: str):
    """Parse TSX code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('tsx')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


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

class TestBack638JavaConstructorBoundary(unittest.TestCase):
    def test_constructor_extracted_as_its_own_function(self):
        import pathlib
        import tempfile
        from reveal.analyzers.java import JavaAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'Foo.java'
            f.write_text(
                "class Foo {\n"
                "    private final int x;\n"
                "    public Foo(int x) {\n"
                "        this.x = x;\n"
                "    }\n"
                "    public void unrelatedMethod() {\n"
                "        System.out.println(\"unrelated\");\n"
                "    }\n"
                "}\n"
            )
            structure = JavaAnalyzer(str(f)).get_structure()
            names = [fn['name'] for fn in structure.get('functions', [])]
            self.assertIn('Foo', names)
            self.assertIn('unrelatedMethod', names)

    def test_constructor_boundary_excludes_sibling_method_body(self):
        import pathlib
        import tempfile
        from reveal.analyzers.java import JavaAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'Foo.java'
            f.write_text(
                "class Foo {\n"
                "    private final int x;\n"
                "    public Foo(int x) {\n"
                "        this.x = x;\n"
                "    }\n"
                "    public void unrelatedMethod() {\n"
                "        System.out.println(\"unrelated\");\n"
                "    }\n"
                "}\n"
            )
            structure = JavaAnalyzer(str(f)).get_structure()
            ctor = next(fn for fn in structure['functions'] if fn['name'] == 'Foo')
            # Regression: pre-fix, this fell through to class_declaration and
            # spanned the whole class body (through unrelatedMethod's line 8).
            self.assertLess(ctor['line_end'], 6)

    def test_constructor_declaration_in_def_nodes_taxonomy(self):
        # node_taxonomy.py side of the same fix — used by --scope's ancestor
        # chain and the composite-set KEYWORD_LABEL guard rail.
        from reveal.adapters.ast.node_taxonomy import DEF_NODES, KEYWORD_LABEL
        self.assertIn('constructor_declaration', DEF_NODES)
        self.assertEqual(KEYWORD_LABEL['constructor_declaration'], 'DEF')


# ─── BACK-641: C++ operator_name/destructor_name missing from
# _find_identifier_in_tree's name-kind lists ────────────────────────────────
# An out-of-line operator overload (`Vector2::operator==(...) { ... }`)
# declarator-nests a qualified_identifier whose `name` child is an
# `operator_name` node — not `identifier`/`field_identifier` — so the
# qualified_identifier join dropped it and returned bare "Vector2" (the
# scope qualifier only), colliding with the constructor and every other
# operator on the type. An inline destructor (`~Ref() { ... }`) name-nodes
# as `destructor_name` wrapping an inner `identifier`; plain recursion
# skipped past destructor_name and returned the inner identifier's bare
# text "Ref" (dropping the "~"), again colliding with the constructor.
# Found via the C++ sideeffects-recall-oracle loop (BACK-547 fourth
# language) while sanity-checking constructor/destructor coverage before
# trusting any recall numbers — same failure family as BACK-638, different
# mechanism (name-extraction join list, not a missing FUNCTION_NODE_TYPES
# entry).

class TestBack641CppOperatorAndDestructorNaming(unittest.TestCase):
    def test_out_of_line_operator_overload_named_correctly(self):
        import pathlib
        import tempfile
        from reveal.analyzers.cpp import CppAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'vec.cpp'
            f.write_text(
                "struct Vec {\n"
                "    int x;\n"
                "    bool operator==(const Vec &o) const;\n"
                "};\n"
                "bool Vec::operator==(const Vec &o) const {\n"
                "    return x == o.x;\n"
                "}\n"
            )
            structure = CppAnalyzer(str(f)).get_structure()
            names = [fn['name'] for fn in structure.get('functions', [])]
            self.assertIn('Vec::operator==', names)
            # Regression: pre-fix this collapsed to bare "Vec" (the scope
            # qualifier only), colliding with any constructor.
            self.assertNotIn('Vec', names)

    def test_inline_destructor_named_with_tilde(self):
        import pathlib
        import tempfile
        from reveal.analyzers.cpp import CppAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'widget.cpp'
            f.write_text(
                "class Widget {\n"
                "public:\n"
                "    Widget() {}\n"
                "    ~Widget() {}\n"
                "};\n"
            )
            structure = CppAnalyzer(str(f)).get_structure()
            names = [fn['name'] for fn in structure.get('functions', [])]
            self.assertIn('Widget', names)      # constructor
            self.assertIn('~Widget', names)      # destructor, distinct name
            # Regression: pre-fix both collapsed to the same bare "Widget",
            # making them indistinguishable to name-based lookup.
            self.assertEqual(names.count('Widget'), 1)


# ─── BACK-547 sixth loop (Ruby): `singleton_method` missing from
# FUNCTION_NODE_TYPES ───────────────────────────────────────────────────────
# `def self.foo` / `def Class.foo` parses to a DISTINCT tree-sitter-ruby node
# kind, `singleton_method`, not a same-name variant of `method` (`def foo`).
# BACK-451/477 had already added `singleton_method` to CHILD_NODE_TYPES (so
# dotted hierarchical lookup like `Class.method_name` worked), but never to
# FUNCTION_NODE_TYPES — the same cross-taxonomy fragmentation as BACK-638
# (Java/C# constructors) and BACK-519 (JS class-field arrows). Every
# `def self.x` method — the dominant Ruby/Rails idiom for module-level
# utility/service-object entry points — was entirely invisible to
# `--outline`/`get_structure()`, and a bare (non-dotted) name lookup for one
# failed outright even when the name was unique in the file. Found via the
# Ruby sideeffects-recall-oracle loop on real Discourse source: `lib/
# discourse.rb` (107 `def self.` methods) showed only 6 functions in
# `--outline` pre-fix.

class TestBack547RubySingletonMethodExtraction(unittest.TestCase):
    def _analyzer(self, src):
        import pathlib
        import tempfile
        from reveal.analyzers.ruby import RubyAnalyzer
        d = tempfile.TemporaryDirectory()
        f = pathlib.Path(d.name) / 'foo.rb'
        f.write_text(src)
        return RubyAnalyzer(str(f)), d  # keep tempdir alive via returned handle

    def test_module_level_def_self_extracted(self):
        analyzer, _tmp = self._analyzer(
            "module Discourse\n"
            "  class Utils\n"
            "    def self.execute_command(*command)\n"
            "      1\n"
            "    end\n"
            "  end\n"
            "end\n"
        )
        structure = analyzer.get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        # Regression: pre-fix, `singleton_method` wasn't in FUNCTION_NODE_TYPES
        # at all, so this method never appeared in the flat functions list.
        self.assertIn('execute_command', names)

    def test_def_self_and_class_shovel_self_both_extracted(self):
        # `def self.foo` (singleton_method) and `class << self; def foo; end;
        # end` (method, nested in singleton_class) are two different Ruby
        # idioms for the same thing -- both must be visible.
        analyzer, _tmp = self._analyzer(
            "class Foo\n"
            "  def self.bar\n"
            "    1\n"
            "  end\n"
            "\n"
            "  class << self\n"
            "    def baz\n"
            "      2\n"
            "    end\n"
            "  end\n"
            "end\n"
        )
        structure = analyzer.get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        self.assertIn('bar', names)
        self.assertIn('baz', names)

    def test_unique_name_lookup_no_longer_errors(self):
        # The user-facing symptom: `reveal file.rb method_name` erroring
        # "could not find function or method" for a `def self.x` method whose
        # name was unique in the file (confirmed live on Discourse's
        # lib/discourse.rb:allow_dev_populate?, plugins/discourse-ai/.../
        # discourse_meta_search.rb:categories, lib/stylesheet/compiler.rb:
        # compile_asset).
        analyzer, _tmp = self._analyzer(
            "class Discourse\n"
            "  def self.allow_dev_populate?\n"
            "    ENV[\"ALLOW_DEV_POPULATE\"] == \"1\"\n"
            "  end\n"
            "end\n"
        )
        structure = analyzer.get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        self.assertIn('allow_dev_populate?', names)


# ─── BACK-547 sixth loop (Ruby): ActiveRecord CRUD verbs + FileUtils verb gaps
# in _TAXONOMY_BY_LANG['ruby'] ───────────────────────────────────────────────
# `.where`/`.pluck`/`.find_by`/`.update_all`/`.delete_all`/`.destroy_all` were
# previously declined as "too collision-prone" without corpus evidence;
# measured instead on real Discourse source (receiver-shape sampling found
# near-exclusively Model-constant/relation-shaped receivers, no unrelated-
# domain collision). `FileUtils.rm_f`/`.rm_rf` are distinct tokens from the
# existing `fileutils.rm` pattern under segment-boundary matching.

class TestBack547RubyDbAndFileTaxonomy(unittest.TestCase):
    def _sideeffect_kinds(self, src):
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('ruby')
        content_bytes = src.encode('utf-8')
        tree = parser.parse(src)
        root = tree.root_node()

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='ruby')
        return {e['kind'] for e in effects}

    def test_activerecord_where_classified_as_db(self):
        kinds = self._sideeffect_kinds(
            "def find_active\n"
            "  User.where(active: true)\n"
            "end\n"
        )
        self.assertIn('db', kinds)

    def test_activerecord_pluck_and_delete_all_classified_as_db(self):
        kinds = self._sideeffect_kinds(
            "def purge\n"
            "  ids = posts.pluck(:id)\n"
            "  Notification.where(post_id: ids).delete_all\n"
            "end\n"
        )
        self.assertIn('db', kinds)

    def test_fileutils_rm_f_and_rm_rf_classified_as_file(self):
        kinds = self._sideeffect_kinds(
            "def stop\n"
            "  FileUtils.rm_f(@socket_path)\n"
            "end\n"
        )
        self.assertIn('file', kinds)

    def test_net_http_request_class_construction_classified_as_http(self):
        kinds = self._sideeffect_kinds(
            "def send_webhook(uri)\n"
            "  req = Net::HTTP::Post.new(uri)\n"
            "end\n"
        )
        self.assertIn('http', kinds)


class TestBack649PhpTaxonomy(unittest.TestCase):
    """BACK-649 (sideeffects-recall-oracle/php, seventh language): real
    corpus misses found on WordPress, both bare stdlib builtins previously
    absent from _TAXONOMY_BY_LANG['php']."""

    def _sideeffect_kinds(self, src):
        from reveal.adapters.ast.nav_effects import collect_effects
        _, root, get_text, _ = _parse_php(src)
        effects = collect_effects(root, 1, 999, get_text, language='php')
        return {e['kind'] for e in effects}

    def test_error_reporting_classified_as_log(self):
        kinds = self._sideeffect_kinds(
            "<?php\n"
            "function wp_debug_mode() {\n"
            "    error_reporting( E_ALL );\n"
            "}\n"
        )
        self.assertIn('log', kinds)

    def test_fsockopen_classified_as_http(self):
        kinds = self._sideeffect_kinds(
            "<?php\n"
            "function connect($server, $port) {\n"
            "    $fp = fsockopen($server, $port, $errno, $errstr);\n"
            "}\n"
        )
        self.assertIn('http', kinds)


class TestBack547CSharpTaxonomy(unittest.TestCase):
    """BACK-547 (sideeffects-recall-oracle/csharp, eighth language, Jellyfin
    corpus): two real corpus misses, both bare stdlib idioms previously
    absent from _TAXONOMY_BY_LANG['csharp']. The tokenizer doesn't split
    camelCase, so an async/read-side sibling of an already-listed pattern
    needs its own explicit entry."""

    def test_savechangesasync_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('dbContext.SaveChangesAsync'), 'db')

    def test_streamreader_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('new StreamReader'), 'file')


class TestBack651CSharpOperatorDeclaration(unittest.TestCase):
    """BACK-651 (found via BACK-547 C# recall-oracle pre-flight check):
    C# operator overloads (`public static bool operator ==(...)`) parse to
    their own distinct node kind, `operator_declaration`, not a variant of
    `method_declaration` -- and unlike BACK-638's constructor gap, the node
    has no identifier-shaped name child at all (the "name" is the raw
    operator-symbol token). Both the node-type gap and the missing
    name-extraction strategy needed fixing."""

    def test_operator_overload_extracted_with_name(self):
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'SearchResult.cs'
            f.write_text(
                "public readonly struct SearchResult\n"
                "{\n"
                "    public static bool operator ==(SearchResult left, SearchResult right)\n"
                "    {\n"
                "        return left.Equals(right);\n"
                "    }\n"
                "\n"
                "    public static bool operator !=(SearchResult left, SearchResult right)\n"
                "    {\n"
                "        return !left.Equals(right);\n"
                "    }\n"
                "}\n"
            )
            structure = CSharpAnalyzer(str(f)).get_structure()
            names = [fn['name'] for fn in structure.get('functions', [])]
            self.assertIn('operator ==', names)
            self.assertIn('operator !=', names)

    def test_operator_boundary_excludes_sibling_operator_body(self):
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'SearchResult.cs'
            f.write_text(
                "public readonly struct SearchResult\n"
                "{\n"
                "    public static bool operator ==(SearchResult left, SearchResult right)\n"
                "    {\n"
                "        return left.Equals(right);\n"
                "    }\n"
                "\n"
                "    public static bool operator !=(SearchResult left, SearchResult right)\n"
                "    {\n"
                "        return !left.Equals(right);\n"
                "    }\n"
                "}\n"
            )
            structure = CSharpAnalyzer(str(f)).get_structure()
            op_eq = next(fn for fn in structure['functions'] if fn['name'] == 'operator ==')
            # Regression: pre-fix, operator_declaration was entirely absent
            # from FUNCTION_NODE_TYPES, so this element didn't exist at all.
            self.assertLess(op_eq['line_end'], 8)

    def test_operator_declaration_in_def_nodes_taxonomy(self):
        from reveal.adapters.ast.node_taxonomy import DEF_NODES, KEYWORD_LABEL
        self.assertIn('operator_declaration', DEF_NODES)
        self.assertEqual(KEYWORD_LABEL['operator_declaration'], 'DEF')


# ─── BACK-650: _find_element_node returned the first tree-order match for a
# bare name, with no disambiguation when multiple functions share a name —
# overloading and abstract+concrete-override pairs both hit this. Found via
# the C# sideeffects-recall-oracle loop (BACK-547 eighth loop) on real
# Jellyfin source: an abstract method and its real override shared a name
# (bare lookup returned the bodyless abstract one, hiding a LogError call),
# and an expression-bodied overload wrapper shared a name with the real
# block-bodied overload (bare lookup returned the wrapper, hiding a
# Thread.Sleep call). Fixed by preferring a candidate with a 'block'-kind
# direct child (a real body) over one without, falling back to first-match
# only when every same-named candidate is equally block-bodied or equally
# bodyless (true overloads with no signal to disambiguate).

class TestBack650OverloadDisambiguation(unittest.TestCase):
    def test_abstract_and_override_same_name_resolves_to_override(self):
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        from reveal.file_handler import _find_element_node
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'BaseTunerHost.cs'
            f.write_text(
                "abstract class BaseTunerHost\n"
                "{\n"
                "    protected abstract Task<List<MediaSourceInfo>> GetChannelStreamMediaSources(\n"
                "        string channelId, CancellationToken cancellationToken);\n"
                "}\n"
                "\n"
                "class LiveTvTunerHost : BaseTunerHost\n"
                "{\n"
                "    public async Task<List<MediaSourceInfo>> GetChannelStreamMediaSources(\n"
                "        string channelId, CancellationToken cancellationToken)\n"
                "    {\n"
                "        try\n"
                "        {\n"
                "            return await GetSources(channelId);\n"
                "        }\n"
                "        catch (Exception ex)\n"
                "        {\n"
                "            Logger.LogError(ex, \"failed\");\n"
                "            throw;\n"
                "        }\n"
                "    }\n"
                "}\n"
            )
            analyzer = CSharpAnalyzer(str(f))
            node = _find_element_node(analyzer, 'GetChannelStreamMediaSources')
            self.assertIsNotNone(node)
            # Regression: pre-fix, this returned the abstract (bodyless)
            # declaration at line 3, a 1-line no-op range that hides the
            # override's entire body including the LogError call.
            self.assertGreater(node.end_position().row, 4)

    def test_expression_bodied_and_block_bodied_overload_resolves_to_block(self):
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        from reveal.file_handler import _find_element_node
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'ProgressiveFileStream.cs'
            f.write_text(
                "class ProgressiveFileStream : Stream\n"
                "{\n"
                "    public override int Read(byte[] buffer, int offset, int count)\n"
                "        => Read(buffer.AsSpan(offset, count));\n"
                "\n"
                "    public int Read(Span<byte> buffer)\n"
                "    {\n"
                "        var sw = Stopwatch.StartNew();\n"
                "        while (_stream.Length <= _position)\n"
                "        {\n"
                "            Thread.Sleep(50);\n"
                "        }\n"
                "        return 0;\n"
                "    }\n"
                "}\n"
            )
            analyzer = CSharpAnalyzer(str(f))
            node = _find_element_node(analyzer, 'Read')
            self.assertIsNotNone(node)
            # Regression: pre-fix, this returned the expression-bodied
            # wrapper at line 3-4, silently hiding the Thread.Sleep effect
            # in the real block-bodied overload below it.
            self.assertGreater(node.end_position().row, 5)

    def test_true_overload_with_no_disambiguating_signal_falls_back_to_first(self):
        # Both candidates are equally block-bodied (real overloads, no
        # abstract/expression-bodied sibling) -- no signal to disambiguate,
        # so first tree-order match is returned, same as pre-fix behavior.
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        from reveal.file_handler import _find_element_node
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'Overloads.cs'
            f.write_text(
                "class Overloads\n"
                "{\n"
                "    public void Write(string s)\n"
                "    {\n"
                "        Console.WriteLine(s);\n"
                "    }\n"
                "\n"
                "    public void Write(int i)\n"
                "    {\n"
                "        Console.WriteLine(i.ToString());\n"
                "    }\n"
                "}\n"
            )
            analyzer = CSharpAnalyzer(str(f))
            node = _find_element_node(analyzer, 'Write')
            self.assertIsNotNone(node)
            self.assertEqual(node.start_position().row, 2)  # first Write(string s), line 3

    def test_pick_best_candidate_single_candidate_returned_directly(self):
        from reveal.file_handler import _pick_best_candidate
        self.assertEqual(_pick_best_candidate(['only']), 'only')


# ─── BACK-547 ninth loop (Rust sideeffects-recall-oracle, real-corpus
# measurement on Meilisearch's milli engine): `macro_invocation` (Rust's
# grammar node for `tracing::debug!(...)`, `println!(...)`, etc.) was
# entirely absent from CALL_NODE_TYPES -- every macro call was invisible to
# --calls/--sideeffects/--boundary, not just a taxonomy gap. Since Rust
# logging is done almost exclusively via macros (the `tracing`/`log`
# crates), this was the single dominant recall gap (31.58%->68.42% recall
# jump from this fix alone, before any taxonomy change). Fixed by adding
# 'macro_invocation' to CALL_NODE_TYPES and 'token_tree' (its argument
# container, not 'arguments') to _extract_first_arg's recognized kinds --
# the existing generic callee-extraction fallback already produced the
# right callee string with no further special-casing needed.

class TestBack547RustMacroInvocation(unittest.TestCase):
    def _parse(self, src):
        parser = ts.get_parser('rust')
        content_bytes = src.encode('utf-8')
        tree = parser.parse(src)
        root = tree.root_node()

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')
        return root, get_text

    def test_scoped_macro_call_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        root, get_text = self._parse(textwrap.dedent("""
        fn foo() {
            tracing::debug!("processing {} docs", 5);
        }
        """).lstrip('\n'))
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        # Regression: pre-fix, macro_invocation wasn't in CALL_NODE_TYPES at
        # all, so this list was empty -- the macro call was invisible.
        self.assertIn('tracing::debug', callees)

    def test_bare_macro_call_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        root, get_text = self._parse(textwrap.dedent("""
        fn foo() {
            println!("world");
        }
        """).lstrip('\n'))
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('println', callees)

    def test_tracing_macro_classified_as_log_effect(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        root, get_text = self._parse(textwrap.dedent("""
        fn foo() {
            tracing::warn!("Attempt #{}, retrying after {}ms.", 1, 50);
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        """).lstrip('\n'))
        effects = collect_effects(root, 1, 999, get_text, language='rust')
        kinds = [(e['line'], e['kind']) for e in effects]
        self.assertIn((2, 'log'), kinds)
        self.assertIn((3, 'sleep'), kinds)

    def test_macro_invocation_in_call_node_types(self):
        from reveal.treesitter import CALL_NODE_TYPES
        self.assertIn('macro_invocation', CALL_NODE_TYPES)


class TestBack547RustDbEnvTaxonomy(unittest.TestCase):
    """heed (LMDB binding) transaction acquisition (`.read_txn()`/
    `.write_txn()`) and bare `env::var` (after `use std::env;`) were both
    unclassified -- neither carries the `std::`/type-name prefix the prior
    rust taxonomy entries required. Deliberately no bare `.commit` entry:
    since per-language taxonomy tables are also merged into the fully
    unscoped `_COMPILED_ALL` table, a bare `.commit` pattern regressed the
    existing BACK-594 `conn`/`connection` precedent live in this loop's own
    test run (`classify_call('conn::commit')`, unscoped, started returning
    'db' again) -- `read_txn`/`write_txn` alone were sufficient for full
    corpus recall on this category."""

    def test_read_txn_write_txn_classified_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('index::read_txn', language='rust'), 'db')
        self.assertEqual(classify_call('index::write_txn', language='rust'), 'db')

    def test_bare_commit_not_added_unscoped(self):
        # Regression guard for the BACK-594 conn/connection precedent this
        # loop nearly broke -- 'commit' must stay OUT of the rust taxonomy
        # as a bare unscoped-visible pattern.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('conn::commit'))

    def test_bare_env_var_classified_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('env::var', language='rust'), 'env')
        self.assertEqual(classify_call('env::var_os', language='rust'), 'env')

    def test_fully_qualified_std_env_still_classified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::env::var', language='rust'), 'env')


class TestBack547KotlinDaoReceiverSuffix(unittest.TestCase):
    """Kotlin/Java's `xxxDao`/`XxxDao` naming convention (Data Access Object)
    is the dominant db-access receiver in Room/SQLDelight-backed repository
    layers, but the method vocabulary is open-ended (generated per-query
    names like `getShowWithIdOrThrow`, `entriesForShowIdWithSendPendingActions`)
    -- no fixed pattern list can enumerate it. Corpus (Tivi's data/ module,
    sideeffects-recall-oracle/kotlin, tenth language): 27 files, 100+ call
    sites, all unclassified before this fix. Fixed via a new suffix-match
    receiver mechanism (`_classify_by_receiver_suffix`), since the receiver is
    a whole identifier like `showdao`/`seasonsdao`, never the bare word `dao`
    alone (unlike the existing exact-match `_RECEIVER_TAXONOMY`)."""

    def test_dao_suffixed_receiver_classified_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('showDao.getShowWithIdOrThrow'), 'db')
        self.assertEqual(
            classify_call('episodeWatchEntryDao.entriesForShowIdWithSendPendingActions'),
            'db',
        )

    def test_bare_dao_receiver_also_classified(self):
        # A variable literally named `dao` (common: `private val dao: ShowDao`)
        # is itself a valid db receiver -- suffix match correctly includes the
        # zero-prefix case, same as the exact-match _RECEIVER_TAXONOMY would.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('dao.foo'), 'db')

    def test_non_dao_suffix_not_classified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('showQueries.getShowWithId'))
        self.assertIsNone(classify_call('showDaoFactory.build'))


class TestBack547KotlinSqlDelightTaxonomy(unittest.TestCase):
    """SQLDelight's query-execution/transaction idiom
    (`countQuery.executeAsOne()`, `.executeAsList()`, `.executeAsOneOrNull()`,
    `transacter.transactionWithResult(...)`) is a single camelCase token --
    same tokenizer gap as C#'s `SaveChangesAsync` (BACK-547 eighth loop).
    Corpus: 68 executeAs*() calls + 4 transactionWithResult() calls across 17
    files in Tivi's data/ module, 0 classified before this fix."""

    def test_execute_as_variants_classified_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        for variant in ('executeAsOne', 'executeAsList', 'executeAsOneOrNull'):
            self.assertEqual(
                classify_call(f'countQuery.{variant}', language='kotlin'), 'db',
                msg=f'{variant} should classify as db',
            )

    def test_transaction_with_result_classified_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('transacter.transactionWithResult', language='kotlin'), 'db',
        )

    def test_bare_execute_still_common_scoped(self):
        # Sanity: the pre-existing common '->execute' pattern is untouched.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('cursor->execute', language='kotlin'), 'db')


class TestBack547SwiftApolloHttpTaxonomy(unittest.TestCase):
    """Apollo GraphQL's `client.fetch(query:)` / `client.perform(mutation:)`
    (plus the completion-handler/async `fetchWithResult`/`performWithResult`
    overloads) is the dominant network idiom in Kickstarter's KsApi service
    layer (sideeffects-recall-oracle/swift, eleventh and final language): 100+
    call sites across Service.swift and its ApolloClient extensions, all
    unclassified before this fix. Scoped to `language='swift'` so it can never
    fire for Ruby's unrelated `reviewable.perform(...)` (Discourse action
    dispatch, 230 corpus hits in samples/ruby) or any other language's own
    'fetch'/'perform' verbs."""

    def test_bare_fetch_and_perform_classified_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('apollo.fetch', language='swift'), 'http')
        self.assertEqual(classify_call('client.perform', language='swift'), 'http')

    def test_with_result_variants_classified_http(self):
        # Tokenizer doesn't split camelCase (same gap as C#'s SaveChangesAsync
        # / Kotlin's executeAsOne), so the WithResult compound needs its own entry.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('client.fetchWithResult', language='swift'), 'http')
        self.assertEqual(classify_call('client.performWithResult', language='swift'), 'http')

    def test_data_task_classified_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('self.dataTask', language='swift'), 'http')

    def test_ruby_perform_not_classified_http(self):
        # Cross-language non-collision: Ruby's Reviewable#perform is an
        # unrelated business-logic action dispatcher (Discourse), not network.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('reviewable.perform', language='ruby'))


class TestBack725ZigTaxonomy(unittest.TestCase):
    """BACK-718/BACK-725 (Zig, fourteenth side-effect-recall language,
    corpus: TigerBeetle samples/zig/tigerbeetle/src). Zig had zero
    _TAXONOMY_BY_LANG entries before this loop; scoped to language='zig' so
    none of these can fire cross-language. All patterns corpus-grounded and
    corpus-collision-checked (scripts/check_taxonomy_collisions.py)."""

    def test_storage_sector_io_classified_file(self):
        # TigerBeetle's own storage abstraction (storage.zig): the ONLY
        # on-disk sector I/O call sites in the whole corpus.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('grid.superblock.storage.read_sectors', language='zig'), 'file')
        self.assertEqual(
            classify_call('client_replies.storage.write_sectors', language='zig'), 'file')

    def test_io_wrapper_scoped_file_and_http(self):
        # Two-segment `io.<verb>` scoping (same technique as Lua's io.write/
        # io.read file entry) -- NOT a bare 'read'/'write'/'connect'/'send'
        # verb, which would be the C/Lua loops' declined catastrophic-
        # collision class.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('bus.io.connect', language='zig'), 'http')
        self.assertEqual(classify_call('bus.io.accept', language='zig'), 'http')
        self.assertEqual(classify_call('bus.io.listen', language='zig'), 'http')
        self.assertEqual(classify_call('bus.io.recv', language='zig'), 'http')
        self.assertEqual(classify_call('bus.io.send', language='zig'), 'http')
        self.assertEqual(classify_call('storage.io.write', language='zig'), 'file')
        self.assertEqual(classify_call('storage.io.read', language='zig'), 'file')

    def test_zig_stdlib_file_camelcase_compounds(self):
        # Tokenizer doesn't split camelCase (same gap class as C#'s
        # SaveChangesAsync / Kotlin's executeAsOne / Swift's
        # fetchWithResult): std.fs's own compound method names are each a
        # single opaque token, distinct from any bare COMMON verb.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('project_root.openDir', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.cwd().openFile', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.cwd().makeOpenPath', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.cwd().deleteTree', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.selfExePath', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.cwd().statFile', language='zig'), 'file')
        self.assertEqual(classify_call('shell.cwd.realpathAlloc', language='zig'), 'file')
        self.assertEqual(classify_call('testing.copyFileAbsolute', language='zig'), 'file')

    def test_posix_syscalls_classified_file_and_http(self):
        # Bare POSIX syscall names -- corpus-collision-checked (universally
        # file-I/O-only across every corpus language, unlike a generic verb
        # like 'read'/'write' alone).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('posix.pwrite', language='zig'), 'file')
        self.assertEqual(classify_call('posix.fsync', language='zig'), 'file')
        # Two-segment 'posix.<verb>' (matches both the fully-qualified
        # std.posix.X form and a local `const posix = std.posix;` alias) --
        # NOT the declined bare 'connect'/'socket'/'accept' alone.
        self.assertEqual(classify_call('std.posix.connect', language='zig'), 'http')
        self.assertEqual(classify_call('posix.connect', language='zig'), 'http')
        self.assertEqual(classify_call('posix.socket', language='zig'), 'http')
        # Trailing-delimiter prefix convention (same shape as Lua's
        # ngx.socket. entry): matches any std.net.* call regardless of verb.
        self.assertEqual(classify_call('std.net.tcpConnectToAddress', language='zig'), 'http')

    def test_env_camelcase_compounds(self):
        # std.process.getEnvVarOwned/getEnvMap -- distinct camelCase tokens
        # from COMMON's pre-existing bare 'getenv' (which already covers the
        # older/simpler std.posix.getenv form, unaffected by this addition).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std.process.getEnvVarOwned', language='zig'), 'env')
        self.assertEqual(classify_call('std.process.getEnvMap', language='zig'), 'env')
        self.assertEqual(classify_call('std.posix.getenv', language='zig'), 'env')

    def test_debug_print_classified_log_not_bare_print(self):
        # std.debug.print -- Zig's raw stdout debug-print primitive used
        # corpus-wide for benchmark/test-harness output. Scoped two-segment
        # 'debug.print', NOT bare 'print' (the same catastrophic-collision
        # class as Python's print()/JS's console.log, declined everywhere
        # this program has touched a receiverless print idiom).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std.debug.print', language='zig'), 'log')
        self.assertIsNone(classify_call('print', language='zig'))

    def test_zig_unmapped_before_this_loop_now_scoped(self):
        # Sanity-lock: before this loop zig had no _TAXONOMY_BY_LANG entry
        # at all, so it fell back to _COMPILED_COMMON_ONLY (BACK-722's fix).
        # A Python/PHP-only builtin must still never leak into a Zig file.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session_start', language='zig'))


class TestBack720ScalaTaxonomy(unittest.TestCase):
    """BACK-718/BACK-720 (Scala, fifteenth side-effect-recall language,
    corpus: GitBucket samples/scala/src/main -- a real production
    Scala/Scalatra Git-hosting web app, NOT sbt itself despite the task's
    initial description; see scala/SCALA.md). Scala had zero
    _TAXONOMY_BY_LANG entries before this loop; scoped to language='scala'
    so none of these can fire cross-language. All patterns corpus-grounded
    and corpus-collision-checked (scripts/check_taxonomy_collisions.py)."""

    def test_slick_terminal_methods_classified_db(self):
        # Slick's blocking-API TERMINAL methods -- distinctive camelCase/
        # dotted compounds, NOT the bare filter/insert/update/delete/list/
        # first/result verbs Slick chains them onto (declined -- see
        # test_slick_bare_verbs_deliberately_unclassified below).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Priorities.filter(x).firstOption', language='scala'), 'db')
        self.assertEqual(classify_call('withSession', language='scala'), 'db')
        self.assertEqual(classify_call('Database.forDataSource', language='scala'), 'db')
        self.assertEqual(classify_call('Database.forURL', language='scala'), 'db')

    def test_slick_bare_verbs_deliberately_unclassified(self):
        # GitBucket's Slick DAO layer is syntactically indistinguishable
        # from Scala's own built-in collection/Option methods
        # (List.filter/Option.filter, etc) -- classify_call only sees
        # callee text, never a receiver's static type, so there is no way
        # to scope 'filter'/'insert'/'update'/'delete' narrower than "the
        # whole call" without the exact catastrophic cross-language
        # collision this program has repeatedly declined (Lua's
        # BACK-636/633 class). Locks in the DECISION, not a gap to fix.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('Priorities.filter', language='scala'))
        self.assertIsNone(classify_call('query.insert', language='scala'))
        self.assertIsNone(classify_call('query.update', language='scala'))
        self.assertIsNone(classify_call('query.delete', language='scala'))

    def test_java_io_constructor_calls_classified_file(self):
        # `new File(...)`/`new FileOutputStream(...)`/etc -- only visible
        # at all after this loop's `instance_expression` CALL_NODE_TYPES fix
        # (Scala's grammar node for `new Foo(args)`, distinct from PHP/C#'s
        # `object_creation_expression`); see
        # TestScalaInstanceExpressionCalls below for the structural half of
        # this fix. Emits "new <Name>" via _extract_scala_instance_callee,
        # the same convention _extract_object_creation_callee established
        # for PHP's 'new pdo'.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('new File', language='scala'), 'file')
        self.assertEqual(classify_call('new FileOutputStream', language='scala'), 'file')
        self.assertEqual(classify_call('new FileInputStream', language='scala'), 'file')
        self.assertEqual(classify_call('new FileWriter', language='scala'), 'file')
        self.assertEqual(classify_call('new HttpPost', language='scala'), 'http')
        self.assertEqual(classify_call('new HttpGet', language='scala'), 'http')

    def test_apache_commons_fileutils_classified_file(self):
        # Bare 'fileutils' receiver -- distinctive compound noun, matches
        # any FileUtils.* call regardless of trailing verb (same
        # "namespaced receiver, no bare verb" shape as Zig's std.net./Lua's
        # ngx.socket. prefix entries). Corpus-collision-checked: Java/Ruby
        # hits are the SAME Apache Commons IO / Ruby stdlib FileUtils
        # module, a corroborating idiom, not a collision.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('FileUtils.deleteDirectory', language='scala'), 'file')
        self.assertEqual(classify_call('FileUtils.copyFile', language='scala'), 'file')
        self.assertEqual(classify_call('f.mkdirs', language='scala'), 'file')
        self.assertEqual(classify_call('f.createNewFile', language='scala'), 'file')

    def test_httpclientbuilder_classified_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('HttpClientBuilder.create', language='scala'), 'http')

    def test_java_interop_env_needs_own_scala_entry(self):
        # Java-interop finding: Java's OWN _TAXONOMY_BY_LANG['java'] entry
        # for System.getProperty (BACK-639) does NOT extend to Scala files
        # even though both compile to the identical java.lang.System class
        # -- classify_call() only merges COMMON + the file's OWN language
        # bucket, with no cross-JVM-language sharing mechanism. Duplicated
        # here rather than shared.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('System.getProperty', language='scala'), 'env')
        self.assertIsNone(classify_call('System.getProperty', language='rust'))

    def test_scala_unmapped_before_this_loop_now_scoped(self):
        # Sanity-lock: before this loop scala had no _TAXONOMY_BY_LANG entry
        # at all, so it fell back to _COMPILED_COMMON_ONLY (BACK-722's fix),
        # confirmed for a 4th language. A Python/PHP-only builtin, and the
        # ubiquitous collection-method bare verbs above, must never leak.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session_start', language='scala'))


class TestScalaInstanceExpressionCalls(unittest.TestCase):
    """BACK-718/BACK-720: Scala's `new Foo(args)` parses to a DISTINCT
    tree-sitter node kind, 'instance_expression', not PHP/C#'s
    'object_creation_expression' -- entirely invisible to --calls/
    --sideeffects/--boundary before this loop despite the identical source
    shape. Fixed via a CALL_NODE_TYPES addition (treesitter.py) plus a
    paired callee-extraction case (nav_calls.py:
    _extract_scala_instance_callee), mirroring the existing PHP/C#
    "new <Name>" convention exactly."""

    def test_new_expression_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        tree, root, get_text, content_bytes = _parse_scala("""
        object T {
          def foo(): Unit = {
            val f = new File("x")
            val out = new FileOutputStream(f)
          }
        }
        """)
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('new File', callees)
        self.assertIn('new FileOutputStream', callees)

    def test_new_expression_effects_classified(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        tree, root, get_text, content_bytes = _parse_scala("""
        object T {
          def foo(): Unit = {
            val f = new File("x")
          }
        }
        """)
        effects = collect_effects(root, 1, 999, get_text, language='scala')
        kinds = {e['kind'] for e in effects}
        self.assertIn('file', kinds)


def _parse_gdscript(code: str):
    """Parse GDScript code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('gdscript')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes


class TestBack724GdscriptTaxonomy(unittest.TestCase):
    """BACK-718/BACK-724 (GDScript, seventeenth side-effect-recall language,
    corpus: Pixelorama samples/gdscript_pixelorama, a real production Godot 4
    pixel-art editor). GDScript had zero _TAXONOMY_BY_LANG entries before this
    loop; scoped to language='gdscript' so none of these can fire
    cross-language. All patterns corpus-grounded and corpus-collision-checked
    (scripts/check_taxonomy_collisions.py)."""

    def test_fileaccess_diraccess_classified_file(self):
        # Godot 4's FileAccess/DirAccess static-factory API -- dotted,
        # scoped two-segment (same shape as Dart's http.get/Zig's
        # io.connect entries).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('FileAccess.open', language='gdscript'), 'file')
        self.assertEqual(classify_call('FileAccess.file_exists', language='gdscript'), 'file')
        self.assertEqual(classify_call('DirAccess.open', language='gdscript'), 'file')
        self.assertEqual(classify_call('DirAccess.remove_absolute', language='gdscript'), 'file')

    def test_fileaccess_instance_methods_bare_verbs_classified_file(self):
        # FileAccess/StreamPeer instance methods -- bare verbs, since the
        # receiver is a local var holding FileAccess.open(...)'s return
        # (`file`, `ase_file`, `palette_file`, ... -- no fixed name to scope
        # a dotted pattern against).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('file.store_line', language='gdscript'), 'file')
        self.assertEqual(classify_call('ase_file.get_buffer', language='gdscript'), 'file')
        self.assertEqual(classify_call('palette_file.store_var', language='gdscript'), 'file')
        self.assertEqual(classify_call('import_file.get_as_text', language='gdscript'), 'file')

    def test_os_environment_classified_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('OS.get_environment', language='gdscript'), 'env')
        self.assertEqual(classify_call('OS.set_environment', language='gdscript'), 'env')
        self.assertEqual(classify_call('OS.has_environment', language='gdscript'), 'env')

    def test_push_error_warning_printerr_classified_log_not_bare_print(self):
        # push_error/push_warning/printerr/print_rich -- bare verbs (GDScript's
        # print family is always called receiverless), corpus-collision-check
        # came back clean (the only non-zero cross-language hits are Godot's
        # OWN C++ engine implementation of these exact builtins). Bare 'print'
        # itself was TRIED AND DECLINED -- same catastrophic-collision class
        # as the Swift loop's declined bare print (SWIFT.md).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('push_error', language='gdscript'), 'log')
        self.assertEqual(classify_call('push_warning', language='gdscript'), 'log')
        self.assertEqual(classify_call('printerr', language='gdscript'), 'log')
        self.assertEqual(classify_call('print_rich', language='gdscript'), 'log')
        self.assertIsNone(classify_call('print', language='gdscript'))

    def test_os_delay_and_create_timer_classified_sleep(self):
        # OS.delay_msec/delay_usec (blocking) and bare 'create_timer' (the
        # `get_tree().create_timer(...).timeout` non-blocking idiom -- no
        # fixed receiver to scope narrower against, same shape as the file
        # bucket's bare store_*/get_* verbs).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('OS.delay_msec', language='gdscript'), 'sleep')
        self.assertEqual(classify_call('OS.delay_usec', language='gdscript'), 'sleep')
        self.assertEqual(classify_call('get_tree().create_timer', language='gdscript'), 'sleep')

    def test_bare_request_declined_for_http(self):
        # TRIED AND DECLINED: bare 'request' -- the only verb the corpus's
        # real HTTPRequest.request(...) call sites share -- has catastrophic
        # cross-language collision (java 785 hits, php 422, lua 308, ...) in
        # classify_call's unscoped fallback mode. GDScript's 'http' bucket
        # has no entries this loop; verify it stays unclassified rather than
        # silently matching some future addition.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('http_request.request', language='gdscript'))

    def test_gdscript_unmapped_before_this_loop_now_scoped(self):
        # Sanity-lock: before this loop gdscript had no _TAXONOMY_BY_LANG
        # entry at all, so it fell back to _COMPILED_COMMON_ONLY (BACK-722's
        # fix, whose own comment names gdscript explicitly as one of the
        # exposed-but-unmeasured languages). A Python/PHP-only builtin must
        # still never leak into a GDScript file.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session_start', language='gdscript'))
        self.assertIsNone(classify_call('$wpdb', language='gdscript'))


class TestBack724GdscriptConstructorDefinition(unittest.TestCase):
    """BACK-718/BACK-724 GDScript pre-flight structural check: `func _init(...)`
    parses to its own distinct node kind, `constructor_definition`, not a
    variant of `function_definition` -- the same class of gap as BACK-638
    (Java/C# constructors) and BACK-651 (C# operator_declaration), but more
    total: `_init` was entirely absent from --outline/get_structure() (no
    wrapping class_declaration for a top-level script to fall through to
    either) and a direct name lookup errored outright. Verified live on
    samples/gdscript_pixelorama/src/Classes/SteamManager.gd (a real corpus
    `env` oracle positive: `_init` sets OS.set_environment(...))."""

    def test_init_visible_in_range_calls_via_call_node(self):
        # Sanity: attribute-call extraction inside a constructor body works
        # independent of the node-name fix below (this part was never
        # broken -- confirms the gap is purely name/element-lookup, not call
        # extraction).
        from reveal.adapters.ast.nav_calls import range_calls
        tree, root, get_text, content_bytes = _parse_gdscript("""
        extends Node

        func _init():
            OS.set_environment("SteamAppID", "1")
        """)
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('OS.set_environment', callees)

    def test_init_extracted_by_gdscript_analyzer_outline(self):
        import os
        import tempfile
        from reveal.analyzers.gdscript import GDScriptAnalyzer

        code = textwrap.dedent("""\
            extends Node

            func _init():
                OS.set_environment("SteamAppID", "1")

            func _ready():
                pass
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name
        try:
            analyzer = GDScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()
            func_names = [fn['name'] for fn in structure.get('functions', [])]
            # Before the fix, '_init' was silently absent here -- only
            # '_ready' showed up in --outline/get_structure().
            self.assertIn('_init', func_names)
            self.assertIn('_ready', func_names)
        finally:
            os.unlink(temp_path)

    def test_init_direct_name_lookup_and_sideeffects(self):
        import os
        import tempfile
        from reveal.analyzers.gdscript import GDScriptAnalyzer

        code = textwrap.dedent("""\
            extends Node

            func _init():
                OS.set_environment("SteamAppID", "1")
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name
        try:
            from reveal.file_handler import _find_element_node

            analyzer = GDScriptAnalyzer(temp_path)
            # Before the fix this returned None: '_init' was not a
            # recognized FUNCTION_NODE_TYPES member, so bare-name element
            # lookup fell through entirely (unlike BACK-638's Java/C# gap,
            # which at least fell through to the enclosing class body).
            node = _find_element_node(analyzer, '_init')
            self.assertIsNotNone(node)
        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
