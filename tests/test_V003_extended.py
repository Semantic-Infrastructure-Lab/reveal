"""Extended tests for V003: Feature matrix coverage."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reveal.rules.validation.V003 import V003, AnalyzerContext


class TestV003AnalyzerContext(unittest.TestCase):
    """Test AnalyzerContext dataclass."""

    def test_relative_path(self):
        """Test relative_path property calculation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzer_path = root / 'analyzers' / 'python.py'
            analyzer_path.parent.mkdir()
            analyzer_path.write_text("# Analyzer")

            ctx = AnalyzerContext(
                analyzer_name='python',
                analyzer_path=analyzer_path,
                reveal_root=root
            )

            self.assertEqual(ctx.relative_path, 'analyzers/python.py')


class TestV003NoRevealRoot(unittest.TestCase):
    """Test V003 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V003()

    def test_no_reveal_root_returns_empty(self):
        """Test that check returns empty when reveal root not found."""
        with mock.patch.object(self.rule, '_find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV003NoAnalyzersDir(unittest.TestCase):
    """Test V003 when analyzers directory doesn't exist."""

    def setUp(self):
        self.rule = V003()

    def test_no_analyzers_dir_returns_empty(self):
        """Test _get_analyzers_with_types returns empty when dir missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            analyzers = self.rule._get_analyzers_with_types(root)

            self.assertEqual(analyzers, {})


class TestV003MissingStructure(unittest.TestCase):
    """Test V003 detection of missing get_structure()."""

    def setUp(self):
        self.rule = V003()

    def test_missing_get_structure_detected(self):
        """Test detection when analyzer missing get_structure()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create analyzer without get_structure
            analyzer = analyzers_dir / 'custom.py'
            analyzer.write_text("""
class CustomAnalyzer:
    def analyze(self, content):
        return []
""")

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should detect missing get_structure
                missing = [d for d in detections if 'get_structure' in d.message]
                self.assertGreaterEqual(len(missing), 1)

    def test_with_get_structure_not_detected(self):
        """Test no detection when analyzer has get_structure()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create analyzer with get_structure
            analyzer = analyzers_dir / 'python.py'
            analyzer.write_text("""
class PythonAnalyzer:
    def get_structure(self, content):
        return {}
""")

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should not detect missing get_structure
                missing = [d for d in detections if 'python' in d.file_path and 'get_structure' in d.message]
                self.assertEqual(len(missing), 0)


class TestV003MissingOutline(unittest.TestCase):
    """Test V003 detection of missing outline support."""

    def setUp(self):
        self.rule = V003()

    def test_missing_outline_detected_for_structured(self):
        """Test detection when structured analyzer missing outline support."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create markdown analyzer without outline support
            analyzer = analyzers_dir / 'markdown.py'
            analyzer.write_text("""
class MarkdownAnalyzer:
    def get_structure(self, content):
        return {}

    def parse_headings(self, content):
        return []
""")

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should detect missing outline
                missing = [d for d in detections if 'outline' in d.message.lower()]
                self.assertGreaterEqual(len(missing), 1)

    def test_with_outline_not_detected(self):
        """Test no detection when analyzer has outline support."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create python analyzer with hierarchy support
            analyzer = analyzers_dir / 'python.py'
            analyzer.write_text("""
class PythonAnalyzer:
    def get_structure(self, content):
        return self.build_hierarchy(content)

    def build_hierarchy(self, content):
        # Build outline tree
        return {}
""")

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should not detect missing outline
                missing = [d for d in detections if 'python' in d.file_path and 'outline' in d.message.lower()]
                self.assertEqual(len(missing), 0)

    def test_non_structured_not_checked(self):
        """Test that non-structured analyzers aren't checked for outline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzers_dir = root / 'analyzers'
            analyzers_dir.mkdir()

            # Create custom analyzer (not in STRUCTURED_FORMATS)
            analyzer = analyzers_dir / 'custom.py'
            analyzer.write_text("""
class CustomAnalyzer:
    def get_structure(self, content):
        return {}
""")

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should not check outline for non-structured
                missing = [d for d in detections if 'custom' in d.file_path and 'outline' in d.message.lower()]
                self.assertEqual(len(missing), 0)


