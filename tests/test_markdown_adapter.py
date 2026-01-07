"""Tests for markdown:// URI adapter."""

import unittest
import tempfile
import shutil
from pathlib import Path

from reveal.adapters.markdown import MarkdownQueryAdapter
from reveal.adapters.base import get_adapter_class, list_supported_schemes


class TestMarkdownAdapterRegistry(unittest.TestCase):
    """Test markdown adapter registration."""

    def test_adapter_registered(self):
        """Markdown adapter should be registered."""
        schemes = list_supported_schemes()
        self.assertIn('markdown', schemes)

    def test_get_adapter_class(self):
        """Should retrieve MarkdownQueryAdapter by scheme."""
        adapter_class = get_adapter_class('markdown')
        self.assertEqual(adapter_class, MarkdownQueryAdapter)


class TestMarkdownQueryAdapter(unittest.TestCase):
    """Test markdown query adapter functionality."""

    def setUp(self):
        """Create temporary directory with test markdown files."""
        self.temp_dir = tempfile.mkdtemp()

        # Create test files with various frontmatter
        self.create_file('doc1.md', '''---
title: First Document
type: guide
status: active
tags:
  - python
  - testing
beth_topics:
  - reveal
  - testing
---

# First Document

Content here.
''')

        self.create_file('doc2.md', '''---
title: Second Document
type: reference
status: draft
tags:
  - javascript
---

# Second Document

More content.
''')

        self.create_file('doc3.md', '''---
title: Third Document
type: tutorial
---

# Third Document

Tutorial content.
''')

        # File without frontmatter
        self.create_file('no_fm.md', '''# No Frontmatter

Just plain markdown.
''')

        # Nested directory
        nested_dir = Path(self.temp_dir) / 'nested'
        nested_dir.mkdir()
        self.create_file('nested/deep.md', '''---
title: Deep Document
type: guide
beth_topics:
  - reveal
---

# Deep Doc
''')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def create_file(self, name: str, content: str):
        """Create a file in the temp directory."""
        path = Path(self.temp_dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_list_all_files(self):
        """Should list all markdown files without filters."""
        adapter = MarkdownQueryAdapter(base_path=self.temp_dir)
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'markdown_query')
        self.assertEqual(result['total_files'], 5)
        self.assertEqual(result['matched_files'], 5)  # No filter = match all

    def test_filter_by_exact_value(self):
        """Should filter by exact field value."""
        adapter = MarkdownQueryAdapter(base_path=self.temp_dir, query='type=guide')
        result = adapter.get_structure()

        self.assertEqual(result['matched_files'], 2)  # doc1.md and nested/deep.md
        paths = [r['relative_path'] for r in result['results']]
        self.assertTrue(any('doc1.md' in p for p in paths))
        self.assertTrue(any('deep.md' in p for p in paths))

    def test_filter_by_list_value(self):
        """Should filter by value in list field."""
        adapter = MarkdownQueryAdapter(base_path=self.temp_dir, query='tags=python')
        result = adapter.get_structure()

        self.assertEqual(result['matched_files'], 1)
        self.assertTrue('doc1.md' in result['results'][0]['relative_path'])

    def test_filter_missing_field(self):
        """Should find files missing a field."""
        adapter = MarkdownQueryAdapter(base_path=self.temp_dir, query='!status')
        result = adapter.get_structure()

        # doc3.md, no_fm.md, nested/deep.md don't have status
        self.assertEqual(result['matched_files'], 3)

    def test_filter_wildcard(self):
        """Should filter with wildcard pattern."""
        adapter = MarkdownQueryAdapter(base_path=self.temp_dir, query='type=*guide*')
        result = adapter.get_structure()

        self.assertEqual(result['matched_files'], 2)  # 'guide' matches

    def test_multiple_filters(self):
        """Should apply multiple filters with AND logic."""
        adapter = MarkdownQueryAdapter(
            base_path=self.temp_dir,
            query='type=guide&beth_topics=reveal'
        )
        result = adapter.get_structure()

        # Both doc1.md and nested/deep.md match
        self.assertEqual(result['matched_files'], 2)

    def test_no_matches(self):
        """Should return empty results when nothing matches."""
        adapter = MarkdownQueryAdapter(
            base_path=self.temp_dir,
            query='type=nonexistent'
        )
        result = adapter.get_structure()

        self.assertEqual(result['matched_files'], 0)
        self.assertEqual(result['results'], [])

    def test_get_element(self):
        """Should get frontmatter for specific file."""
        adapter = MarkdownQueryAdapter(base_path=self.temp_dir)
        result = adapter.get_element('doc1.md')

        self.assertIsNotNone(result)
        self.assertTrue(result['has_frontmatter'])
        self.assertEqual(result['frontmatter']['title'], 'First Document')
        self.assertEqual(result['frontmatter']['type'], 'guide')

    def test_get_element_no_frontmatter(self):
        """Should handle file without frontmatter."""
        adapter = MarkdownQueryAdapter(base_path=self.temp_dir)
        result = adapter.get_element('no_fm.md')

        self.assertIsNotNone(result)
        self.assertFalse(result['has_frontmatter'])
        self.assertIsNone(result['frontmatter'])

    def test_get_element_not_found(self):
        """Should return None for missing file."""
        adapter = MarkdownQueryAdapter(base_path=self.temp_dir)
        result = adapter.get_element('nonexistent.md')

        self.assertIsNone(result)

    def test_get_help(self):
        """Should provide help documentation."""
        help_data = MarkdownQueryAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertEqual(help_data['name'], 'markdown')
        self.assertIn('description', help_data)
        self.assertIn('examples', help_data)
        self.assertIn('syntax', help_data)
        self.assertIn('filters', help_data)

    def test_get_metadata(self):
        """Should return metadata about query scope."""
        adapter = MarkdownQueryAdapter(base_path=self.temp_dir)
        meta = adapter.get_metadata()

        self.assertEqual(meta['type'], 'markdown_query')
        self.assertEqual(meta['total_files'], 5)
        self.assertEqual(meta['with_frontmatter'], 4)  # All except no_fm.md
        self.assertEqual(meta['without_frontmatter'], 1)


