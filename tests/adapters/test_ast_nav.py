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
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree, root, get_text, content_bytes



def _find_func_with_text(root, get_text, name: str):
    """Find a function_definition node whose identifier matches name."""
    stack = [root.child(i) for i in range(root.child_count())]
    while stack:
        node = stack.pop()
        if node.kind() == 'function_definition':
            for child in [node.child(i) for i in range(node.child_count())]:
                if child.kind() == 'identifier' and get_text(child) == name:
                    return node
        stack.extend(reversed([node.child(i) for i in range(node.child_count())]))
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

    def test_nested_function_shown_as_def(self):
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
        # inner function definition should appear as DEF, not the raw node type
        self.assertIn('DEF', keywords)
        self.assertNotIn('FUNCTION_DEFINITION', keywords)

    def test_closure_only_function_not_empty(self):
        code = """
        def outer(items):
            def helper(x):
                return x + 1
            def transform(x):
                if x > 0:
                    return helper(x)
                return 0
            return [transform(i) for i in items]
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'outer')
        from reveal.adapters.ast.nav import element_outline
        items = element_outline(func, get_text, max_depth=3)
        keywords = [i['keyword'] for i in items]
        # A function composed entirely of closures should NOT produce an empty outline
        self.assertTrue(len(items) > 0)
        self.assertIn('DEF', keywords)


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
        # With def-inclusion, the enclosing function is the outermost ancestor
        chain = self._chain(4)
        self.assertEqual(chain[0]['keyword'], 'DEF')

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

    def test_scope_includes_enclosing_def(self):
        # Line inside a control-flow block should include the enclosing function
        chain = self._chain(4)
        keywords = [item['keyword'] for item in chain]
        self.assertIn('DEF', keywords)

    def test_scope_closure_chain(self):
        code = """
        def outer():
            def inner():
                if True:
                    x = 1
        """
        _, root, get_text, _ = _parse_python(code)
        from reveal.adapters.ast.nav import scope_chain
        # Line 4 is "x = 1" inside if inside inner() inside outer()
        chain = scope_chain(root, 4, get_text)
        keywords = [item['keyword'] for item in chain]
        # Should see both enclosing defs AND the if block
        self.assertIn('DEF', keywords)
        self.assertIn('IF', keywords)
        # DEF should appear before IF (outer scopes first)
        first_def = next(i for i, k in enumerate(keywords) if k == 'DEF')
        first_if = next(i for i, k in enumerate(keywords) if k == 'IF')
        self.assertLess(first_def, first_if)


# ---------------------------------------------------------------------------
# scope_chain cross-language DEF-recognition tests (BACK-462)
# ---------------------------------------------------------------------------

class TestScopeChainDefRecognitionCrossLanguage(unittest.TestCase):
    """node_taxonomy.DEF_NODES and treesitter.py's FUNCTION_NODE_TYPES had
    independently drifted (BACK-431 Issue A's documented-but-unfixed tail):
    'method' (Ruby), 'function_signature' (Dart), 'Decl' (Zig) were tracked
    for element extraction but absent from DEF_NODES, so scope_chain silently
    dropped the enclosing function from a nested line's ancestor chain in
    those languages — verified against the Python case above, which correctly
    includes DEF. Dart's function_signature/function_body are disjoint
    siblings (documented in treesitter.py's _function_end_node): the plain
    taxonomy fix (BACK-462) couldn't reach it because the body's lines are
    never inside the signature node, so scope_chain synthesizes the DEF from
    the sibling signature (BACK-463) — asserted below.
    """

    def _chain_for(self, language: str, code: str, line_no: int):
        from reveal.adapters.ast.nav import scope_chain
        parser = ts.get_parser(language)
        src = textwrap.dedent(code).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = parser.parse(src)
        root = tree.root_node()

        def get_text(node):
            return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

        return scope_chain(root, line_no, get_text)

    def test_ruby_method_is_in_ancestor_chain(self):
        code = """
        def foo
          x = 1
          if x > 0
            y = 2
          end
        end
        """
        # Line 4 ("y = 2") is inside the if inside the method.
        chain = self._chain_for('ruby', code, 4)
        keywords = [item['keyword'] for item in chain]
        self.assertIn('DEF', keywords)
        self.assertIn('IF', keywords)

    def test_zig_fn_decl_is_in_ancestor_chain(self):
        code = """
        fn foo() void {
            var x: i32 = 1;
            if (x > 0) {
                var y: i32 = 2;
            }
        }
        """
        # Line 4 ("var y: i32 = 2;") is inside the if inside the fn.
        chain = self._chain_for('zig', code, 4)
        keywords = [item['keyword'] for item in chain]
        self.assertIn('DEF', keywords)
        self.assertIn('IF', keywords)

    def test_dart_method_is_in_ancestor_chain(self):
        # BACK-463: function_signature (name) and function_body (the lines) are
        # disjoint siblings, so a line inside the body is never inside the
        # signature — pre-fix the DEF was silently absent from the chain.
        code = """
        class Batch {
          void run(int x) {
            if (x > 0) {
              print("positive");
            }
          }
        }
        """
        # Line 4 ('print("positive");') is inside the if inside the method body.
        chain = self._chain_for('dart', code, 4)
        keywords = [item['keyword'] for item in chain]
        self.assertEqual(['CLASS', 'DEF', 'IF'], keywords)
        # The synthesized DEF spans signature-start → body-end and is labeled
        # from the signature.
        def_item = next(i for i in chain if i['keyword'] == 'DEF')
        self.assertIn('run', def_item['label'])
        self.assertEqual(2, def_item['line_start'])

    def test_dart_top_level_function_is_in_ancestor_chain(self):
        code = """
        void run(int x) {
          if (x > 0) {
            print("positive");
          }
        }
        """
        # Line 3 ('print("positive");') is inside the if inside the function.
        chain = self._chain_for('dart', code, 3)
        keywords = [item['keyword'] for item in chain]
        self.assertEqual(['DEF', 'IF'], keywords)

    def test_dart_signature_line_yields_single_def(self):
        # Guard: querying the signature line itself must not double-count the
        # DEF (the real function_signature node AND the synthesized one).
        code = """
        class Batch {
          void run(int x) {
            if (x > 0) {
              print("positive");
            }
          }
        }
        """
        # Line 2 is the signature 'void run(int x) {'.
        chain = self._chain_for('dart', code, 2)
        keywords = [item['keyword'] for item in chain]
        self.assertEqual(1, keywords.count('DEF'))


# ---------------------------------------------------------------------------
# scope_chain condition field tests (BACK-439a)
# ---------------------------------------------------------------------------

class TestScopeChainCondition(unittest.TestCase):
    """--scope's JSON `condition` field, extracted via nav_exits._get_condition."""

    def test_python_if_condition_present(self):
        code = """
        def process(items):
            for item in items:
                if item.active:
                    x = item.value
        """
        _, root, get_text, _ = _parse_python(code)
        from reveal.adapters.ast.nav import scope_chain
        chain = scope_chain(root, 4, get_text)
        by_keyword = {item['keyword']: item for item in chain}
        self.assertEqual(by_keyword['IF']['condition'], 'item.active')

    def test_python_for_condition_null(self):
        # Python's for_statement has no 'condition' field (left/right instead) —
        # _get_condition() returns None for it, same as collect_gate_chains.
        code = """
        def process(items):
            for item in items:
                if item.active:
                    x = item.value
        """
        _, root, get_text, _ = _parse_python(code)
        from reveal.adapters.ast.nav import scope_chain
        chain = scope_chain(root, 4, get_text)
        by_keyword = {item['keyword']: item for item in chain}
        self.assertIsNone(by_keyword['FOR']['condition'])

    def test_python_def_and_try_condition_null(self):
        code = """
        def process(items):
            try:
                x = items[0]
            except IndexError:
                x = None
        """
        _, root, get_text, _ = _parse_python(code)
        from reveal.adapters.ast.nav import scope_chain
        chain = scope_chain(root, 3, get_text)
        by_keyword = {item['keyword']: item for item in chain}
        self.assertIsNone(by_keyword['DEF']['condition'])
        self.assertIsNone(by_keyword['TRY']['condition'])

    def test_python_while_condition_present(self):
        code = """
        def process(items):
            while items:
                x = items.pop()
        """
        _, root, get_text, _ = _parse_python(code)
        from reveal.adapters.ast.nav import scope_chain
        chain = scope_chain(root, 3, get_text)
        by_keyword = {item['keyword']: item for item in chain}
        self.assertEqual(by_keyword['WHILE']['condition'], 'items')

    def test_php_if_and_loop_condition(self):
        root, get_text = _parse_lang('php', '''
        <?php
        function process($items) {
            foreach ($items as $item) {
                if ($item->active) {
                    $x = $item->value;
                }
            }
        }
        ''')
        from reveal.adapters.ast.nav import scope_chain
        # Line 5 is "$x = $item->value;"
        chain = scope_chain(root, 5, get_text)
        keywords = [item['keyword'] for item in chain]
        self.assertIn('IF', keywords)
        by_keyword = {item['keyword']: item for item in chain}
        self.assertIn('active', by_keyword['IF']['condition'])

    def test_rust_if_condition_and_for_expression_null(self):
        # Expression-oriented language: guards node_taxonomy's documented gap
        # (for_expression/match_expression have no 'condition' field, BACK-430).
        root, get_text = _parse_lang('rust', '''
        fn process(items: &[i32]) -> i32 {
            for item in items {
                if *item > 0 {
                    return *item;
                }
            }
            0
        }
        ''')
        from reveal.adapters.ast.nav import scope_chain
        # Line 4 is "return *item;"
        chain = scope_chain(root, 4, get_text)
        by_keyword = {item['keyword']: item for item in chain}
        self.assertIn('IF', by_keyword)
        self.assertIn('*item > 0', by_keyword['IF']['condition'])
        self.assertIn('FOR', by_keyword)
        self.assertIsNone(by_keyword['FOR']['condition'])


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
        positions = [(e['line'], e['node'].start_position().column) for e in events]
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
# BACK-415: chained/fluent calls must not fold the whole chain into one callee
# ---------------------------------------------------------------------------

def _parse_lang(lang: str, code: str):
    """Parse *code* in *lang* and return (root, get_text_fn)."""
    parser = ts.get_parser(lang)
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = parser.parse(src)

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return tree.root_node(), get_text


def _find_any_func(root, get_text, name: str):
    stack = [root.child(i) for i in range(root.child_count())]
    while stack:
        node = stack.pop()
        if ('function' in node.kind() or 'method' in node.kind()) and name in get_text(node):
            return node
        stack.extend(node.child(i) for i in range(node.child_count()))
    return None


class TestChainedCallCallee(unittest.TestCase):
    """A call on a call result (`f(x).then(...)`) must collapse the outer callee
    to `.then`, not fold the entire (possibly multi-line) chain into one bogus
    name — while the inner call is still captured as its own edge, and plain
    receiver-qualified calls (`obj.method`) keep their receiver for the taxonomy.
    """

    def _callees(self, lang, code, fname):
        from reveal.adapters.ast.nav import range_calls
        root, get_text = _parse_lang(lang, code)
        func = _find_any_func(root, get_text, fname)
        return [c['callee'] for c in range_calls(func, 1, 999, get_text)]

    def test_ts_promise_chain_not_folded(self):
        callees = self._callees('typescript', '''
        export function run(url, moveToPath) {
          rimrafUnlink(moveToPath).catch(() => {});
          fetch(url).then(r => r.json()).catch(handleError);
          obj.method(b);
          plain(a);
        }
        ''', 'run')
        # The chained methods collapse to the bare property, no folded chain.
        self.assertIn('.catch', callees)
        self.assertIn('.then', callees)
        self.assertNotIn('rimrafUnlink(moveToPath).catch', callees)
        self.assertFalse(any('.then(' in (c or '') for c in callees),
                         f"chain folded into a callee: {callees}")
        # Inner calls are still captured as their own edges.
        self.assertIn('rimrafUnlink', callees)
        self.assertIn('fetch', callees)
        # Non-chained member call keeps its receiver (taxonomy needs it).
        self.assertIn('obj.method', callees)
        self.assertIn('plain', callees)

    def test_python_chained_call_collapses_but_receiver_call_kept(self):
        callees = self._callees('python', '''
        def process():
            get_thing().do_stuff()
            File.read(path)
        ''', 'process')
        self.assertIn('.do_stuff', callees)      # chained on a call result
        self.assertIn('get_thing', callees)      # inner call captured
        self.assertIn('File.read', callees)      # plain receiver kept


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

    def test_render_scope_chain_empty_with_line_text(self):
        from reveal.adapters.ast.nav import render_scope_chain
        result = render_scope_chain(42, [], line_text='x = compute()')
        self.assertIn('L42', result)
        self.assertIn('x = compute()', result)
        self.assertNotIn('top level', result)

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

    def test_render_scope_chain_with_line_text(self):
        from reveal.adapters.ast.nav import render_scope_chain
        chain = [
            {'keyword': 'FOR', 'label': 'FOR  x in xs', 'line_start': 2, 'line_end': 20, 'depth': 0},
        ]
        result = render_scope_chain(5, chain, line_text='result.append(x)')
        self.assertIn('▶ L5: result.append(x)', result)
        self.assertNotIn('is here', result)

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


# ---------------------------------------------------------------------------
# BACK-439b: collect_loops (--loopmap) / collect_fanout (--fanout)
# ---------------------------------------------------------------------------

class TestLoopMap(unittest.TestCase):
    """collect_loops(): FOR/WHILE/LOOP/DO nodes within a range, with depth."""

    def test_cpp_range_based_for_loop(self):
        # C++'s range-based for (`for (T x : items)`) is its own node kind,
        # `for_range_loop` — distinct from for_statement and from Java's
        # enhanced_for_statement. Found via the BACK-439b/c conformance-matrix
        # cross-language pass: the existing Tier 1 C++ fixture had no
        # range-based for loop, so --outline/--ifmap/--loopmap were silently
        # blind to it until this fixture addition caught it.
        root, get_text = _parse_lang('cpp', '''
        void f(std::vector<int>& items) {
            for (int item : items) {
                g(item);
            }
        }
        ''')
        from reveal.adapters.ast.nav import collect_loops
        loops = collect_loops(root, 1, 10, get_text, max_depth=6)
        self.assertEqual(len(loops), 1)
        self.assertEqual(loops[0]['keyword'], 'FOR')

    def test_single_loop_with_effects(self):
        code = """
        def process_batch(items):
            for item in items:
                db.execute(item)
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'process_batch')
        from reveal.adapters.ast.nav import collect_loops
        loops = collect_loops(func, 1, 10, get_text)
        self.assertEqual(len(loops), 1)
        self.assertEqual(loops[0]['keyword'], 'FOR')
        self.assertIn('item in items', loops[0]['label'])

    def test_nested_loop_depth_reported(self):
        code = """
        def process_batch(rows):
            for row in rows:
                for cell in row:
                    log.info(cell)
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'process_batch')
        from reveal.adapters.ast.nav import collect_loops
        loops = collect_loops(func, 1, 10, get_text, max_depth=6)
        self.assertEqual(len(loops), 2)
        outer = next(l for l in loops if 'row in rows' in l['label'])
        inner = next(l for l in loops if 'cell in row' in l['label'])
        self.assertLess(outer['depth'], inner['depth'])

    def test_loop_with_no_effects_no_false_positive(self):
        code = """
        def total(items):
            acc = 0
            for item in items:
                acc = acc + item
            return acc
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'total')
        from reveal.adapters.ast.nav import collect_loops, collect_fanout
        loops = collect_loops(func, 1, 10, get_text)
        self.assertEqual(len(loops), 1)
        fanout = collect_fanout(func, 1, 10, get_text)
        self.assertEqual(fanout[0]['effects'], [])

    def test_php_foreach_and_go_for(self):
        root, get_text = _parse_lang('php', '''
        <?php
        function process($items) {
            foreach ($items as $item) {
                $wpdb->query($item);
            }
        }
        ''')
        from reveal.adapters.ast.nav import collect_loops
        loops = collect_loops(root, 1, 10, get_text)
        self.assertEqual(len(loops), 1)
        self.assertEqual(loops[0]['keyword'], 'FOR')

        root, get_text = _parse_lang('go', '''
        func process(items []int) {
            for _, item := range items {
                db.Query(item)
            }
        }
        ''')
        loops = collect_loops(root, 1, 10, get_text)
        self.assertEqual(len(loops), 1)
        self.assertEqual(loops[0]['keyword'], 'FOR')


class TestFanout(unittest.TestCase):
    """collect_fanout(): each loop paired with its classified side effects."""

    def test_loop_with_db_and_http_effects(self):
        code = """
        def process_batch(items):
            for item in items:
                cursor.execute(item)
                requests.get(item)
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'process_batch')
        from reveal.adapters.ast.nav import collect_fanout
        loops = collect_fanout(func, 1, 10, get_text, language='python')
        self.assertEqual(len(loops), 1)
        kinds = {e['kind'] for e in loops[0]['effects']}
        self.assertIn('db', kinds)
        self.assertIn('http', kinds)

    def test_render_fanout_no_loops(self):
        from reveal.adapters.ast.nav import render_fanout
        result = render_fanout([], 1, 10)
        self.assertIn('No loops found', result)

    def test_render_fanout_no_effects(self):
        from reveal.adapters.ast.nav import render_fanout
        loops = [{'keyword': 'FOR', 'label': 'FOR  x in xs', 'line_start': 2,
                  'line_end': 5, 'depth': 1, 'effects': []}]
        result = render_fanout(loops, 1, 10)
        self.assertIn('no classified side effects', result)

    def test_render_fanout_with_effects(self):
        from reveal.adapters.ast.nav import render_fanout
        loops = [{'keyword': 'FOR', 'label': 'FOR  x in xs', 'line_start': 2,
                  'line_end': 5, 'depth': 1,
                  'effects': [{'line': 3, 'kind': 'db', 'callee': 'cursor.execute',
                               'first_arg': 'x', 'has_more_args': False}]}]
        result = render_fanout(loops, 1, 10)
        self.assertIn('db', result)
        self.assertIn('cursor.execute(x)', result)


