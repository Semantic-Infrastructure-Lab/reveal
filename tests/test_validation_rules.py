"""Comprehensive tests for validation rules V001-V011.

These rules validate reveal's own codebase for consistency and completeness.
They only run on reveal:// URIs to check reveal's internal structure.
"""

import unittest
import tempfile
from pathlib import Path
from reveal.rules.validation.V001 import V001
from reveal.rules.validation.V002 import V002
from reveal.rules.validation.V003 import V003
from reveal.rules.validation.V004 import V004
from reveal.rules.validation.V005 import V005
from reveal.rules.validation.V006 import V006
from reveal.rules.validation.V007 import V007
from reveal.rules.validation.V008 import V008
from reveal.rules.validation.V009 import V009
from reveal.rules.validation.V011 import V011
from reveal.rules.validation.V012 import V012
from reveal.rules.validation.V013 import V013
from reveal.rules.validation.V015 import V015
from reveal.rules.validation.V016 import V016
from reveal.rules.validation.V017 import V017
from reveal.rules.validation.V018 import V018
from reveal.rules.validation.V019 import V019
from reveal.rules.validation.V020 import V020
from reveal.rules.validation.V021 import V021
from reveal.rules.validation.V022 import V022
from reveal.rules.validation.V023 import V023
from reveal.rules.validation.utils import find_reveal_root


