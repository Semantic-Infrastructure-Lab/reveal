"""Extended test coverage for reveal.utils.query module.

This test file targets uncovered code paths to increase coverage from 77% to 85%+.
Focus areas:
- Edge cases in value coercion
- Exception handling in comparison operators
- Invalid input handling in result control parsing
- Mixed-type sorting scenarios
- Budget limit enforcement with truncation
"""

import pytest
from reveal.utils.query import (
    coerce_value,
    parse_query_filters,
    QueryFilter,
    compare_values,
    parse_result_control,
    apply_result_control,
    apply_budget_limits,
    _handle_range_operator,
    _handle_wildcard_operator,
    _handle_numeric_operator,
    _handle_equality_operator,
    _dispatch_comparison,
    _safe_numeric,
    _apply_sorting,
    _truncate_string_values,
    _truncate_dict_strings,
)


class TestCoerceValueEdgeCases:
    """Test edge cases in coerce_value function."""

    def test_non_string_input_returns_as_is(self):
        """Non-string values should be returned unchanged."""
        assert coerce_value(42) == 42
        assert coerce_value(3.14) == 3.14
        assert coerce_value(True) is True
        assert coerce_value(None) is None
        assert coerce_value([1, 2, 3]) == [1, 2, 3]


class TestQueryFilterNormalization:
    """Test QueryFilter operator normalization."""

    def test_double_equals_normalized_to_single(self):
        """== operator should be normalized to = in __post_init__."""
        filter = QueryFilter('field', '==', 'value')
        assert filter.op == '='


class TestParseQueryFiltersEdgeCases:
    """Test edge cases in parse_query_filters."""

    def test_empty_parts_skipped(self):
        """Empty filter parts should be skipped."""
        # Multiple ampersands create empty parts
        filters = parse_query_filters('field=value&&other=test')
        assert len(filters) == 2
        assert filters[0].field == 'field'
        assert filters[1].field == 'other'


class TestComparisonExceptionHandling:
    """Test exception handling in comparison operators."""

    def test_range_operator_invalid_format(self):
        """Range operator should return False for invalid range format."""
        # Missing .. in value
        opts = {'coerce_numeric': True, 'case_sensitive': False}
        result = _handle_range_operator('value', 'notarange', opts)
        assert result is False

    def test_range_operator_exception_handling(self):
        """Range operator should handle exceptions gracefully."""
        opts = {'coerce_numeric': True, 'case_sensitive': False}
        # Malformed range that causes exception
        result = _handle_range_operator('test', '..', opts)
        assert result is False

    def test_wildcard_operator_invalid_regex(self):
        """Wildcard operator should handle regex errors gracefully."""
        opts = {'coerce_numeric': True, 'case_sensitive': False}
        # While wildcards are escaped, test edge case handling
        result = _handle_wildcard_operator('test', '*', opts)
        assert result is True  # Should match anything

    def test_equality_operator_range_special_case(self):
        """Equality operator should handle range patterns."""
        opts = {'coerce_numeric': True, 'case_sensitive': False}
        # When = is used with range pattern, it should delegate to range handler
        result = _handle_equality_operator(5, '=', '1..10', opts)
        assert result is True

    def test_numeric_operator_string_fallback(self):
        """Numeric operator should fall back to string comparison."""
        opts = {'coerce_numeric': False, 'case_sensitive': False}
        # String comparison when coercion disabled
        result = _handle_numeric_operator('b', '>', 'a', opts)
        assert result is True

        result = _handle_numeric_operator('a', '<', 'b', opts)
        assert result is True

        result = _handle_numeric_operator('b', '>=', 'b', opts)
        assert result is True

        result = _handle_numeric_operator('a', '<=', 'a', opts)
        assert result is True

    def test_numeric_operator_string_fallback_coercion_failed(self):
        """Numeric operator string fallback when conversion fails with coercion enabled."""
        opts = {'coerce_numeric': True, 'case_sensitive': False}
        # Non-numeric strings that can't be coerced
        result = _handle_numeric_operator('apple', '>', 'banana', opts)
        assert result is False  # Falls back but returns False

    def test_dispatch_comparison_default_return(self):
        """Dispatch comparison should return False for unhandled operators."""
        opts = {'coerce_numeric': True, 'case_sensitive': False}
        # Invalid operator
        result = _dispatch_comparison('value', 'invalid_op', 'target', opts)
        assert result is False


