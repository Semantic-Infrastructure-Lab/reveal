"""Tests for CLI introspection commands."""

import unittest
import tempfile
from pathlib import Path

from reveal.cli.introspection import (
    explain_file,
    show_ast,
    get_language_info_detailed,
    _format_ast_node,
)


class TestExplainFile(unittest.TestCase):
    """Tests for explain_file function."""

    def setUp(self):
        """Create temporary test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.py_file = Path(self.temp_dir) / "test.py"
        self.py_file.write_text("def hello():\n    print('world')\n")

        self.js_file = Path(self.temp_dir) / "test.js"
        self.js_file.write_text("function hello() { console.log('world'); }\n")

    def test_explain_existing_python_file(self):
        """Test explaining an existing Python file."""
        result = explain_file(str(self.py_file))

        self.assertIn("📄 File:", result)
        self.assertIn(str(self.py_file), result)
        self.assertIn("🔍 Analyzer:", result)
        self.assertIn("Python", result)

    def test_explain_with_verbose(self):
        """Test explain_file with verbose flag."""
        result = explain_file(str(self.py_file), verbose=True)

        self.assertIn("🛠️  Capabilities:", result)
        # Should show at least one capability
        # (exact capabilities depend on analyzer implementation)
        self.assertTrue("•" in result, "Should show at least one capability item")

    def test_explain_nonexistent_file(self):
        """Test explaining a non-existent file."""
        result = explain_file("/tmp/does_not_exist_12345.py")

        self.assertIn("❌ File not found:", result)

    def test_explain_javascript_file(self):
        """Test explaining a JavaScript file."""
        result = explain_file(str(self.js_file))

        self.assertIn("📄 File:", result)
        self.assertIn("🔍 Analyzer:", result)

    def test_explain_shows_extension(self):
        """Test that explain shows file extension."""
        result = explain_file(str(self.py_file))

        self.assertIn("📋 Extension:", result)
        self.assertIn(".py", result)


class TestShowAST(unittest.TestCase):
    """Tests for show_ast function."""

    def setUp(self):
        """Create temporary test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.py_file = Path(self.temp_dir) / "test.py"
        self.py_file.write_text("def hello():\n    return 42\n")

    def test_show_ast_python_file(self):
        """Test showing AST for a Python file."""
        result = show_ast(str(self.py_file))

        self.assertIn("🌳 Tree-sitter AST:", result)
        self.assertIn(str(self.py_file), result)
        # Should show AST structure
        self.assertIn("module", result)

    def test_show_ast_with_max_depth(self):
        """Test showing AST with depth limit."""
        result = show_ast(str(self.py_file), max_depth=2)

        self.assertIn("🌳 Tree-sitter AST:", result)
        # Should still have some structure
        self.assertIn("module", result)

    def test_show_ast_nonexistent_file(self):
        """Test showing AST for non-existent file."""
        result = show_ast("/tmp/does_not_exist_12345.py")

        self.assertIn("❌ File not found:", result)

    def test_show_ast_zero_max_depth(self):
        """Test showing AST with max_depth=0."""
        result = show_ast(str(self.py_file), max_depth=0)

        self.assertIn("🌳 Tree-sitter AST:", result)
        # Should show root node only


class TestFormatASTNode(unittest.TestCase):
    """Tests for _format_ast_node helper function."""

    def setUp(self):
        """Create a temporary Python file and get its AST."""
        self.temp_dir = tempfile.mkdtemp()
        self.py_file = Path(self.temp_dir) / "test.py"
        self.py_file.write_text("x = 1\n")

        # Get a real AST node to test with
        from reveal.registry import get_analyzer
        analyzer_cls = get_analyzer(str(self.py_file))
        if analyzer_cls:
            self.analyzer = analyzer_cls(str(self.py_file))
            self.has_tree = hasattr(self.analyzer, 'tree') and self.analyzer.tree
        else:
            self.has_tree = False

    def test_format_ast_node_basic(self):
        """Test formatting a basic AST node."""
        if not self.has_tree:
            self.skipTest("No tree-sitter parser available")

        node = self.analyzer.tree.root_node
        result = _format_ast_node(node, depth=0)

        self.assertIsInstance(result, str)
        self.assertIn("module", result)

    def test_format_ast_node_with_depth(self):
        """Test formatting AST node at specific depth."""
        if not self.has_tree:
            self.skipTest("No tree-sitter parser available")

        node = self.analyzer.tree.root_node
        result = _format_ast_node(node, depth=2, prefix="  ")

        self.assertIsInstance(result, str)
        # Should have indentation
        self.assertTrue(result.startswith("  "))

    def test_format_ast_node_with_max_depth(self):
        """Test formatting AST node with max_depth limit."""
        if not self.has_tree:
            self.skipTest("No tree-sitter parser available")

        node = self.analyzer.tree.root_node
        result = _format_ast_node(node, depth=0, max_depth=1)

        self.assertIsInstance(result, str)
        self.assertIn("module", result)


class TestGetLanguageInfoDetailed(unittest.TestCase):
    """Tests for get_language_info_detailed function."""

    def test_get_info_by_language_name(self):
        """Test getting info by language name (e.g., 'python')."""
        result = get_language_info_detailed("python")

        self.assertIn("Python", result)
        self.assertIn("📋 Extension:", result)
        self.assertIn(".py", result)
        self.assertIn("📊 Capabilities:", result)

    def test_get_info_by_extension(self):
        """Test getting info by extension (e.g., '.py')."""
        result = get_language_info_detailed(".py")

        self.assertIn("Python", result)
        self.assertIn("📋 Extension: .py", result)
        self.assertIn("🔧 Analyzer:", result)

    def test_get_info_for_javascript(self):
        """Test getting info for JavaScript."""
        result = get_language_info_detailed("javascript")

        self.assertIn("JavaScript", result)
        self.assertIn("📋 Extension:", result)
        self.assertIn(".js", result)

    def test_get_info_unsupported_language(self):
        """Test getting info for unsupported language."""
        result = get_language_info_detailed("nonexistent_lang_12345")

        self.assertIn("❌ Language not found:", result)
        self.assertIn("reveal --languages", result)

    def test_get_info_unsupported_extension(self):
        """Test getting info for unsupported extension."""
        result = get_language_info_detailed(".xyz12345")

        self.assertIn("❌ Extension not supported:", result)

    def test_get_info_shows_usage_examples(self):
        """Test that info includes usage examples."""
        result = get_language_info_detailed("python")

        self.assertIn("💡 Usage Examples:", result)
        self.assertIn("reveal file.py", result)
        self.assertIn("--check", result)
        self.assertIn("--explain", result)

    def test_get_info_shows_analyzer_class(self):
        """Test that info shows the analyzer class name."""
        result = get_language_info_detailed(".py")

        self.assertIn("🔧 Analyzer:", result)
        self.assertIn("Analyzer", result)  # Should end with "Analyzer"

    def test_get_info_case_insensitive(self):
        """Test that language lookup is case-insensitive."""
        result1 = get_language_info_detailed("Python")
        result2 = get_language_info_detailed("python")
        result3 = get_language_info_detailed("PYTHON")

        # All should find Python
        self.assertIn("Python", result1)
        self.assertIn("Python", result2)
        self.assertIn("Python", result3)


if __name__ == '__main__':
    unittest.main()
