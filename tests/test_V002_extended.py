"""Extended tests for V002: Analyzer registration validation.

Comprehensive edge case coverage for V002 rule testing.
"""

import sys
import unittest
from pathlib import Path
import tempfile
import shutil
from unittest import mock
import pytest

from reveal.rules.validation.V002 import V002


class TestV002NoRevealRoot(unittest.TestCase):
    """Test V002 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V002()

    def test_no_reveal_root_returns_empty(self):
        """Test that no detections when reveal root not found."""
        with mock.patch('reveal.rules.validation.V002.find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV002NoAnalyzersDirectory(unittest.TestCase):
    """Test V002 when analyzers directory doesn't exist."""

    def setUp(self):
        self.rule = V002()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_no_analyzers_dir_returns_empty(self):
        """Test no detection when analyzers directory missing."""
        with mock.patch('reveal.rules.validation.V002.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV002AnalyzerRegistration(unittest.TestCase):
    """Test V002 analyzer registration detection."""

    def setUp(self):
        self.rule = V002()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir)
        self.analyzers_dir = self.reveal_root / 'analyzers'
        self.analyzers_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_analyzer_with_register_decorator_no_detection(self):
        """Test no detection when analyzer has @register decorator."""
        analyzer_file = self.analyzers_dir / 'python.py'
        analyzer_file.write_text("""
from ..base import register

@register('.py', name='Python')
class PythonAnalyzer:
    pass
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V002.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)

    def test_analyzer_without_register_creates_detection(self):
        """Test detection when analyzer has class but no @register."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
class CustomAnalyzer:
    def analyze(self):
        pass
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V002.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 1)
            self.assertIn("no @register decorator", detections[0].message)
            self.assertIn("custom", detections[0].message)

    def test_analyzer_no_classes_no_detection(self):
        """Test no detection when file has no classes."""
        analyzer_file = self.analyzers_dir / 'utils.py'
        analyzer_file.write_text("""
def helper_function():
    return None

CONSTANT = 42
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V002.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)

    @pytest.mark.skipif(sys.platform == 'win32', reason="chmod does not restrict access on Windows")
    def test_analyzer_file_read_exception_no_detection(self):
        """Test no detection when file cannot be read."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
class CustomAnalyzer:
    pass
""", encoding='utf-8')
        analyzer_file.chmod(0o000)

        try:
            with mock.patch('reveal.rules.validation.V002.find_reveal_root', return_value=self.reveal_root):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                # Should handle exception gracefully
                self.assertEqual(len(detections), 0)
        finally:
            # Restore permissions for cleanup
            analyzer_file.chmod(0o644)

    def test_skips_underscore_files(self):
        """Test that files starting with underscore are skipped."""
        analyzer_file = self.analyzers_dir / '_private.py'
        analyzer_file.write_text("""
class PrivateAnalyzer:
    pass
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V002.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            # Should skip _private.py
            self.assertEqual(len(detections), 0)


class TestV002HasRegisterDecorator(unittest.TestCase):
    """Test V002 _has_register_decorator helper method."""

    def setUp(self):
        self.rule = V002()

    def test_has_register_with_decorator(self):
        """Test detection of @register decorator."""
        content = """
@register('.py', name='Python')
class PythonAnalyzer:
    pass
"""
        result = self.rule._has_register_decorator(content)
        self.assertTrue(result)

    def test_has_register_with_import(self):
        """Test detection of register import."""
        content = """
from ..base import register

class PythonAnalyzer:
    pass
"""
        result = self.rule._has_register_decorator(content)
        self.assertTrue(result)

    def test_no_register(self):
        """Test when no register decorator or import."""
        content = """
class CustomAnalyzer:
    def analyze(self):
        pass
"""
        result = self.rule._has_register_decorator(content)
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
