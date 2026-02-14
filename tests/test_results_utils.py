"""Tests for reveal/utils/results.py - Output Contract result builders.

Tests ResultBuilder class and convenience functions for creating standardized
result dictionaries compliant with Output Contract v1.0 and v1.1 specifications.
"""

import pytest
from pathlib import Path
from reveal.utils.results import (
    ResultBuilder,
    create_result,
    create_error_result,
    create_meta
)


class TestResultBuilderCreate:
    """Test ResultBuilder.create() for standard results."""

    def test_minimal_v10_result(self, tmp_path):
        """Create minimal v1.0 result with file source."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = ResultBuilder.create(
            result_type='ast_query',
            source=test_file
        )

        assert result['contract_version'] == '1.0'
        assert result['type'] == 'ast_query'
        assert result['source'] == str(test_file)
        assert result['source_type'] == 'file'
        assert 'meta' not in result
        assert 'data' not in result

    def test_v10_result_with_data(self, tmp_path):
        """Create v1.0 result with adapter-specific data."""
        test_dir = tmp_path / "src"
        test_dir.mkdir()

        result = ResultBuilder.create(
            result_type='stats_summary',
            source=test_dir,
            data={
                'summary': {'total_files': 10, 'total_lines': 500},
                'files': ['file1.py', 'file2.py']
            }
        )

        assert result['contract_version'] == '1.0'
        assert result['type'] == 'stats_summary'
        assert result['source'] == str(test_dir)
        assert result['source_type'] == 'directory'
        assert result['summary'] == {'total_files': 10, 'total_lines': 500}
        assert result['files'] == ['file1.py', 'file2.py']

    def test_v11_result_with_meta(self, tmp_path):
        """Create v1.1 result with parse metadata."""
        test_file = tmp_path / "module.py"
        test_file.write_text("def foo(): pass")

        result = ResultBuilder.create(
            result_type='ast_query',
            source=test_file,
            data={'functions': ['foo']},
            contract_version='1.1',
            parse_mode='tree_sitter_full',
            confidence=0.98
        )

        assert result['contract_version'] == '1.1'
        assert result['type'] == 'ast_query'
        assert result['functions'] == ['foo']
        assert 'meta' in result
        assert result['meta']['parse_mode'] == 'tree_sitter_full'
        assert result['meta']['confidence'] == 0.98
        assert result['meta']['warnings'] == []
        assert result['meta']['errors'] == []

    def test_v11_result_with_warnings_errors(self, tmp_path):
        """Create v1.1 result with warnings and errors in meta."""
        test_file = tmp_path / "broken.py"
        test_file.write_text("invalid syntax here")

        warnings = [
            {'code': 'W001', 'message': 'Deprecated syntax', 'line': 10}
        ]
        errors = [
            {'code': 'E002', 'message': 'Parse failed', 'fallback': 'regex'}
        ]

        result = ResultBuilder.create(
            result_type='ast_query',
            source=test_file,
            contract_version='1.1',
            parse_mode='fallback',
            confidence=0.65,
            warnings=warnings,
            errors=errors
        )

        assert result['meta']['warnings'] == warnings
        assert result['meta']['errors'] == errors
        assert result['meta']['parse_mode'] == 'fallback'
        assert result['meta']['confidence'] == 0.65

    def test_string_source_path(self, tmp_path):
        """Accept string source paths."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = ResultBuilder.create(
            result_type='content',
            source=str(test_file)
        )

        assert result['source'] == str(test_file)
        assert result['source_type'] == 'file'

    def test_extra_fields(self, tmp_path):
        """Support extra custom fields in result."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = ResultBuilder.create(
            result_type='custom',
            source=test_file,
            custom_field='custom_value',
            another_field=42
        )

        assert result['custom_field'] == 'custom_value'
        assert result['another_field'] == 42

    def test_v11_no_meta_if_no_metadata(self, tmp_path):
        """Don't add meta dict in v1.1 if no metadata provided."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = ResultBuilder.create(
            result_type='query',
            source=test_file,
            contract_version='1.1'
        )

        assert result['contract_version'] == '1.1'
        assert 'meta' not in result

    def test_empty_data_dict(self, tmp_path):
        """Handle empty data dictionary."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = ResultBuilder.create(
            result_type='query',
            source=test_file,
            data={}
        )

        # Empty dict should not add any fields
        assert 'data' not in result
        assert len(result) == 4  # version, type, source, source_type

    def test_none_data_dict(self, tmp_path):
        """Handle None data (default parameter)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = ResultBuilder.create(
            result_type='query',
            source=test_file,
            data=None
        )

        assert 'data' not in result


