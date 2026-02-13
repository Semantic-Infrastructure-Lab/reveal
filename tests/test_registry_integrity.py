"""Tests for registry integrity - ensures all adapters/analyzers are properly registered.

These tests prevent bugs like:
- Adapters with @register_adapter but not imported in __init__.py
- Analyzers with @register but not showing up in listings
- Documentation claiming N adapters/languages but actual count differs

These tests would have caught the bug where DiffAdapter and MarkdownQueryAdapter
weren't imported in adapters/__init__.py, causing list_supported_schemes() to
show 10 instead of 12 adapters.
"""

import unittest
import re
from pathlib import Path
from typing import Set, Dict

from reveal.adapters.base import list_supported_schemes, get_adapter_class
from reveal.registry import get_all_analyzers


class TestAdapterRegistryIntegrity(unittest.TestCase):
    """Test that all adapters are properly registered and importable."""

    @staticmethod
    def _get_production_adapters():
        """Get registered production adapters, excluding test-only adapters.

        The 'test' adapter is registered during test runs but is not a production
        adapter (not imported in adapters/__init__.py, not documented).
        """
        adapters = set(list_supported_schemes())
        adapters.discard('test')
        return adapters

    def test_all_adapter_files_are_registered(self):
        """All files with @register_adapter should appear in list_supported_schemes().

        This test would have caught the bug where diff.py and markdown.py had
        @register_adapter but weren't imported in __init__.py.
        """
        # Find all adapter files (including subdirectories)
        adapters_dir = Path(__file__).parent.parent / 'reveal' / 'adapters'

        # Scan both top-level and subdirectories
        adapter_files = []
        adapter_files.extend(adapters_dir.glob('*.py'))

        # Scan subdirectories for adapter.py files
        for subdir in adapters_dir.iterdir():
            if subdir.is_dir() and subdir.name not in ('__pycache__', 'help_data'):
                adapter_files.extend(subdir.glob('*.py'))

        # Filter out non-adapter files
        adapter_files = [f for f in adapter_files if f.stem not in ('__init__', 'base', 'help_data')]

        # Find which ones have @register_adapter
        registered_in_code = set()
        for adapter_file in adapter_files:
            # Skip test-only adapters not imported in __init__.py
            if adapter_file.name == 'test.py':
                continue
            content = adapter_file.read_text()
            # Look for @register_adapter('scheme')
            matches = re.findall(r'@register_adapter\([\'"](\w+)[\'"]\)', content)
            registered_in_code.update(matches)

        # Get actually registered production adapters (excludes test-only adapters)
        actually_registered = self._get_production_adapters()

        # They should match
        missing = registered_in_code - actually_registered
        extra = actually_registered - registered_in_code

        self.assertEqual(
            registered_in_code, actually_registered,
            f"Registry mismatch!\n"
            f"  Decorated with @register_adapter but not in registry: {missing}\n"
            f"  In registry but no @register_adapter found: {extra}\n"
            f"  Expected: {sorted(registered_in_code)}\n"
            f"  Got: {sorted(actually_registered)}"
        )

    def test_all_registered_adapters_are_importable(self):
        """All registered adapters should have importable classes.

        Tests that get_adapter_class() works for all registered schemes.
        """
        schemes = list_supported_schemes()

        for scheme in schemes:
            with self.subTest(scheme=scheme):
                adapter_class = get_adapter_class(scheme)
                self.assertIsNotNone(
                    adapter_class,
                    f"{scheme}:// is registered but get_adapter_class() returns None"
                )

                # Should be able to instantiate (at least for basic adapters)
                # Some adapters need parameters, so we just check the class exists
                self.assertTrue(
                    callable(adapter_class),
                    f"{scheme}:// adapter class is not callable"
                )

    def test_adapters_init_imports_match_registration(self):
        """Check that adapters/__init__.py imports all registered adapters.

        This ensures that adapters are loaded on import, not just via lazy loading.
        """
        # Get all registered production adapters (excludes test-only adapters)
        registered_schemes = self._get_production_adapters()

        # Read adapters/__init__.py
        init_file = Path(__file__).parent.parent / 'reveal' / 'adapters' / '__init__.py'
        init_content = init_file.read_text()

        # Find all imports (from .xyz import XyzAdapter)
        import_pattern = r'from \.\w+ import \w+Adapter'
        imports = re.findall(import_pattern, init_content)

        # We should have at least as many imports as registered schemes
        # (Some adapters might be in subdirectories)
        self.assertGreaterEqual(
            len(imports), len(registered_schemes),
            f"adapters/__init__.py has {len(imports)} imports but "
            f"{len(registered_schemes)} schemes are registered. "
            f"Missing imports?"
        )


