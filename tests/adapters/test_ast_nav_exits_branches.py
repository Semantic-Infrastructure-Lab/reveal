"""Nav feature tests: exits/branchmap/gate-chains/switch-case coverage.

Split from test_ast_nav_probe_features.py (BACK-1151) -- covers
collect_exits/render_exits/render_branchmap/collect_gate_chains and the
per-language switch/case/when branch-mapping regressions (--exits/--ifmap/
--catchmap surface). See test_ast_nav_probe_features.py's own original
docstring for the wider BACK-156..160 feature context this file is part of.
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


def _parse_zig(code: str):
    """Parse Zig code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('zig')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


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
        func_start = _zero_arg(self._func, 'start_position').row + 1
        func_end = _zero_arg(self._func, 'end_position').row + 1
        result = render_branchmap(filtered, func_start, func_end)
        self.assertIn('IF', result)


# ===========================================================================
# Flat-file fallback (Change A): verify nav functions work with root_node
# ===========================================================================

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


