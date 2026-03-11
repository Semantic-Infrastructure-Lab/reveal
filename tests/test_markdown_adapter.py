"""Tests for markdown query adapter (markdown://)."""

import pytest
from pathlib import Path
from reveal.adapters.markdown import MarkdownQueryAdapter


@pytest.fixture
def sample_docs(tmp_path):
    """Create sample markdown files with frontmatter for testing."""
    # File with frontmatter
    (tmp_path / "guide.md").write_text("""---
title: Developer Guide
type: guide
status: active
priority: 10
tags:
  - python
  - development
topics:
  - reveal
  - testing
---

# Developer Guide

This is a guide.
""")

    # File with different frontmatter
    (tmp_path / "tutorial.md").write_text("""---
title: Quick Tutorial
type: tutorial
status: draft
priority: 5
tags:
  - beginner
topics:
  - reveal
---

# Tutorial

This is a tutorial.
""")

    # File with numeric fields
    (tmp_path / "api.md").write_text("""---
title: API Reference
type: reference
status: active
priority: 20
version: 2.5
tags:
  - api
  - advanced
---

# API Reference

This is API documentation.
""")

    # File without frontmatter
    (tmp_path / "readme.md").write_text("""# README

Just a plain markdown file.
""")

    # File with minimal frontmatter
    (tmp_path / "notes.md").write_text("""---
title: Random Notes
---

# Notes

Some notes.
""")

    return tmp_path


class TestMarkdownAdapter:
    """Test basic markdown adapter functionality."""

    def test_init(self):
        """Test adapter initialization."""
        adapter = MarkdownQueryAdapter('.', query='topics=reveal')
        assert adapter.base_path.is_absolute()
        assert adapter.query == 'topics=reveal'

    def test_find_markdown_files(self, sample_docs):
        """Test finding all markdown files."""
        adapter = MarkdownQueryAdapter(str(sample_docs))
        files = adapter._find_markdown_files()
        assert len(files) == 5
        assert all(f.suffix in ('.md', '.markdown') for f in files)

    def test_extract_frontmatter(self, sample_docs):
        """Test extracting YAML frontmatter."""
        adapter = MarkdownQueryAdapter(str(sample_docs))
        fm = adapter._extract_frontmatter(sample_docs / "guide.md")
        assert fm is not None
        assert fm['title'] == 'Developer Guide'
        assert fm['type'] == 'guide'
        assert 'python' in fm['tags']

    def test_no_frontmatter(self, sample_docs):
        """Test files without frontmatter."""
        adapter = MarkdownQueryAdapter(str(sample_docs))
        fm = adapter._extract_frontmatter(sample_docs / "readme.md")
        assert fm is None


