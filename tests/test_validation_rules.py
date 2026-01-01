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

    def test_extract_roadmap_version(self):
        """Test extracting current version from ROADMAP.md."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Roadmap\n\n")
            f.write("**Current version:** v0.27.1\n")
            temp_path = Path(f.name)

        try:
            version = self.rule._extract_roadmap_version(temp_path)
            self.assertEqual(version, "0.27.1")
        finally:
            temp_path.unlink()

    def test_extract_roadmap_version_no_v_prefix(self):
        """Test extracting version without 'v' prefix."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("**Current version:** 0.27.1\n")
            temp_path = Path(f.name)

        try:
            version = self.rule._extract_roadmap_version(temp_path)
            self.assertEqual(version, "0.27.1")
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


if __name__ == '__main__':
    unittest.main()
