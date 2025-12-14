"""Tests for markdown support fixes - regression prevention.

These tests would have caught the three bugs fixed in 2025-12-11:
- Issue #1: --links showing headings in text output
- Issue #3: Missing --outline hierarchical tree for markdown
- Issue #2: Missing help://markdown topic

See: docs/ROOT_CAUSE_ANALYSIS_MARKDOWN_BUGS.md
"""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.analyzers.markdown import MarkdownAnalyzer
from reveal.display import build_heading_hierarchy


class TestIssue1ConditionalHeadingInclusion(unittest.TestCase):
    """Tests for Issue #1: --links should show ONLY links, not headings.

    Root cause: MarkdownAnalyzer always included headings in structure,
    even when specific features (links/code) were requested.
    """

    def create_temp_markdown(self, content: str) -> str:
        """Helper: Create temp markdown file."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.md")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_links_only_no_headings(self):
        """REGRESSION: extract_links=True should NOT include headings in structure."""
        content = """# Title

[Link](https://example.com)

## Section
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_links=True)

            # Issue #1 bug: headings were incorrectly included
            self.assertNotIn('headings', structure,
                           "When extract_links=True, headings should NOT be in structure")
            self.assertIn('links', structure,
                        "When extract_links=True, links SHOULD be in structure")

        finally:
            self.teardown_file(path)

    def test_code_only_no_headings(self):
        """REGRESSION: extract_code=True should NOT include headings in structure."""
        content = """# Title

```python
def foo():
    pass
```

## Section
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_code=True)

            self.assertNotIn('headings', structure,
                           "When extract_code=True, headings should NOT be in structure")
            self.assertIn('code_blocks', structure,
                        "When extract_code=True, code_blocks SHOULD be in structure")

        finally:
            self.teardown_file(path)

    def test_links_and_code_no_headings(self):
        """REGRESSION: Both extract_links and extract_code should NOT include headings."""
        content = """# Title

