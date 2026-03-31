"""Tests for display/outline.py — hierarchy building and outline rendering."""

import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reveal.display.outline import (
    build_hierarchy,
    build_heading_hierarchy,
    _build_metrics_display,
    _build_item_display,
    _get_child_indent,
    render_outline,
)


# ============================================================================
# build_hierarchy
# ============================================================================

class TestBuildHierarchy:
    def test_empty_structure_returns_empty(self):
        assert build_hierarchy({}) == []

    def test_flat_items_all_root(self):
        structure = {
            'functions': [
                {'name': 'foo', 'line': 1, 'line_start': 1, 'line_end': 5},
                {'name': 'bar', 'line': 10, 'line_start': 10, 'line_end': 15},
            ]
        }
        roots = build_hierarchy(structure)
        assert len(roots) == 2
        assert all(item['children'] == [] for item in roots)

    def test_nested_item_becomes_child(self):
        # bar is inside foo (lines 3-5 within 1-10)
        structure = {
            'classes': [
                {'name': 'Outer', 'line': 1, 'line_start': 1, 'line_end': 20},
            ],
            'functions': [
                {'name': 'method', 'line': 5, 'line_start': 5, 'line_end': 10},
            ],
        }
        roots = build_hierarchy(structure)
        assert len(roots) == 1
        assert roots[0]['name'] == 'Outer'
        assert len(roots[0]['children']) == 1
        assert roots[0]['children'][0]['name'] == 'method'

    def test_items_sorted_by_line(self):
        structure = {
            'functions': [
                {'name': 'b', 'line': 20, 'line_start': 20, 'line_end': 25},
                {'name': 'a', 'line': 1, 'line_start': 1, 'line_end': 5},
            ]
        }
        roots = build_hierarchy(structure)
        assert roots[0]['name'] == 'a'
        assert roots[1]['name'] == 'b'

    def test_category_added_to_items(self):
        structure = {'functions': [{'name': 'foo', 'line': 1, 'line_start': 1, 'line_end': 5}]}
        roots = build_hierarchy(structure)
        assert roots[0]['category'] == 'functions'

    def test_non_list_category_skipped(self):
        # contract metadata fields like source_type are strings, not lists
        structure = {
            'source_type': 'python',
            'functions': [{'name': 'foo', 'line': 1, 'line_start': 1, 'line_end': 5}],
        }
        roots = build_hierarchy(structure)
        assert len(roots) == 1

    def test_non_dict_item_skipped(self):
        structure = {'functions': ['not_a_dict', {'name': 'foo', 'line': 1, 'line_start': 1, 'line_end': 5}]}
        roots = build_hierarchy(structure)
        assert len(roots) == 1
        assert roots[0]['name'] == 'foo'

    def test_original_items_not_mutated(self):
        items = [{'name': 'foo', 'line': 1, 'line_start': 1, 'line_end': 5}]
        structure = {'functions': items}
        build_hierarchy(structure)
        assert 'children' not in items[0]
        assert 'category' not in items[0]


# ============================================================================
# build_heading_hierarchy
# ============================================================================

class TestBuildHeadingHierarchy:
    def test_empty_returns_empty(self):
        assert build_heading_hierarchy([]) == []

    def test_all_h1_are_roots(self):
        headings = [
            {'level': 1, 'name': 'A', 'line': 1},
            {'level': 1, 'name': 'B', 'line': 10},
        ]
        roots = build_heading_hierarchy(headings)
        assert len(roots) == 2
        assert roots[0]['name'] == 'A'
        assert roots[1]['name'] == 'B'

    def test_h2_becomes_child_of_h1(self):
        headings = [
            {'level': 1, 'name': 'H1', 'line': 1},
            {'level': 2, 'name': 'H2', 'line': 5},
        ]
        roots = build_heading_hierarchy(headings)
        assert len(roots) == 1
        assert roots[0]['name'] == 'H1'
        assert len(roots[0]['children']) == 1
        assert roots[0]['children'][0]['name'] == 'H2'

    def test_three_level_nesting(self):
        headings = [
            {'level': 1, 'name': 'A', 'line': 1},
            {'level': 2, 'name': 'B', 'line': 2},
            {'level': 3, 'name': 'C', 'line': 3},
        ]
        roots = build_heading_hierarchy(headings)
        assert len(roots) == 1
        b = roots[0]['children'][0]
        assert b['name'] == 'B'
        assert b['children'][0]['name'] == 'C'

    def test_sibling_h2s_under_same_h1(self):
        headings = [
            {'level': 1, 'name': 'Root', 'line': 1},
            {'level': 2, 'name': 'Child1', 'line': 2},
            {'level': 2, 'name': 'Child2', 'line': 5},
        ]
        roots = build_heading_hierarchy(headings)
        assert len(roots[0]['children']) == 2

    def test_new_h1_resets_to_root(self):
        headings = [
            {'level': 1, 'name': 'First', 'line': 1},
            {'level': 2, 'name': 'Sub', 'line': 2},
            {'level': 1, 'name': 'Second', 'line': 10},
        ]
        roots = build_heading_hierarchy(headings)
        assert len(roots) == 2
        assert roots[1]['name'] == 'Second'
        assert roots[1]['children'] == []

    def test_original_headings_not_mutated(self):
        headings = [{'level': 1, 'name': 'A', 'line': 1}]
        build_heading_hierarchy(headings)
        assert 'children' not in headings[0]


