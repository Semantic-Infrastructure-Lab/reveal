"""Comprehensive tests for V022: Package manifest file inclusion validation.

V022 validates that files referenced in CLI handlers and critical paths are
properly included in package manifests (MANIFEST.in).

Prevents deployment bugs where files work in development but are excluded
from PyPI packages (known bug: AGENT_HELP.md path mismatch in CHANGELOG).

Test Structure:
    - TestV022Metadata: Rule metadata validation
    - TestV022CLIHandlerPaths: CLI handler path validation
    - TestV022ManifestPaths: MANIFEST.in path validation
    - TestV022CriticalFiles: Critical file inclusion validation
    - TestV022Integration: End-to-end validation scenarios
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from reveal.rules.validation.V022 import V022


class TestV022Metadata(unittest.TestCase):
    """Test V022 rule metadata."""

    def setUp(self):
        self.rule = V022()

    def test_rule_code(self):
        """Rule code should be V022."""
        self.assertEqual(self.rule.code, "V022")

    def test_rule_severity(self):
        """Rule severity should be HIGH (blocks deployment)."""
        self.assertEqual(self.rule.severity.name, "HIGH")

    def test_rule_message(self):
        """Rule message should mention manifest."""
        self.assertIn("manifest", self.rule.message.lower())

    def test_rule_category(self):
        """Rule should be validation category."""
        from reveal.rules.base import RulePrefix
        self.assertEqual(self.rule.category, RulePrefix.V)

    def test_non_reveal_uri_ignored(self):
        """Non-reveal URIs should be ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)


class TestV022CLIHandlerPaths(unittest.TestCase):
    """Test CLI handler path validation (_check_cli_handler_paths)."""

    def setUp(self):
        self.rule = V022()
        self.temp_dir = tempfile.mkdtemp()
        self.reveal_root = Path(self.temp_dir) / "reveal"
        self.project_root = Path(self.temp_dir)

        # Create reveal directory structure
        self.reveal_root.mkdir(parents=True)
        (self.reveal_root / "cli").mkdir()
        (self.reveal_root / "docs").mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_handler_valid_path(self):
        """Valid CLI handler paths should not trigger detection."""
        # Create valid file
        docs_file = self.reveal_root / "docs" / "AGENT_HELP.md"
        docs_file.write_text("# Help")

        # Create CLI handler referencing valid path
        handlers_file = self.reveal_root / "cli" / "handlers.py"
        handlers_file.write_text("""
            from pathlib import Path
            help_file = Path(__file__).parent.parent / 'docs' / 'AGENT_HELP.md'
        """)

        detections = self.rule._check_cli_handler_paths(self.reveal_root)
        self.assertEqual(len(detections), 0)

    def test_cli_handler_missing_file(self):
        """Missing CLI handler path should trigger detection.

        Note: V022 regex only captures first path segment after parent.parent,
        so this test validates directory existence, not file existence.
        """
        # Create CLI handler referencing non-existent directory
        handlers_file = self.reveal_root / "cli" / "handlers.py"
        handlers_file.write_text("""
            from pathlib import Path
            help_file = Path(__file__).parent.parent / 'missing_docs'
        """)

        detections = self.rule._check_cli_handler_paths(self.reveal_root)
        self.assertEqual(len(detections), 1)
        self.assertIn("missing_docs", detections[0].message)
        self.assertIn("non-existent", detections[0].message.lower())

    def test_cli_handler_missing_directory(self):
        """Missing CLI handler directory should trigger detection."""
        # Create CLI handler referencing non-existent directory
        handlers_file = self.reveal_root / "cli" / "handlers.py"
        handlers_file.write_text("""
            from pathlib import Path
            config_dir = Path(__file__).parent.parent / 'configs'
        """)

        detections = self.rule._check_cli_handler_paths(self.reveal_root)
        self.assertEqual(len(detections), 1)
        self.assertIn("configs", detections[0].message)

    def test_cli_handler_wildcard_path_ignored(self):
        """Wildcard paths should be skipped (can't validate)."""
        handlers_file = self.reveal_root / "cli" / "handlers.py"
        handlers_file.write_text("""
            from pathlib import Path
            files = Path(__file__).parent.parent / 'docs' / '*.md'
        """)

        detections = self.rule._check_cli_handler_paths(self.reveal_root)
        self.assertEqual(len(detections), 0)  # Wildcards skipped

    def test_cli_handler_multiple_paths(self):
        """Multiple CLI handler paths should all be validated."""
        # Create one valid directory, one invalid
        (self.reveal_root / "configs").mkdir()

        handlers_file = self.reveal_root / "cli" / "handlers.py"
        handlers_file.write_text("""
            from pathlib import Path
            valid = Path(__file__).parent.parent / 'configs'
            invalid = Path(__file__).parent.parent / 'missing'
        """)

        detections = self.rule._check_cli_handler_paths(self.reveal_root)
        self.assertEqual(len(detections), 1)
        self.assertIn("missing", detections[0].message)

    def test_cli_handler_no_handlers_file(self):
        """Missing handlers.py should return empty detections."""
        detections = self.rule._check_cli_handler_paths(self.reveal_root)
        self.assertEqual(len(detections), 0)

    def test_cli_handler_detection_metadata(self):
        """Detection should have correct file path and metadata."""
        handlers_file = self.reveal_root / "cli" / "handlers.py"
        handlers_file.write_text("""
            from pathlib import Path
            missing = Path(__file__).parent.parent / 'missing_dir'
        """)

        detections = self.rule._check_cli_handler_paths(self.reveal_root)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].file_path, "reveal/cli/handlers.py")
        self.assertEqual(detections[0].line, 1)
        self.assertIsNotNone(detections[0].suggestion)
        self.assertIn("missing_dir", detections[0].context)


