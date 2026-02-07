"""Tests for query parsing utilities."""

import pytest
from reveal.utils.query import (
    coerce_value,
    parse_query_params,
    parse_query_filters,
    QueryFilter,
    apply_filter,
    apply_filters,
    parse_result_control,
    apply_result_control,
    ResultControl,
)


class TestCoerceValue:
    """Tests for value coercion."""

    def test_boolean_true_variants(self):
        assert coerce_value('true') is True
        assert coerce_value('True') is True
        assert coerce_value('TRUE') is True
        assert coerce_value('1') is True
        assert coerce_value('yes') is True
        assert coerce_value('Yes') is True

    def test_boolean_false_variants(self):
        assert coerce_value('false') is False
        assert coerce_value('False') is False
        assert coerce_value('FALSE') is False
        assert coerce_value('0') is False
        assert coerce_value('no') is False
        assert coerce_value('No') is False

    def test_integer_coercion(self):
        assert coerce_value('42') == 42
        assert coerce_value('-10') == -10
        assert coerce_value('0') is False  # 0 is coerced to bool False

    def test_float_coercion(self):
        assert coerce_value('3.14') == 3.14
        assert coerce_value('-2.5') == -2.5
        assert coerce_value('0.0') == 0.0

    def test_string_passthrough(self):
        assert coerce_value('hello') == 'hello'
        assert coerce_value('world') == 'world'
        assert coerce_value('') == ''


class TestParseQueryParams:
    """Tests for simple key=value parsing."""

    def test_empty_query(self):
        assert parse_query_params('') == {}
        assert parse_query_params(None) == {}

    def test_single_key_value(self):
        assert parse_query_params('key=value') == {'key': 'value'}

    def test_multiple_key_values(self):
        result = parse_query_params('a=1&b=2&c=3')
        assert result == {'a': '1', 'b': '2', 'c': '3'}

    def test_bare_keyword(self):
        assert parse_query_params('errors') == {'errors': True}
        assert parse_query_params('summary') == {'summary': True}

    def test_mixed_keywords_and_values(self):
        result = parse_query_params('tools=Bash&errors')
        assert result == {'tools': 'Bash', 'errors': True}

    def test_coercion_disabled(self):
        result = parse_query_params('count=42&active=true', coerce=False)
        assert result == {'count': '42', 'active': 'true'}

    def test_coercion_enabled(self):
        result = parse_query_params('count=42&active=true', coerce=True)
        assert result == {'count': 42, 'active': True}

    def test_whitespace_handling(self):
        result = parse_query_params('  key = value  &  other = test  ')
        assert result == {'key': 'value', 'other': 'test'}

    def test_empty_parts_skipped(self):
        result = parse_query_params('a=1&&b=2&')
        assert result == {'a': '1', 'b': '2'}


class TestQueryFilter:
    """Tests for QueryFilter dataclass."""

    def test_valid_operators(self):
        for op in ['=', '>', '<', '>=', '<=', '!', '?', '*']:
            f = QueryFilter('field', op, 'value')
            assert f.op == op

    def test_invalid_operator(self):
        with pytest.raises(ValueError):
            QueryFilter('field', '~', 'value')