# ============================================================================
# _build_metrics_display
# ============================================================================

class TestBuildMetricsDisplay:
    def test_no_metrics_returns_empty(self):
        assert _build_metrics_display({'name': 'foo'}) == ''

    def test_line_count_only(self):
        result = _build_metrics_display({'line_count': 10})
        assert result == ' [10 lines]'

    def test_depth_only(self):
        result = _build_metrics_display({'depth': 3})
        assert result == ' [depth:3]'

    def test_both_line_count_and_depth(self):
        result = _build_metrics_display({'line_count': 10, 'depth': 2})
        assert '10 lines' in result
        assert 'depth:2' in result
        assert result.startswith(' [')
        assert result.endswith(']')


# ============================================================================
# _build_item_display
# ============================================================================

class TestBuildItemDisplay:
    def test_name_and_signature(self):
        item = {'name': 'foo', 'signature': '(x, y)'}
        assert _build_item_display(item) == 'foo(x, y)'

    def test_name_only(self):
        item = {'name': 'foo'}
        assert _build_item_display(item) == 'foo'

    def test_no_name_falls_back_to_content(self):
        item = {'content': 'section text'}
        assert _build_item_display(item) == 'section text'

    def test_no_name_no_content_shows_question_mark(self):
        assert _build_item_display({}) == '?'

    def test_metrics_appended(self):
        item = {'name': 'foo', 'line_count': 5}
        result = _build_item_display(item)
        assert result == 'foo [5 lines]'


# ============================================================================
# _get_child_indent
# ============================================================================

class TestGetChildIndent:
    def test_root_parent_minimal_indent(self):
        assert _get_child_indent('', is_root=True, is_last_item=True) == '  '
        assert _get_child_indent('', is_root=True, is_last_item=False) == '  '

    def test_nested_last_item_uses_spaces(self):
        result = _get_child_indent('  ', is_root=False, is_last_item=True)
        assert result == '     '  # indent + '   '

    def test_nested_non_last_item_uses_pipe(self):
        result = _get_child_indent('  ', is_root=False, is_last_item=False)
        assert result == '  │  '


# ============================================================================
# render_outline
# ============================================================================

class TestRenderOutline:
    def test_empty_items_prints_nothing(self, capsys):
        render_outline([], Path('/tmp/test.py'))
        captured = capsys.readouterr()
        assert captured.out == ''

    def test_single_root_item(self, capsys):
        items = [{'name': 'foo', 'line': 1, 'line_start': 1, 'children': []}]
        p = Path('/tmp/test.py')
        render_outline(items, p)
        captured = capsys.readouterr()
        assert 'foo' in captured.out
        assert f'{p}:1' in captured.out

    def test_nested_child_uses_tree_chars(self, capsys):
        child = {'name': 'bar', 'line': 5, 'line_start': 5, 'children': []}
        items = [{'name': 'foo', 'line': 1, 'line_start': 1, 'children': [child]}]
        render_outline(items, Path('/tmp/test.py'))
        captured = capsys.readouterr()
        # Child should use └─ or ├─ tree chars
        assert '└─' in captured.out or '├─' in captured.out
        assert 'bar' in captured.out

    def test_multiple_siblings_last_uses_corner(self, capsys):
        child1 = {'name': 'a', 'line': 2, 'line_start': 2, 'children': []}
        child2 = {'name': 'b', 'line': 3, 'line_start': 3, 'children': []}
        items = [{'name': 'root', 'line': 1, 'line_start': 1, 'children': [child1, child2]}]
        render_outline(items, Path('/tmp/test.py'))
        captured = capsys.readouterr()
        assert '├─' in captured.out  # non-last child
        assert '└─' in captured.out  # last child