class TestLegacyFiltering:
    """Test backward compatibility with legacy filter syntax."""

    def test_exact_match(self, sample_docs):
        """Test field=value syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='status=active')
        result = adapter.get_structure()
        assert result['matched_files'] == 2
        assert all('status' in r for r in result['results'] if 'status' in r)

    def test_list_field_match(self, sample_docs):
        """Test matching against list fields."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='tags=python')
        result = adapter.get_structure()
        assert result['matched_files'] >= 1
        assert any('guide' in r.get('title', '').lower() for r in result['results'])

    def test_wildcard_match(self, sample_docs):
        """Test field=*pattern* wildcard syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='type=*guide*')
        result = adapter.get_structure()
        assert result['matched_files'] >= 1

    def test_missing_field(self, sample_docs):
        """Test !field syntax for missing fields."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='!status')
        result = adapter.get_structure()
        # Should match files without status field
        assert result['matched_files'] >= 2  # readme.md and notes.md

    def test_multiple_filters(self, sample_docs):
        """Test field1=val1&field2=val2 syntax (AND logic)."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='status=active&type=guide')
        result = adapter.get_structure()
        assert result['matched_files'] == 1
        assert result['results'][0]['type'] == 'guide'


class TestUnifiedQuerySyntax:
    """Test new unified query syntax (operators and result control)."""

    def test_greater_than_operator(self, sample_docs):
        """Test priority>10 syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='priority>10')
        result = adapter.get_structure()
        assert result['matched_files'] == 1
        assert any('API' in r.get('title', '') for r in result['results'])

    def test_less_than_operator(self, sample_docs):
        """Test priority<10 syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='priority<10')
        result = adapter.get_structure()
        assert result['matched_files'] >= 1
        assert all(r.get('priority', 0) < 10 for r in result['results'] if 'priority' in r)

    def test_greater_equals_operator(self, sample_docs):
        """Test priority>=10 syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='priority>=10')
        result = adapter.get_structure()
        assert result['matched_files'] >= 2
        assert all(r.get('priority', 0) >= 10 for r in result['results'] if 'priority' in r)

    def test_less_equals_operator(self, sample_docs):
        """Test priority<=10 syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='priority<=10')
        result = adapter.get_structure()
        assert result['matched_files'] >= 2

    def test_equals_operator(self, sample_docs):
        """Test priority=10 syntax (exact match)."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='priority=10')
        result = adapter.get_structure()
        # Note: priority field is not included in results by default
        # Just check that we match the right file count
        assert result['matched_files'] == 1

    def test_not_equals_operator(self, sample_docs):
        """Test status!=draft syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='status!=draft')
        result = adapter.get_structure()
        # Should match files with status != 'draft' (but not files without status)
        assert result['matched_files'] >= 2

    def test_regex_operator(self, sample_docs):
        """Test title~=^API syntax (regex match)."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='title~=^API')
        result = adapter.get_structure()
        assert result['matched_files'] == 1
        assert result['results'][0]['title'] == 'API Reference'

    def test_regex_operator_case_insensitive(self, sample_docs):
        """Test title~=(?i)guide syntax (case-insensitive regex)."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='title~=(?i)guide')
        result = adapter.get_structure()
        assert result['matched_files'] >= 1

    def test_range_operator_numeric(self, sample_docs):
        """Test priority=5..15 syntax (numeric range)."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='priority=5..15')
        result = adapter.get_structure()
        assert result['matched_files'] == 2
        assert all(5 <= r.get('priority', 0) <= 15 for r in result['results'] if 'priority' in r)

    def test_range_operator_string(self, sample_docs):
        """Test type=guide..tutorial syntax (string range)."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='type=guide..tutorial')
        result = adapter.get_structure()
        # Lexicographic range
        assert result['matched_files'] >= 2

    def test_result_control_sort_ascending(self, sample_docs):
        """Test sort=priority syntax (ascending)."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='sort=priority')
        result = adapter.get_structure()
        # Results should be sorted by priority ascending
        results_with_priority = [r for r in result['results'] if 'priority' in r]
        for i in range(len(results_with_priority) - 1):
            assert results_with_priority[i]['priority'] <= results_with_priority[i + 1]['priority']

    def test_result_control_sort_descending(self, sample_docs):
        """Test sort=-priority syntax (descending)."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='sort=-priority')
        result = adapter.get_structure()
        # Results should be sorted by priority descending
        results_with_priority = [r for r in result['results'] if 'priority' in r]
        for i in range(len(results_with_priority) - 1):
            assert results_with_priority[i]['priority'] >= results_with_priority[i + 1]['priority']

    def test_result_control_limit(self, sample_docs):
        """Test limit=2 syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='limit=2')
        result = adapter.get_structure()
        # Should only show 2 files
        assert len(result['results']) == 2
        assert result['displayed_results'] == 2
        assert result['matched_files'] == 5

    def test_result_control_offset(self, sample_docs):
        """Test offset=2 syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='offset=2')
        result = adapter.get_structure()
        # Should skip first 2 files, show remaining 3
        assert len(result['results']) == 3

    def test_result_control_combined(self, sample_docs):
        """Test sort=-priority&limit=2&offset=1 syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='sort=-priority&limit=2&offset=1')
        result = adapter.get_structure()
        # Should skip highest priority (offset=1), show next 2 (limit=2)
        assert len(result['results']) == 2
        # Should be in descending order
        results_with_priority = [r for r in result['results'] if 'priority' in r]
        if len(results_with_priority) >= 2:
            for i in range(len(results_with_priority) - 1):
                assert results_with_priority[i]['priority'] >= results_with_priority[i + 1]['priority']

    def test_filter_and_result_control_combined(self, sample_docs):
        """Test priority>5&sort=-priority&limit=2 syntax."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='priority>5&sort=-priority&limit=2')
        result = adapter.get_structure()
        # Should filter (priority>5), sort descending, limit to 2
        assert len(result['results']) == 2
        # All should have priority > 5
        assert all(r.get('priority', 0) > 5 for r in result['results'] if 'priority' in r)
        # Should be in descending order
        results_with_priority = [r for r in result['results'] if 'priority' in r]
        for i in range(len(results_with_priority) - 1):
            assert results_with_priority[i]['priority'] >= results_with_priority[i + 1]['priority']

    def test_truncation_warning(self, sample_docs):
        """Test that truncation warning is added when results are limited."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='limit=2')
        result = adapter.get_structure()
        # Should have warning about truncation
        assert 'warnings' in result
        assert any(w['type'] == 'truncated' for w in result['warnings'])
        assert result['displayed_results'] == 2
        assert result['matched_files'] == 5


