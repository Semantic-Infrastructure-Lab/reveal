"""Tests for query parsing utilities."""

import pytest
from reveal.utils.query import (
    coerce_value,
    parse_query_params,
    parse_query_filters,
    QueryFilter,
    apply_filter,
    apply_filters,
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
