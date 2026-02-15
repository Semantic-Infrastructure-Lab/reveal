"""Tests for reveal.display.formatting module."""

import pytest
from pathlib import Path
from unittest.mock import Mock
from reveal.display.formatting import (
    set_nested,
    _find_list_field,
    _extract_nested_value,
    _filter_single_item_fields,
    _preserve_metadata,
    _filter_list_items,
    _filter_toplevel_structure,
    filter_fields,
)


# ============================================================================
# Test utility functions (lines 28-32, 46-49, 62-71, 86-95, 107-109)
# ============================================================================

class TestSetNested:
    """Test set_nested utility function."""

    def test_single_level(self):
        """Test setting single-level key."""
        d = {}
        set_nested(d, ['key'], 'value')
        assert d == {'key': 'value'}

    def test_nested_keys(self):
        """Test setting nested keys."""
        d = {}
        set_nested(d, ['a', 'b', 'c'], 42)
        assert d == {'a': {'b': {'c': 42}}}

    def test_existing_keys(self):
        """Test setting value when some keys exist."""
        d = {'a': {'existing': 'value'}}
        set_nested(d, ['a', 'b'], 'new')
        assert d == {'a': {'existing': 'value', 'b': 'new'}}


class TestFindListField:
    """Test _find_list_field utility function."""

    def test_finds_results(self):
        """Test finding 'results' field."""
        structure = {'results': [1, 2, 3]}
        assert _find_list_field(structure) == 'results'

    def test_finds_items(self):
        """Test finding 'items' field."""
        structure = {'items': [1, 2, 3]}
        assert _find_list_field(structure) == 'items'

    def test_returns_none_when_not_list(self):
        """Test returns None when field is not a list."""
        structure = {'results': 'not_a_list'}
        assert _find_list_field(structure) is None

    def test_returns_none_when_no_list_field(self):
        """Test returns None when no list field exists."""
        structure = {'other': [1, 2, 3]}
        assert _find_list_field(structure) is None


class TestExtractNestedValue:
    """Test _extract_nested_value utility function."""

    def test_flat_field(self):
        """Test extracting flat field."""
        obj = {'name': 'test'}
        assert _extract_nested_value(obj, 'name') == 'test'

    def test_nested_field(self):
        """Test extracting nested field."""
        obj = {'certificate': {'expiry': '2025-01-01'}}
        assert _extract_nested_value(obj, 'certificate.expiry') == '2025-01-01'

    def test_deep_nesting(self):
        """Test extracting deeply nested field."""
        obj = {'a': {'b': {'c': {'d': 'value'}}}}
        assert _extract_nested_value(obj, 'a.b.c.d') == 'value'

    def test_returns_none_for_missing_field(self):
        """Test returns None when field doesn't exist."""
        obj = {'name': 'test'}
        assert _extract_nested_value(obj, 'missing') is None

    def test_returns_none_for_non_dict_intermediate(self):
        """Test returns None when intermediate value is not dict."""
        obj = {'name': 'test'}
        assert _extract_nested_value(obj, 'name.nested') is None


class TestFilterSingleItemFields:
    """Test _filter_single_item_fields utility function."""

    def test_flat_fields(self):
        """Test filtering flat fields."""
        item = {'name': 'test', 'value': 42, 'extra': 'ignore'}
        result = _filter_single_item_fields(item, ['name', 'value'])
        assert result == {'name': 'test', 'value': 42}

    def test_nested_fields(self):
        """Test filtering nested fields."""
        item = {'certificate': {'expiry': '2025-01-01', 'issuer': 'CA'}}
        result = _filter_single_item_fields(item, ['certificate.expiry'])
        assert result == {'certificate': {'expiry': '2025-01-01'}}

    def test_mixed_flat_and_nested(self):
        """Test filtering mix of flat and nested fields."""
        item = {
            'name': 'test',
            'certificate': {'expiry': '2025-01-01', 'issuer': 'CA'},
            'extra': 'ignore'
        }
        result = _filter_single_item_fields(item, ['name', 'certificate.expiry'])
        assert result == {'name': 'test', 'certificate': {'expiry': '2025-01-01'}}

    def test_missing_fields_skipped(self):
        """Test missing fields are skipped."""
        item = {'name': 'test'}
        result = _filter_single_item_fields(item, ['name', 'missing', 'also.missing'])
        assert result == {'name': 'test'}