class TestParseQueryFilters:
    """Tests for operator-aware filter parsing."""

    def test_empty_query(self):
        assert parse_query_filters('') == []
        assert parse_query_filters(None) == []

    def test_equality_filter(self):
        filters = parse_query_filters('type=function')
        assert len(filters) == 1
        assert filters[0] == QueryFilter('type', '=', 'function')

    def test_comparison_filters(self):
        filters = parse_query_filters('lines>50')
        assert filters[0] == QueryFilter('lines', '>', 50)

        filters = parse_query_filters('lines<100')
        assert filters[0] == QueryFilter('lines', '<', 100)

        filters = parse_query_filters('lines>=50')
        assert filters[0] == QueryFilter('lines', '>=', 50)

        filters = parse_query_filters('lines<=100')
        assert filters[0] == QueryFilter('lines', '<=', 100)

    def test_missing_field_operator(self):
        filters = parse_query_filters('!draft')
        assert filters[0] == QueryFilter('draft', '!', '')

    def test_existence_check(self):
        filters = parse_query_filters('tags')
        assert filters[0] == QueryFilter('tags', '?', '')

    def test_wildcard_filter(self):
        filters = parse_query_filters('name=*test*')
        assert filters[0] == QueryFilter('name', '*', '*test*')

    def test_multiple_filters(self):
        filters = parse_query_filters('lines>50&type=function&!draft')
        assert len(filters) == 3
        assert filters[0] == QueryFilter('lines', '>', 50)
        assert filters[1] == QueryFilter('type', '=', 'function')
        assert filters[2] == QueryFilter('draft', '!', '')

    def test_numeric_coercion_disabled(self):
        filters = parse_query_filters('lines>50', coerce_numeric=False)
        assert filters[0].value == '50'

    def test_existence_support_disabled(self):
        filters = parse_query_filters('!draft&bare', support_existence=False)
        # With existence disabled, !draft and bare are skipped
        assert len(filters) == 0


class TestApplyFilter:
    """Tests for applying filters to items."""

    def test_equality_match(self):
        item = {'type': 'function'}
        assert apply_filter(item, QueryFilter('type', '=', 'function'))
        assert not apply_filter(item, QueryFilter('type', '=', 'class'))

    def test_greater_than(self):
        item = {'lines': 100}
        assert apply_filter(item, QueryFilter('lines', '>', 50))
        assert not apply_filter(item, QueryFilter('lines', '>', 100))
        assert not apply_filter(item, QueryFilter('lines', '>', 150))

    def test_less_than(self):
        item = {'lines': 50}
        assert apply_filter(item, QueryFilter('lines', '<', 100))
        assert not apply_filter(item, QueryFilter('lines', '<', 50))
        assert not apply_filter(item, QueryFilter('lines', '<', 25))

    def test_greater_or_equal(self):
        item = {'lines': 100}
        assert apply_filter(item, QueryFilter('lines', '>=', 100))
        assert apply_filter(item, QueryFilter('lines', '>=', 50))
        assert not apply_filter(item, QueryFilter('lines', '>=', 150))

    def test_less_or_equal(self):
        item = {'lines': 50}
        assert apply_filter(item, QueryFilter('lines', '<=', 50))
        assert apply_filter(item, QueryFilter('lines', '<=', 100))
        assert not apply_filter(item, QueryFilter('lines', '<=', 25))

    def test_missing_field(self):
        item = {'name': 'test'}
        assert apply_filter(item, QueryFilter('draft', '!', ''))
        assert not apply_filter(item, QueryFilter('name', '!', ''))

    def test_field_exists(self):
        item = {'name': 'test'}
        assert apply_filter(item, QueryFilter('name', '?', ''))
        assert not apply_filter(item, QueryFilter('draft', '?', ''))

    def test_wildcard_match(self):
        item = {'name': 'test_function_helper'}
        assert apply_filter(item, QueryFilter('name', '*', '*function*'))
        assert apply_filter(item, QueryFilter('name', '*', '*test*'))
        assert not apply_filter(item, QueryFilter('name', '*', '*class*'))

    def test_missing_field_returns_false(self):
        item = {'name': 'test'}
        assert not apply_filter(item, QueryFilter('missing', '=', 'value'))
        assert not apply_filter(item, QueryFilter('missing', '>', 50))


class TestApplyFilters:
    """Tests for applying multiple filters."""

    def test_all_must_match(self):
        item = {'type': 'function', 'lines': 100}
        filters = [
            QueryFilter('type', '=', 'function'),
            QueryFilter('lines', '>', 50),
        ]
        assert apply_filters(item, filters)

    def test_one_fails_all_fails(self):
        item = {'type': 'function', 'lines': 30}
        filters = [
            QueryFilter('type', '=', 'function'),  # passes
            QueryFilter('lines', '>', 50),  # fails
        ]
        assert not apply_filters(item, filters)

    def test_empty_filters_always_passes(self):
        item = {'anything': 'value'}
        assert apply_filters(item, [])


