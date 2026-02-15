"""Extended tests for V021: Detect inappropriate regex usage when tree-sitter is available."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reveal.rules.validation.V021 import V021


class TestV021NoRevealRoot(unittest.TestCase):
    """Test V021 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V021()

    def test_no_reveal_root_returns_empty(self):
        """Test that check returns empty when reveal root not found."""
        with mock.patch('reveal.rules.validation.V021.find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV021NoAnalyzersDir(unittest.TestCase):
    """Test V021 when analyzers directory doesn't exist."""

    def setUp(self):
        self.rule = V021()

    def test_no_analyzers_dir_returns_empty(self):
        """Test that check returns empty when analyzers dir missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            with mock.patch('reveal.rules.validation.V021.find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 0)


class TestV021FileReadingErrors(unittest.TestCase):
    """Test V021 handles file reading errors."""

    def setUp(self):
        self.rule = V021()

    def test_file_read_exception_continues(self):
        """Test that file read exceptions are handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create analyzer file
            analyzer = analyzers_dir / 'test.py'
            analyzer.write_text("import re")

            # Make file unreadable
            analyzer.chmod(0o000)

            try:
                with mock.patch('reveal.rules.validation.V021.find_reveal_root', return_value=root):
                    detections = self.rule.check(
                        file_path="reveal://",
                        structure=None,
                        content=""
                    )

                    # Should handle error and return empty
                    self.assertIsInstance(detections, list)
            finally:
                # Restore permissions for cleanup
                analyzer.chmod(0o644)


class TestV021ImportsReModule(unittest.TestCase):
    """Test V021 _imports_re_module method."""

    def setUp(self):
        self.rule = V021()

    def test_import_re(self):
        """Test detection of 'import re'."""
        content = "import re\nimport os"
        self.assertTrue(self.rule._imports_re_module(content))

    def test_from_re_import(self):
        """Test detection of 'from re import'."""
        content = "from re import compile, match"
        self.assertTrue(self.rule._imports_re_module(content))

    def test_no_import(self):
        """Test no re import."""
        content = "import os\nimport sys"
        self.assertFalse(self.rule._imports_re_module(content))

    def test_syntax_error_fallback(self):
        """Test fallback to string search on syntax error."""
        content = "import re\ndef func(\n  # incomplete"
        # Should use fallback string search due to syntax error
        self.assertTrue(self.rule._imports_re_module(content))

    def test_syntax_error_fallback_no_match(self):
        """Test fallback returns false when no import found."""
        content = "def func(\n  # incomplete"
        self.assertFalse(self.rule._imports_re_module(content))


class TestV021UsesTreesitterAnalyzer(unittest.TestCase):
    """Test V021 _uses_treesitter_analyzer method."""

    def setUp(self):
        self.rule = V021()

    def test_uses_treesitter(self):
        """Test detection of TreeSitterAnalyzer usage."""
        content = """
from ..treesitter import TreeSitterAnalyzer

class MyAnalyzer(TreeSitterAnalyzer):
    language = 'python'
"""
        self.assertTrue(self.rule._uses_treesitter_analyzer(content))

    def test_not_uses_treesitter(self):
        """Test when TreeSitterAnalyzer not used."""
        content = """
from ..base import FileAnalyzer

class MyAnalyzer(FileAnalyzer):
    pass
"""
        self.assertFalse(self.rule._uses_treesitter_analyzer(content))


class TestV021RegexDetection(unittest.TestCase):
    """Test V021 detection of regex usage in analyzers."""

    def setUp(self):
        self.rule = V021()

    def test_regex_analyzer_detected(self):
        """Test detection of regex-based analyzer when tree-sitter available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create regex-based Python analyzer (tree-sitter available for Python)
            python_analyzer = analyzers_dir / 'python.py'
            python_analyzer.write_text("""
import re

class PythonAnalyzer:
    pattern = re.compile(r'def (\\w+)\\(')

    def analyze(self, content):
        return pattern.findall(content)
""")

            with mock.patch('reveal.rules.validation.V021.find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should detect regex usage
                self.assertGreater(len(detections), 0)
                self.assertTrue(any('regex' in d.message.lower() for d in detections))

    def test_treesitter_analyzer_not_detected(self):
        """Test that analyzers using TreeSitterAnalyzer are not flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create tree-sitter based Python analyzer
            python_analyzer = analyzers_dir / 'python.py'
            python_analyzer.write_text("""
import re
from ..treesitter import TreeSitterAnalyzer

class PythonAnalyzer(TreeSitterAnalyzer):
    language = 'python'

    # Regex for supplemental text patterns (allowed)
    VERSION_PATTERN = re.compile(r'\\d+\\.\\d+\\.\\d+')
""")

            with mock.patch('reveal.rules.validation.V021.find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should not detect - TreeSitterAnalyzer is primary
                python_detections = [d for d in detections if 'python' in str(d.file_path).lower()]
                self.assertEqual(len(python_detections), 0)

    def test_no_treesitter_language_not_detected(self):
        """Test that analyzers for languages without tree-sitter are not flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create analyzer for language without tree-sitter
            custom_analyzer = analyzers_dir / 'customlang.py'
            custom_analyzer.write_text("""
import re

class CustomAnalyzer:
    pattern = re.compile(r'something')
""")

            with mock.patch('reveal.rules.validation.V021.find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should not detect - no tree-sitter for customlang
                self.assertEqual(len(detections), 0)

    def test_whitelisted_file_not_detected(self):
        """Test that whitelisted files are not flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create whitelisted markdown analyzer
            markdown_analyzer = analyzers_dir / 'markdown.py'
            markdown_analyzer.write_text("""
import re

class MarkdownAnalyzer:
    link_pattern = re.compile(r'\\[([^\\]]+)\\]\\(([^)]+)\\)')
""")

            with mock.patch('reveal.rules.validation.V021.find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should not detect - markdown.py is whitelisted
                self.assertEqual(len(detections), 0)


class TestV021CreateViolation(unittest.TestCase):
    """Test V021 _create_violation method."""

    def setUp(self):
        self.rule = V021()

    def test_create_violation(self):
        """Test violation creation with effort estimation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            analyzer_file = Path(tmpdir) / 'test.py'
            analyzer_file.write_text("""
import re

pattern1 = re.compile(r'test')
pattern2 = re.compile(r'foo')
result1 = re.match(r'bar', text)
result2 = re.search(r'baz', text)
items = re.findall(r'item', text)
# 5 regex operations total
""")

            detection = self.rule._create_violation(
                analyzer_file,
                'python',
                analyzer_file.read_text()
            )

            self.assertIsNotNone(detection)
            self.assertIn('python', detection.message)
            self.assertIn('5', detection.message)  # regex count
            self.assertIn('medium', detection.message.lower())  # effort estimate
            self.assertIn('TreeSitterAnalyzer', detection.suggestion)


if __name__ == '__main__':
    unittest.main()