class TestPreserveMetadata:
    """Test _preserve_metadata utility function."""

    def test_preserves_contract_version(self):
        """Test preserves contract_version field."""
        result = {}
        structure = {'contract_version': '1.0'}
        _preserve_metadata(result, structure)
        assert result == {'contract_version': '1.0'}

    def test_preserves_type(self):
        """Test preserves type field."""
        result = {}
        structure = {'type': 'document'}
        _preserve_metadata(result, structure)
        assert result == {'type': 'document'}

    def test_preserves_multiple_metadata(self):
        """Test preserves multiple metadata fields."""
        result = {}
        structure = {
            'contract_version': '1.0',
            'type': 'document',
            'meta': {'key': 'value'}
        }
        _preserve_metadata(result, structure)
        assert result == {
            'contract_version': '1.0',
            'type': 'document',
            'meta': {'key': 'value'}
        }

    def test_skips_missing_metadata(self):
        """Test skips missing metadata fields."""
        result = {}
        structure = {'data': 'value'}
        _preserve_metadata(result, structure)
        assert result == {}


# ============================================================================
# Test filter_fields function (lines 159-186)
# ============================================================================

class TestFilterFields:
    """Test filter_fields main function."""

    def test_filter_list_items(self):
        """Test filtering items in a list field."""
        structure = {
            'contract_version': '1.0',
            'results': [
                {'name': 'item1', 'value': 1, 'extra': 'ignore'},
                {'name': 'item2', 'value': 2, 'extra': 'ignore'},
            ]
        }
        result = filter_fields(structure, ['name', 'value'])

        assert result['contract_version'] == '1.0'
        assert len(result['results']) == 2
        assert result['results'][0] == {'name': 'item1', 'value': 1}
        assert result['results'][1] == {'name': 'item2', 'value': 2}

    def test_filter_toplevel_structure(self):
        """Test filtering when no list field present."""
        structure = {
            'contract_version': '1.0',
            'name': 'test',
            'value': 42,
            'extra': 'ignore'
        }
        result = filter_fields(structure, ['name', 'value'])

        # Toplevel filtering doesn't preserve metadata
        assert result['name'] == 'test'
        assert result['value'] == 42
        assert 'extra' not in result
        assert 'contract_version' not in result

    def test_preserves_metadata_in_list_case(self):
        """Test metadata is preserved when filtering list items."""
        # List case - metadata IS preserved
        structure1 = {
            'type': 'list',
            'items': [{'field': 'value'}]
        }
        result1 = filter_fields(structure1, ['field'])
        assert result1['type'] == 'list'

        # Toplevel case - metadata is NOT preserved
        structure2 = {
            'type': 'toplevel',
            'field': 'value'
        }
        result2 = filter_fields(structure2, ['field'])
        assert result2 == {'field': 'value'}


class TestFormatFrontmatter:
    """Tests for _format_frontmatter function."""

    def test_none_frontmatter(self, capsys):
        """Test formatting when frontmatter is None."""
        from reveal.display.formatting import _format_frontmatter
        _format_frontmatter(None)
        captured = capsys.readouterr()
        assert "(No front matter found)" in captured.out

    def test_empty_frontmatter(self, capsys):
        """Test formatting when frontmatter data is empty."""
        from reveal.display.formatting import _format_frontmatter
        fm = {'line_start': 1, 'line_end': 3, 'data': {}}
        _format_frontmatter(fm)
        captured = capsys.readouterr()
        assert "(Empty front matter)" in captured.out

    def test_simple_frontmatter(self, capsys):
        """Test formatting simple frontmatter with scalar values."""
        from reveal.display.formatting import _format_frontmatter
        fm = {
            'line_start': 1,
            'line_end': 5,
            'data': {'title': 'Test Doc', 'author': 'Alice'}
        }
        _format_frontmatter(fm)
        captured = capsys.readouterr()
        assert "Lines 1-5:" in captured.out
        assert "title: Test Doc" in captured.out
        assert "author: Alice" in captured.out

    def test_frontmatter_with_list(self, capsys):
        """Test formatting frontmatter with list values."""
        from reveal.display.formatting import _format_frontmatter
        fm = {
            'line_start': 1,
            'line_end': 8,
            'data': {'tags': ['python', 'testing', 'ci']}
        }
        _format_frontmatter(fm)
        captured = capsys.readouterr()
        assert "tags:" in captured.out
        assert "- python" in captured.out
        assert "- testing" in captured.out
        assert "- ci" in captured.out

    def test_frontmatter_with_dict(self, capsys):
        """Test formatting frontmatter with nested dict values."""
        from reveal.display.formatting import _format_frontmatter
        fm = {
            'line_start': 1,
            'line_end': 6,
            'data': {'metadata': {'version': '1.0', 'status': 'draft'}}
        }
        _format_frontmatter(fm)
        captured = capsys.readouterr()
        assert "metadata:" in captured.out
        assert "version: 1.0" in captured.out
        assert "status: draft" in captured.out