class TestRealWorldScenarios:
    """Tests matching actual adapter usage patterns."""

    def test_ast_adapter_pattern(self):
        """ast.py: lines>50&type=function"""
        filters = parse_query_filters('lines>50&type=function')
        item = {'lines': 100, 'type': 'function'}
        assert apply_filters(item, filters)

        item_fails = {'lines': 30, 'type': 'function'}
        assert not apply_filters(item_fails, filters)

    def test_stats_adapter_pattern(self):
        """stats.py: hotspots=true&min_lines=50"""
        params = parse_query_params('hotspots=true&min_lines=50', coerce=True)
        assert params == {'hotspots': True, 'min_lines': 50}

    def test_claude_adapter_pattern(self):
        """claude adapter: errors&tools=Bash"""
        params = parse_query_params('errors&tools=Bash')
        assert params == {'errors': True, 'tools': 'Bash'}

    def test_markdown_adapter_pattern(self):
        """markdown.py: !draft&tags&category=*guide*"""
        filters = parse_query_filters('!draft&tags&category=*guide*')
        assert len(filters) == 3
        assert filters[0] == QueryFilter('draft', '!', '')
        assert filters[1] == QueryFilter('tags', '?', '')
        assert filters[2] == QueryFilter('category', '*', '*guide*')

        # Test with matching item
        item = {'tags': ['docs'], 'category': 'user-guide'}
        assert apply_filters(item, filters)

        # Test with non-matching item (has draft)
        item_draft = {'draft': True, 'tags': ['docs'], 'category': 'user-guide'}
        assert not apply_filters(item_draft, filters)


class TestNewOperators:
    """Tests for new operators (!=, ~=, ..)."""

    def test_not_equals_operator(self):
        """Test != (not equals) operator."""
        filters = parse_query_filters('decorator!=property')
        assert len(filters) == 1
        assert filters[0] == QueryFilter('decorator', '!=', 'property')

        # Test matching (not equals)
        item = {'decorator': 'cached'}
        assert apply_filter(item, filters[0])

        # Test non-matching (equals)
        item_property = {'decorator': 'property'}
        assert not apply_filter(item_property, filters[0])

    def test_regex_operator(self):
        """Test ~= (regex match) operator."""
        filters = parse_query_filters('name~=^test_')
        assert len(filters) == 1
        assert filters[0] == QueryFilter('name', '~=', '^test_')

        # Test matching
        item = {'name': 'test_foo'}
        assert apply_filter(item, filters[0])

        # Test non-matching
        item_no_match = {'name': 'foo_test'}
        assert not apply_filter(item_no_match, filters[0])

    def test_range_operator(self):
        """Test .. (range) operator."""
        filters = parse_query_filters('lines=50..200')
        assert len(filters) == 1
        assert filters[0] == QueryFilter('lines', '..', '50..200')

        # Test within range
        item = {'lines': 100}
        assert apply_filter(item, filters[0])

        # Test below range
        item_below = {'lines': 30}
        assert not apply_filter(item_below, filters[0])

        # Test above range
        item_above = {'lines': 300}
        assert not apply_filter(item_above, filters[0])

        # Test edge cases (inclusive)
        item_min = {'lines': 50}
        assert apply_filter(item_min, filters[0])

        item_max = {'lines': 200}
        assert apply_filter(item_max, filters[0])

    def test_combined_new_operators(self):
        """Test multiple new operators together."""
        filters = parse_query_filters('decorator!=property&name~=^test_&lines=50..200')
        assert len(filters) == 3

        # Test matching item
        item = {'decorator': 'cached', 'name': 'test_foo', 'lines': 100}
        assert apply_filters(item, filters)

        # Test non-matching (decorator)
        item_fail = {'decorator': 'property', 'name': 'test_foo', 'lines': 100}
        assert not apply_filters(item_fail, filters)