class TestAnalyzerRegistryIntegrity(unittest.TestCase):
    """Test that all analyzers are properly registered and discoverable."""

    def test_analyzer_count_is_consistent(self):
        """Analyzer count should be consistent with language claims.

        Note: Analyzer files can register multiple extensions (e.g., yaml_json.py
        registers both .yaml and .json), so we count unique language names.
        """
        analyzers = get_all_analyzers()

        # Count unique language names (not extensions)
        unique_languages = set()
        for analyzer_info in analyzers.values():
            if 'name' in analyzer_info:
                unique_languages.add(analyzer_info['name'])

        actual_count = len(unique_languages)

        # Expected language count (update when adding new languages)
        # This should match README.md's "38 languages built-in" claim
        expected_min = 38  # At least 38 languages

        self.assertGreaterEqual(
            actual_count, expected_min,
            f"Language count dropped! Expected at least {expected_min}, got {actual_count}.\n"
            f"Did you remove a language analyzer?"
        )

        # If this test fails because count increased, update README.md and this test
        if actual_count > expected_min:
            print(f"\n⚠️  Language count increased: {expected_min} → {actual_count}")
            print(f"   Please update:")
            print(f"   1. This test's expected_min value")
            print(f"   2. README.md language count")

    def test_all_analyzer_files_have_tests(self):
        """All analyzer files should have corresponding test files (V004 compliance).

        This is informational - missing tests are flagged by V004 rule.
        """
        analyzers_dir = Path(__file__).parent.parent / 'reveal' / 'analyzers'
        analyzer_files = [
            f for f in analyzers_dir.glob('*.py')
            if f.stem not in ('__init__', 'base') and not f.stem.startswith('_')
        ]

        tests_dir = Path(__file__).parent
        missing_tests = []

        for analyzer_file in analyzer_files:
            test_file = tests_dir / f'test_{analyzer_file.stem}.py'
            if not test_file.exists():
                # Check for _analyzer suffix variant
                test_file_alt = tests_dir / f'test_{analyzer_file.stem}_analyzer.py'
                if not test_file_alt.exists():
                    missing_tests.append(analyzer_file.stem)

        # This is a soft warning - we allow some analyzers to not have tests
        # (they might be tested in shared test suites)
        if missing_tests:
            print(f"\n⚠️  Analyzers without dedicated test files: {', '.join(missing_tests)}")
            print(f"   Run `reveal reveal:// --check` to see V004 warnings")