class TestNoneComparison:
    """Test None value comparison special cases."""

    def test_none_equals_null_string(self):
        """None should equal 'null' string with = operator."""
        result = compare_values(None, '=', 'null')
        assert result is True

    def test_none_equals_null_case_insensitive(self):
        """None should equal 'NULL' or 'Null' (case insensitive)."""
        result = compare_values(None, '=', 'NULL')
        assert result is True

        result = compare_values(None, '=', 'Null')
        assert result is True


class TestResultControlInvalidInput:
    """Test result control parsing with invalid input."""

    def test_empty_parts_skipped(self):
        """Empty parts should be skipped in result control parsing."""
        query, control = parse_result_control('field=value&&limit=5')
        assert 'field=value' in query
        assert control.limit == 5

    def test_invalid_limit_value(self):
        """Invalid limit value should be ignored."""
        query, control = parse_result_control('sort=name&limit=invalid')
        assert control.limit is None

    def test_invalid_offset_value(self):
        """Invalid offset value should be ignored."""
        query, control = parse_result_control('sort=name&offset=notanumber')
        assert control.offset == 0  # Default


class TestSortingMixedTypes:
    """Test sorting with mixed types and fallback behavior."""

    def test_safe_numeric_with_none(self):
        """_safe_numeric should return None for None input."""
        assert _safe_numeric(None) is None

    def test_safe_numeric_with_numbers(self):
        """_safe_numeric should return numbers unchanged."""
        assert _safe_numeric(42) == 42
        assert _safe_numeric(3.14) == 3.14

    def test_safe_numeric_with_string_number(self):
        """_safe_numeric should convert numeric strings."""
        assert _safe_numeric('42') == 42.0
        assert _safe_numeric('3.14') == 3.14

    def test_safe_numeric_with_non_numeric_string(self):
        """_safe_numeric should return None for non-numeric strings."""
        assert _safe_numeric('not a number') is None

    def test_sorting_with_mixed_types(self):
        """Sorting should handle mixed numeric and string types."""
        items = [
            {'value': 'text'},
            {'value': 10},
            {'value': 'another'},
            {'value': 5},
        ]
        result = _apply_sorting(items, 'value', False)
        # Should sort without raising TypeError
        assert len(result) == 4

    def test_sorting_with_none_values(self):
        """Sorting should handle None values (sorted to end)."""
        items = [
            {'value': 5},
            {'value': None},
            {'value': 10},
        ]
        result = _apply_sorting(items, 'value', False)
        assert result[-1]['value'] is None  # None sorted to end

    def test_sorting_type_error_fallback(self):
        """Sorting should fall back to string comparison on TypeError."""
        items = [
            {'value': {'nested': 'dict'}},
            {'value': 'string'},
            {'value': 42},
        ]
        # Should not raise exception
        result = _apply_sorting(items, 'value', False)
        assert len(result) == 3


