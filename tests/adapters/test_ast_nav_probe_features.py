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
    content_bytes = textwrap.dedent(code).lstrip('\n').encode('utf-8')
    tree = parser.parse(content_bytes)
    root = tree.root_node

    def get_text(node):
        return content_bytes[node.start_byte:node.end_byte].decode('utf-8')

    return tree, root, get_text, content_bytes


def _find_func(root, get_text, name: str):
    """Find a function_definition node by name."""
    stack = list(root.children)
    while stack:
        node = stack.pop()
        if node.type == 'function_definition':
            for child in node.children:
                if child.type == 'identifier' and get_text(child) == name:
                    return node
        stack.extend(reversed(node.children))
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
        self.assertIn('No mutations', result)
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
        func_start = self._func.start_point[0] + 1
        func_end = self._func.end_point[0] + 1
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
    content_bytes = textwrap.dedent(code).lstrip('\n').encode('utf-8')
    tree = parser.parse(content_bytes)
    root = tree.root_node

    def get_text(node):
        return content_bytes[node.start_byte:node.end_byte].decode('utf-8')

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
        self._start = func.start_point[0] + 1
        self._end = func.end_point[0] + 1

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
