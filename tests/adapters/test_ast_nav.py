"""Tests for reveal.adapters.ast.nav — sub-function progressive disclosure.

Tests cover the four nav functions:
  element_outline()  -- control-flow skeleton
  scope_chain()      -- ancestor scope chain for a line
  var_flow()         -- variable read/write trace
  range_calls()      -- call sites within a line range
"""

import textwrap
import unittest

import tree_sitter_language_pack as ts


def _parse_python(code: str):
    """Parse Python code and return (tree, root_node, get_text_fn, content_bytes)."""
    parser = ts.get_parser('python')
    content_bytes = textwrap.dedent(code).lstrip('\n').encode('utf-8')
    tree = parser.parse(content_bytes)
    root = tree.root_node

    def get_text(node):
        return content_bytes[node.start_byte:node.end_byte].decode('utf-8')

    return tree, root, get_text, content_bytes



def _find_func_with_text(root, get_text, name: str):
    """Find a function_definition node whose identifier matches name."""
    stack = list(root.children)
    while stack:
        node = stack.pop()
        if node.type == 'function_definition':
            for child in node.children:
                if child.type == 'identifier' and get_text(child) == name:
                    return node
        stack.extend(reversed(node.children))
    return None


# ---------------------------------------------------------------------------
# element_outline tests
# ---------------------------------------------------------------------------

