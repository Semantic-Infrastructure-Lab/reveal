"""Tests for CLI languages listing and information commands."""

import unittest

from reveal.cli.languages import (
    list_supported_languages,
    get_language_info,
    _get_fallback_languages,
    _get_analyzer_features,
)


class TestListSupportedLanguages(unittest.TestCase):
    """Tests for list_supported_languages function."""

    def test_basic_structure(self):
        """Test that the list has the expected structure."""
        result = list_supported_languages()

        # Should have main sections
        self.assertIn("Supported Languages", result)
        self.assertIn("✅ Explicit Analyzers", result)
        self.assertIn("🔄 Tree-sitter Fallback", result)
        self.assertIn("Total:", result)

    def test_includes_python(self):
        """Test that Python is in the explicit analyzers."""
        result = list_supported_languages()

        self.assertIn("Python", result)
        self.assertIn(".py", result)

    def test_includes_javascript(self):
        """Test that JavaScript is included."""
        result = list_supported_languages()

        self.assertIn("JavaScript", result)
        self.assertIn(".js", result)

    def test_shows_usage_hints(self):
        """Test that usage hints are included."""
        result = list_supported_languages()

        self.assertIn("💡 Usage:", result)
        self.assertIn("reveal file.ext", result)

    def test_shows_total_count(self):
        """Test that total language count is shown."""
        result = list_supported_languages()

        self.assertIn("Total:", result)
        self.assertIn("languages supported", result)

    def test_explicit_section_format(self):
        """Test that explicit analyzers section is properly formatted."""
        result = list_supported_languages()

        # Should have section header
        self.assertIn("Explicit Analyzers", result)
        # Should describe what explicit means
        self.assertIn("Full analysis", result)

    def test_fallback_section_format(self):
        """Test that fallback section is properly formatted."""
        result = list_supported_languages()

        # Should have fallback header
        self.assertIn("Tree-sitter Fallback", result)
        # Should describe what fallback means
        self.assertIn("Basic analysis", result)

    def test_separator_lines(self):
        """Test that separator lines are present."""
        result = list_supported_languages()

        # Should have separator lines (=== and ---)
        self.assertIn("=" * 70, result)
        self.assertIn("-" * 70, result)


class TestGetFallbackLanguages(unittest.TestCase):
    """Tests for _get_fallback_languages helper function."""

    def test_returns_list_of_tuples(self):
        """Test that fallback languages returns list of tuples."""
        result = _get_fallback_languages()

        self.assertIsInstance(result, list)
        if result:  # If there are fallback languages
            self.assertIsInstance(result[0], tuple)
            self.assertEqual(len(result[0]), 2)  # (name, extensions)

    def test_each_entry_has_extensions(self):
        """Test that each entry has extensions list."""
        result = _get_fallback_languages()

        for entry in result:
            lang_name, extensions = entry
            self.assertIsInstance(lang_name, str)
            self.assertIsInstance(extensions, list)
            if extensions:
                self.assertIsInstance(extensions[0], str)


class TestGetLanguageInfo(unittest.TestCase):
    """Tests for get_language_info function."""

    def test_get_python_info(self):
        """Test getting info for Python."""
        result = get_language_info("python")

        # Should not have error
        self.assertNotIn("error", result)
        # Should have expected fields
        self.assertIn("name", result)
        self.assertIn("extension", result)
        self.assertIn("analyzer", result)
        self.assertIn("is_fallback", result)
        self.assertIn("features", result)

    def test_python_info_content(self):
        """Test Python info has correct content."""
        result = get_language_info("python")

        self.assertEqual(result["name"], "python")
        self.assertIn(".py", result["extension"])
        self.assertIn("Analyzer", result["analyzer"])
        self.assertIsInstance(result["is_fallback"], bool)
        self.assertIsInstance(result["features"], list)

    def test_case_insensitive(self):
        """Test that language lookup is case-insensitive."""
        result1 = get_language_info("Python")
        result2 = get_language_info("python")
        result3 = get_language_info("PYTHON")

        # All should find Python
        self.assertNotIn("error", result1)
        self.assertNotIn("error", result2)
        self.assertNotIn("error", result3)

        # All should return same info
        self.assertEqual(result1["name"], result2["name"])
        self.assertEqual(result2["name"], result3["name"])

    def test_nonexistent_language(self):
        """Test getting info for non-existent language."""
        result = get_language_info("nonexistent_lang_12345")

        self.assertIn("error", result)
        self.assertIn("not found", result["error"].lower())

    def test_get_javascript_info(self):
        """Test getting info for JavaScript."""
        result = get_language_info("javascript")

        # Should not have error
        self.assertNotIn("error", result)
        self.assertEqual(result["name"], "javascript")

    def test_features_is_list(self):
        """Test that features field is a list."""
        result = get_language_info("python")

        if "features" in result:
            self.assertIsInstance(result["features"], list)


class TestGetAnalyzerFeatures(unittest.TestCase):
    """Tests for _get_analyzer_features helper function."""

    def test_python_analyzer_features(self):
        """Test getting features for Python analyzer."""
        from reveal.registry import get_analyzer

        analyzer_cls = get_analyzer("test.py")
        if analyzer_cls:
            features = _get_analyzer_features(analyzer_cls)

            self.assertIsInstance(features, list)
            # Python should have some features
            self.assertGreater(len(features), 0)

    def test_features_are_strings(self):
        """Test that all features are strings."""
        from reveal.registry import get_analyzer

        analyzer_cls = get_analyzer("test.py")
        if analyzer_cls:
            features = _get_analyzer_features(analyzer_cls)

            for feature in features:
                self.assertIsInstance(feature, str)

    def test_javascript_analyzer_features(self):
        """Test getting features for JavaScript analyzer."""
        from reveal.registry import get_analyzer

        analyzer_cls = get_analyzer("test.js")
        if analyzer_cls:
            features = _get_analyzer_features(analyzer_cls)

            self.assertIsInstance(features, list)

    def test_features_common_items(self):
        """Test that features include common analysis capabilities."""
        from reveal.registry import get_analyzer

        analyzer_cls = get_analyzer("test.py")
        if analyzer_cls:
            features = _get_analyzer_features(analyzer_cls)

            # Features should mention capabilities
            features_str = " ".join(features).lower()
            # At least one of these should be present
            has_capability = any(
                term in features_str
                for term in ["function", "class", "import", "structure", "type"]
            )
            self.assertTrue(has_capability, f"No expected capabilities in: {features}")


if __name__ == '__main__':
    unittest.main()
