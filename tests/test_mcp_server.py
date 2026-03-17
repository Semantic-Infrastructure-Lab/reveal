"""Tests for reveal MCP server tools.

Tests verify that each tool returns plausible output for real inputs.
They do NOT test the MCP protocol itself (that's the SDK's job) — they
test reveal_structure, reveal_element, reveal_query, reveal_pack, and
reveal_check as callable Python functions.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path


class TestRevealStructureTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_structure
        self.reveal_structure = reveal_structure
        self._orig_dir = os.getcwd()
        # Work from the repo root so relative paths resolve
        os.chdir(Path(__file__).parent.parent)

    def tearDown(self):
        os.chdir(self._orig_dir)

    def test_file_returns_function_names(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def greet(name):\n    return f'Hello {name}'\n\ndef farewell():\n    pass\n")
            fpath = f.name
        try:
            result = self.reveal_structure(fpath)
            self.assertIsInstance(result, str)
            self.assertIn('greet', result)
            self.assertIn('farewell', result)
        finally:
            os.unlink(fpath)

    def test_directory_returns_file_listing(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("x = 1\n")
            (Path(d) / 'utils.py').write_text("y = 2\n")
            result = self.reveal_structure(d)
            self.assertIsInstance(result, str)
            self.assertIn('app.py', result)
            self.assertIn('utils.py', result)

    def test_missing_path_returns_error_string(self):
        result = self.reveal_structure('/nonexistent/path/xyz')
        self.assertIsInstance(result, str)
        # Should return an error message, not raise
        self.assertGreater(len(result), 0)

    def test_real_python_file_has_no_crash(self):
        # Use reveal's own codebase
        result = self.reveal_structure('reveal/utils/query.py')
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_returns_string_not_none(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("pass\n")
            fpath = f.name
        try:
            result = self.reveal_structure(fpath)
            self.assertIsNotNone(result)
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)


class TestRevealElementTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_element
        self.reveal_element = reveal_element
        self._orig_dir = os.getcwd()
        os.chdir(Path(__file__).parent.parent)

    def tearDown(self):
        os.chdir(self._orig_dir)

    def test_extracts_function_body(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n")
            fpath = f.name
        try:
            result = self.reveal_element(fpath, 'add')
            self.assertIsInstance(result, str)
            self.assertIn('add', result)
            self.assertIn('return a + b', result)
        finally:
            os.unlink(fpath)

    def test_real_codebase_function(self):
        result = self.reveal_element('reveal/utils/query.py', 'parse_query_params')
        self.assertIsInstance(result, str)
        self.assertIn('parse_query_params', result)

    def test_missing_element_returns_string(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        try:
            result = self.reveal_element(fpath, 'nonexistent_function')
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)


class TestRevealQueryTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_query
        self.reveal_query = reveal_query
        self._orig_dir = os.getcwd()
        os.chdir(Path(__file__).parent.parent)

    def tearDown(self):
        os.chdir(self._orig_dir)

    def test_ast_query_returns_functions(self):
        result = self.reveal_query('ast://reveal/utils/query.py?show=functions')
        self.assertIsInstance(result, str)
        self.assertIn('parse_query_params', result)

    def test_calls_uncalled_query(self):
        result = self.reveal_query('calls://reveal/utils/?uncalled')
        self.assertIsInstance(result, str)
        # Should get some output without crashing
        self.assertGreater(len(result), 0)

    def test_invalid_scheme_returns_error(self):
        result = self.reveal_query('notascheme://something')
        self.assertIsInstance(result, str)
        # Should gracefully return error, not crash

    def test_help_quick_uri(self):
        result = self.reveal_query('help://quick')
        self.assertIsInstance(result, str)
        # help://quick should return the quick help
        self.assertGreater(len(result), 0)

    def test_imports_unused_query(self):
        result = self.reveal_query('imports://reveal/utils/query.py?unused')
        self.assertIsInstance(result, str)


class TestRevealPackTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_pack
        self.reveal_pack = reveal_pack

    def test_pack_returns_selected_files(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'main.py').write_text("def main():\n    pass\n")
            (Path(d) / 'utils.py').write_text("def helper():\n    pass\n")
            result = self.reveal_pack(d, budget=5000)
            self.assertIsInstance(result, str)
            self.assertIn('Pack:', result)
            self.assertIn('Selected', result)

    def test_pack_with_content(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("def run():\n    pass\n")
            result = self.reveal_pack(d, budget=5000, content=True)
            self.assertIsInstance(result, str)
            self.assertIn('CONTENT', result)

    def test_pack_without_content(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'app.py').write_text("x = 1\n")
            result = self.reveal_pack(d, budget=1000, content=False)
            self.assertIsInstance(result, str)
            self.assertNotIn('CONTENT', result)

    def test_pack_missing_path_returns_string(self):
        result = self.reveal_pack('/nonexistent/path/xyz')
        self.assertIsInstance(result, str)


class TestRevealCheckTool(unittest.TestCase):

    def setUp(self):
        from reveal.mcp_server import reveal_check
        self.reveal_check = reveal_check

    def test_clean_file_returns_output(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        try:
            result = self.reveal_check(fpath)
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)

    def test_severity_filter_accepted(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1\n")
            fpath = f.name
        try:
            result = self.reveal_check(fpath, severity='high')
            self.assertIsInstance(result, str)
        finally:
            os.unlink(fpath)

    def test_missing_path_returns_string(self):
        result = self.reveal_check('/nonexistent/path.py')
        self.assertIsInstance(result, str)


class TestMcpServerRegistration(unittest.TestCase):
    """Verify the MCP server registers all expected tools."""

    def test_all_tools_registered(self):
        from reveal.mcp_server import mcp
        tool_names = list(mcp._tool_manager._tools.keys())
        self.assertIn('reveal_structure', tool_names)
        self.assertIn('reveal_element', tool_names)
        self.assertIn('reveal_query', tool_names)
        self.assertIn('reveal_pack', tool_names)
        self.assertIn('reveal_check', tool_names)

    def test_tool_count(self):
        from reveal.mcp_server import mcp
        self.assertEqual(len(mcp._tool_manager._tools), 5)

    def test_server_name(self):
        from reveal.mcp_server import mcp
        self.assertEqual(mcp.name, 'reveal')

    def test_server_has_instructions(self):
        from reveal.mcp_server import mcp
        self.assertIn('progressive disclosure', mcp.instructions.lower())


class TestDefaultArgs(unittest.TestCase):
    """Verify _default_args produces a complete Namespace."""

    def test_has_key_tree_attrs(self):
        from reveal.mcp_server import _default_args
        args = _default_args()
        self.assertEqual(args.max_entries, 200)
        self.assertEqual(args.dir_limit, 50)
        self.assertFalse(args.fast)
        self.assertTrue(args.respect_gitignore)

    def test_overrides_applied(self):
        from reveal.mcp_server import _default_args
        args = _default_args(format='json', verbose=True, budget='8000')
        self.assertEqual(args.format, 'json')
        self.assertTrue(args.verbose)
        self.assertEqual(args.budget, '8000')

    def test_no_missing_exclude_attr(self):
        from reveal.mcp_server import _default_args
        args = _default_args()
        # exclude was the first failure — verify it's present
        self.assertIsNone(args.exclude)


if __name__ == '__main__':
    unittest.main()