class TestResultBuilderCreateError:
    """Test ResultBuilder.create_error() for error results."""

    def test_basic_error_result(self, tmp_path):
        """Create basic error result."""
        missing = tmp_path / "missing.py"

        result = ResultBuilder.create_error(
            result_type='ast_query',
            source=missing,
            error='File not found'
        )

        assert result['contract_version'] == '1.0'
        assert result['type'] == 'ast_query'
        assert result['source'] == str(missing)
        assert result['source_type'] == 'file'
        assert result['error'] == 'File not found'

    def test_error_with_string_source(self):
        """Create error with string source path."""
        result = ResultBuilder.create_error(
            result_type='stats',
            source='/missing/directory',
            error='Directory not accessible'
        )

        assert result['source'] == '/missing/directory'
        assert result['error'] == 'Directory not accessible'

    def test_error_with_v11_contract(self, tmp_path):
        """Create v1.1 error result."""
        test_file = tmp_path / "broken.py"
        test_file.write_text("invalid")

        result = ResultBuilder.create_error(
            result_type='parse',
            source=test_file,
            error='Syntax error on line 5',
            contract_version='1.1'
        )

        assert result['contract_version'] == '1.1'
        assert result['error'] == 'Syntax error on line 5'

    def test_error_with_extra_fields(self, tmp_path):
        """Include extra fields in error result."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = ResultBuilder.create_error(
            result_type='query',
            source=test_file,
            error='Query failed',
            error_code='E001',
            stack_trace='...'
        )

        assert result['error'] == 'Query failed'
        assert result['error_code'] == 'E001'
        assert result['stack_trace'] == '...'


class TestResultBuilderCreateMeta:
    """Test ResultBuilder._create_meta() for v1.1 metadata."""

    def test_empty_meta(self):
        """Create meta dict with empty warnings/errors when no params provided."""
        meta = ResultBuilder._create_meta()

        # Always includes warnings/errors arrays (even if empty)
        assert meta == {'warnings': [], 'errors': []}

    def test_parse_mode_only(self):
        """Include only parse_mode."""
        meta = ResultBuilder._create_meta(parse_mode='tree_sitter_full')

        assert meta['parse_mode'] == 'tree_sitter_full'
        assert meta['warnings'] == []
        assert meta['errors'] == []

    def test_confidence_only(self):
        """Include only confidence score."""
        meta = ResultBuilder._create_meta(confidence=0.85)

        assert meta['confidence'] == 0.85
        assert meta['warnings'] == []
        assert meta['errors'] == []

    def test_confidence_clamping_upper(self):
        """Clamp confidence to max 1.0."""
        meta = ResultBuilder._create_meta(confidence=1.5)

        assert meta['confidence'] == 1.0

    def test_confidence_clamping_lower(self):
        """Clamp confidence to min 0.0."""
        meta = ResultBuilder._create_meta(confidence=-0.3)

        assert meta['confidence'] == 0.0

    def test_warnings_list(self):
        """Include warnings list."""
        warnings = [
            {'code': 'W001', 'message': 'Deprecated'},
            {'code': 'W002', 'message': 'Unused import'}
        ]
        meta = ResultBuilder._create_meta(warnings=warnings)

        assert meta['warnings'] == warnings
        assert meta['errors'] == []

    def test_errors_list(self):
        """Include errors list."""
        errors = [
            {'code': 'E001', 'message': 'Parse failure', 'fallback': 'regex'}
        ]
        meta = ResultBuilder._create_meta(errors=errors)

        assert meta['errors'] == errors
        assert meta['warnings'] == []

    def test_full_meta(self):
        """Create meta with all fields."""
        warnings = [{'code': 'W001', 'message': 'Warning'}]
        errors = [{'code': 'E001', 'message': 'Error'}]

        meta = ResultBuilder._create_meta(
            parse_mode='tree_sitter_partial',
            confidence=0.75,
            warnings=warnings,
            errors=errors
        )

        assert meta['parse_mode'] == 'tree_sitter_partial'
        assert meta['confidence'] == 0.75
        assert meta['warnings'] == warnings
        assert meta['errors'] == errors

    def test_empty_warnings_list(self):
        """Empty warnings list sets to empty array."""
        meta = ResultBuilder._create_meta(warnings=[])

        assert meta['warnings'] == []

    def test_empty_errors_list(self):
        """Empty errors list sets to empty array."""
        meta = ResultBuilder._create_meta(errors=[])

        assert meta['errors'] == []


class TestResultBuilderPagination:
    """Test ResultBuilder.add_pagination_meta()."""

    def test_basic_pagination(self):
        """Add basic pagination metadata."""
        result = {'type': 'query', 'results': [1, 2, 3]}

        ResultBuilder.add_pagination_meta(
            result,
            total=100,
            displayed=25
        )

        assert result['pagination']['total'] == 100
        assert result['pagination']['displayed'] == 25
        assert result['pagination']['offset'] == 0
        assert result['pagination']['truncated'] is True

    def test_pagination_with_offset_limit(self):
        """Add pagination with explicit offset and limit."""
        result = {'type': 'query', 'results': []}

        ResultBuilder.add_pagination_meta(
            result,
            total=100,
            displayed=25,
            offset=25,
            limit=25
        )

        assert result['pagination']['offset'] == 25
        assert result['pagination']['limit'] == 25
        assert result['pagination']['truncated'] is True

    def test_pagination_not_truncated(self):
        """Mark pagination as not truncated when all shown."""
        result = {'results': []}

        ResultBuilder.add_pagination_meta(
            result,
            total=10,
            displayed=10
        )

        assert result['pagination']['truncated'] is False

    def test_pagination_returns_result(self):
        """Method returns modified result for chaining."""
        original = {'data': 'test'}

        returned = ResultBuilder.add_pagination_meta(
            original,
            total=50,
            displayed=20
        )

        assert returned is original
        assert 'pagination' in returned

    def test_pagination_without_limit(self):
        """Pagination without explicit limit."""
        result = {}

        ResultBuilder.add_pagination_meta(
            result,
            total=100,
            displayed=100
        )

        assert 'limit' not in result['pagination']
        assert result['pagination']['offset'] == 0


class TestResultBuilderTruncation:
    """Test ResultBuilder.add_truncation_warning()."""

    def test_truncation_warning_added(self):
        """Add warning when results truncated."""
        result = {'results': []}

        ResultBuilder.add_truncation_warning(
            result,
            displayed=25,
            total=100
        )

        assert result['warning'] == 'Results truncated: showing 25 of 100 matches'

    def test_truncation_warning_with_limit(self):
        """Include limit in warning message."""
        result = {}

        ResultBuilder.add_truncation_warning(
            result,
            displayed=25,
            total=100,
            limit=25
        )

        assert result['warning'] == 'Results truncated: showing 25 of 100 matches (limit=25)'

    def test_no_warning_when_not_truncated(self):
        """Don't add warning when all results shown."""
        result = {}

        ResultBuilder.add_truncation_warning(
            result,
            displayed=50,
            total=50
        )

        assert 'warning' not in result

    def test_truncation_returns_result(self):
        """Method returns modified result for chaining."""
        original = {'data': 'test'}

        returned = ResultBuilder.add_truncation_warning(
            original,
            displayed=10,
            total=100
        )

        assert returned is original

    def test_no_warning_when_displayed_exceeds_total(self):
        """Handle edge case where displayed > total."""
        result = {}

        ResultBuilder.add_truncation_warning(
            result,
            displayed=100,
            total=50
        )

        assert 'warning' not in result


