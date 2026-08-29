"""Tests for CLI introspection commands."""

import unittest
import tempfile
from pathlib import Path

import pytest

from reveal.cli.introspection import (
    explain_file,
    show_ast,
    get_language_info_detailed,
    _format_ast_node,
)
from reveal.core.treesitter_compat import tree_root

# BACK-1149: component-layer test -- calls a reveal.cli.* handler function directly, not through reveal.main
pytestmark = pytest.mark.component


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

    def test_explain_cached_grammar_is_unqualified_success(self):
        """BACK-979: a downloaded grammar keeps the plain success claim."""
        import tree_sitter_language_pack as tslp
        from unittest.mock import patch

        with patch.object(tslp, "downloaded_languages", return_value=["python"]):
            result = explain_file(str(self.py_file))

        self.assertIn("✅ Full language-specific analysis", result)
        self.assertNotIn("not yet downloaded", result)

    def test_explain_uncached_grammar_warns_of_network_fetch(self):
        """BACK-979: --explain-file must not claim full support for a
        grammar that hasn't been downloaded yet — that claim was actively
        wrong on air-gapped hosts (see BACK-979 case study)."""
        import tree_sitter_language_pack as tslp
        from unittest.mock import patch

        with patch.object(tslp, "downloaded_languages", return_value=[]):
            result = explain_file(str(self.py_file))

        self.assertIn("grammar not yet downloaded", result)
        self.assertIn("network fetch", result)

    def test_explain_degraded_conformance_language_shows_caveat(self):
        """BACK-1107: --explain-file claimed 'Full language-specific
        analysis' unconditionally, even for a language whose conformance
        tier and known limitations (capabilities.py, already surfaced by
        --language-info) show it's degraded. A smoke-tested-tier language
        (Scala) must show its real conformance level, not read as full."""
        import tree_sitter_language_pack as tslp
        from unittest.mock import patch

        scala_file = Path(self.temp_dir) / "test.scala"
        scala_file.write_text("object Hello { def main(args: Array[String]): Unit = {} }\n")

        with patch.object(tslp, "downloaded_languages", return_value=["scala"]):
            result = explain_file(str(scala_file))

        self.assertIn("Conformance level: smoke-tested", result)
        self.assertIn("Known limitations:", result)

    def test_explain_tier1_language_with_known_limitations_shows_them(self):
        """A tier1-verified language can still have documented known
        limitations (e.g. Go) -- those must not be hidden just because the
        conformance tier itself is the best one."""
        import tree_sitter_language_pack as tslp
        from unittest.mock import patch

        go_file = Path(self.temp_dir) / "test.go"
        go_file.write_text("package main\nfunc main() {}\n")

        with patch.object(tslp, "downloaded_languages", return_value=["go"]):
            result = explain_file(str(go_file))

        self.assertIn("✅ Full language-specific analysis", result)
        self.assertIn("Known limitations:", result)

    def test_explain_tier1_language_no_limitations_has_no_caveat(self):
        """BACK-1107 must not introduce a caveat for a language that
        genuinely has none (Python: tier1-verified, no known limitations) --
        this is the existing unqualified-success behavior from BACK-979."""
        import tree_sitter_language_pack as tslp
        from unittest.mock import patch

        with patch.object(tslp, "downloaded_languages", return_value=["python"]):
            result = explain_file(str(self.py_file))

        self.assertNotIn("Conformance level:", result)
        self.assertNotIn("Known limitations:", result)


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

    def test_show_ast_clean_file_has_no_recovery_banner(self):
        """A cleanly-parsed file must not print the BACK-1129 warning banner."""
        result = show_ast(str(self.py_file))
        self.assertNotIn("parse recovered with error/missing node", result)

    def test_show_ast_missing_token_shows_banner_and_marker(self):
        """BACK-1129: an unclosed construct (`def foo(:`) recovers with a
        MISSING token spliced into an otherwise well-typed subtree and no
        ERROR node anywhere in the tree -- the exact shape that used to be
        completely invisible (a MISSING ')' rendered identically to a real
        empty token)."""
        broken = Path(self.temp_dir) / "broken.py"
        broken.write_text("def foo(:\n    pass\n")

        result = show_ast(str(broken))

        self.assertIn("parse recovered with error/missing node(s)", result)
        self.assertIn("MISSING", result)

    def test_show_ast_error_node_shows_banner_and_marker(self):
        """A genuine ERROR node (parser lost its place) must also get the
        summary banner and an inline marker, not just its literal 'ERROR'
        kind text easy to miss deep in a large tree."""
        broken = Path(self.temp_dir) / "broken.py"
        broken.write_text("def foo(: * / @ #\n")

        result = show_ast(str(broken))

        self.assertIn("parse recovered with error/missing node(s)", result)
        self.assertIn("ERROR", result)


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

        node = tree_root(self.analyzer.tree)
        result = _format_ast_node(node, depth=0)

        self.assertIsInstance(result, str)
        self.assertIn("module", result)

    def test_format_ast_node_with_depth(self):
        """Test formatting AST node at specific depth."""
        if not self.has_tree:
            self.skipTest("No tree-sitter parser available")

        node = tree_root(self.analyzer.tree)
        result = _format_ast_node(node, depth=2, prefix="  ")

        self.assertIsInstance(result, str)
        # Should have indentation
        self.assertTrue(result.startswith("  "))

    def test_format_ast_node_with_max_depth(self):
        """Test formatting AST node with max_depth limit."""
        if not self.has_tree:
            self.skipTest("No tree-sitter parser available")

        node = tree_root(self.analyzer.tree)
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

    def test_get_info_advertises_explain_file_not_stale_explain(self):
        """BACK-452: file-analysis help must say --explain-file, the live flag —

        bare --explain is rule documentation (a different, unrelated flag).
        """
        result = get_language_info_detailed("python")

        self.assertIn("--explain-file", result)

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