class TestV022ManifestPaths(unittest.TestCase):
    """Test MANIFEST.in path validation (_check_manifest_paths)."""

    def setUp(self):
        self.rule = V022()
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_manifest_valid_path(self):
        """Valid MANIFEST.in paths should not trigger detection."""
        # Create valid file
        readme = self.project_root / "README.md"
        readme.write_text("# README")

        # Create MANIFEST.in with valid path
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("include README.md\n")

        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 0)

    def test_manifest_missing_file(self):
        """MANIFEST.in referencing non-existent file should trigger detection."""
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("include MISSING.md\n")

        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 1)
        self.assertIn("MISSING.md", detections[0].message)
        self.assertIn("non-existent", detections[0].message.lower())
        self.assertEqual(detections[0].file_path, "MANIFEST.in")
        self.assertEqual(detections[0].line, 1)

    def test_manifest_wildcard_path_ignored(self):
        """Wildcard paths should be skipped (can't validate)."""
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("include docs/*.md\n")

        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 0)  # Wildcards skipped

    def test_manifest_comment_ignored(self):
        """Comments in MANIFEST.in should be ignored."""
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("# include MISSING.md\n")

        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 0)

    def test_manifest_empty_lines_ignored(self):
        """Empty lines should be ignored."""
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("\n\n\n")

        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 0)

    def test_manifest_multiple_paths(self):
        """Multiple MANIFEST.in paths should all be validated."""
        # Create one valid file
        (self.project_root / "VALID.md").write_text("# Valid")

        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("""
include VALID.md
include INVALID1.md
include INVALID2.md
""")

        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 2)
        messages = [d.message for d in detections]
        self.assertTrue(any("INVALID1.md" in msg for msg in messages))
        self.assertTrue(any("INVALID2.md" in msg for msg in messages))

    def test_manifest_line_numbers_correct(self):
        """Detection line numbers should match MANIFEST.in."""
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("""# Comment
include VALID1.md

include INVALID.md
""")

        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 2)  # VALID1 and INVALID both missing

        # Find INVALID detection
        invalid_detection = [d for d in detections if "INVALID" in d.message][0]
        self.assertEqual(invalid_detection.line, 4)  # Line 4 in manifest

    def test_manifest_no_manifest_file(self):
        """Missing MANIFEST.in should return empty detections."""
        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 0)

    def test_manifest_recursive_include_ignored(self):
        """recursive-include directives should not be validated."""
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("recursive-include reveal *.md\n")

        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 0)

    def test_manifest_graft_ignored(self):
        """graft directives should not be validated."""
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("graft reveal/docs\n")

        detections = self.rule._check_manifest_paths(self.project_root)
        self.assertEqual(len(detections), 0)