class TestFormatLinks:
    """Tests for link formatting functions."""

    def test_format_single_link_normal(self, capsys):
        """Test formatting a normal link."""
        from reveal.display.formatting import _format_single_link
        from pathlib import Path

        item = {'line': 42, 'text': 'Example', 'url': 'https://example.com', 'broken': False}
        _format_single_link(item, 'external', Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "Line 42" in captured.out
        assert "[Example](https://example.com)" in captured.out

    def test_format_single_link_broken(self, capsys):
        """Test formatting a broken link."""
        from reveal.display.formatting import _format_single_link
        from pathlib import Path

        item = {'line': 10, 'text': 'Broken', 'url': 'https://404.com', 'broken': True}
        _format_single_link(item, 'external', Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "Line 10" in captured.out
        assert "[BROKEN]" in captured.out

    def test_format_single_link_with_domain(self, capsys):
        """Test formatting external link with domain display."""
        from reveal.display.formatting import _format_single_link
        from pathlib import Path

        item = {
            'line': 5,
            'text': 'Link',
            'url': 'https://example.com/page',
            'broken': False,
            'domain': 'example.com'
        }
        _format_single_link(item, 'external', Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "-> example.com" in captured.out

    def test_format_single_link_grep_format(self, capsys):
        """Test formatting link in grep format."""
        from reveal.display.formatting import _format_single_link
        from pathlib import Path

        item = {'line': 42, 'text': 'Example', 'url': 'https://example.com'}
        _format_single_link(item, 'external', Path('test.md'), 'grep')
        captured = capsys.readouterr()
        assert "test.md:42:https://example.com" in captured.out

    def test_format_links_grouped_by_type(self, capsys):
        """Test formatting multiple links grouped by type."""
        from reveal.display.formatting import _format_links
        from pathlib import Path

        items = [
            {'line': 1, 'text': 'Ext1', 'url': 'https://example.com', 'type': 'external'},
            {'line': 2, 'text': 'Ext2', 'url': 'https://test.com', 'type': 'external'},
            {'line': 3, 'text': 'Int', 'url': './local.md', 'type': 'internal'},
            {'line': 4, 'text': 'Email', 'url': 'mailto:test@example.com', 'type': 'email'},
        ]
        _format_links(items, Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "External (2):" in captured.out
        assert "Internal (1):" in captured.out
        assert "Email (1):" in captured.out


class TestFormatCodeBlocks:
    """Tests for code block formatting functions."""

    def test_format_fenced_block_normal(self, capsys):
        """Test formatting a fenced code block."""
        from reveal.display.formatting import _format_fenced_block
        from pathlib import Path

        item = {
            'line_start': 10,
            'line_end': 15,
            'line_count': 5,
            'source': 'def foo():\n    return 42\n\nprint(foo())\n# Comment'
        }
        _format_fenced_block(item, Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "Lines 10-15 (5 lines)" in captured.out
        assert "def foo():" in captured.out
        assert "return 42" in captured.out
        assert "... (2 more lines)" in captured.out

    def test_format_fenced_block_grep(self, capsys):
        """Test formatting fenced block in grep format."""
        from reveal.display.formatting import _format_fenced_block
        from pathlib import Path

        item = {
            'line_start': 10,
            'line_end': 12,
            'line_count': 2,
            'source': 'first line\nsecond line'
        }
        _format_fenced_block(item, Path('test.md'), 'grep')
        captured = capsys.readouterr()
        assert "test.md:10:first line" in captured.out

    def test_format_inline_code_items(self, capsys):
        """Test formatting inline code snippets."""
        from reveal.display.formatting import _format_inline_code_items
        from pathlib import Path

        items = [
            {'line': 5, 'source': 'foo()'},
            {'line': 10, 'source': 'bar()'},
        ]
        _format_inline_code_items(items, Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "Inline code (2 snippets):" in captured.out
        assert "`foo()`" in captured.out
        assert "`bar()`" in captured.out

    def test_format_inline_code_items_truncated(self, capsys):
        """Test formatting inline code with truncation."""
        from reveal.display.formatting import _format_inline_code_items
        from pathlib import Path

        items = [{'line': i, 'source': f'code_{i}()'} for i in range(15)]
        _format_inline_code_items(items, Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "Inline code (15 snippets):" in captured.out
        assert "... and 5 more" in captured.out

    def test_format_inline_code_grep_format(self, capsys):
        """Test formatting inline code in grep format."""
        from reveal.display.formatting import _format_inline_code_items
        from pathlib import Path

        items = [{'line': 5, 'source': 'foo()'}]
        _format_inline_code_items(items, Path('test.md'), 'grep')
        captured = capsys.readouterr()
        assert "test.md:5:foo()" in captured.out

    def test_format_code_blocks_grouped_by_language(self, capsys):
        """Test formatting code blocks grouped by language."""
        from reveal.display.formatting import _format_code_blocks
        from pathlib import Path

        items = [
            {'language': 'python', 'line_start': 10, 'line_end': 15, 'line_count': 5, 'source': 'def foo(): pass'},
            {'language': 'python', 'line_start': 20, 'line_end': 25, 'line_count': 5, 'source': 'def bar(): pass'},
            {'language': 'javascript', 'line_start': 30, 'line_end': 35, 'line_count': 5, 'source': 'function baz() {}'},
        ]
        _format_code_blocks(items, Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "Python (2 blocks):" in captured.out
        assert "Javascript (1 blocks):" in captured.out

    def test_format_code_blocks_with_inline(self, capsys):
        """Test formatting code blocks including inline code."""
        from reveal.display.formatting import _format_code_blocks
        from pathlib import Path

        items = [
            {'language': 'python', 'line_start': 10, 'line_end': 15, 'line_count': 5, 'source': 'def foo(): pass'},
            {'language': 'inline', 'line': 5, 'source': 'foo()'},
        ]
        _format_code_blocks(items, Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "Python (1 blocks):" in captured.out
        assert "Inline code (1 snippets):" in captured.out


class TestFormatRelated:
    """Tests for related document formatting functions."""

    def test_format_related_item_exists(self, capsys):
        """Test formatting a related item that exists."""
        from reveal.display.formatting import _format_related_item

        item = {'path': '/docs/related.md', 'exists': True, 'headings': ['Intro', 'Details']}
        _format_related_item(item)
        captured = capsys.readouterr()
        assert "/docs/related.md ✓" in captured.out
        assert "Headings (2):" in captured.out
        assert "- Intro" in captured.out
        assert "- Details" in captured.out

    def test_format_related_item_not_found(self, capsys):
        """Test formatting a related item that doesn't exist."""
        from reveal.display.formatting import _format_related_item

        item = {'path': '/docs/missing.md', 'exists': False}
        _format_related_item(item)
        captured = capsys.readouterr()
        assert "/docs/missing.md ✗ NOT FOUND" in captured.out

    def test_format_related_item_with_error(self, capsys):
        """Test formatting a related item with error."""
        from reveal.display.formatting import _format_related_item

        item = {'path': '/docs/broken.md', 'exists': True, 'error': 'Invalid format'}
        _format_related_item(item)
        captured = capsys.readouterr()
        assert "/docs/broken.md ⚠ Invalid format" in captured.out

    def test_format_related_item_with_nested(self, capsys):
        """Test formatting related item with nested related docs."""
        from reveal.display.formatting import _format_related_item

        item = {
            'path': '/docs/parent.md',
            'exists': True,
            'related': [
                {'path': '/docs/child.md', 'exists': True},
            ]
        }
        _format_related_item(item)
        captured = capsys.readouterr()
        assert "/docs/parent.md ✓" in captured.out
        assert "Related (1):" in captured.out
        assert "/docs/child.md ✓" in captured.out

    def test_format_related_item_headings_truncated(self, capsys):
        """Test formatting related item with many headings."""
        from reveal.display.formatting import _format_related_item

        headings = [f'Heading {i}' for i in range(10)]
        item = {'path': '/docs/many.md', 'exists': True, 'headings': headings}
        _format_related_item(item)
        captured = capsys.readouterr()
        assert "Headings (10):" in captured.out
        assert "... and 5 more" in captured.out

    def test_count_related_stats_single_level(self):
        """Test counting stats for single-level related docs."""
        from reveal.display.formatting import _count_related_stats

        items = [
            {'path': '/docs/a.md'},
            {'path': '/docs/b.md'},
        ]
        stats = _count_related_stats(items)
        assert stats['total'] == 2
        assert stats['max_depth'] == 1

    def test_count_related_stats_nested(self):
        """Test counting stats for nested related docs."""
        from reveal.display.formatting import _count_related_stats

        items = [
            {'path': '/docs/a.md', 'related': [{'path': '/docs/b.md'}]},
            {'path': '/docs/c.md'},
        ]
        stats = _count_related_stats(items)
        assert stats['total'] == 3
        assert stats['max_depth'] == 2

    def test_count_related_stats_empty(self):
        """Test counting stats for empty related list."""
        from reveal.display.formatting import _count_related_stats

        stats = _count_related_stats([])
        assert stats['total'] == 0
        assert stats['max_depth'] == 0

    def test_format_related_flat(self):
        """Test extracting flat list of paths."""
        from reveal.display.formatting import _format_related_flat

        items = [
            {'path': '/docs/a.md', 'resolved_path': '/abs/docs/a.md'},
            {'path': '/docs/b.md', 'resolved_path': '/abs/docs/b.md', 'related': [
                {'path': '/docs/c.md', 'resolved_path': '/abs/docs/c.md'}
            ]},
        ]
        paths = _format_related_flat(items)
        assert len(paths) == 3
        assert '/abs/docs/a.md' in paths
        assert '/abs/docs/b.md' in paths
        assert '/abs/docs/c.md' in paths

    def test_format_related_flat_deduplication(self):
        """Test flat path list deduplicates."""
        from reveal.display.formatting import _format_related_flat

        items = [
            {'path': '/docs/a.md', 'resolved_path': '/abs/docs/a.md'},
            {'path': '/docs/a.md', 'resolved_path': '/abs/docs/a.md'},  # Duplicate
        ]
        paths = _format_related_flat(items)
        assert len(paths) == 1

    def test_format_related_empty(self, capsys):
        """Test formatting empty related list."""
        from reveal.display.formatting import _format_related
        from pathlib import Path

        _format_related([], Path('test.md'), 'text')
        captured = capsys.readouterr()
        assert "(No related documents found in front matter)" in captured.out

    def test_format_related_flat_mode(self, capsys):
        """Test formatting related in flat mode."""
        from reveal.display.formatting import _format_related
        from pathlib import Path

        items = [
            {'path': '/docs/a.md', 'resolved_path': '/abs/docs/a.md'},
            {'path': '/docs/b.md', 'resolved_path': '/abs/docs/b.md'},
        ]
        _format_related(items, Path('test.md'), 'text', flat=True)
        captured = capsys.readouterr()
        assert "/abs/docs/a.md" in captured.out
        assert "/abs/docs/b.md" in captured.out

    def test_format_related_grep_mode(self, capsys):
        """Test formatting related in grep mode."""
        from reveal.display.formatting import _format_related
        from pathlib import Path

        items = [
            {'path': '/docs/a.md', 'exists': True},
            {'path': '/docs/b.md', 'exists': False},
        ]
        _format_related(items, Path('test.md'), 'grep')
        captured = capsys.readouterr()
        assert "test.md:related:/docs/a.md:EXISTS" in captured.out
        assert "test.md:related:/docs/b.md:MISSING" in captured.out

    def test_format_related_with_summary(self, capsys):
        """Test formatting related with summary for deep trees."""
        from reveal.display.formatting import _format_related
        from pathlib import Path

        items = [
            {
                'path': '/docs/a.md',
                'exists': True,
                'related': [{'path': '/docs/b.md', 'exists': True}]
            },
        ]
        _format_related(items, Path('test.md'), 'text', show_summary=True)
        captured = capsys.readouterr()
        assert "(2 docs across 2 levels)" in captured.out


class TestFormatCsvSchema:
    """Tests for CSV schema formatting."""

    def test_format_csv_schema_basic(self, capsys):
        """Test formatting CSV schema with basic info."""
        from reveal.display.formatting import _format_csv_schema

        items = [
            {'name': 'id', 'type': 'int64', 'missing_pct': 0, 'unique_count': 100},
            {'name': 'name', 'type': 'string', 'missing_pct': 5.5, 'unique_count': 98},
        ]
        _format_csv_schema(items)
        captured = capsys.readouterr()
        assert "id" in captured.out
        assert "int64" in captured.out
        assert "100 unique" in captured.out
        assert "name" in captured.out
        assert "5.5% missing" in captured.out

    def test_format_csv_schema_with_samples(self, capsys):
        """Test formatting CSV schema with sample values."""
        from reveal.display.formatting import _format_csv_schema

        items = [
            {
                'name': 'category',
                'type': 'string',
                'missing_pct': 0,
                'unique_count': 5,
                'sample_values': ['A', 'B', 'C']
            },
        ]
        _format_csv_schema(items)
        captured = capsys.readouterr()
        assert "category" in captured.out
        assert "→ A, B, C" in captured.out

    def test_format_csv_schema_truncated_samples(self, capsys):
        """Test formatting CSV schema with long sample values."""
        from reveal.display.formatting import _format_csv_schema

        long_value = 'x' * 30
        items = [
            {
                'name': 'description',
                'type': 'string',
                'missing_pct': 0,
                'unique_count': 10,
                'sample_values': [long_value]
            },
        ]
        _format_csv_schema(items)
        captured = capsys.readouterr()
        assert "..." in captured.out  # Truncation marker


class TestFormatXmlChildren:
    """Tests for XML children formatting."""

    def test_format_xml_children_basic(self, capsys):
        """Test formatting basic XML children."""
        from reveal.display.formatting import _format_xml_children

        items = [
            {'tag': 'div', 'attributes': {}, 'text': '', 'children': [], 'child_count': 0},
        ]
        _format_xml_children(items)
        captured = capsys.readouterr()
        assert "<div>" in captured.out

    def test_format_xml_children_with_attributes(self, capsys):
        """Test formatting XML children with attributes."""
        from reveal.display.formatting import _format_xml_children

        items = [
            {
                'tag': 'div',
                'attributes': {'class': 'container', 'id': 'main'},
                'text': '',
                'children': [],
                'child_count': 0
            },
        ]
        _format_xml_children(items)
        captured = capsys.readouterr()
        assert "<div" in captured.out
        assert 'class="container"' in captured.out
        assert 'id="main"' in captured.out

    def test_format_xml_children_with_text(self, capsys):
        """Test formatting XML children with text content."""
        from reveal.display.formatting import _format_xml_children

        items = [
            {
                'tag': 'p',
                'attributes': {},
                'text': 'Hello world',
                'children': [],
                'child_count': 0
            },
        ]
        _format_xml_children(items)
        captured = capsys.readouterr()
        assert '<p> → "Hello world"' in captured.out

    def test_format_xml_children_with_child_count(self, capsys):
        """Test formatting XML children with child count."""
        from reveal.display.formatting import _format_xml_children

        items = [
            {
                'tag': 'ul',
                'attributes': {},
                'text': '',
                'children': [],
                'child_count': 5
            },
        ]
        _format_xml_children(items)
        captured = capsys.readouterr()
        assert "<ul> (5 children)" in captured.out

    def test_format_xml_children_nested(self, capsys):
        """Test formatting nested XML children."""
        from reveal.display.formatting import _format_xml_children

        items = [
            {
                'tag': 'div',
                'attributes': {},
                'text': '',
                'children': [
                    {'tag': 'p', 'attributes': {}, 'text': 'Nested', 'children': [], 'child_count': 0}
                ],
                'child_count': 1
            },
        ]
        _format_xml_children(items)
        captured = capsys.readouterr()
        assert "<div>" in captured.out
        assert "<p>" in captured.out

    def test_format_xml_children_truncated_text(self, capsys):
        """Test formatting XML children with long text."""
        from reveal.display.formatting import _format_xml_children

        long_text = 'x' * 50
        items = [
            {
                'tag': 'p',
                'attributes': {},
                'text': long_text,
                'children': [],
                'child_count': 0
            },
        ]
        _format_xml_children(items)
        captured = capsys.readouterr()
        assert "..." in captured.out  # Truncation marker

    def test_format_xml_children_many_attributes(self, capsys):
        """Test formatting XML with many attributes."""
        from reveal.display.formatting import _format_xml_children

        items = [
            {
                'tag': 'div',
                'attributes': {'a': '1', 'b': '2', 'c': '3', 'd': '4', 'e': '5'},
                'text': '',
                'children': [],
                'child_count': 0
            },
        ]
        _format_xml_children(items)
        captured = capsys.readouterr()
        assert "..." in captured.out  # Truncation for attributes


class TestKwargsBuilders:
    """Tests for kwargs builder functions."""

    def test_add_navigation_kwargs_empty_args(self):
        """Test add_navigation_kwargs with None args."""
        from reveal.display.formatting import _add_navigation_kwargs

        kwargs = {}
        _add_navigation_kwargs(kwargs, None)
        assert kwargs == {}

    def test_add_navigation_kwargs_head(self):
        """Test add_navigation_kwargs with head argument."""
        from reveal.display.formatting import _add_navigation_kwargs

        args = Mock()
        args.head = 10
        args.tail = None
        args.range = None

        kwargs = {}
        _add_navigation_kwargs(kwargs, args)
        assert kwargs['head'] == 10

    def test_add_navigation_kwargs_tail(self):
        """Test add_navigation_kwargs with tail argument."""
        from reveal.display.formatting import _add_navigation_kwargs

        args = Mock()
        args.head = None
        args.tail = 20
        args.range = None

        kwargs = {}
        _add_navigation_kwargs(kwargs, args)
        assert kwargs['tail'] == 20

    def test_add_navigation_kwargs_range(self):
        """Test add_navigation_kwargs with range argument."""
        from reveal.display.formatting import _add_navigation_kwargs

        args = Mock()
        args.head = None
        args.tail = None
        args.range = '10-20'

        kwargs = {}
        _add_navigation_kwargs(kwargs, args)
        assert kwargs['range'] == '10-20'

    def test_add_markdown_link_kwargs_no_flags(self):
        """Test add_markdown_link_kwargs with no link flags."""
        from reveal.display.formatting import _add_markdown_link_kwargs

        args = Mock()
        args.links = False
        args.link_type = None
        args.domain = None

        kwargs = {}
        _add_markdown_link_kwargs(kwargs, args)
        assert 'extract_links' not in kwargs

    def test_add_markdown_link_kwargs_with_links(self):
        """Test add_markdown_link_kwargs with links flag."""
        from reveal.display.formatting import _add_markdown_link_kwargs

        args = Mock()
        args.links = True
        args.link_type = None
        args.domain = None

        kwargs = {}
        _add_markdown_link_kwargs(kwargs, args)
        assert kwargs['extract_links'] is True

    def test_add_markdown_link_kwargs_with_link_type(self):
        """Test add_markdown_link_kwargs with link_type."""
        from reveal.display.formatting import _add_markdown_link_kwargs

        args = Mock()
        args.links = False
        args.link_type = 'external'
        args.domain = None

        kwargs = {}
        _add_markdown_link_kwargs(kwargs, args)
        assert kwargs['extract_links'] is True
        assert kwargs['link_type'] == 'external'

    def test_add_markdown_link_kwargs_with_domain(self):
        """Test add_markdown_link_kwargs with domain filter."""
        from reveal.display.formatting import _add_markdown_link_kwargs

        args = Mock()
        args.links = False
        args.link_type = None
        args.domain = 'example.com'

        kwargs = {}
        _add_markdown_link_kwargs(kwargs, args)
        assert kwargs['extract_links'] is True
        assert kwargs['domain'] == 'example.com'

    def test_add_markdown_code_kwargs_no_flags(self):
        """Test add_markdown_code_kwargs with no code flags."""
        from reveal.display.formatting import _add_markdown_code_kwargs

        args = Mock()
        args.code = False
        args.language = None
        args.inline = None

        kwargs = {}
        _add_markdown_code_kwargs(kwargs, args)
        assert 'extract_code' not in kwargs

    def test_add_markdown_code_kwargs_with_code(self):
        """Test add_markdown_code_kwargs with code flag."""
        from reveal.display.formatting import _add_markdown_code_kwargs

        args = Mock()
        args.code = True
        args.language = None
        args.inline = None

        kwargs = {}
        _add_markdown_code_kwargs(kwargs, args)
        assert kwargs['extract_code'] is True

    def test_add_markdown_code_kwargs_with_language(self):
        """Test add_markdown_code_kwargs with language filter."""
        from reveal.display.formatting import _add_markdown_code_kwargs

        args = Mock()
        args.code = False
        args.language = 'python'
        args.inline = None

        kwargs = {}
        _add_markdown_code_kwargs(kwargs, args)
        assert kwargs['extract_code'] is True
        assert kwargs['language'] == 'python'

    def test_add_markdown_code_kwargs_with_inline(self):
        """Test add_markdown_code_kwargs with inline flag."""
        from reveal.display.formatting import _add_markdown_code_kwargs

        args = Mock()
        args.code = False
        args.language = None
        args.inline = True

        kwargs = {}
        _add_markdown_code_kwargs(kwargs, args)
        assert kwargs['extract_code'] is True
        assert kwargs['inline_code'] is True

    def test_add_html_kwargs_no_flags(self):
        """Test add_html_kwargs with no HTML flags."""
        from reveal.display.formatting import _add_html_kwargs

        args = Mock()
        args.metadata = False
        args.scripts = False
        args.styles = False
        args.semantic = False

        kwargs = {}
        _add_html_kwargs(kwargs, args)
        assert 'metadata' not in kwargs
        assert 'scripts' not in kwargs

    def test_add_html_kwargs_with_metadata(self):
        """Test add_html_kwargs with metadata flag."""
        from reveal.display.formatting import _add_html_kwargs

        args = Mock()
        args.metadata = True
        args.scripts = False
        args.styles = False
        args.semantic = False

        kwargs = {}
        _add_html_kwargs(kwargs, args)
        assert kwargs['metadata'] is True

    def test_add_html_kwargs_with_scripts(self):
        """Test add_html_kwargs with scripts flag."""
        from reveal.display.formatting import _add_html_kwargs

        args = Mock()
        args.metadata = False
        args.scripts = 'external'
        args.styles = False
        args.semantic = False

        kwargs = {}
        _add_html_kwargs(kwargs, args)
        assert kwargs['scripts'] == 'external'

    def test_add_html_kwargs_with_styles(self):
        """Test add_html_kwargs with styles flag."""
        from reveal.display.formatting import _add_html_kwargs

        args = Mock()
        args.metadata = False
        args.scripts = False
        args.styles = 'inline'
        args.semantic = False

        kwargs = {}
        _add_html_kwargs(kwargs, args)
        assert kwargs['styles'] == 'inline'

    def test_add_html_kwargs_with_semantic(self):
        """Test add_html_kwargs with semantic flag."""
        from reveal.display.formatting import _add_html_kwargs

        args = Mock()
        args.metadata = False
        args.scripts = False
        args.styles = False
        args.semantic = 'article'

        kwargs = {}
        _add_html_kwargs(kwargs, args)
        assert kwargs['semantic'] == 'article'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