# ---------------------------------------------------------------------------
# BACK-439c: collect_statewrites (--statewrites)
# ---------------------------------------------------------------------------

class TestStateWrites(unittest.TestCase):
    """collect_statewrites(): field/env/session/call-based shared-state mutations."""

    def test_python_field_write(self):
        code = """
        class A:
            def f(self):
                self.x = 1
                self.y = 2
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'f')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(func, 1, 10, get_text)
        self.assertEqual(len(writes), 2)
        self.assertTrue(all(w['kind'] == 'field' for w in writes))
        self.assertEqual(writes[0]['target'], 'self.x')

    def test_python_module_global_write_not_misclassified_as_field(self):
        # A bare identifier write is not a member-access target — collect_statewrites
        # is silent on it (local/global distinction is out of this slice).
        code = """
        def f():
            x = 1
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'f')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(func, 1, 10, get_text)
        self.assertEqual(writes, [])

    def test_python_env_subscript_write(self):
        code = """
        def f():
            os.environ['X'] = '1'
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'f')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(func, 1, 10, get_text)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]['kind'], 'env')

    def test_no_false_positive_on_read_only_function(self):
        code = """
        def total(items):
            return sum(items)
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'total')
        from reveal.adapters.ast.nav import collect_statewrites
        self.assertEqual(collect_statewrites(func, 1, 10, get_text), [])

    def test_php_session_and_field_write(self):
        root, get_text = _parse_lang('php', '''
        <?php
        function f() {
            $_SESSION['user'] = 1;
            $this->x = 2;
        }
        ''')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(root, 1, 10, get_text)
        kinds = {w['kind'] for w in writes}
        self.assertEqual(kinds, {'session', 'field'})

    def test_go_selector_field_write_through_expression_list(self):
        # Go's assignment_statement always wraps 'left' in an expression_list
        # (to support multi-assign `a, b = 1, 2`), even for a single target —
        # found via the BACK-439b/c conformance-matrix cross-language pass.
        # Without unwrapping it, `b.Total = ...` was silently invisible.
        root, get_text = _parse_lang('go', '''
        package m
        func run(b *Batch, item int) {
            b.Total = b.Total + item
        }
        ''')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(root, 1, 10, get_text)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]['kind'], 'field')
        self.assertEqual(writes[0]['target'], 'b.Total')

    def test_js_this_and_process_env_write(self):
        root, get_text = _parse_lang('javascript', '''
        class A {
            f() {
                this.x = 1;
                process.env.X = "1";
            }
        }
        ''')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(root, 1, 10, get_text)
        kinds = {w['kind'] for w in writes}
        self.assertEqual(kinds, {'field', 'env'})

    def test_java_this_field_write(self):
        # Java's `this.x` is `field_access` — a distinct node kind from every
        # other Tier 1 language's member-access shape (found via the
        # conformance-matrix cross-language pass, BACK-439c).
        root, get_text = _parse_lang('java', '''
        class A {
            int total;
            void f() {
                this.total = this.total + 1;
            }
        }
        ''')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(root, 1, 10, get_text)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]['kind'], 'field')

    def test_call_based_cache_write_merged_in(self):
        code = """
        def f(item):
            self.x = 1
            cache.set(item)
        """
        _, root, get_text, _ = _parse_python(code)
        func = _find_func_with_text(root, get_text, 'f')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(func, 1, 10, get_text, language='python')
        kinds = {w['kind'] for w in writes}
        self.assertIn('field', kinds)
        self.assertIn('cache', kinds)
        # in line order
        self.assertLess(writes[0]['line'], writes[1]['line'])

    def test_kotlin_field_reassignment_write(self):
        # BACK-478 Finding 2: nav_statewrites._walk_assignments read
        # node.child_by_field_name('left') directly, but Kotlin/Swift's
        # `assignment` node has no 'left'/'right' fields at all (positional
        # children only — the exact BACK-476 shape nav_varflow/nav_keys
        # already handle via resolve_assignment_sides). `total = total + 1`
        # and `this.total = 5` were both silently invisible to --statewrites
        # while --varflow/--keys saw them correctly post-BACK-476.
        root, get_text = _parse_lang('kotlin', '''
        class Batch {
            var total: Int = 0
            fun run() {
                total = total + 1
                this.total = 5
            }
        }
        ''')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(root, 1, 10, get_text)
        self.assertEqual(len(writes), 1, f'expected only the this.total field write: {writes}')
        self.assertEqual(writes[0]['kind'], 'field')
        self.assertEqual(writes[0]['target'], 'this.total')

    def test_swift_field_reassignment_write(self):
        root, get_text = _parse_lang('swift', '''
        class Batch {
            var total: Int = 0
            func run() {
                self.total = 5
            }
        }
        ''')
        from reveal.adapters.ast.nav import collect_statewrites
        writes = collect_statewrites(root, 1, 10, get_text)
        self.assertEqual(len(writes), 1, f'expected the self.total field write: {writes}')
        self.assertEqual(writes[0]['kind'], 'field')

    def test_render_statewrites_empty(self):
        from reveal.adapters.ast.nav import render_statewrites
        result = render_statewrites([], 1, 10)
        self.assertIn('No state writes found', result)

    def test_render_statewrites_with_findings(self):
        from reveal.adapters.ast.nav import render_statewrites
        writes = [{'kind': 'field', 'line': 3, 'target': 'self.x'}]
        result = render_statewrites(writes, 1, 10)
        self.assertIn('field', result)
        self.assertIn('self.x', result)


if __name__ == '__main__':
    unittest.main()