class TestV022CriticalFiles(unittest.TestCase):
    """Test critical file inclusion validation (_check_critical_files)."""

    def setUp(self):
        self.rule = V022()
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.reveal_root = self.project_root / "reveal"
        self.reveal_root.mkdir()
        (self.reveal_root / "docs").mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_critical_file_included_direct(self):
        """Critical file directly included should not trigger detection."""
        # Create critical file
        agent_help = self.reveal_root / "docs" / "AGENT_HELP.md"
        agent_help.write_text("# Agent Help")

        # Include it directly in MANIFEST.in
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("include reveal/docs/AGENT_HELP.md\n")

        detections = self.rule._check_critical_files(self.project_root)
        self.assertEqual(len(detections), 0)

    def test_critical_file_included_recursive(self):
        """Critical file included via recursive-include should not trigger."""
        # Create critical file
        agent_help = self.reveal_root / "docs" / "AGENT_HELP.md"
        agent_help.write_text("# Agent Help")

        # Include via recursive-include
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("recursive-include reveal/docs *.md\n")

        detections = self.rule._check_critical_files(self.project_root)
        self.assertEqual(len(detections), 0)

    def test_critical_file_missing_from_manifest(self):
        """Critical file not in manifest should trigger detection."""
        # Create critical file but don't include in manifest
        agent_help = self.reveal_root / "docs" / "AGENT_HELP.md"
        agent_help.write_text("# Agent Help")

        # Empty manifest
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("")

        detections = self.rule._check_critical_files(self.project_root)
        self.assertEqual(len(detections), 1)
        self.assertIn("AGENT_HELP.md", detections[0].message)
        self.assertIn("not included", detections[0].message.lower())

    def test_critical_file_nonexistent_not_checked(self):
        """Non-existent critical files should not trigger detection."""
        # Don't create critical file
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("")

        detections = self.rule._check_critical_files(self.project_root)
        self.assertEqual(len(detections), 0)  # File doesn't exist, so not checked

    def test_single_critical_file_missing_from_manifest(self):
        """AGENT_HELP.md missing from manifest should be flagged.

        AGENT_HELP_FULL.md was consolidated into AGENT_HELP.md (commit 9292da3)
        so there is now only one critical docs file to validate.
        """
        (self.reveal_root / "docs" / "AGENT_HELP.md").write_text("# Help")

        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("")

        detections = self.rule._check_critical_files(self.project_root)
        self.assertEqual(len(detections), 1)
        self.assertIn("AGENT_HELP.md", detections[0].message)

    def test_critical_file_detection_has_suggestion(self):
        """Detection should include helpful suggestion."""
        agent_help = self.reveal_root / "docs" / "AGENT_HELP.md"
        agent_help.write_text("# Help")

        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("")

        detections = self.rule._check_critical_files(self.project_root)
        self.assertEqual(len(detections), 1)
        self.assertIn("recursive-include", detections[0].suggestion)
        # Path separator agnostic check (Windows uses \\ instead of /)
        self.assertTrue("reveal/docs" in detections[0].suggestion or "reveal\\docs" in detections[0].suggestion)

    def test_no_manifest_file(self):
        """Missing MANIFEST.in should return empty detections."""
        detections = self.rule._check_critical_files(self.project_root)
        self.assertEqual(len(detections), 0)