class TestV003CheckHierarchySupport(unittest.TestCase):
    """Test V003 _check_hierarchy_support method."""

    def setUp(self):
        self.rule = V003()

    def test_hierarchy_keyword(self):
        """Test detection of 'hierarchy' keyword."""
        content = "def build_hierarchy(self): pass"
        self.assertTrue(self.rule._check_hierarchy_support(content))

    def test_outline_keyword(self):
        """Test detection of 'outline' keyword."""
        content = "def render_outline(self): pass"
        self.assertTrue(self.rule._check_hierarchy_support(content))

    def test_tree_keyword(self):
        """Test detection of 'tree' keyword."""
        content = "tree = build_tree()"
        self.assertTrue(self.rule._check_hierarchy_support(content))

    def test_nested_keyword(self):
        """Test detection of 'nested' keyword."""
        content = "nested_items = []"
        self.assertTrue(self.rule._check_hierarchy_support(content))

    def test_parent_keyword(self):
        """Test detection of 'parent' keyword."""
        content = "parent_node = None"
        self.assertTrue(self.rule._check_hierarchy_support(content))

    def test_children_keyword(self):
        """Test detection of 'children' keyword."""
        content = "children = []"
        self.assertTrue(self.rule._check_hierarchy_support(content))

    def test_no_hierarchy_support(self):
        """Test when no hierarchy keywords found."""
        content = "def parse(self): pass"
        self.assertFalse(self.rule._check_hierarchy_support(content))


class TestV003FindClassLine(unittest.TestCase):
    """Test V003 _find_class_line method."""

    def setUp(self):
        self.rule = V003()

    def test_find_class(self):
        """Test finding class definition line."""
        content = """
# Comment
import os

class MyAnalyzer:
    pass
"""
        self.assertEqual(self.rule._find_class_line(content), 5)

    def test_no_class_returns_one(self):
        """Test returns 1 when no class found."""
        content = "def function(): pass"
        self.assertEqual(self.rule._find_class_line(content), 1)


class TestV003FindRevealRoot(unittest.TestCase):
    """Test V003 _find_reveal_root method."""

    def setUp(self):
        self.rule = V003()

    def test_find_reveal_root_from_rule_location(self):
        """Test _find_reveal_root finds root from rule file location."""
        # This uses the actual reveal installation
        root = self.rule._find_reveal_root()

        self.assertIsNotNone(root)
        self.assertTrue((root / 'analyzers').exists())
        self.assertTrue((root / 'rules').exists())

    def test_find_reveal_root_alternative_search(self):
        """Test _find_reveal_root searches parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create nested structure: tmpdir/reveal/analyzers
            reveal_dir = root / 'reveal'
            reveal_dir.mkdir()
            (reveal_dir / 'analyzers').mkdir()
            (reveal_dir / 'rules').mkdir()

            # Mock __file__ to point to nested location
            with mock.patch('reveal.rules.validation.V003.__file__', str(reveal_dir / 'rules' / 'validation' / 'V003.py')):
                rule = V003()
                found_root = rule._find_reveal_root()

                self.assertIsNotNone(found_root)
                self.assertEqual(found_root.name, 'reveal')

    def test_find_reveal_root_not_found(self):
        """Test _find_reveal_root returns None when not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Mock __file__ to point to temp location with no reveal
            fake_file = root / 'fake' / 'location' / 'file.py'
            fake_file.parent.mkdir(parents=True)

            with mock.patch('reveal.rules.validation.V003.__file__', str(fake_file)):
                rule = V003()
                found_root = rule._find_reveal_root()

                self.assertIsNone(found_root)


class TestV003CreateDetections(unittest.TestCase):
    """Test V003 detection creation methods."""

    def setUp(self):
        self.rule = V003()

    def test_create_missing_structure_detection(self):
        """Test _create_missing_structure_detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzer_path = root / 'analyzers' / 'test.py'
            analyzer_path.parent.mkdir()
            analyzer_path.write_text("# Test")

            ctx = AnalyzerContext(
                analyzer_name='test',
                analyzer_path=analyzer_path,
                reveal_root=root
            )

            detection = self.rule._create_missing_structure_detection(ctx)

            self.assertIsNotNone(detection)
            self.assertIn('test', detection.message)
            self.assertIn('get_structure', detection.message)

    def test_create_missing_outline_detection(self):
        """Test _create_missing_outline_detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzer_path = root / 'analyzers' / 'markdown.py'
            analyzer_path.parent.mkdir()
            analyzer_path.write_text("# Markdown")

            ctx = AnalyzerContext(
                analyzer_name='markdown',
                analyzer_path=analyzer_path,
                reveal_root=root
            )

            detection = self.rule._create_missing_outline_detection(ctx, 10)

            self.assertIsNotNone(detection)
            self.assertIn('markdown', detection.message)
            self.assertIn('outline', detection.message.lower())
            self.assertEqual(detection.line, 10)


if __name__ == '__main__':
    unittest.main()