class TestConvenienceFunctions:
    """Test convenience wrapper functions."""

    def test_create_result_wrapper(self, tmp_path):
        """Test create_result() convenience function."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = create_result(
            result_type='query',
            source=test_file,
            data={'items': [1, 2, 3]}
        )

        assert result['type'] == 'query'
        assert result['items'] == [1, 2, 3]

    def test_create_result_with_kwargs(self, tmp_path):
        """Pass kwargs through create_result()."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = create_result(
            result_type='query',
            source=test_file,
            contract_version='1.1',
            parse_mode='tree_sitter_full'
        )

        assert result['contract_version'] == '1.1'
        assert 'meta' in result

    def test_create_error_result_wrapper(self, tmp_path):
        """Test create_error_result() convenience function."""
        test_file = tmp_path / "missing.py"

        result = create_error_result(
            result_type='parse',
            source=test_file,
            error='File not found'
        )

        assert result['type'] == 'parse'
        assert result['error'] == 'File not found'

    def test_create_meta_wrapper(self):
        """Test create_meta() convenience function."""
        meta = create_meta(
            parse_mode='regex',
            confidence=0.8
        )

        assert meta['parse_mode'] == 'regex'
        assert meta['confidence'] == 0.8
        assert meta['warnings'] == []
        assert meta['errors'] == []


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_nonexistent_path_source_type(self):
        """Handle nonexistent paths (defaults to file)."""
        result = ResultBuilder.create(
            result_type='test',
            source='/nonexistent/path/file.py'
        )

        # Nonexistent paths default to file type
        assert result['source_type'] == 'file'

    def test_data_overwrites_core_fields(self, tmp_path):
        """Data dict can overwrite core fields (by design)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = ResultBuilder.create(
            result_type='query',
            source=test_file,
            data={
                'type': 'different_type',  # Overwrites core field
                'custom': 'value'
            }
        )

        # Data overwrites happen in update()
        assert result['type'] == 'different_type'
        assert result['custom'] == 'value'

    def test_extra_fields_overwrite_data(self, tmp_path):
        """Extra fields can overwrite data fields."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        result = ResultBuilder.create(
            result_type='query',
            source=test_file,
            data={'field': 'from_data'},
            field='from_extra'
        )

        # Extra fields applied after data
        assert result['field'] == 'from_extra'

    def test_confidence_edge_values(self):
        """Test confidence boundary values."""
        # Exactly 0.0
        meta = ResultBuilder._create_meta(confidence=0.0)
        assert meta['confidence'] == 0.0

        # Exactly 1.0
        meta = ResultBuilder._create_meta(confidence=1.0)
        assert meta['confidence'] == 1.0

        # Very large
        meta = ResultBuilder._create_meta(confidence=999.9)
        assert meta['confidence'] == 1.0

        # Very negative
        meta = ResultBuilder._create_meta(confidence=-999.9)
        assert meta['confidence'] == 0.0