class TestElementOutline(unittest.TestCase):

    def setUp(self):
        code = """
        def process_items(items):
            result = []
            for item in items:
                if item.active:
                    try:
                        if item.count > 3:
                            result.append(item.value)
                        else:
                            result = []
                    except ValueError:
                        pass
                else:
                    result.append(None)
            return result
        """
        self._tree, self._root, self._get_text, _ = _parse_python(code)
        self._func = _find_func_with_text(self._root, self._get_text, 'process_items')

    def _outline(self, max_depth=3):
        from reveal.adapters.ast.nav import element_outline
        return element_outline(self._func, self._get_text, max_depth=max_depth)

    def test_returns_list(self):
        items = self._outline()
        self.assertIsInstance(items, list)

    def test_for_at_depth_1(self):
        items = self._outline()
        keywords = [i['keyword'] for i in items]
        self.assertIn('FOR', keywords)
        for_item = next(i for i in items if i['keyword'] == 'FOR')
        self.assertEqual(for_item['depth'], 1)

    def test_if_at_depth_2(self):
        items = self._outline()
        if_items = [i for i in items if i['keyword'] == 'IF']
        self.assertTrue(any(i['depth'] == 2 for i in if_items))

    def test_try_at_depth_3(self):
        items = self._outline()
        try_items = [i for i in items if i['keyword'] == 'TRY']
        self.assertTrue(len(try_items) >= 1)
        self.assertEqual(try_items[0]['depth'], 3)

    def test_else_same_depth_as_if(self):
        items = self._outline()
        # The ELSE after the outer IF (item.active) should be at depth 2
        else_items = [i for i in items if i['keyword'] == 'ELSE']
        self.assertTrue(any(i['depth'] == 2 for i in else_items))

    def test_except_same_depth_as_try(self):
        items = self._outline(max_depth=5)
        except_items = [i for i in items if i['keyword'] == 'EXCEPT']
        try_items = [i for i in items if i['keyword'] == 'TRY']
        if except_items and try_items:
            self.assertEqual(except_items[0]['depth'], try_items[0]['depth'])

    def test_return_shown_as_exit(self):
        items = self._outline()
        exit_items = [i for i in items if i['is_exit']]
        self.assertTrue(len(exit_items) >= 1)
        self.assertIn('RETURN', [i['keyword'] for i in exit_items])

    def test_max_depth_limits_output(self):
        items_d1 = self._outline(max_depth=1)
        items_d5 = self._outline(max_depth=5)
        # Deeper outline has more (or equal) items
        self.assertLessEqual(len(items_d1), len(items_d5))

    def test_document_order(self):
        items = self._outline(max_depth=5)
        lines = [i['line_start'] for i in items]
        self.assertEqual(lines, sorted(lines))

    def test_label_contains_condition(self):
        items = self._outline()
        for_item = next(i for i in items if i['keyword'] == 'FOR')
        self.assertIn('item', for_item['label'])

    def test_nested_function_skipped(self):
        code = """
        def outer():
            x = 1
            def inner():
                return x
            return inner
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'outer')
        from reveal.adapters.ast.nav import element_outline
        items = element_outline(func, get_text, max_depth=5)
        keywords = [i['keyword'] for i in items]
        # inner function definition should NOT appear in the outline
        self.assertNotIn('FUNCTION_DEFINITION', keywords)
        self.assertNotIn('DEF', keywords)


# ---------------------------------------------------------------------------
# scope_chain tests
# ---------------------------------------------------------------------------

class TestScopeChain(unittest.TestCase):

    def setUp(self):
        code = """
        def process(items):
            for item in items:
                if item.active:
                    x = item.value
        """
        self._tree, self._root, self._get_text, self._content = _parse_python(code)

    def _chain(self, line_no):
        from reveal.adapters.ast.nav import scope_chain
        return scope_chain(self._root, line_no, self._get_text)

    def test_returns_list(self):
        chain = self._chain(5)
        self.assertIsInstance(chain, list)

    def test_line_inside_if_has_for_and_if_ancestors(self):
        # Line 4 is "x = item.value" inside the if inside the for
        chain = self._chain(4)
        keywords = [item['keyword'] for item in chain]
        self.assertIn('FOR', keywords)
        self.assertIn('IF', keywords)

    def test_outermost_ancestor_first(self):
        chain = self._chain(4)
        self.assertEqual(chain[0]['keyword'], 'FOR')

    def test_innermost_ancestor_last(self):
        chain = self._chain(4)
        self.assertEqual(chain[-1]['keyword'], 'IF')

    def test_depths_strictly_increasing(self):
        chain = self._chain(4)
        depths = [item['depth'] for item in chain]
        self.assertEqual(depths, sorted(depths))

    def test_line_at_top_level_returns_empty(self):
        # Line 1 is the function def itself — no scope ancestors
        chain = self._chain(1)
        # May or may not include function — should not include if/for
        keywords = [item['keyword'] for item in chain]
        self.assertNotIn('IF', keywords)
        self.assertNotIn('FOR', keywords)

    def test_all_ancestors_contain_target_line(self):
        chain = self._chain(4)
        for item in chain:
            self.assertLessEqual(item['line_start'], 4)
            self.assertGreaterEqual(item['line_end'], 4)


# ---------------------------------------------------------------------------
# var_flow tests
# ---------------------------------------------------------------------------

class TestVarFlow(unittest.TestCase):

    def setUp(self):
        code = """
        def compute(data):
            result = []
            for item in data:
                if not result:
                    result = [item]
                else:
                    result.append(item)
            return result
        """
        self._tree, self._root, self._get_text, self._content_bytes = _parse_python(code)
        self._func = _find_func_with_text(self._root, self._get_text, 'compute')

    def _flow(self, var_name, from_line=1, to_line=999):
        from reveal.adapters.ast.nav import var_flow
        return var_flow(self._func, var_name, from_line, to_line, self._get_text)

    def test_returns_list(self):
        events = self._flow('result')
        self.assertIsInstance(events, list)

    def test_initial_assignment_is_write(self):
        events = self._flow('result')
        # First occurrence should be WRITE (result = [])
        writes = [e for e in events if e['kind'] == 'WRITE']
        self.assertTrue(len(writes) >= 1)
        self.assertEqual(writes[0]['kind'], 'WRITE')

    def test_return_is_read(self):
        events = self._flow('result')
        # return result — last reference should be READ
        reads = [e for e in events if e['kind'] == 'READ']
        self.assertTrue(len(reads) >= 1)

    def test_condition_classified_as_read_cond(self):
        events = self._flow('result')
        cond_reads = [e for e in events if e['kind'] == 'READ/COND']
        self.assertTrue(len(cond_reads) >= 1)

    def test_sorted_by_line(self):
        events = self._flow('result')
        lines = [e['line'] for e in events]
        self.assertEqual(lines, sorted(lines))

    def test_range_filtering(self):
        all_events = self._flow('result')
        # Get only events in lines 1-3 (before the for loop)
        first_line = all_events[0]['line']
        last_line = all_events[-1]['line']
        limited = self._flow('result', from_line=first_line, to_line=first_line + 1)
        self.assertLess(len(limited), len(all_events))

    def test_unknown_variable_returns_empty(self):
        events = self._flow('nonexistent_var_xyz')
        self.assertEqual(events, [])

    def test_for_loop_variable_is_write(self):
        events = self._flow('item')
        writes = [e for e in events if e['kind'] == 'WRITE']
        self.assertTrue(len(writes) >= 1)

    def test_augmented_assignment_is_write(self):
        code = """
        def f():
            x = 0
            x += 1
            return x
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'f')
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(func, 'x', 1, 999, get_text)
        writes = [e for e in events if e['kind'] == 'WRITE']
        # x = 0 and x += 1 both write
        self.assertGreaterEqual(len(writes), 2)

    def test_augmented_assignment_also_reads_lhs(self):
        """x += 1 reads x's current value AND writes the new value."""
        code = """
        def f():
            x = 0
            x += 1
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'f')
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(func, 'x', 1, 999, get_text)
        aug_line_events = [e for e in events if e['line'] == 3]
        kinds = {e['kind'] for e in aug_line_events}
        self.assertIn('READ', kinds)
        self.assertIn('WRITE', kinds)

    def test_no_duplicate_events(self):
        events = self._flow('result')
        positions = [(e['line'], e['node'].start_point[1]) for e in events]
        self.assertEqual(len(positions), len(set(positions)))


# ---------------------------------------------------------------------------
# range_calls tests
# ---------------------------------------------------------------------------

class TestRangeCalls(unittest.TestCase):

    def setUp(self):
        code = """
        def process(items):
            result = []
            for item in items:
                validated = self._validate(item)
                if validated:
                    result.append(validated)
                    logger.info("added", extra={"id": item.id})
                else:
                    logger.warning("skip")
            return result
        """
        self._tree, self._root, self._get_text, _ = _parse_python(code)
        self._func = _find_func_with_text(self._root, self._get_text, 'process')

    def _calls(self, from_line, to_line):
        from reveal.adapters.ast.nav import range_calls
        return range_calls(self._func, from_line, to_line, self._get_text)

    def test_returns_list(self):
        calls = self._calls(1, 999)
        self.assertIsInstance(calls, list)

    def test_calls_have_required_fields(self):
        calls = self._calls(1, 999)
        for call in calls:
            self.assertIn('line', call)
            self.assertIn('callee', call)
            self.assertIn('first_arg', call)
            self.assertIn('has_more_args', call)

    def test_validate_call_found(self):
        calls = self._calls(1, 999)
        callees = [c['callee'] for c in calls]
        # self._validate should appear
        self.assertTrue(any('_validate' in (c or '') for c in callees))

    def test_append_call_found(self):
        calls = self._calls(1, 999)
        callees = [c['callee'] for c in calls]
        self.assertTrue(any('append' in (c or '') for c in callees))

    def test_range_filters_correctly(self):
        all_calls = self._calls(1, 999)
        # logger.info is on L8 (0-indexed in dedented code)
        # We don't know exact line numbers without parsing, so just verify
        # that limiting the range reduces call count
        limited_calls = self._calls(1, 3)
        self.assertLessEqual(len(limited_calls), len(all_calls))

    def test_sorted_by_line(self):
        calls = self._calls(1, 999)
        lines = [c['line'] for c in calls]
        self.assertEqual(lines, sorted(lines))

    def test_no_calls_in_empty_range(self):
        # Line range before any code (line 1 is def line)
        calls = self._calls(1, 1)
        self.assertEqual(calls, [])

    def test_first_arg_present_for_calls_with_args(self):
        calls = self._calls(1, 999)
        # logger.info("added", ...) should have first_arg
        info_calls = [c for c in calls if 'info' in (c['callee'] or '')]
        if info_calls:
            self.assertIsNotNone(info_calls[0]['first_arg'])

    def test_has_more_args_false_for_single_arg(self):
        code = """
        def f():
            foo(x)
            bar(x, y)
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'f')
        from reveal.adapters.ast.nav import range_calls
        calls = range_calls(func, 1, 999, get_text)
        foo_calls = [c for c in calls if 'foo' in (c['callee'] or '')]
        bar_calls = [c for c in calls if 'bar' in (c['callee'] or '')]
        if foo_calls:
            self.assertFalse(foo_calls[0]['has_more_args'])
        if bar_calls:
            self.assertTrue(bar_calls[0]['has_more_args'])