class TestRevealAdapterOutputIntegrity(unittest.TestCase):
    """Test that reveal:// adapter output is accurate.

    These tests ensure that `reveal reveal://` shows correct counts.
    """

    def test_reveal_adapter_shows_all_adapters(self):
        """reveal:// should list all registered adapters.

        Note: This includes test-only adapters if they are registered during test runs.
        """
        from reveal.adapters.reveal import RevealAdapter

        adapter = RevealAdapter()
        structure = adapter.get_structure()

        # Get adapter info from structure (it's a list of dicts)
        adapter_info = structure.get('adapters', [])
        # Extract scheme from each adapter dict
        listed_adapters = set(a['scheme'] for a in adapter_info)

        # Get all actually registered adapters (including test adapters during test runs)
        registered_adapters = set(list_supported_schemes())

        # They should match exactly
        self.assertEqual(
            listed_adapters, registered_adapters,
            f"reveal:// output doesn't match registered adapters!\n"
            f"  Listed: {sorted(listed_adapters)}\n"
            f"  Registered: {sorted(registered_adapters)}\n"
            f"  Missing from output: {registered_adapters - listed_adapters}\n"
            f"  Extra in output: {listed_adapters - registered_adapters}"
        )

    def test_reveal_adapter_shows_all_analyzers(self):
        """reveal:// should list all registered analyzers."""
        from reveal.adapters.reveal import RevealAdapter

        adapter = RevealAdapter()
        structure = adapter.get_structure()

        # Get analyzer info from structure (it's a list of dicts)
        analyzer_info = structure.get('analyzers', [])
        # Extract name from each analyzer dict
        listed_analyzers = set(a['name'] for a in analyzer_info)

        # Get actually registered analyzers (these are file extensions)
        # get_all_analyzers() returns {ext: {name, ...}}
        analyzers = get_all_analyzers()

        # Count unique analyzer names (not extensions)
        # An analyzer file can register multiple extensions
        unique_analyzer_names = set()
        for info in analyzers.values():
            # Normalize analyzer name (remove _analyzer suffix, etc.)
            name = info.get('name', '').lower().replace(' ', '_').replace('-', '_')
            if name:
                unique_analyzer_names.add(name)

        # reveal:// shows analyzer filenames (without .py)
        # Check that count is reasonable
        self.assertGreater(
            len(listed_analyzers), 0,
            "reveal:// shows no analyzers!"
        )

        # Listed should be close to unique language count (within reason)
        # Some analyzers register multiple languages
        self.assertGreaterEqual(
            len(listed_analyzers), 25,  # At least 25 analyzer files
            f"reveal:// shows too few analyzers: {len(listed_analyzers)}"
        )


class TestDocumentationAccuracy(unittest.TestCase):
    """Test that documentation counts match reality.

    These tests complement the V012-V013 validation rules by running in CI.
    """

    def test_adapter_count_in_readme_is_accurate(self):
        """README adapter count claim should match list_supported_schemes().

        This is what V013 validation rule checks, but as a test it runs in CI.
        """
        # Count production adapters only (excludes test-only adapters)
        actual_count = len(TestAdapterRegistryIntegrity._get_production_adapters())

        # Read README
        readme_file = Path(__file__).parent.parent / 'README.md'
        if not readme_file.exists():
            self.skipTest("README.md not found")

        readme_content = readme_file.read_text()

        # Look for "N adapters" claim
        match = re.search(r'(\d+)\s+adapters', readme_content, re.IGNORECASE)
        if not match:
            self.skipTest("README doesn't claim adapter count")

        claimed_count = int(match.group(1))

        self.assertEqual(
            actual_count, claimed_count,
            f"README adapter count is wrong!\n"
            f"  README claims: {claimed_count} adapters\n"
            f"  Actually registered: {actual_count} adapters\n"
            f"  Please update README.md"
        )

    def test_language_count_in_readme_is_accurate(self):
        """README language count claim should match registered analyzers.

        This is what V012 validation rule checks, but as a test it runs in CI.
        """
        analyzers = get_all_analyzers()

        # Count unique language names
        unique_languages = set()
        for analyzer_info in analyzers.values():
            if 'name' in analyzer_info:
                unique_languages.add(analyzer_info['name'])

        actual_count = len(unique_languages)

        # Read README
        readme_file = Path(__file__).parent.parent / 'README.md'
        if not readme_file.exists():
            self.skipTest("README.md not found")

        readme_content = readme_file.read_text()

        # Look for "N languages" or "N+ languages" claim
        match = re.search(r'(\d+)(\+)?\s+languages?\s+built-in', readme_content, re.IGNORECASE)
        if not match:
            self.skipTest("README doesn't claim language count")

        claimed_count = int(match.group(1))
        is_minimum = match.group(2) == '+'  # "40+" means "at least 40"

        if is_minimum:
            self.assertGreaterEqual(
                actual_count, claimed_count,
                f"README language count is wrong!\n"
                f"  README claims: {claimed_count}+ languages\n"
                f"  Actually registered: {actual_count} languages\n"
                f"  Please update README.md"
            )
        else:
            self.assertEqual(
                actual_count, claimed_count,
                f"README language count is wrong!\n"
                f"  README claims: {claimed_count} languages\n"
                f"  Actually registered: {actual_count} languages\n"
                f"  Please update README.md"
            )


if __name__ == '__main__':
    unittest.main()