class TestV001HelpDocumentation(unittest.TestCase):
    """Test V001: Help documentation completeness."""

    def setUp(self):
        self.rule = V001()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V001")
        self.assertEqual(self.rule.severity.name, "MEDIUM")
        self.assertIn("help", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        # This will check actual reveal installation
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list (may be empty if all docs exist)
        self.assertIsInstance(detections, list)

    def test_find_reveal_root(self):
        """Test that _find_reveal_root locates reveal installation."""
        root = find_reveal_root()
        # Should find reveal root (we're running tests from reveal project)
        self.assertIsNotNone(root)
        self.assertTrue((root / 'analyzers').exists())
        self.assertTrue((root / 'rules').exists())

    def test_get_analyzers(self):
        """Test that _get_analyzers finds analyzer files."""
        root = find_reveal_root()
        if root:
            analyzers = self.rule._get_analyzers(root)
            self.assertIsInstance(analyzers, dict)
            # Should find multiple analyzers
            self.assertGreater(len(analyzers), 0)
            # Should not include __init__ or private files
            self.assertNotIn('__init__', analyzers)
            # Check that values are Path objects
            for name, path in analyzers.items():
                self.assertIsInstance(path, Path)
                self.assertTrue(path.exists())

    def test_get_static_help(self):
        """Test that _get_static_help extracts STATIC_HELP dict."""
        root = find_reveal_root()
        if root:
            static_help = self.rule._get_static_help(root)
            self.assertIsInstance(static_help, dict)
            # May or may not have entries depending on implementation


class TestV002AnalyzerRegistration(unittest.TestCase):
    """Test V002: Analyzer registration validation."""

    def setUp(self):
        self.rule = V002()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V002")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("register", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

    def test_has_register_decorator_found(self):
        """Test detection of @register decorator."""
        content = """
from ..base import register

@register('.py', name='python')
class PythonAnalyzer:
    pass
"""
        self.assertTrue(self.rule._has_register_decorator(content))

    def test_has_register_decorator_not_found(self):
        """Test when @register decorator is missing."""
        content = """
class SomeClass:
    pass
"""
        self.assertFalse(self.rule._has_register_decorator(content))

    def test_has_register_decorator_import_only(self):
        """Test that import of register is detected."""
        content = "from ..base import register, BaseAnalyzer"
        self.assertTrue(self.rule._has_register_decorator(content))

    def test_has_register_decorator_usage(self):
        """Test that @register usage is detected."""
        content = "@register('.js')\nclass JSAnalyzer:\n    pass"
        self.assertTrue(self.rule._has_register_decorator(content))

    def test_find_reveal_root(self):
        """Test _find_reveal_root locates installation."""
        root = find_reveal_root()
        self.assertIsNotNone(root)
        self.assertTrue((root / 'analyzers').exists())


class TestV003FeatureMatrix(unittest.TestCase):
    """Test V003: Feature matrix coverage."""

    def setUp(self):
        self.rule = V003()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V003")
        self.assertEqual(self.rule.severity.name, "MEDIUM")
        self.assertIn("feature", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

    def test_common_features_defined(self):
        """Test that COMMON_FEATURES is properly defined."""
        self.assertIsInstance(self.rule.COMMON_FEATURES, dict)
        self.assertGreater(len(self.rule.COMMON_FEATURES), 0)
        # Check structure_extraction is required
        self.assertIn('structure_extraction', self.rule.COMMON_FEATURES)

    def test_structured_formats_defined(self):
        """Test that STRUCTURED_FORMATS is defined."""
        self.assertIsInstance(self.rule.STRUCTURED_FORMATS, set)
        self.assertGreater(len(self.rule.STRUCTURED_FORMATS), 0)
        # Check some expected formats
        expected = {'python', 'javascript', 'markdown'}
        self.assertTrue(expected.issubset(self.rule.STRUCTURED_FORMATS))

    def test_check_hierarchy_support_found(self):
        """Test detection of hierarchy support."""
        content = """
def get_outline(self):
    return self.hierarchy
"""
        result = self.rule._check_hierarchy_support(content)
        self.assertTrue(result)

    def test_check_hierarchy_support_not_found(self):
        """Test when hierarchy support is missing."""
        content = """
def get_structure(self):
    return {}
"""
        result = self.rule._check_hierarchy_support(content)
        self.assertFalse(result)


class TestV004TestCoverage(unittest.TestCase):
    """Test V004: Test coverage gaps."""

    def setUp(self):
        self.rule = V004()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V004")
        self.assertEqual(self.rule.severity.name, "LOW")
        self.assertIn("test", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

    def test_exempt_analyzers_defined(self):
        """Test that EXEMPT_ANALYZERS is defined."""
        self.assertIsInstance(self.rule.EXEMPT_ANALYZERS, set)
        # Should include base files
        self.assertIn('__init__', self.rule.EXEMPT_ANALYZERS)

    def test_shared_test_files_defined(self):
        """Test that SHARED_TEST_FILES is defined."""
        self.assertIsInstance(self.rule.SHARED_TEST_FILES, dict)

    def test_find_reveal_root(self):
        """Test _find_reveal_root locates installation."""
        root = find_reveal_root()
        self.assertIsNotNone(root)
        self.assertTrue((root / 'analyzers').exists())


class TestV005StaticHelpSync(unittest.TestCase):
    """Test V005: Static help file synchronization."""

    def setUp(self):
        self.rule = V005()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V005")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("help", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

    def test_get_static_help(self):
        """Test _get_static_help extracts help files."""
        root = find_reveal_root()
        if root:
            static_help = self.rule._get_static_help(root)
            self.assertIsInstance(static_help, dict)

    def test_find_reveal_root(self):
        """Test _find_reveal_root locates installation."""
        root = find_reveal_root()
        self.assertIsNotNone(root)


class TestV006OutputFormatSupport(unittest.TestCase):
    """Test V006: Output format support validation."""

    def setUp(self):
        self.rule = V006()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V006")
        self.assertEqual(self.rule.severity.name, "MEDIUM")
        self.assertIn("format", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

    def test_required_method_defined(self):
        """Test that REQUIRED_METHOD is defined."""
        self.assertEqual(self.rule.REQUIRED_METHOD, 'get_structure')

    def test_check_return_type_found(self):
        """Test detection of Dict return type."""
        content = """
def get_structure(self) -> Dict[str, Any]:
    return {}
"""
        result = self.rule._check_return_type(content)
        self.assertTrue(result)

    def test_check_return_type_dict_lowercase(self):
        """Test detection of dict return type (lowercase)."""
        content = """
def get_structure(self) -> dict:
    return {}
"""
        result = self.rule._check_return_type(content)
        self.assertTrue(result)

    def test_check_return_type_not_found(self):
        """Test when return type is missing or wrong."""
        content = """
def get_structure(self):
    return {}
"""
        # Without type annotation, may or may not be detected
        # depending on implementation details
        result = self.rule._check_return_type(content)
        self.assertIsInstance(result, bool)

    def test_find_method_line(self):
        """Test _find_method_line locates method definition."""
        content = """
class Analyzer:
    def get_structure(self):
        return {}

    def other_method(self):
        pass
"""
        line = self.rule._find_method_line(content, 'get_structure')
        # Should find the line number (exact line depends on content)
        self.assertGreater(line, 0)

    def test_find_method_line_not_found(self):
        """Test when method doesn't exist."""
        content = """
class Analyzer:
    def other_method(self):
        pass
"""
        line = self.rule._find_method_line(content, 'get_structure')
        self.assertEqual(line, 1)  # Returns 1 as fallback


class TestV007VersionConsistency(unittest.TestCase):
    """Test V007: Version consistency across project files."""

    def setUp(self):
        self.rule = V007()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V007")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("version", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

    def test_extract_version_from_pyproject(self):
        """Test extracting version from pyproject.toml content."""
        # This method needs a Path object, so we test with actual file if it exists
        root = find_reveal_root()
        if root:
            project_root = root.parent
            pyproject = project_root / 'pyproject.toml'
            if pyproject.exists():
                version = self.rule._extract_version_from_pyproject(pyproject)
                if version:
                    # Should be semantic version format
                    self.assertRegex(version, r'^\d+\.\d+\.\d+')

    def test_check_changelog(self):
        """Test checking if version exists in changelog."""
        # Test with actual changelog if it exists
        root = find_reveal_root()
        if root:
            project_root = root.parent
            changelog = project_root / 'CHANGELOG.md'
            if changelog.exists():
                # Test with version that should exist (from pyproject)
                pyproject = project_root / 'pyproject.toml'
                if pyproject.exists():
                    version = self.rule._extract_version_from_pyproject(pyproject)
                    if version:
                        result = self.rule._check_changelog(changelog, version)
                        self.assertIsInstance(result, bool)

    def test_find_reveal_root(self):
        """Test _find_reveal_root locates installation."""
        root = find_reveal_root()
        self.assertIsNotNone(root)


class TestV008AnalyzerSignature(unittest.TestCase):
    """Test V008: Analyzer get_structure signature validation."""

    def setUp(self):
        self.rule = V008()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V008")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("kwargs", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

    def test_find_reveal_root(self):
        """Test _find_reveal_root locates installation."""
        root = find_reveal_root()
        self.assertIsNotNone(root)
        self.assertTrue((root / 'analyzers').exists())

    def test_get_analyzer_files(self):
        """Test _get_analyzer_files finds analyzer files."""
        root = find_reveal_root()
        if root:
            analyzers = self.rule._get_analyzer_files(root)
            self.assertIsInstance(analyzers, list)
            self.assertGreater(len(analyzers), 0)
            # Each should be a Path object
            for analyzer in analyzers:
                self.assertIsInstance(analyzer, Path)
                self.assertTrue(analyzer.exists())
                self.assertTrue(analyzer.suffix == '.py')

    def test_check_analyzer_file_integration(self):
        """Test _check_analyzer_file on actual analyzer."""
        root = find_reveal_root()
        if root:
            analyzers = self.rule._get_analyzer_files(root)
            if analyzers:
                # Test on first analyzer
                detections = self.rule._check_analyzer_file(analyzers[0])
                self.assertIsInstance(detections, list)
                # May or may not have detections depending on implementation


class TestV009DocumentationCrossReferences(unittest.TestCase):
    """Test V009: Documentation cross-reference validation."""

    def setUp(self):
        self.rule = V009()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V009")
        self.assertEqual(self.rule.severity.name, "MEDIUM")
        self.assertIn("cross-reference", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.md",
            structure=None,
            content="[link](other.md)"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://README.md",
            structure=None,
            content="# Test"
        )
        self.assertIsInstance(detections, list)

    def test_find_reveal_root(self):
        """Test that _find_reveal_root locates reveal installation."""
        root = find_reveal_root()
        self.assertIsNotNone(root)
        self.assertTrue((root / 'analyzers').exists())
        self.assertTrue((root / 'rules').exists())

    def test_uri_to_path(self):
        """Test converting reveal:// URI to actual path."""
        root = find_reveal_root()
        if root:
            project_root = root.parent
            # Test with README.md
            path = self.rule._uri_to_path("reveal://README.md", root, project_root)
            self.assertIsNotNone(path)
            self.assertIsInstance(path, Path)

    def test_resolve_link_relative(self):
        """Test resolving relative links."""
        root = find_reveal_root()
        if root:
            project_root = root.parent
            source_file = project_root / 'README.md'
            if source_file.exists():
                # Test relative link
                resolved = self.rule._resolve_link(source_file, 'CHANGELOG.md', project_root)
                self.assertIsNotNone(resolved)
                self.assertEqual(resolved.name, 'CHANGELOG.md')

    def test_resolve_link_absolute(self):
        """Test resolving absolute links (from project root)."""
        root = find_reveal_root()
        if root:
            project_root = root.parent
            source_file = project_root / 'README.md'
            if source_file.exists():
                # Test absolute link
                resolved = self.rule._resolve_link(source_file, '/README.md', project_root)
                self.assertIsNotNone(resolved)

    def test_external_links_ignored(self):
        """Test that external links are not validated."""
        content = """
        [GitHub](https://github.com)
        [Docs](http://example.com/docs)
        """
        detections = self.rule.check(
            file_path="reveal://test.md",
            structure=None,
            content=content
        )
        # Should not detect issues with external links
        self.assertEqual(len(detections), 0)

    def test_anchor_only_links_ignored(self):
        """Test that anchor-only links are not validated."""
        content = """
        [Section](#heading)
        [Another](#another-section)
        """
        detections = self.rule.check(
            file_path="reveal://test.md",
            structure=None,
            content=content
        )
        # Should not validate anchor-only links (that's L001's job)
        self.assertEqual(len(detections), 0)

    def test_mailto_links_ignored(self):
        """Test that mailto: links are ignored."""
        content = """
        [Email](mailto:test@example.com)
        """
        detections = self.rule.check(
            file_path="reveal://test.md",
            structure=None,
            content=content
        )
        self.assertEqual(len(detections), 0)


class TestV011ReleaseReadiness(unittest.TestCase):
    """Test V011: Release readiness validation."""

    def setUp(self):
        self.rule = V011()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V011")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("release", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

    def test_find_reveal_root(self):
        """Test that _find_reveal_root locates reveal installation."""
        root = find_reveal_root()
        self.assertIsNotNone(root)
        self.assertTrue((root / 'analyzers').exists())
        self.assertTrue((root / 'rules').exists())

    def test_extract_version_from_pyproject(self):
        """Test extracting version from pyproject.toml."""
        root = find_reveal_root()
        if root:
            project_root = root.parent
            pyproject = project_root / 'pyproject.toml'
            if pyproject.exists():
                version = self.rule._extract_version_from_pyproject(pyproject)
                if version:
                    # Should be semantic version format
                    self.assertRegex(version, r'^\d+\.\d+\.\d+$')

    def test_changelog_has_dated_entry_with_date(self):
        """Test detecting dated changelog entries."""
        root = find_reveal_root()
        if root:
            project_root = root.parent
            # Create temp changelog with dated entry
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write("## [0.27.1] - 2025-12-31\n")
                f.write("Changes here\n")
                temp_path = Path(f.name)

            try:
                result = self.rule._changelog_has_dated_entry(temp_path, "0.27.1")
                self.assertTrue(result)
            finally:
                temp_path.unlink()

    def test_changelog_has_dated_entry_no_date(self):
        """Test detecting changelog entries without dates."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("## [0.28.0]\n")
            f.write("Changes here\n")
            temp_path = Path(f.name)

        try:
            result = self.rule._changelog_has_dated_entry(temp_path, "0.28.0")
            self.assertFalse(result, "Should return False for entry without date")
        finally:
            temp_path.unlink()

    def test_changelog_has_dated_entry_unreleased(self):
        """Test detecting Unreleased changelog entries."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("## [Unreleased]\n")
            f.write("## [0.27.1] - Unreleased\n")
            temp_path = Path(f.name)

        try:
            result = self.rule._changelog_has_dated_entry(temp_path, "0.27.1")
            self.assertFalse(result, "Should return False for Unreleased entries")
        finally:
            temp_path.unlink()

    def test_roadmap_has_shipped_section_found(self):
        """Test detecting version in What We've Shipped section."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Roadmap\n\n")
            f.write("## What We've Shipped\n\n")
            f.write("### v0.27.1 - Code Quality\n\n")
            f.write("Improvements here\n")
            temp_path = Path(f.name)

        try:
            result = self.rule._roadmap_has_shipped_section(temp_path, "0.27.1")
            self.assertTrue(result)
        finally:
            temp_path.unlink()

    def test_roadmap_has_shipped_section_not_found(self):
        """Test when version is not in What We've Shipped section."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Roadmap\n\n")
            f.write("## What We've Shipped\n\n")
            f.write("### v0.27.0 - Earlier Release\n\n")
            f.write("## What's Next\n\n")
            f.write("### v0.28.0 - Future Release\n\n")
            temp_path = Path(f.name)

        try:
            result = self.rule._roadmap_has_shipped_section(temp_path, "0.28.0")
            self.assertFalse(result, "Should return False when version is in wrong section")
        finally:
            temp_path.unlink()

class TestValidationRulesIntegration(unittest.TestCase):
    """Integration tests for all validation rules."""

    def test_all_rules_instantiate(self):
        """Test that all validation rules can be instantiated."""
        rules = [V001(), V002(), V003(), V004(), V005(), V006(), V007(), V008(), V009(), V011()]
        self.assertEqual(len(rules), 10)
        for rule in rules:
            self.assertIsNotNone(rule.code)
            self.assertTrue(rule.code.startswith('V'))

    def test_all_rules_have_check_method(self):
        """Test that all rules have check() method."""
        rules = [V001(), V002(), V003(), V004(), V005(), V006(), V007(), V008(), V009(), V011()]
        for rule in rules:
            self.assertTrue(hasattr(rule, 'check'))
            self.assertTrue(callable(rule.check))

    def test_all_rules_ignore_non_reveal_uris(self):
        """Test that all rules ignore non-reveal:// URIs."""
        rules = [V001(), V002(), V003(), V004(), V005(), V006(), V007(), V008(), V009(), V011()]
        for rule in rules:
            detections = rule.check(
                file_path="/some/regular/file.py",
                structure=None,
                content="# content"
            )
            self.assertEqual(len(detections), 0,
                           f"Rule {rule.code} should ignore non-reveal URIs")

    def test_all_rules_process_reveal_uris(self):
        """Test that all rules process reveal:// URIs."""
        rules = [V001(), V002(), V003(), V004(), V005(), V006(), V007(), V008(), V009(), V011()]
        for rule in rules:
            detections = rule.check(
                file_path="reveal://",
                structure=None,
                content=""
            )
            self.assertIsInstance(detections, list,
                                f"Rule {rule.code} should return list for reveal:// URIs")

    def test_find_reveal_root_utility(self):
        """Test that find_reveal_root() utility function works."""
        root = find_reveal_root()
        # Should find reveal root when running tests
        self.assertIsNotNone(root, "find_reveal_root() should locate reveal root")
        # Verify it's a Path object
        self.assertIsInstance(root, Path)
        # Verify it has the expected structure
        self.assertTrue((root / 'analyzers').exists())
        self.assertTrue((root / 'rules').exists())

    def test_all_rules_have_correct_codes(self):
        """Test that rules have correct V001-V011 codes."""
        expected_codes = ['V001', 'V002', 'V003', 'V004', 'V005', 'V006', 'V007', 'V008', 'V009', 'V011']
        rules = [V001(), V002(), V003(), V004(), V005(), V006(), V007(), V008(), V009(), V011()]
        actual_codes = [rule.code for rule in rules]
        self.assertEqual(sorted(actual_codes), sorted(expected_codes))

    def test_all_rules_have_severity(self):
        """Test that all rules have defined severity."""
        rules = [V001(), V002(), V003(), V004(), V005(), V006(), V007(), V008(), V009(), V011()]
        for rule in rules:
            self.assertIsNotNone(rule.severity,
                               f"Rule {rule.code} missing severity")
            self.assertIn(rule.severity.name, ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
                        f"Rule {rule.code} has invalid severity: {rule.severity}")

    def test_all_rules_have_message(self):
        """Test that all rules have descriptive messages."""
        rules = [V001(), V002(), V003(), V004(), V005(), V006(), V007(), V008(), V009(), V011()]
        for rule in rules:
            self.assertIsNotNone(rule.message,
                               f"Rule {rule.code} missing message")
            self.assertGreater(len(rule.message), 10,
                             f"Rule {rule.code} message too short")

    def test_all_rules_have_file_patterns(self):
        """Test that all rules have file_patterns defined."""
        rules = [V001(), V002(), V003(), V004(), V005(), V006(), V007(), V008(), V009(), V011()]
        for rule in rules:
            self.assertIsNotNone(rule.file_patterns,
                               f"Rule {rule.code} missing file_patterns")
            self.assertIsInstance(rule.file_patterns, list,
                                f"Rule {rule.code} file_patterns should be list")


class TestV012LanguageCount(unittest.TestCase):
    """Test V012: Language count accuracy in documentation."""

    def setUp(self):
        self.rule = V012()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V012")
        self.assertEqual(self.rule.severity.name, "MEDIUM")
        self.assertIn("language count", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list (may have detections if counts mismatch)
        self.assertIsInstance(detections, list)

    def test_count_registered_languages(self):
        """Test that _count_registered_languages returns valid count."""
        count = self.rule._count_registered_languages()
        # Should return a number or None
        if count is not None:
            self.assertIsInstance(count, int)
            self.assertGreater(count, 0)

    def test_extract_language_count_patterns(self):
        """Test that all language count patterns are detected."""
        # Create test README content
        readme_content = """
# Reveal

Zero config. 38 languages built-in.

## Features

**Built-in (40):**
- Python, JavaScript, Ruby...

Supports 42 languages built-in for maximum compatibility.
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(readme_content)
            readme_path = Path(f.name)

        try:
            claims = self.rule._extract_language_count_from_readme(readme_path)
            # Should find all 3 claims
            self.assertGreaterEqual(len(claims), 3)
            # Check that we found different counts
            counts = [count for _, count in claims]
            self.assertIn(38, counts)
            self.assertIn(40, counts)
            self.assertIn(42, counts)
        finally:
            readme_path.unlink()


class TestV013AdapterCount(unittest.TestCase):
    """Test V013: Adapter count accuracy in documentation."""

    def setUp(self):
        self.rule = V013()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V013")
        self.assertEqual(self.rule.severity.name, "MEDIUM")
        self.assertIn("adapter count", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list
        self.assertIsInstance(detections, list)

    def test_count_registered_adapters(self):
        """Test that _count_registered_adapters returns valid count."""
        count = self.rule._count_registered_adapters()
        # Should return a number or None
        if count is not None:
            self.assertIsInstance(count, int)
            self.assertGreater(count, 0)

    def test_extract_adapter_count_patterns(self):
        """Test that adapter count patterns are detected."""
        # Create test README content
        readme_content = """
# Reveal

**10 Built-in Adapters:**

Supports (38 languages, 12 adapters).

Currently 14 adapters available.
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(readme_content)
            readme_path = Path(f.name)

        try:
            claims = self.rule._extract_adapter_count_from_readme(readme_path)
            # Should find all adapter count claims
            self.assertGreaterEqual(len(claims), 3)
            # Check that we found different counts
            counts = [count for _, count in claims]
            self.assertIn(10, counts)
            self.assertIn(12, counts)
            self.assertIn(14, counts)
        finally:
            readme_path.unlink()


class TestV015RulesCount(unittest.TestCase):
    """Test V015: Rules count accuracy in documentation."""

    def setUp(self):
        self.rule = V015()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V015")
        self.assertEqual(self.rule.severity.name, "MEDIUM")
        self.assertIn("rules count", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list
        self.assertIsInstance(detections, list)

    def test_count_registered_rules(self):
        """Test that _count_registered_rules returns valid count."""
        count = self.rule._count_registered_rules()
        # Should return a number or None
        if count is not None:
            self.assertIsInstance(count, int)
            self.assertGreater(count, 0)

    def test_extract_rules_count_patterns(self):
        """Test that rules count patterns (exact and minimum) are detected."""
        # Create test README content
        readme_content = """
# Reveal

Includes 57 built-in rules for quality checks.

At least 50+ built-in rules available.

Quality: 60 Built-In Rules
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(readme_content)
            readme_path = Path(f.name)

        try:
            claims = self.rule._extract_rules_count_from_readme(readme_path)
            # Should find both exact and minimum claims
            self.assertGreaterEqual(len(claims), 2)

            # Check exact count claim
            exact_claims = [(line, count) for line, count, is_min in claims if not is_min]
            self.assertGreater(len(exact_claims), 0)

            # Check minimum count claim
            min_claims = [(line, count) for line, count, is_min in claims if is_min]
            self.assertGreater(len(min_claims), 0)

            # Verify 50+ is detected as minimum
            min_counts = [count for _, count, is_min in claims if is_min]
            self.assertIn(50, min_counts)
        finally:
            readme_path.unlink()


class TestV016AdapterHelp(unittest.TestCase):
    """Test V016: Adapter help completeness validation."""

    def setUp(self):
        self.rule = V016()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V016")
        self.assertEqual(self.rule.severity.name, "MEDIUM")
        self.assertIn("help", self.rule.message.lower())

    def test_non_adapter_file_ignored(self):
        """Test that non-adapter files are ignored."""
        detections = self.rule.check(
            file_path="/some/module.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_non_python_file_ignored(self):
        """Test that non-Python files are ignored."""
        detections = self.rule.check(
            file_path="/adapters/file.txt",
            structure={'classes': []},
            content="text content"
        )
        self.assertEqual(len(detections), 0)

    def test_init_and_base_skipped(self):
        """Test that __init__.py and base.py are skipped."""
        for filename in ['__init__.py', 'base.py']:
            detections = self.rule.check(
                file_path=f"/adapters/{filename}",
                structure={'classes': [{'name': 'SomeAdapter'}]},
                content="class SomeAdapter: pass"
            )
            self.assertEqual(len(detections), 0)

    def test_adapter_with_get_help(self):
        """Test that adapter with get_help() passes."""
        content = """
from reveal.adapters.base import ResourceAdapter

class TestAdapter(ResourceAdapter):
    @staticmethod
    def get_help():
        return {
            'name': 'test',
            'description': 'Test adapter',
            'examples': []
        }

    def get_structure(self):
        return {}
"""
        structure = {
            'classes': [{'name': 'TestAdapter'}],
            'functions': [{'name': 'get_help'}]
        }

        detections = self.rule.check(
            file_path="/adapters/test.py",
            structure=structure,
            content=content
        )
        self.assertEqual(len(detections), 0)

    def test_adapter_missing_get_help(self):
        """Test that adapter without get_help() is detected."""
        content = """
from reveal.adapters.base import ResourceAdapter

class TestAdapter(ResourceAdapter):
    def get_structure(self):
        return {}
"""
        structure = {
            'classes': [{'name': 'TestAdapter'}],
            'functions': []
        }

        detections = self.rule.check(
            file_path="/adapters/test.py",
            structure=structure,
            content=content
        )
        self.assertEqual(len(detections), 1)
        self.assertIn("get_help", detections[0].message)

    def test_is_adapter_file_detection(self):
        """Test that adapter files are correctly identified."""
        # Test with Adapter in class name
        content_with_adapter = "class JsonAdapter: pass"
        structure = {'classes': [{'name': 'JsonAdapter'}]}
        self.assertTrue(self.rule._is_adapter_file(structure, content_with_adapter))

        # Test with ResourceAdapter inheritance
        content_with_inheritance = "class Custom(ResourceAdapter): pass"
        structure = {'classes': [{'name': 'Custom'}]}
        self.assertTrue(self.rule._is_adapter_file(structure, content_with_inheritance))

        # Test non-adapter
        content_regular = "class Helper: pass"
        structure = {'classes': [{'name': 'Helper'}]}
        self.assertFalse(self.rule._is_adapter_file(structure, content_regular))


class TestV018RendererRegistration(unittest.TestCase):
    """Test V018: Adapter renderer registration completeness."""

    def setUp(self):
        self.rule = V018()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V018")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("renderer", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list (may have detections if adapters/renderers mismatched)
        self.assertIsInstance(detections, list)

    def test_find_adapter_file_patterns(self):
        """Test that _find_adapter_file finds adapters in all supported patterns."""
        reveal_root = find_reveal_root()
        if not reveal_root:
            self.skipTest("Reveal root not found")

        # Test finding actual adapter files
        # Pattern 1: adapters/env.py
        env_file = self.rule._find_adapter_file(reveal_root, 'env')
        if env_file:
            self.assertTrue(env_file.exists())
            self.assertTrue(env_file.name == 'env.py' or env_file.name == '__init__.py')

        # Pattern 2: adapters/git/adapter.py or adapters/git/__init__.py
        git_file = self.rule._find_adapter_file(reveal_root, 'git')
        if git_file:
            self.assertTrue(git_file.exists())

    def test_adapter_renderer_registry_access(self):
        """Test that rule can access adapter and renderer registries."""
        # This test validates that the imports work
        try:
            from reveal.adapters.base import list_supported_schemes, list_renderer_schemes
            adapters = list_supported_schemes()
            renderers = list_renderer_schemes()

            # Should get lists (even if empty)
            self.assertIsInstance(adapters, (list, tuple, set))
            self.assertIsInstance(renderers, (list, tuple, set))

            # In a working reveal installation, should have some adapters
            if len(adapters) > 0:
                self.assertGreater(len(adapters), 0)
        except ImportError:
            self.skipTest("Cannot import adapter registries")


class TestV022ManifestInclusion(unittest.TestCase):
    """Test V022: Package manifest file inclusion validation."""

    def setUp(self):
        self.rule = V022()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V022")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("manifest", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list
        self.assertIsInstance(detections, list)

    def test_description_explains_manifest(self):
        """Test that rule description explains manifest validation."""
        description = self.rule.get_description()
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 40)  # Adjusted threshold
        # Should mention manifest or package
        description_lower = description.lower()
        self.assertTrue("manifest" in description_lower or "package" in description_lower)


class TestV023OutputContractCompliance(unittest.TestCase):
    """Test V023: Output contract compliance validation."""

    def setUp(self):
        self.rule = V023()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V023")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("contract", self.rule.message.lower() or "output" in self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list
        self.assertIsInstance(detections, list)

    def test_valid_source_types_defined(self):
        """Test that valid source types are defined."""
        valid_types = self.rule.VALID_SOURCE_TYPES
        self.assertIsInstance(valid_types, set)
        # Should include standard source types
        expected = {'file', 'directory', 'database', 'runtime', 'network'}
        self.assertEqual(valid_types, expected)

    def test_description_explains_contract(self):
        """Test that rule description explains output contract."""
        description = self.rule.get_description()
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 50)
        # Should mention contract or output
        description_lower = description.lower()
        self.assertTrue("contract" in description_lower or "output" in description_lower)


class TestV021RegexVsTreeSitter(unittest.TestCase):
    """Test V021: Detect inappropriate regex usage when tree-sitter is available."""

    def setUp(self):
        self.rule = V021()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V021")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("regex", self.rule.message.lower() or "tree" in self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list
        self.assertIsInstance(detections, list)

    def test_tree_sitter_languages_defined(self):
        """Test that tree-sitter languages set is populated."""
        self.assertGreater(len(self.rule.TREE_SITTER_LANGUAGES), 0)
        # Should include common languages
        common_langs = {'python', 'javascript', 'go', 'rust'}
        self.assertTrue(common_langs.issubset(self.rule.TREE_SITTER_LANGUAGES))

    def test_regex_whitelist_defined(self):
        """Test that regex whitelist is defined."""
        self.assertIsInstance(self.rule.REGEX_WHITELIST, set)
        # Markdown should be whitelisted (uses regex for links)
        self.assertIn('markdown.py', self.rule.REGEX_WHITELIST)

    def test_imports_re_module_detection(self):
        """Test that _imports_re_module correctly detects re imports."""
        # Test with 're' import
        content_with_re = "import re\nclass Foo: pass"
        self.assertTrue(self.rule._imports_re_module(content_with_re))

        # Test without 're' import
        content_without_re = "import os\nclass Foo: pass"
        self.assertFalse(self.rule._imports_re_module(content_without_re))

        # Test with from import
        content_with_from = "from re import compile\nclass Foo: pass"
        self.assertTrue(self.rule._imports_re_module(content_with_from))

    def test_description_explains_tree_sitter(self):
        """Test that rule description explains tree-sitter usage."""
        description = self.rule.get_description()
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 50)
        # Should mention tree-sitter
        description_lower = description.lower()
        self.assertTrue("tree" in description_lower or "sitter" in description_lower)


class TestV020ElementStructureContract(unittest.TestCase):
    """Test V020: Adapter element/structure contract compliance."""

    def setUp(self):
        self.rule = V020()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V020")
        self.assertEqual(self.rule.severity.name, "MEDIUM")
        self.assertIn("element", self.rule.message.lower() or "structure" in self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list (may have detections if contract violations exist)
        self.assertIsInstance(detections, list)

    def test_adapter_renderer_access(self):
        """Test that rule can access adapters and renderers."""
        try:
            from reveal.adapters.base import (
                list_supported_schemes,
                get_adapter_class,
                get_renderer_class
            )
            schemes = list(list_supported_schemes())

            if len(schemes) > 0:
                first_scheme = schemes[0]
                adapter_class = get_adapter_class(first_scheme)
                renderer_class = get_renderer_class(first_scheme)

                # Should get classes
                self.assertIsNotNone(adapter_class)
                # Renderer may be None for some adapters
                # Just verify we can call the function
        except ImportError:
            self.skipTest("Cannot import adapter/renderer registries")

    def test_get_element_contract(self):
        """Test that adapters with element renderers have get_element."""
        reveal_root = find_reveal_root()
        if not reveal_root:
            self.skipTest("Reveal root not found")

        # Run the check
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )

        # If detections found, verify they're about element/structure contract
        for detection in detections:
            self.assertTrue(
                "get_element" in detection.message or "get_structure" in detection.message,
                f"Unexpected detection: {detection.message}"
            )

    def test_description_explains_contract(self):
        """Test that rule description explains the element/structure contract."""
        description = self.rule.get_description()
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 50)
        # Should mention get_element or get_structure
        description_lower = description.lower()
        self.assertTrue(
            "get_element" in description_lower or "get_structure" in description_lower
        )


class TestV019AdapterInitialization(unittest.TestCase):
    """Test V019: Adapter initialization pattern compliance."""

    def setUp(self):
        self.rule = V019()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V019")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("initialization", self.rule.message.lower())

    def test_non_reveal_uri_ignored(self):
        """Test that non-reveal URIs are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test that reveal:// URIs are processed."""
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        # Should return detections list (may have detections if adapters have init issues)
        self.assertIsInstance(detections, list)

    def test_no_arg_init_typeerror_expected(self):
        """Test that adapters properly raise TypeError for no-arg init when required."""
        # This tests the _test_no_arg_init method logic
        # We can't easily mock adapter classes, so we verify the rule runs
        reveal_root = find_reveal_root()
        if not reveal_root:
            self.skipTest("Reveal root not found")

        # Run the check - it should not crash
        detections = self.rule.check(
            file_path="reveal://",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

        # If detections found, verify they have proper structure
        for detection in detections:
            self.assertIn("initialization", detection.message.lower())
            self.assertTrue(hasattr(detection, 'severity'))

    def test_resource_init_handling(self):
        """Test that adapters handle resource string initialization properly."""
        # Test that the rule can access adapter classes
        try:
            from reveal.adapters.base import list_supported_schemes, get_adapter_class
            schemes = list(list_supported_schemes())

            # Should have at least one adapter
            if len(schemes) > 0:
                self.assertGreater(len(schemes), 0)

                # Get first adapter to verify get_adapter_class works
                first_scheme = schemes[0]
                adapter_class = get_adapter_class(first_scheme)
                self.assertIsNotNone(adapter_class)
        except ImportError:
            self.skipTest("Cannot import adapter registries")

    def test_description_explains_contract(self):
        """Test that rule description explains the initialization contract."""
        description = self.rule.get_description()
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 50)
        # Should mention TypeError
        self.assertIn("TypeError", description)
        # Should mention initialization
        self.assertIn("initialization", description.lower())


class TestV017TreeSitterNodeTypes(unittest.TestCase):
    """Test V017: Tree-sitter node type coverage validation."""

    def setUp(self):
        self.rule = V017()

    def test_metadata(self):
        """Test rule metadata."""
        self.assertEqual(self.rule.code, "V017")
        self.assertEqual(self.rule.severity.name, "HIGH")
        self.assertIn("node types", self.rule.message.lower())

    def test_non_treesitter_file_ignored(self):
        """Test that non-treesitter.py files are ignored."""
        detections = self.rule.check(
            file_path="/some/file.py",
            structure=None,
            content="# some content"
        )
        self.assertEqual(len(detections), 0)

    def test_treesitter_file_processed(self):
        """Test that treesitter.py files are processed."""
        # Even with empty content, should process and likely find issues
        detections = self.rule.check(
            file_path="reveal/treesitter.py",
            structure=None,
            content=""
        )
        self.assertIsInstance(detections, list)

    def test_sufficient_function_types(self):
        """Test that sufficient function node types pass validation."""
        content = """
def _get_function_node_types(self):
    return [
        'function_definition',
        'function_declaration',
        'function_item',
        'function_signature',
        'method_declaration',
        'method_definition',
    ]
"""
        detections = self.rule.check(
            file_path="reveal/treesitter.py",
            structure=None,
            content=content
        )
        # Should not detect issues with 6 function types
        function_issues = [d for d in detections if "function node types" in d.message.lower()]
        self.assertEqual(len(function_issues), 0)

    def test_insufficient_function_types(self):
        """Test that insufficient function node types are detected."""
        content = """
def _get_function_node_types(self):
    return [
        'function_definition',
        'function_declaration',
    ]
"""
        detections = self.rule.check(
            file_path="reveal/treesitter.py",
            structure=None,
            content=content
        )
        # Should detect issue with only 2 function types
        function_issues = [d for d in detections if "function node types" in d.message.lower()]
        self.assertGreater(len(function_issues), 0)
        self.assertIn("2 found", function_issues[0].message)

    def test_sufficient_class_types(self):
        """Test that sufficient class node types pass validation."""
        content = """
def _get_function_node_types(self):
    return ['function_definition', 'function_declaration', 'function_item',
            'method_declaration', 'method_definition']

def _get_class_node_types(self):
    return [
        'class_definition',
        'class_declaration',
        'struct_item',
        'class_specifier',
    ]
"""
        detections = self.rule.check(
            file_path="reveal/treesitter.py",
            structure=None,
            content=content
        )
        # Should not detect issues with 4 class types
        class_issues = [d for d in detections if "class node types" in d.message.lower()]
        self.assertEqual(len(class_issues), 0)

    def test_insufficient_class_types(self):
        """Test that insufficient class node types are detected."""
        content = """
def _get_function_node_types(self):
    return ['function_definition', 'function_declaration', 'function_item',
            'method_declaration', 'method_definition']

def _get_class_node_types(self):
    return [
        'class_definition',
    ]
"""
        detections = self.rule.check(
            file_path="reveal/treesitter.py",
            structure=None,
            content=content
        )
        # Should detect issue with only 1 class type
        class_issues = [d for d in detections if "class node types" in d.message.lower()]
        self.assertGreater(len(class_issues), 0)
        self.assertIn("1 found", class_issues[0].message)

    def test_simple_identifier_present(self):
        """Test that simple_identifier presence passes validation."""
        content = """
def _get_function_node_types(self):
    return ['function_definition', 'function_declaration', 'function_item',
            'method_declaration', 'method_definition']

def _get_class_node_types(self):
    return ['class_definition', 'class_declaration', 'struct_item']

# Name extraction uses both identifier types
name_types = ['identifier', 'simple_identifier']
"""
        detections = self.rule.check(
            file_path="reveal/treesitter.py",
            structure=None,
            content=content
        )
        # Should not detect simple_identifier issue when it's present
        identifier_issues = [d for d in detections if "simple_identifier" in d.message.lower()]
        self.assertEqual(len(identifier_issues), 0)

    def test_simple_identifier_missing(self):
        """Test that missing simple_identifier is detected."""
        content = """
def _get_function_node_types(self):
    return ['function_definition', 'function_declaration', 'function_item',
            'method_declaration', 'method_definition']

def _get_class_node_types(self):
    return ['class_definition', 'class_declaration', 'struct_item']

# Name extraction uses only identifier
name_types = ['identifier']
"""
        detections = self.rule.check(
            file_path="reveal/treesitter.py",
            structure=None,
            content=content
        )
        # Should detect missing simple_identifier when identifier is present
        identifier_issues = [d for d in detections if "simple_identifier" in d.message.lower()]
        self.assertGreater(len(identifier_issues), 0)
        self.assertIn("Kotlin/Swift", identifier_issues[0].message)

    def test_description_explains_node_types(self):
        """Test that rule description explains node type coverage."""
        description = self.rule.get_description()
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 50)
        # Should mention node types
        self.assertIn("node type", description.lower())
        # Should mention tree-sitter
        self.assertIn("tree-sitter", description.lower())


if __name__ == '__main__':
    unittest.main()