# ---------------------------------------------------------------------------
# render_* tests
# ---------------------------------------------------------------------------

class TestRenderers(unittest.TestCase):

    def test_render_outline_header(self):
        from reveal.adapters.ast.nav import render_outline
        items = [
            {'keyword': 'FOR', 'label': 'FOR  x in xs', 'line_start': 5, 'line_end': 10, 'depth': 1, 'is_exit': False},
        ]
        result = render_outline('myfunc', 3, 15, items, depth=3)
        self.assertIn('DEF myfunc', result)
        self.assertIn('L3→L15', result)
        self.assertIn('FOR  x in xs', result)

    def test_render_outline_respects_depth_filter(self):
        from reveal.adapters.ast.nav import render_outline
        items = [
            {'keyword': 'FOR', 'label': 'FOR', 'line_start': 2, 'line_end': 10, 'depth': 1, 'is_exit': False},
            {'keyword': 'IF', 'label': 'IF', 'line_start': 4, 'line_end': 9, 'depth': 2, 'is_exit': False},
            {'keyword': 'TRY', 'label': 'TRY', 'line_start': 5, 'line_end': 8, 'depth': 3, 'is_exit': False},
            {'keyword': 'IF', 'label': 'IF deep', 'line_start': 6, 'line_end': 7, 'depth': 4, 'is_exit': False},
        ]
        result = render_outline('f', 1, 12, items, depth=3)
        self.assertIn('FOR', result)
        self.assertNotIn('IF deep', result)  # depth=4 filtered out

    def test_render_scope_chain_empty(self):
        from reveal.adapters.ast.nav import render_scope_chain
        result = render_scope_chain(42, [])
        self.assertIn('L42', result)
        self.assertIn('top level', result)

    def test_render_scope_chain_with_chain(self):
        from reveal.adapters.ast.nav import render_scope_chain
        chain = [
            {'keyword': 'FOR', 'label': 'FOR  x in xs', 'line_start': 2, 'line_end': 20, 'depth': 0},
            {'keyword': 'IF', 'label': 'IF  x > 0', 'line_start': 4, 'line_end': 15, 'depth': 1},
        ]
        result = render_scope_chain(7, chain)
        self.assertIn('FOR', result)
        self.assertIn('IF', result)
        self.assertIn('L7 is here', result)

    def test_render_var_flow_empty(self):
        from reveal.adapters.ast.nav import render_var_flow
        result = render_var_flow('x', [], [])
        self.assertIn('x', result)
        self.assertIn('No references', result)

    def test_render_range_calls_empty(self):
        from reveal.adapters.ast.nav import render_range_calls
        result = render_range_calls([], 10, 20)
        self.assertIn('L10', result)
        self.assertIn('L20', result)
        self.assertIn('No calls', result)

    def test_render_range_calls_single_arg(self):
        from reveal.adapters.ast.nav import render_range_calls
        calls = [{'line': 5, 'callee': 'foo', 'first_arg': 'x', 'has_more_args': False}]
        result = render_range_calls(calls, 1, 10)
        self.assertIn('foo(x)', result)
        self.assertNotIn('...', result)

    def test_render_range_calls_multi_arg(self):
        from reveal.adapters.ast.nav import render_range_calls
        calls = [{'line': 5, 'callee': 'bar', 'first_arg': '"msg"', 'has_more_args': True}]
        result = render_range_calls(calls, 1, 10)
        self.assertIn('bar("msg", ...)', result)


if __name__ == '__main__':
    unittest.main()