class TestOutputContract:
    """Test output contract compliance."""

    def test_structure_output(self, sample_docs):
        """Test get_structure() output format."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='status=active')
        result = adapter.get_structure()

        # Check required fields
        assert 'contract_version' in result
        assert result['type'] == 'markdown_query'
        assert 'source' in result
        assert 'base_path' in result
        assert 'total_files' in result
        assert 'matched_files' in result
        assert 'results' in result
        assert isinstance(result['results'], list)

    def test_result_fields(self, sample_docs):
        """Test fields in result items."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='status=active')
        result = adapter.get_structure()

        for item in result['results']:
            assert 'path' in item
            assert 'relative_path' in item
            assert 'has_frontmatter' in item

    def test_element_output(self, sample_docs):
        """Test get_element() output format."""
        adapter = MarkdownQueryAdapter(str(sample_docs))
        result = adapter.get_element('guide.md')

        assert result is not None
        assert 'path' in result
        assert 'has_frontmatter' in result
        assert 'frontmatter' in result
        assert result['has_frontmatter'] is True
        assert result['frontmatter']['title'] == 'Developer Guide'


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_query(self, sample_docs):
        """Test with no query (should return all files)."""
        adapter = MarkdownQueryAdapter(str(sample_docs))
        result = adapter.get_structure()
        assert result['matched_files'] == result['total_files']

    def test_nonexistent_field(self, sample_docs):
        """Test filtering on non-existent field."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='nonexistent>10')
        result = adapter.get_structure()
        # Should return no matches (field doesn't exist)
        assert result['matched_files'] == 0

    def test_invalid_regex(self, sample_docs):
        """Test with invalid regex pattern."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='title~=[invalid')
        result = adapter.get_structure()
        # Should not crash, regex errors are handled
        assert 'results' in result

    def test_list_field_comparison(self, sample_docs):
        """Test numeric comparison on list fields."""
        # tags is a list, should check each element
        adapter = MarkdownQueryAdapter(str(sample_docs), query='tags~=python')
        result = adapter.get_structure()
        assert result['matched_files'] >= 1

    def test_missing_field_with_comparison(self, sample_docs):
        """Test comparison on missing field."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='missing_field>10')
        result = adapter.get_structure()
        # Should return no matches (field doesn't exist)
        assert result['matched_files'] == 0

    def test_sort_missing_field(self, sample_docs):
        """Test sorting by field that some files don't have."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='sort=priority')
        result = adapter.get_structure()
        # Should not crash, files without field go to end
        assert len(result['results']) == 5

    def test_offset_greater_than_total(self, sample_docs):
        """Test offset larger than total results."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='offset=100')
        result = adapter.get_structure()
        # Should return empty results
        assert len(result['results']) == 0

    def test_zero_limit(self, sample_docs):
        """Test limit=0 (edge case)."""
        adapter = MarkdownQueryAdapter(str(sample_docs), query='limit=0')
        result = adapter.get_structure()
        # limit=0 means no results
        assert len(result['results']) == 0


class TestBodyContainsFilter:
    """Tests for ?body-contains= body text search."""

    @pytest.fixture
    def body_docs(self, tmp_path):
        """Create docs with distinct body content for body-contains testing."""
        (tmp_path / "nginx.md").write_text("""---