class TestQueryParsing(unittest.TestCase):
    """Test query string parsing."""

    def test_parse_exact_match(self):
        """Should parse exact match filter."""
        adapter = MarkdownQueryAdapter(base_path='.', query='field=value')
        self.assertEqual(adapter.filters, [('field', '=', 'value')])

    def test_parse_missing_field(self):
        """Should parse missing field filter."""
        adapter = MarkdownQueryAdapter(base_path='.', query='!field')
        self.assertEqual(adapter.filters, [('field', '!', '')])

    def test_parse_wildcard(self):
        """Should parse wildcard filter."""
        adapter = MarkdownQueryAdapter(base_path='.', query='field=*pattern*')
        self.assertEqual(adapter.filters, [('field', '*', '*pattern*')])

    def test_parse_multiple(self):
        """Should parse multiple filters."""
        adapter = MarkdownQueryAdapter(base_path='.', query='a=1&b=2&!c')
        self.assertEqual(len(adapter.filters), 3)
        self.assertEqual(adapter.filters[0], ('a', '=', '1'))
        self.assertEqual(adapter.filters[1], ('b', '=', '2'))
        self.assertEqual(adapter.filters[2], ('c', '!', ''))

    def test_parse_empty(self):
        """Should handle empty query."""
        adapter = MarkdownQueryAdapter(base_path='.', query='')
        self.assertEqual(adapter.filters, [])

    def test_parse_none(self):
        """Should handle None query."""
        adapter = MarkdownQueryAdapter(base_path='.', query=None)
        self.assertEqual(adapter.filters, [])


if __name__ == '__main__':
    unittest.main()