class TestResultControl:
    """Tests for result control (sort, limit, offset)."""

    def test_parse_sort_ascending(self):
        """Test parsing sort=field (ascending)."""
        query, control = parse_result_control('lines>50&sort=complexity')
        assert query == 'lines>50'
        assert control.sort_field == 'complexity'
        assert control.sort_descending is False

    def test_parse_sort_descending(self):
        """Test parsing sort=-field (descending)."""
        query, control = parse_result_control('lines>50&sort=-complexity')
        assert query == 'lines>50'
        assert control.sort_field == 'complexity'
        assert control.sort_descending is True

    def test_parse_limit(self):
        """Test parsing limit=N."""
        query, control = parse_result_control('type=function&limit=20')
        assert query == 'type=function'
        assert control.limit == 20

    def test_parse_offset(self):
        """Test parsing offset=M."""
        query, control = parse_result_control('type=function&offset=10')
        assert query == 'type=function'
        assert control.offset == 10

    def test_parse_combined_control(self):
        """Test parsing sort, limit, and offset together."""
        query, control = parse_result_control('lines>50&sort=-complexity&limit=20&offset=5')
        assert query == 'lines>50'
        assert control.sort_field == 'complexity'
        assert control.sort_descending is True
        assert control.limit == 20
        assert control.offset == 5

    def test_apply_sort_ascending(self):
        """Test applying ascending sort."""
        items = [
            {'name': 'a', 'value': 3},
            {'name': 'b', 'value': 1},
            {'name': 'c', 'value': 2}
        ]
        control = ResultControl(sort_field='value')
        result = apply_result_control(items, control)

        assert result[0]['value'] == 1
        assert result[1]['value'] == 2
        assert result[2]['value'] == 3

    def test_apply_sort_descending(self):
        """Test applying descending sort."""
        items = [
            {'name': 'a', 'value': 3},
            {'name': 'b', 'value': 1},
            {'name': 'c', 'value': 2}
        ]
        control = ResultControl(sort_field='value', sort_descending=True)
        result = apply_result_control(items, control)

        assert result[0]['value'] == 3
        assert result[1]['value'] == 2
        assert result[2]['value'] == 1

    def test_apply_limit(self):
        """Test applying limit."""
        items = [{'id': i} for i in range(10)]
        control = ResultControl(limit=3)
        result = apply_result_control(items, control)

        assert len(result) == 3
        assert result[0]['id'] == 0
        assert result[2]['id'] == 2

    def test_apply_offset(self):
        """Test applying offset."""
        items = [{'id': i} for i in range(10)]
        control = ResultControl(offset=5)
        result = apply_result_control(items, control)

        assert len(result) == 5
        assert result[0]['id'] == 5
        assert result[4]['id'] == 9

    def test_apply_offset_and_limit(self):
        """Test applying offset and limit together (pagination)."""
        items = [{'id': i} for i in range(100)]
        control = ResultControl(offset=10, limit=5)
        result = apply_result_control(items, control)

        assert len(result) == 5
        assert result[0]['id'] == 10
        assert result[4]['id'] == 14

    def test_apply_sort_limit_offset(self):
        """Test applying sort, limit, and offset together."""
        items = [
            {'name': 'item_a', 'score': 50},
            {'name': 'item_b', 'score': 80},
            {'name': 'item_c', 'score': 30},
            {'name': 'item_d', 'score': 90},
            {'name': 'item_e', 'score': 60}
        ]
        control = ResultControl(
            sort_field='score',
            sort_descending=True,
            offset=1,
            limit=2
        )
        result = apply_result_control(items, control)

        # After sorting descending: 90, 80, 60, 50, 30
        # After offset=1: 80, 60, 50, 30
        # After limit=2: 80, 60
        assert len(result) == 2
        assert result[0]['score'] == 80
        assert result[1]['score'] == 60