title: Nginx Config
type: guide
---

# Nginx Configuration

This document covers nginx server blocks and SSL termination.
""")
        (tmp_path / "postgres.md").write_text("""---
title: Postgres Setup
type: guide
---

# Postgres Configuration

This document covers postgres connection pooling and replication.
""")
        (tmp_path / "both.md").write_text("""---
title: Full Stack
type: reference
---

# Full Stack Guide

This doc mentions nginx reverse proxy and postgres as the backend.
""")
        (tmp_path / "no_fm.md").write_text("""# Plain File

No frontmatter here but mentions nginx configuration.
""")
        return tmp_path

    def test_body_contains_single_term(self, body_docs):
        """Single body-contains term filters to matching files."""
        adapter = MarkdownQueryAdapter(str(body_docs), query='body-contains=nginx')
        result = adapter.get_structure()
        titles = {r['title'] for r in result['results'] if r.get('title')}
        assert 'Nginx Config' in titles
        assert 'Full Stack' in titles
        # postgres-only doc should not appear
        assert 'Postgres Setup' not in titles

    def test_body_contains_multiple_terms_and(self, body_docs):
        """Multiple body-contains terms are AND'd — must all appear."""
        adapter = MarkdownQueryAdapter(str(body_docs), query='body-contains=nginx&body-contains=postgres')
        result = adapter.get_structure()
        titles = {r['title'] for r in result['results'] if r.get('title')}
        # Only 'both.md' mentions both
        assert titles == {'Full Stack'}

    def test_body_contains_case_insensitive(self, body_docs):
        """body-contains search is case-insensitive."""
        adapter = MarkdownQueryAdapter(str(body_docs), query='body-contains=NGINX')
        result = adapter.get_structure()
        titles = {r['title'] for r in result['results'] if r.get('title')}
        assert 'Nginx Config' in titles
        assert 'Full Stack' in titles

    def test_body_contains_no_match(self, body_docs):
        """body-contains with no matching files returns empty results."""
        adapter = MarkdownQueryAdapter(str(body_docs), query='body-contains=kubernetes')
        result = adapter.get_structure()
        assert len(result['results']) == 0

    def test_body_contains_with_frontmatter_filter(self, body_docs):
        """body-contains can be combined with frontmatter filters."""
        adapter = MarkdownQueryAdapter(str(body_docs), query='type=reference&body-contains=nginx')
        result = adapter.get_structure()
        titles = {r['title'] for r in result['results'] if r.get('title')}
        # Full Stack is type=reference and mentions nginx
        assert titles == {'Full Stack'}

    def test_body_contains_no_frontmatter_file(self, body_docs):
        """body-contains matches files even without frontmatter."""
        adapter = MarkdownQueryAdapter(str(body_docs), query='body-contains=nginx')
        result = adapter.get_structure()
        paths = [r['path'] for r in result['results']]
        assert any('no_fm' in p for p in paths)

    def test_body_contains_parsed_from_query(self, body_docs):
        """body-contains terms are stored in adapter.body_contains."""
        adapter = MarkdownQueryAdapter(str(body_docs), query='body-contains=nginx&body-contains=ssl')
        assert adapter.body_contains == ['nginx', 'ssl']

    def test_body_contains_does_not_leak_into_frontmatter_filters(self, body_docs):
        """body-contains= is stripped before frontmatter filter parsing."""
        adapter = MarkdownQueryAdapter(str(body_docs), query='body-contains=nginx&type=guide')
        # Should have no frontmatter filter for 'body-contains' field
        filter_fields = {f[0] for f in adapter.filters}
        assert 'body-contains' not in filter_fields

    def test_body_contains_with_result_control(self, body_docs):
        """body-contains works alongside sort/limit result control."""
        adapter = MarkdownQueryAdapter(str(body_docs), query='body-contains=nginx&limit=1')
        result = adapter.get_structure()
        assert len(result['results']) == 1