class TestV022Integration(unittest.TestCase):
    """Integration tests for V022 end-to-end validation."""

    def setUp(self):
        self.rule = V022()
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.reveal_root = self.project_root / "reveal"
        self.reveal_root.mkdir()
        (self.reveal_root / "cli").mkdir()
        (self.reveal_root / "docs").mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_perfect_package_no_detections(self):
        """Perfect package setup should have no detections."""
        # Create critical file (AGENT_HELP_FULL.md was consolidated into AGENT_HELP.md at 9292da3)
        (self.reveal_root / "docs" / "AGENT_HELP.md").write_text("# Help")

        handlers_file = self.reveal_root / "cli" / "handlers.py"
        handlers_file.write_text("""
            from pathlib import Path
            help_file = Path(__file__).parent.parent / 'docs' / 'AGENT_HELP.md'
        """)

        # Perfect manifest
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("recursive-include reveal/docs *.md\n")

        # Mock find_reveal_root to return our temp directory
        import reveal.rules.validation.V022 as v022_module
        original_find = v022_module.find_reveal_root
        v022_module.find_reveal_root = lambda: self.reveal_root

        try:
            detections = self.rule.check(
                file_path="reveal://",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)
        finally:
            v022_module.find_reveal_root = original_find

    def test_multiple_violations_all_detected(self):
        """Multiple violations should all be detected."""
        # Create only one file (missing others)
        (self.reveal_root / "docs" / "AGENT_HELP.md").write_text("# Help")

        # CLI handler references missing directory
        handlers_file = self.reveal_root / "cli" / "handlers.py"
        handlers_file.write_text("""
            from pathlib import Path
            missing = Path(__file__).parent.parent / 'missing_dir'
        """)

        # Manifest references missing file + doesn't include critical files
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("include reveal/NONEXISTENT.txt\n")

        # Mock find_reveal_root
        import reveal.rules.validation.V022 as v022_module
        original_find = v022_module.find_reveal_root
        v022_module.find_reveal_root = lambda: self.reveal_root

        try:
            detections = self.rule.check(
                file_path="reveal://",
                structure=None,
                content=""
            )
            # Should detect:
            # 1. CLI handler missing directory
            # 2. Manifest missing file
            # 3. Critical file not included (AGENT_HELP.md)
            self.assertGreaterEqual(len(detections), 3)

            messages = [d.message for d in detections]
            self.assertTrue(any("missing_dir" in msg for msg in messages))
            self.assertTrue(any("NONEXISTENT" in msg for msg in messages))
            self.assertTrue(any("AGENT_HELP.md" in msg for msg in messages))
        finally:
            v022_module.find_reveal_root = original_find

    def test_known_bug_agent_help_path_mismatch(self):
        """Test known bug: AGENT_HELP.md path mismatch (from CHANGELOG)."""
        # Reproduce bug scenario from CHANGELOG:
        # - CLI handler: Path(__file__).parent.parent / 'docs' / 'AGENT_HELP.md'
        # - MANIFEST.in: include reveal/AGENT_HELP.md (wrong path!)

        # Create file in correct location
        (self.reveal_root / "docs" / "AGENT_HELP.md").write_text("# Help")

        handlers_file = self.reveal_root / "cli" / "handlers.py"
        handlers_file.write_text("""
            from pathlib import Path
            help_file = Path(__file__).parent.parent / 'docs' / 'AGENT_HELP.md'
        """)

        # WRONG path in manifest (root instead of docs/)
        manifest = self.project_root / "MANIFEST.in"
        manifest.write_text("include reveal/AGENT_HELP.md\n")  # Wrong!

        # Mock find_reveal_root
        import reveal.rules.validation.V022 as v022_module
        original_find = v022_module.find_reveal_root
        v022_module.find_reveal_root = lambda: self.reveal_root

        try:
            detections = self.rule.check(
                file_path="reveal://",
                structure=None,
                content=""
            )
            # Should detect:
            # 1. Manifest path doesn't exist (reveal/AGENT_HELP.md)
            # 2. Critical file not properly included (reveal/docs/AGENT_HELP.md)
            self.assertGreaterEqual(len(detections), 2)

            # Verify manifest path detection
            manifest_detections = [d for d in detections if d.file_path == "MANIFEST.in"]
            self.assertGreater(len(manifest_detections), 0)

        finally:
            v022_module.find_reveal_root = original_find


if __name__ == '__main__':
    unittest.main()
