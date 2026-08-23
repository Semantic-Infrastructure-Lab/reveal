"""Nav feature tests: boundary coverage (--boundary surface).

Split from test_ast_nav_probe_features.py (BACK-1151) -- covers
collect_boundary/render_boundary.
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
        self._start = _zero_arg(func, 'start_position').row + 1
        self._end = _zero_arg(func, 'end_position').row + 1

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

