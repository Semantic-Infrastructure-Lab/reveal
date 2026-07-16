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
        adapters.discard('demo')
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

        # Filter out non-adapter files (registry.py/factory.py are infrastructure,
        # not adapters — their docstrings contain @register_adapter examples)
        adapter_files = [f for f in adapter_files if f.stem not in ('__init__', 'base', 'help_data', 'registry', 'factory')]

        # Find which ones have @register_adapter
        registered_in_code = set()
        for adapter_file in adapter_files:
            # Skip test-only and scaffold adapters not counted as production
            if adapter_file.name in ('test.py', 'demo.py'):
                continue
            content = adapter_file.read_text(encoding='utf-8')
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
        init_content = init_file.read_text(encoding='utf-8')

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

    def test_all_analyzer_files_are_imported(self):
        """Every reveal/analyzers/*.py defining @register should be imported by __init__.py.

        BACK-454: ElixirAnalyzer's @register never fired in production because
        analyzers/__init__.py never imported the elixir module at all — only
        tests/test_elixir_analyzer.py (which imports it directly) exercised it,
        masked by pytest's shared import cache. Checks module-level import
        (the decorator fires as an import side effect), not whether the class
        name is re-exported — e.g. TSXAnalyzer lives in typescript.py, whose
        module import already fires its @register even though only
        TypeScriptAnalyzer is bound as a name in __init__.py.
        """
        analyzers_dir = Path(__file__).parent.parent / 'reveal' / 'analyzers'

        registered_modules = {
            f.stem for f in analyzers_dir.glob('*.py')
            if f.stem != '__init__' and '@register(' in f.read_text(encoding='utf-8')
        }

        init_source = (analyzers_dir / '__init__.py').read_text(encoding='utf-8')
        imported_modules = set(re.findall(r'^from \.(\w+) import', init_source, re.MULTILINE))

        missing = registered_modules - imported_modules
        self.assertFalse(
            missing,
            f"Analyzer modules with @register but never imported by "
            f"reveal/analyzers/__init__.py (their @register never fires in "
            f"production CLI use): {sorted(missing)}"
        )

    def test_extension_collisions_are_documented_as_ambiguous(self):
        """Every extension registered by more than one analyzer must be listed
        in registry.AMBIGUOUS_EXTENSIONS (BACK-583).

        The registry is a single dict slot per extension — a second @register
        for the same extension silently overwrites the first, so introspection
        callers (get_all_analyzers(), `reveal --languages`) report only the
        last-registered class as if it were the only answer. That's fine when
        real dispatch resolves the ambiguity via content/path sniffing (see
        _try_conf_detection for '.conf'), but it must be a *documented*
        exception, not a silent one — otherwise a new double-registration
        (e.g. a future analyzer accidentally reusing an existing extension)
        would introduce the same misleading-introspection bug with nothing
        to catch it.
        """
        from reveal.registry import AMBIGUOUS_EXTENSIONS

        analyzers_dir = Path(__file__).parent.parent / 'reveal' / 'analyzers'
        registrations: Dict[str, Set[str]] = {}
        for f in analyzers_dir.glob('*.py'):
            if f.stem == '__init__':
                continue
            source = f.read_text(encoding='utf-8')
            for match in re.finditer(r"@register\(([^)]*)\)", source):
                for ext_match in re.finditer(r"'(\.[\w.]+)'|\"(\.[\w.]+)\"", match.group(1)):
                    ext = (ext_match.group(1) or ext_match.group(2)).lower()
                    registrations.setdefault(ext, set()).add(f.stem)

        colliding = {ext: mods for ext, mods in registrations.items() if len(mods) > 1}
        undocumented = set(colliding) - set(AMBIGUOUS_EXTENSIONS)
        self.assertFalse(
            undocumented,
            f"Extension(s) registered by multiple analyzers but missing from "
            f"registry.AMBIGUOUS_EXTENSIONS: "
            f"{ {ext: sorted(colliding[ext]) for ext in undocumented} }. "
            f"Either this is a real bug (accidental extension reuse), or it's "
            f"intentional content-dependent dispatch — if the latter, add an "
            f"entry to AMBIGUOUS_EXTENSIONS explaining how it resolves."
        )

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

        readme_content = readme_file.read_text(encoding='utf-8')

        # Look for "N adapters", "N built-in adapters", or "N URI adapters" claim
        match = re.search(r'(\d+)\s+(?:[\w-]+\s+)*adapters', readme_content, re.IGNORECASE)
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
        """README language count claim should match what `reveal --languages` reports.

        The honest count is the set of languages reveal can actually route a file to
        and analyze — i.e. extensions with an explicit analyzer, plus the curated
        tree-sitter fallback languages. That is exactly the "Total: N languages
        supported" figure `reveal --languages` prints (see cli/languages.py).

        NOTE: this deliberately does NOT count the full tree-sitter-language-pack
        grammar set (~306). Those grammars exist in the dependency but reveal only
        maps ~84 of them by extension; a file in an unmapped language (e.g. .f90)
        errors with "No analyzer found". Claiming the pack's grammar count would be
        an overclaim the tool itself contradicts.
        """
        from reveal.cli.languages import list_supported_languages

        # Source of truth: the same routine that backs `reveal --languages`.
        listing = list_supported_languages()
        total_match = re.search(r'Total:\s*(\d+)\s+languages?\s+supported', listing)
        self.assertIsNotNone(
            total_match,
            "Could not parse the 'Total: N languages supported' line from "
            "list_supported_languages() — did its output format change?"
        )
        actual_count = int(total_match.group(1))

        # Read README
        readme_file = Path(__file__).parent.parent / 'README.md'
        if not readme_file.exists():
            self.skipTest("README.md not found")

        readme_content = readme_file.read_text(encoding='utf-8')

        # Look for "N languages" / "N+ languages" claim (e.g. "84 languages")
        match = re.search(r'(\d+)(\+)?\s+languages?\b', readme_content, re.IGNORECASE)
        if not match:
            self.skipTest("README doesn't claim language count")

        claimed_count = int(match.group(1))

        # Floor semantics: the documented count is correct as long as reveal
        # actually supports AT LEAST that many languages. This catches the
        # dangerous direction — overclaims like the historical "305+" (which the
        # tool contradicts: reveal file.f90 errors) fail here — while tolerating
        # the +1 registry pollution that leaks in when the full suite registers
        # test-only analyzers (standalone this reports exactly 84; in-suite 85).
        self.assertGreaterEqual(
            actual_count, claimed_count,
            f"README language count is an overclaim!\n"
            f"  README claims: {claimed_count} languages\n"
            f"  reveal --languages reports only: {actual_count} languages\n"
            f"  Please update README.md (or the analyzer registry)"
        )


