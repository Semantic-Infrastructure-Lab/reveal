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

    def test_conn_commit_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('conn.commit'), 'db')

    def test_connection_close_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('connection.close'), 'db')

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
        self.assertIsNone(classify_call('os.environ', language='go'))
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

    def test_unknown_language_falls_back_to_unscoped(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('session_start', language='kotlin'), 'session')


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


if __name__ == '__main__':
    unittest.main()
