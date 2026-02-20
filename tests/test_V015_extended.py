"""Extended tests for V015: Rules count accuracy validation.

Comprehensive edge case coverage for V015 rule testing.
"""

import sys
import unittest
from pathlib import Path
import tempfile
import shutil
from unittest import mock
import pytest

from reveal.rules.validation.V015 import V015


class TestV015NoRevealRoot(unittest.TestCase):
    """Test V015 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V015()

    def test_no_reveal_root_returns_empty(self):
        """Test that no detections when reveal root not found."""
        with mock.patch('reveal.rules.validation.V015.find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV015MissingFiles(unittest.TestCase):
    """Test V015 when files are missing."""

    def setUp(self):
        self.rule = V015()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_readme_returns_empty(self):
        """Test no detection when README.md doesn't exist."""
        with mock.patch('reveal.rules.validation.V015.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)

    def test_no_rules_directory_returns_empty(self):
        """Test no detection when rules directory missing."""
        # Create README but no rules directory
        readme_file = self.project_root / 'README.md'
        readme_file.write_text("50+ built-in rules", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V015.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            # Can't count rules without rules directory
            self.assertEqual(len(detections), 0)


class TestV015CountMismatches(unittest.TestCase):
    """Test V015 count mismatch detection."""

    def setUp(self):
        self.rule = V015()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.project_root = Path(self.tmpdir)
        # Create rules directory
        self.rules_dir = self.reveal_root / 'rules'
        self.rules_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_minimum_claim_below_actual_creates_detection(self):
        """Test detection when minimum claim is below actual count."""
        # Create 10 actual rules
        for category in ['validation', 'naming']:
            category_dir = self.rules_dir / category
            category_dir.mkdir()
            for i in range(5):
                rule_file = category_dir / f'V{i:03d}.py'
                rule_file.write_text('# rule', encoding='utf-8')

        # README claims 15+ (minimum) but actual is 10
        readme_file = self.project_root / 'README.md'
        readme_file.write_text("15+ built-in rules", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V015.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 1)
            self.assertIn("below minimum", detections[0].message)
            self.assertIn("15", detections[0].message)

    def test_exact_claim_mismatch_creates_detection(self):
        """Test detection when exact claim doesn't match actual."""
        # Create 10 actual rules
        for category in ['validation']:
            category_dir = self.rules_dir / category
            category_dir.mkdir()
            for i in range(10):
                rule_file = category_dir / f'V{i:03d}.py'
                rule_file.write_text('# rule', encoding='utf-8')

        # README claims exactly 15 but actual is 10
        readme_file = self.project_root / 'README.md'
        readme_file.write_text("15 built-in rules", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V015.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 1)
            self.assertIn("mismatch", detections[0].message)
            self.assertIn("15", detections[0].message)

    def test_minimum_claim_at_actual_no_detection(self):
        """Test no detection when minimum claim equals actual."""
        # Create 10 actual rules
        category_dir = self.rules_dir / 'validation'
        category_dir.mkdir()
        for i in range(10):
            rule_file = category_dir / f'V{i:03d}.py'
            rule_file.write_text('# rule', encoding='utf-8')

        # README claims 10+ (minimum) and actual is 10
        readme_file = self.project_root / 'README.md'
        readme_file.write_text("10+ built-in rules", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V015.find_reveal_root', return_value=self.reveal_root):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV015CountingLogic(unittest.TestCase):
    """Test V015 rule counting logic."""

    def setUp(self):
        self.rule = V015()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.rules_dir = self.reveal_root / 'rules'
        self.rules_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_count_skips_utils_files(self):
        """Test that utils.py files are not counted."""
        category_dir = self.rules_dir / 'validation'
        category_dir.mkdir()
        # Create actual rules
        (category_dir / 'V001.py').write_text('# rule', encoding='utf-8')
        (category_dir / 'V002.py').write_text('# rule', encoding='utf-8')
        # Create utils (should not count)
        (category_dir / 'utils.py').write_text('# utils', encoding='utf-8')
        (category_dir / '__init__.py').write_text('# init', encoding='utf-8')
        (category_dir / 'adapter_utils.py').write_text('# utils', encoding='utf-8')
        (category_dir / '_private.py').write_text('# private', encoding='utf-8')

        with mock.patch('reveal.rules.validation.V015.find_reveal_root', return_value=self.reveal_root):
            count = self.rule._count_registered_rules()
            # Should only count V001 and V002, not utils/init/_private
            self.assertEqual(count, 2)

    @pytest.mark.skipif(sys.platform == 'win32', reason="chmod does not restrict access on Windows")
    def test_count_exception_handled(self):
        """Test exception handling in count_registered_rules."""
        # Make rules_dir unreadable
        self.rules_dir.chmod(0o000)

        try:
            with mock.patch('reveal.rules.validation.V015.find_reveal_root', return_value=self.reveal_root):
                count = self.rule._count_registered_rules()
                # Should handle exception gracefully
                self.assertIsNone(count)
        finally:
            # Restore permissions for cleanup
            self.rules_dir.chmod(0o755)


class TestV015ReadmeExtraction(unittest.TestCase):
    """Test V015 README extraction logic."""

    def setUp(self):
        self.rule = V015()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_extract_multiple_claims(self):
        """Test extracting multiple claims from README."""
        readme_file = Path(self.tmpdir) / 'README.md'
        readme_file.write_text("""
# Project

Features:
- 50+ built-in rules
- Other features

Details:
- Exactly 57 built-in rules available
""", encoding='utf-8')

        claims = self.rule._extract_rules_count_from_readme(readme_file)
        # Should find both claims
        self.assertEqual(len(claims), 2)
        # First claim: line 5, count 50, is_minimum=True
        self.assertEqual(claims[0][1], 50)
        self.assertTrue(claims[0][2])
        # Second claim: line 10, count 57, is_minimum=False
        self.assertEqual(claims[1][1], 57)
        self.assertFalse(claims[1][2])

    @pytest.mark.skipif(sys.platform == 'win32', reason="chmod does not restrict access on Windows")
    def test_extract_readme_exception_handled(self):
        """Test exception handling in extract_rules_count_from_readme."""
        readme_file = Path(self.tmpdir) / 'README.md'
        readme_file.write_text("50+ built-in rules", encoding='utf-8')
        readme_file.chmod(0o000)

        try:
            claims = self.rule._extract_rules_count_from_readme(readme_file)
            # Should handle exception gracefully
            self.assertEqual(claims, [])
        finally:
            # Restore permissions for cleanup
            readme_file.chmod(0o644)


if __name__ == '__main__':
    unittest.main()
