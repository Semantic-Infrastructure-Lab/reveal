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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
