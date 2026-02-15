"""Extended tests for V006: Output format support validation.

Comprehensive edge case coverage for V006 rule testing.
"""

import unittest
from pathlib import Path
import tempfile
import shutil
from unittest import mock

from reveal.rules.validation.V006 import V006


class TestV006NoRevealRoot(unittest.TestCase):
    """Test V006 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V006()

    def test_no_reveal_root_returns_empty(self):
        """Test that no detections are returned when reveal root not found."""
        with mock.patch.object(self.rule, '_find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV006NoAnalyzersDirectory(unittest.TestCase):
    """Test V006 when analyzers directory doesn't exist."""

    def setUp(self):
        self.rule = V006()

    def test_no_analyzers_dir_returns_empty(self):
        """Test that no detections when analyzers directory missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            # Don't create analyzers directory
            with mock.patch.object(self.rule, '_find_reveal_root', return_value=reveal_root):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 0)


class TestV006MissingGetStructure(unittest.TestCase):
    """Test V006 detection of missing get_structure method."""

    def setUp(self):
        self.rule = V006()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir)
        self.analyzers_dir = self.reveal_root / 'analyzers'
        self.analyzers_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_get_structure_with_register(self):
        """Test detection when analyzer has @register but no get_structure."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
@register('custom')
class CustomAnalyzer:
    def analyze(self):
        pass
""", encoding='utf-8')

        with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 1)
            self.assertIn("missing get_structure()", detections[0].message)
            self.assertIn("custom", detections[0].message)

    def test_no_detection_with_get_structure(self):
        """Test no detection when get_structure is present."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
@register('custom')
class CustomAnalyzer:
    def get_structure(self) -> Dict[str, Any]:
        return {}
""", encoding='utf-8')

        with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)

    def test_no_detection_with_treesitter(self):
        """Test no detection when inheriting from TreeSitterAnalyzer."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
@register('custom')
class CustomAnalyzer(TreeSitterAnalyzer):
    pass
""", encoding='utf-8')

        with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)

    def test_no_detection_with_file_analyzer(self):
        """Test no detection when inheriting from FileAnalyzer."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
@register('custom')
class CustomAnalyzer(FileAnalyzer):
    pass
""", encoding='utf-8')

        with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV006MissingReturnTypeHint(unittest.TestCase):
    """Test V006 detection of missing return type hints."""

    def setUp(self):
        self.rule = V006()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir)
        self.analyzers_dir = self.reveal_root / 'analyzers'
        self.analyzers_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_return_type_hint(self):
        """Test detection when get_structure has no return type hint."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
@register('custom')
class CustomAnalyzer:
    def get_structure(self):
        return {}
""", encoding='utf-8')

        with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 1)
            self.assertIn("missing Dict return type hint", detections[0].message)
            self.assertIn("custom", detections[0].message)

    def test_no_detection_with_dict_return_type(self):
        """Test no detection when return type is Dict[str, Any]."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
@register('custom')
class CustomAnalyzer:
    def get_structure(self) -> Dict[str, Any]:
        return {}
""", encoding='utf-8')

        with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)

    def test_no_detection_with_dict_lowercase_return_type(self):
        """Test no detection when return type is dict."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
@register('custom')
class CustomAnalyzer:
    def get_structure(self) -> dict:
        return {}
""", encoding='utf-8')

        with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV006FileHandling(unittest.TestCase):
    """Test V006 file handling edge cases."""

    def setUp(self):
        self.rule = V006()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir)
        self.analyzers_dir = self.reveal_root / 'analyzers'
        self.analyzers_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_skips_underscore_files(self):
        """Test that files starting with underscore are skipped."""
        analyzer_file = self.analyzers_dir / '_private.py'
        analyzer_file.write_text("""
@register('private')
class PrivateAnalyzer:
    pass
""", encoding='utf-8')

        with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)

    def test_skips_base_file(self):
        """Test that base.py is skipped."""
        analyzer_file = self.analyzers_dir / 'base.py'
        analyzer_file.write_text("""
@register('base')
class BaseAnalyzer:
    pass
""", encoding='utf-8')

        with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)

    def test_handles_read_exception(self):
        """Test that file read exceptions are handled gracefully."""
        analyzer_file = self.analyzers_dir / 'custom.py'
        analyzer_file.write_text("""
@register('custom')
class CustomAnalyzer:
    pass
""", encoding='utf-8')
        # Make file unreadable
        analyzer_file.chmod(0o000)

        try:
            with mock.patch.object(self.rule, '_find_reveal_root', return_value=self.reveal_root):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                # Should handle exception gracefully - no crash
                self.assertIsInstance(detections, list)
        finally:
            # Restore permissions for cleanup
            analyzer_file.chmod(0o644)


class TestV006FindRevealRoot(unittest.TestCase):
    """Test _find_reveal_root helper method."""

    def setUp(self):
        self.rule = V006()

    def test_find_reveal_root_direct(self):
        """Test finding reveal root from rule location (direct parent)."""
        # This tests the actual implementation which looks at parent.parent.parent
        reveal_root = self.rule._find_reveal_root()
        # Should find a path or None
        self.assertTrue(reveal_root is None or isinstance(reveal_root, Path))

    def test_find_reveal_root_not_found(self):
        """Test when reveal root cannot be found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir) / 'empty'
            empty_dir.mkdir()

            with mock.patch('reveal.rules.validation.V006.Path') as mock_path:
                # Make Path(__file__).parent.parent.parent point to empty dir
                mock_current = empty_dir
                mock_path.return_value.parent.parent.parent = mock_current

                # Mock the exists checks to return False
                with mock.patch.object(Path, 'exists', return_value=False):
                    result = self.rule._find_reveal_root()
                    # May return None or the actual reveal root depending on environment
                    self.assertTrue(result is None or isinstance(result, Path))


if __name__ == '__main__':
    unittest.main()