class TestBudgetLimits:
    """Test budget limit enforcement."""

    def test_max_items_truncation(self):
        """max_items should truncate results."""
        items = [{'id': i} for i in range(10)]
        result = apply_budget_limits(items, max_items=5)

        assert result['meta']['truncated'] is True
        assert result['meta']['reason'] == 'max_items_exceeded'
        assert len(result['items']) == 5
        assert result['meta']['total_available'] == 10
        assert result['meta']['returned'] == 5

    def test_max_items_within_limit(self):
        """max_items should not truncate if within limit."""
        items = [{'id': i} for i in range(3)]
        result = apply_budget_limits(items, max_items=5)

        assert result['meta']['truncated'] is False
        assert result['meta']['reason'] is None
        assert len(result['items']) == 3

    def test_max_bytes_truncation(self):
        """max_bytes should truncate based on size."""
        items = [{'data': 'x' * 100} for _ in range(10)]
        result = apply_budget_limits(items, max_bytes=500)

        assert result['meta']['truncated'] is True
        assert result['meta']['reason'] == 'max_bytes_exceeded'
        assert len(result['items']) < 10

    def test_max_bytes_within_limit(self):
        """max_bytes should not truncate if within limit."""
        items = [{'id': i} for i in range(3)]
        result = apply_budget_limits(items, max_bytes=10000)

        assert result['meta']['truncated'] is False
        assert len(result['items']) == 3

    def test_truncate_strings(self):
        """truncate_strings should truncate long string values."""
        items = [
            {'name': 'short'},
            {'name': 'this is a very long string that should be truncated'},
        ]
        result = apply_budget_limits(items, truncate_strings=20)

        assert len(result['items'][0]['name']) <= 23  # 20 + '...'
        assert len(result['items'][1]['name']) == 23  # 20 + '...'
        assert result['items'][1]['name'].endswith('...')

    def test_next_cursor_in_metadata(self):
        """Truncated results should include next_cursor."""
        items = [{'id': i} for i in range(10)]
        result = apply_budget_limits(items, max_items=5)

        assert 'next_cursor' in result['meta']
        assert result['meta']['next_cursor'] == 'offset=5'

    def test_no_truncation_no_cursor(self):
        """Non-truncated results should not include next_cursor."""
        items = [{'id': i} for i in range(3)]
        result = apply_budget_limits(items, max_items=5)

        assert 'next_cursor' not in result['meta']


class TestStringTruncation:
    """Test string truncation utilities."""

    def test_truncate_string_values_basic(self):
        """_truncate_string_values should truncate long strings."""
        items = [
            {'text': 'short'},
            {'text': 'this is a very long string'},
        ]
        result = _truncate_string_values(items, 10)

        assert result[0]['text'] == 'short'
        assert result[1]['text'] == 'this is a ...'

    def test_truncate_string_values_nested_dict(self):
        """_truncate_string_values should handle nested dicts."""
        items = [
            {'data': {'nested': 'very long nested string that needs truncation'}},
        ]
        result = _truncate_string_values(items, 10)

        assert result[0]['data']['nested'] == 'very long ...'

    def test_truncate_string_values_list(self):
        """_truncate_string_values should handle lists."""
        items = [
            {'tags': ['short', 'this is a very long tag']},
        ]
        result = _truncate_string_values(items, 10)

        assert result[0]['tags'][0] == 'short'
        assert result[0]['tags'][1] == 'this is a ...'

    def test_truncate_string_values_list_of_dicts(self):
        """_truncate_string_values should handle lists of dicts."""
        items = [
            {'entries': [{'text': 'very long text in list'}]},
        ]
        result = _truncate_string_values(items, 10)

        assert result[0]['entries'][0]['text'] == 'very long ...'

    def test_truncate_dict_strings_basic(self):
        """_truncate_dict_strings should truncate strings in dict."""
        d = {'text': 'very long string here'}
        result = _truncate_dict_strings(d, 10)

        assert result['text'] == 'very long ...'

    def test_truncate_dict_strings_nested(self):
        """_truncate_dict_strings should handle nested dicts recursively."""
        d = {
            'level1': {
                'level2': {
                    'text': 'deeply nested long string'
                }
            }
        }
        result = _truncate_dict_strings(d, 10)

        assert result['level1']['level2']['text'] == 'deeply nes...'

    def test_truncate_dict_strings_list(self):
        """_truncate_dict_strings should handle lists in dicts."""
        d = {'items': ['short', 'very long string in list']}
        result = _truncate_dict_strings(d, 10)

        assert result['items'][0] == 'short'
        assert result['items'][1] == 'very long ...'

    def test_truncate_dict_strings_list_of_dicts(self):
        """_truncate_dict_strings should handle lists of dicts recursively."""
        d = {'entries': [{'text': 'long text here'}]}
        result = _truncate_dict_strings(d, 10)

        assert result['entries'][0]['text'] == 'long text ...'