[Link](https://example.com)

```python
x = 1
```
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure(extract_links=True, extract_code=True)

            self.assertNotIn('headings', structure,
                           "When both flags set, headings should NOT be in structure")
            self.assertIn('links', structure)
            self.assertIn('code_blocks', structure)

        finally:
            self.teardown_file(path)

    def test_default_includes_headings(self):
        """Default behavior (no flags) should include headings."""
        content = """# Title

Content here.

## Section
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            structure = analyzer.get_structure()

            # Default should include headings
            self.assertIn('headings', structure,
                        "Default behavior should include headings")
            # But not other features
            self.assertNotIn('links', structure)
            self.assertNotIn('code_blocks', structure)

        finally:
            self.teardown_file(path)

    def test_outline_mode_includes_headings(self):
        """Outline mode should force headings even with other flags."""
        content = """# Title

[Link](https://example.com)
"""
        path = self.create_temp_markdown(content)
        try:
            analyzer = MarkdownAnalyzer(path)
            # Outline mode needs headings to build hierarchy
            structure = analyzer.get_structure(extract_links=True, outline=True)

            # With outline=True, headings should be included
            self.assertIn('headings', structure,
                        "Outline mode requires headings for hierarchy building")
            self.assertIn('links', structure)

        finally:
            self.teardown_file(path)


class TestIssue3OutlineHierarchy(unittest.TestCase):
    """Tests for Issue #3: --outline hierarchical tree for markdown.

    Root cause: Outline feature only worked for code (line-range hierarchy),
    not for markdown (level-based hierarchy).
    """

    def test_build_heading_hierarchy_simple(self):
        """Test basic heading hierarchy building (H1 -> H2)."""
        headings = [
            {'level': 1, 'line': 1, 'name': 'Title'},
            {'level': 2, 'line': 5, 'name': 'Section One'},
            {'level': 2, 'line': 10, 'name': 'Section Two'},
        ]

        hierarchy = build_heading_hierarchy(headings)

        # Should have 1 root (Title)
        self.assertEqual(len(hierarchy), 1)
        self.assertEqual(hierarchy[0]['name'], 'Title')

        # Title should have 2 children
        self.assertEqual(len(hierarchy[0]['children']), 2)
        self.assertEqual(hierarchy[0]['children'][0]['name'], 'Section One')
        self.assertEqual(hierarchy[0]['children'][1]['name'], 'Section Two')

    def test_build_heading_hierarchy_deep_nesting(self):
        """Test deep nesting (H1 -> H2 -> H3)."""
        headings = [
            {'level': 1, 'line': 1, 'name': 'A'},
            {'level': 2, 'line': 2, 'name': 'A1'},
            {'level': 3, 'line': 3, 'name': 'A1a'},
            {'level': 3, 'line': 4, 'name': 'A1b'},
            {'level': 2, 'line': 5, 'name': 'A2'},
        ]

        hierarchy = build_heading_hierarchy(headings)

        # Root: A
        self.assertEqual(len(hierarchy), 1)
        self.assertEqual(hierarchy[0]['name'], 'A')

        # A's children: A1, A2
        self.assertEqual(len(hierarchy[0]['children']), 2)
        a1 = hierarchy[0]['children'][0]
        a2 = hierarchy[0]['children'][1]
        self.assertEqual(a1['name'], 'A1')
        self.assertEqual(a2['name'], 'A2')

        # A1's children: A1a, A1b
        self.assertEqual(len(a1['children']), 2)
        self.assertEqual(a1['children'][0]['name'], 'A1a')
        self.assertEqual(a1['children'][1]['name'], 'A1b')

        # A2 has no children
        self.assertEqual(len(a2['children']), 0)

    def test_build_heading_hierarchy_skip_levels(self):
        """Test skipping heading levels (H1 -> H3, no H2)."""
        headings = [
            {'level': 1, 'line': 1, 'name': 'Title'},
            {'level': 3, 'line': 2, 'name': 'Subsection'},  # Skipped H2
        ]

        hierarchy = build_heading_hierarchy(headings)

        # Should treat H3 as child of H1 despite level skip
        self.assertEqual(len(hierarchy), 1)
        self.assertEqual(hierarchy[0]['name'], 'Title')
        self.assertEqual(len(hierarchy[0]['children']), 1)
        self.assertEqual(hierarchy[0]['children'][0]['name'], 'Subsection')

    def test_build_heading_hierarchy_flat(self):
        """Test flat structure (all same level)."""
        headings = [
            {'level': 1, 'line': 1, 'name': 'A'},
            {'level': 1, 'line': 2, 'name': 'B'},
            {'level': 1, 'line': 3, 'name': 'C'},
        ]

        hierarchy = build_heading_hierarchy(headings)

        # All should be roots
        self.assertEqual(len(hierarchy), 3)
        self.assertEqual(hierarchy[0]['name'], 'A')
        self.assertEqual(hierarchy[1]['name'], 'B')
        self.assertEqual(hierarchy[2]['name'], 'C')

        # No children
        for item in hierarchy:
            self.assertEqual(len(item['children']), 0)

    def test_build_heading_hierarchy_empty(self):
        """Test with empty heading list."""
        hierarchy = build_heading_hierarchy([])
        self.assertEqual(hierarchy, [])

    def test_build_heading_hierarchy_multiple_roots(self):
        """Test multiple H1 headings (multiple roots)."""
        headings = [
            {'level': 1, 'line': 1, 'name': 'A'},
            {'level': 2, 'line': 2, 'name': 'A1'},
            {'level': 1, 'line': 3, 'name': 'B'},
            {'level': 2, 'line': 4, 'name': 'B1'},
        ]

        hierarchy = build_heading_hierarchy(headings)

        # Two roots: A and B
        self.assertEqual(len(hierarchy), 2)
        self.assertEqual(hierarchy[0]['name'], 'A')
        self.assertEqual(hierarchy[1]['name'], 'B')

        # Each has one child
        self.assertEqual(len(hierarchy[0]['children']), 1)
        self.assertEqual(hierarchy[0]['children'][0]['name'], 'A1')
        self.assertEqual(len(hierarchy[1]['children']), 1)
        self.assertEqual(hierarchy[1]['children'][0]['name'], 'B1')

    def test_build_heading_hierarchy_preserves_metadata(self):
        """Test that hierarchy building preserves original metadata."""
        headings = [
            {'level': 1, 'line': 1, 'name': 'Title', 'custom_field': 'value'},
            {'level': 2, 'line': 5, 'name': 'Section'},
        ]

        hierarchy = build_heading_hierarchy(headings)

        # Original fields should be preserved
        self.assertEqual(hierarchy[0]['line'], 1)
        self.assertEqual(hierarchy[0]['level'], 1)
        self.assertEqual(hierarchy[0]['custom_field'], 'value')


class TestIssue2HelpSystemIntegration(unittest.TestCase):
    """Tests for Issue #2: Missing help://markdown topic.

    Root cause: Markdown analyzer added without updating help system.
    No automated validation that all file types have help topics.
    """

    def test_help_system_has_markdown_topic(self):
        """REGRESSION: Help system should include markdown topic."""
        from reveal.adapters.help import HelpAdapter

        adapter = HelpAdapter('')
        topics = adapter._list_topics()

        self.assertIn('markdown', topics,
                     "help:// system should include 'markdown' topic")

    def test_markdown_guide_file_exists(self):
        """REGRESSION: MARKDOWN_GUIDE.md file should exist."""
        from reveal.adapters.help import HelpAdapter

        # Check that markdown is registered
        self.assertIn('markdown', HelpAdapter.STATIC_HELP,
                     "Markdown should be in STATIC_HELP dict")

        # Check that the file exists
        guide_path = HelpAdapter.STATIC_HELP['markdown']
        adapter_dir = Path(__file__).parent.parent / 'reveal'
        full_path = adapter_dir / guide_path

        self.assertTrue(full_path.exists(),
                       f"Markdown guide should exist at {full_path}")

    def test_markdown_guide_has_content(self):
        """REGRESSION: Markdown guide should have meaningful content."""
        from reveal.adapters.help import HelpAdapter

        adapter = HelpAdapter('markdown')
        result = adapter.get_element('markdown')

        # Should return a dict or string
        self.assertIsNotNone(result)

        # Convert to string if dict (get_element may return dict or string)
        if isinstance(result, dict):
            content = str(result)
        else:
            content = result

        content_lower = content.lower()
        self.assertIn('markdown', content_lower,
                     "Guide should mention markdown")
        self.assertIn('link', content_lower,
                     "Guide should cover links")
        self.assertIn('code', content_lower,
                     "Guide should cover code blocks")

        # Should be substantial (more than minimal)
        self.assertGreater(len(content), 1000,
                          "Guide should be comprehensive (>1000 chars)")


class TestFeatureMatrixCoverage(unittest.TestCase):
    """Tests for feature × file type combinations.

    Root cause: No systematic testing of feature combinations across
    different file types.
    """

    def test_markdown_supports_all_common_flags(self):
        """Markdown should support common CLI flags."""
        content = """# Title

[Link](https://example.com)

```python
x = 1
```
"""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.md")
        with open(path, 'w') as f:
            f.write(content)

        try:
            analyzer = MarkdownAnalyzer(path)

            # Should support all these without error
            structure1 = analyzer.get_structure()
            structure2 = analyzer.get_structure(head=2)
            structure3 = analyzer.get_structure(tail=2)
            structure4 = analyzer.get_structure(extract_links=True)
            structure5 = analyzer.get_structure(extract_code=True)
            structure6 = analyzer.get_structure(range=(1, 2))
            structure7 = analyzer.get_structure(outline=True)  # NEW: outline flag

            # All should return valid structures
            for struct in [structure1, structure2, structure3, structure4,
                          structure5, structure6, structure7]:
                self.assertIsInstance(struct, dict)

        finally:
            os.unlink(path)
            os.rmdir(temp_dir)


class TestOutputFormatRegression(unittest.TestCase):
    """Tests for output rendering layer (main.py).

    Root cause: Tests only verified data extraction (analyzer layer),
    not output rendering (presentation layer).
    """

    def test_structure_categories_match_request(self):
        """Structure should only contain requested categories."""
        content = """# Title

[Link](https://example.com)

```python
x = 1
```
"""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.md")
        with open(path, 'w') as f:
            f.write(content)

        try:
            analyzer = MarkdownAnalyzer(path)

            # Default: only headings
            struct1 = analyzer.get_structure()
            self.assertEqual(set(struct1.keys()), {'headings'})

            # Links only
            struct2 = analyzer.get_structure(extract_links=True)
            self.assertEqual(set(struct2.keys()), {'links'})

            # Code only
            struct3 = analyzer.get_structure(extract_code=True)
            self.assertEqual(set(struct3.keys()), {'code_blocks'})

            # Links + Code (no headings)
            struct4 = analyzer.get_structure(extract_links=True, extract_code=True)
            self.assertEqual(set(struct4.keys()), {'links', 'code_blocks'})

            # Outline mode: headings required
            struct5 = analyzer.get_structure(extract_links=True, outline=True)
            self.assertIn('headings', struct5)
            self.assertIn('links', struct5)

        finally:
            os.unlink(path)
            os.rmdir(temp_dir)


if __name__ == '__main__':
    unittest.main()