class TestAnalyzerCategoryAttribute(unittest.TestCase):
    """Tests for BACK-369: CATEGORY attribute and get_code_extensions()."""

    def setUp(self):
        import reveal.analyzers  # noqa: F401 — trigger registration
        from reveal.registry import get_code_extensions, get_all_analyzers
        self.get_code_extensions = get_code_extensions
        self.get_all_analyzers = get_all_analyzers

    def test_all_registered_analyzers_have_category(self):
        """Every registered analyzer class must carry a CATEGORY attribute."""
        analyzers = self.get_all_analyzers()
        missing = [
            ext for ext, info in analyzers.items()
            if not hasattr(info['class'], 'CATEGORY')
        ]
        self.assertEqual(
            missing, [],
            f"Analyzers missing CATEGORY attribute: {missing}"
        )

    def test_category_values_are_valid(self):
        """CATEGORY must be one of the four allowed values."""
        valid = {'code', 'data', 'doc', 'config'}
        analyzers = self.get_all_analyzers()
        bad = [
            (ext, info['class'].CATEGORY)
            for ext, info in analyzers.items()
            if getattr(info['class'], 'CATEGORY', None) not in valid
        ]
        self.assertEqual(bad, [], f"Invalid CATEGORY values: {bad}")

    def test_get_all_analyzers_exposes_category_key(self):
        """get_all_analyzers() metadata dict must include 'category' key."""
        analyzers = self.get_all_analyzers()
        for ext, info in analyzers.items():
            self.assertIn('category', info, f"Missing 'category' key for {ext}")

    def test_known_code_extensions_are_code(self):
        """Core code extensions must be in get_code_extensions()."""
        code = self.get_code_extensions()
        for ext in ['.py', '.js', '.ts', '.rs', '.go', '.java', '.zig',
                    '.lua', '.dart', '.mjs', '.cjs', '.bat', '.ex', '.hs', '.v']:
            self.assertIn(ext, code, f"{ext} should be in code extensions")

    def test_data_doc_config_extensions_excluded(self):
        """Data/doc/config extensions must not appear in get_code_extensions()."""
        code = self.get_code_extensions()
        for ext in ['.md', '.json', '.yaml', '.yml', '.csv', '.tsv',
                    '.xml', '.toml', '.html', '.htm', '.docx', '.xlsx',
                    '.pptx', '.odt', '.ods', '.odp', '.ini', '.cfg',
                    '.conf', '.properties', '.tf', '.hcl']:
            self.assertNotIn(ext, code, f"{ext} should NOT be in code extensions")

    def test_get_code_extensions_is_frozenset(self):
        """get_code_extensions() must return a frozenset."""
        result = self.get_code_extensions()
        self.assertIsInstance(result, frozenset)

    def test_get_code_extensions_is_cached(self):
        """Repeated calls must return the same object (lru_cache)."""
        s1 = self.get_code_extensions()
        s2 = self.get_code_extensions()
        self.assertIs(s1, s2)

    def test_is_code_file_uses_registry(self):
        """is_code_file() must agree with get_code_extensions() for all extensions."""
        import reveal.analyzers  # noqa: F401
        from pathlib import Path
        from reveal.adapters.ast.analysis import is_code_file
        code = self.get_code_extensions()

        for ext in ['.py', '.zig', '.rs', '.md', '.json', '.yaml', '.csv', '.html']:
            expected = ext in code
            result = is_code_file(Path('test' + ext))
            self.assertEqual(
                result, expected,
                f"is_code_file('{ext}') = {result}, but get_code_extensions() says {expected}"
            )

    def test_treesitter_fallback_extensions_are_code(self):
        """All TREESITTER_EXTENSION_MAP keys must appear in get_code_extensions()."""
        from reveal.registry import TREESITTER_EXTENSION_MAP
        code = self.get_code_extensions()
        missing = [ext for ext in TREESITTER_EXTENSION_MAP if ext not in code]
        self.assertEqual(missing, [], f"Tree-sitter extensions missing from code set: {missing}")


if __name__ == '__main__':
    unittest.main()
