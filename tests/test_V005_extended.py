"""Extended tests for V005: Static help file synchronization."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reveal.rules.validation.V005 import V005


class TestV005NoRevealRoot(unittest.TestCase):
    """Test V005 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V005()

    def test_no_reveal_root_returns_empty(self):
        """Test that check returns empty when reveal root not found."""
        with mock.patch.object(self.rule, '_find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV005StaticHelpParsing(unittest.TestCase):
    """Test V005 STATIC_HELP parsing logic."""

    def setUp(self):
        self.rule = V005()

    def test_static_help_not_found_creates_detection(self):
        """Test detection when STATIC_HELP dict cannot be parsed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create structure without proper STATIC_HELP
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("# No STATIC_HELP here\n")

            # Create docs dir (empty)
            (root / 'docs').mkdir()

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                self.assertEqual(len(detections), 1)
                self.assertIn("Could not parse STATIC_HELP", detections[0].message)
                self.assertEqual(detections[0].file_path, "reveal/adapters/help.py")

    def test_help_py_missing_returns_empty_dict(self):
        """Test _get_static_help returns empty dict when help.py missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            result = self.rule._get_static_help(root)

            self.assertEqual(result, {})

    def test_static_help_pattern_not_found(self):
        """Test _get_static_help returns empty when pattern not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'

            # Content without STATIC_HELP dict
            help_file.write_text("""
# Some other code
DYNAMIC_HELP = {
    'topic': 'file.md'
}
""")

            result = self.rule._get_static_help(root)

            self.assertEqual(result, {})

    def test_static_help_exception_handling(self):
        """Test _get_static_help handles exceptions gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("STATIC_HELP = {")

            # Should handle invalid syntax gracefully
            result = self.rule._get_static_help(root)

            self.assertEqual(result, {})


class TestV005MissingHelpFiles(unittest.TestCase):
    """Test V005 detection of missing help files."""

    def setUp(self):
        self.rule = V005()

    def test_missing_help_file_detected(self):
        """Test detection when referenced help file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create help.py with STATIC_HELP
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("""
STATIC_HELP = {
    'markdown': 'MARKDOWN_GUIDE.md',
    'python': 'PYTHON_GUIDE.md'
}
""")

            # Create docs dir but NOT the files
            docs_dir = root / 'docs'
            docs_dir.mkdir()

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should detect 2 missing files
                self.assertEqual(len(detections), 2)
                messages = [d.message for d in detections]
                self.assertTrue(any('MARKDOWN_GUIDE.md' in msg for msg in messages))
                self.assertTrue(any('PYTHON_GUIDE.md' in msg for msg in messages))

    def test_existing_help_file_no_detection(self):
        """Test no detection when help file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create help.py with STATIC_HELP
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("""
STATIC_HELP = {
    'test': 'TEST_GUIDE.md'
}
""")

            # Create the referenced file
            docs_dir = root / 'docs'
            docs_dir.mkdir()
            (docs_dir / 'TEST_GUIDE.md').write_text("# Test")

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should not detect missing files
                missing_detections = [d for d in detections if 'does not exist' in d['message']]
                self.assertEqual(len(missing_detections), 0)


class TestV005FindLineInStaticHelp(unittest.TestCase):
    """Test V005 _find_line_in_static_help method."""

    def setUp(self):
        self.rule = V005()

    def test_find_line_help_file_missing(self):
        """Test _find_line_in_static_help returns 1 when help.py missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            line = self.rule._find_line_in_static_help(root, 'markdown')

            self.assertEqual(line, 1)

    def test_find_line_topic_found(self):
        """Test _find_line_in_static_help finds correct line number."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("""# Line 1
STATIC_HELP = {  # Line 2
    'markdown': 'MD.md',  # Line 3
    'python': 'PY.md',  # Line 4
}  # Line 5
""")

            line = self.rule._find_line_in_static_help(root, 'python')

            self.assertEqual(line, 4)

    def test_find_line_topic_not_found(self):
        """Test _find_line_in_static_help returns 1 when topic not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("""
STATIC_HELP = {
    'markdown': 'MD.md'
}
""")

            line = self.rule._find_line_in_static_help(root, 'nonexistent')

            self.assertEqual(line, 1)

    def test_find_line_exception_handling(self):
        """Test _find_line_in_static_help handles exceptions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("content")

            # Mock read_text to raise exception
            with mock.patch.object(Path, 'read_text', side_effect=Exception("Read error")):
                line = self.rule._find_line_in_static_help(root, 'topic')

                self.assertEqual(line, 1)


class TestV005UnregisteredGuides(unittest.TestCase):
    """Test V005 detection of unregistered guide files."""

    def setUp(self):
        self.rule = V005()

    def test_docs_dir_missing_no_detection(self):
        """Test no unregistered guide detection when docs dir missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create help.py but no docs dir
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("""
STATIC_HELP = {
    'test': 'TEST.md'
}
""")

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should only detect missing file, not unregistered guides
                unregistered = [d for d in detections if 'not registered' in d.message]
                self.assertEqual(len(unregistered), 0)

    def test_unregistered_guide_detected(self):
        """Test detection of unregistered guide files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create help.py with valid but non-matching STATIC_HELP
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("""
STATIC_HELP = {
    'other': 'OTHER.md'
}
""")

            # Create docs dir with both registered and unregistered guides
            docs_dir = root / 'docs'
            docs_dir.mkdir()
            (docs_dir / 'OTHER.md').write_text("# Other")  # Registered file
            # Note: As of v0.50.0+, *_GUIDE.md files are auto-discovered,
            # so we use a non-standard name to test unregistered detection
            (docs_dir / 'MY_SPECIAL_HELP.md').write_text("# Help")  # Unregistered (doesn't match auto-discovery patterns)

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should NOT detect *_GUIDE.md files (auto-discovered as of v0.50.0+)
                # Only non-standard help files should be flagged
                # For this test, MY_SPECIAL_HELP.md doesn't match auto-discovery patterns,
                # but V005 only checks *_GUIDE.md and *GUIDE.md patterns, so no detection expected
                unregistered = [d for d in detections if 'not registered' in d.message]
                # With auto-discovery, standard guide patterns aren't flagged
                self.assertEqual(len(unregistered), 0)  # No detections expected

    def test_auto_discovered_guides_not_flagged(self):
        """Test that *_GUIDE.md files are auto-discovered and not flagged (v0.50.0+)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create help.py with minimal STATIC_HELP
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("""
STATIC_HELP = {
    'manual': 'MANUAL.md'
}
""")

            # Create docs dir with auto-discoverable guide files
            docs_dir = root / 'docs'
            docs_dir.mkdir()
            (docs_dir / 'MANUAL.md').write_text("# Manual")  # Manually registered
            (docs_dir / 'AST_ADAPTER_GUIDE.md').write_text("# AST")  # Auto-discovered
            (docs_dir / 'GIT_ADAPTER_GUIDE.md').write_text("# Git")  # Auto-discovered
            (docs_dir / 'QUERY_SYNTAX_GUIDE.md').write_text("# Query")  # Auto-discovered

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # With auto-discovery (v0.50.0+), *_GUIDE.md files should NOT be flagged
                unregistered = [d for d in detections if 'not registered' in d.message]
                self.assertEqual(len(unregistered), 0)  # No guides should be flagged

                # Verify no detections for the specific guide files
                guide_detections = [
                    d for d in detections
                    if any(name in d.message for name in ['AST_ADAPTER_GUIDE.md', 'GIT_ADAPTER_GUIDE.md', 'QUERY_SYNTAX_GUIDE.md'])
                ]
                self.assertEqual(len(guide_detections), 0)

    def test_registered_guide_not_detected(self):
        """Test registered guides are not flagged as unregistered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create help.py with registered guide
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("""
STATIC_HELP = {
    'awesome': 'AWESOME_GUIDE.md'
}
""")

            # Create the guide
            docs_dir = root / 'docs'
            docs_dir.mkdir()
            (docs_dir / 'AWESOME_GUIDE.md').write_text("# Guide")

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should not detect unregistered guides
                unregistered = [d for d in detections if 'not registered' in d.message]
                self.assertEqual(len(unregistered), 0)

    def test_test_files_skipped(self):
        """Test that test files in /test directories are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create help.py with valid STATIC_HELP
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()
            help_file = adapters_dir / 'help.py'
            help_file.write_text("""
STATIC_HELP = {
    'main': 'MAIN_GUIDE.md'
}
""")

            # Create docs with guides
            docs_dir = root / 'docs'
            docs_dir.mkdir()
            (docs_dir / 'MAIN_GUIDE.md').write_text("# Main")  # Registered

            # Create guide in /test subdirectory (should be skipped)
            guides_dir = docs_dir / 'guides'
            guides_dir.mkdir()
            test_dir = guides_dir / 'test'
            test_dir.mkdir()
            (test_dir / 'TEST_GUIDE.md').write_text("# Test")  # Should be skipped

            with mock.patch.object(self.rule, '_find_reveal_root', return_value=root):
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should not detect test guides (only skip files with /test in path)
                unregistered = [d for d in detections if 'not registered' in d.message]
                # The path is 'guides/test/TEST_GUIDE.md' which contains '/test'
                self.assertEqual(len(unregistered), 0)


class TestV005FindRevealRoot(unittest.TestCase):
    """Test V005 _find_reveal_root method."""

    def setUp(self):
        self.rule = V005()

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

            # Create nested directory to search from
            nested = reveal_dir / 'rules' / 'validation'
            nested.mkdir(parents=True)

            # Mock __file__ to point to nested location
            with mock.patch('reveal.rules.validation.V005.__file__', str(nested / 'V005.py')):
                # Create new rule instance to use mocked __file__
                rule = V005()
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

            with mock.patch('reveal.rules.validation.V005.__file__', str(fake_file)):
                rule = V005()
                found_root = rule._find_reveal_root()

                self.assertIsNone(found_root)


if __name__ == '__main__':
    unittest.main()
