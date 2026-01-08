"""Tests for front matter schema loader.

Tests schema loading, caching, validation, and built-in schemas.
"""

import pytest
import tempfile
import yaml
from pathlib import Path

from reveal.schemas.frontmatter import (
    SchemaLoader,
    load_schema,
    list_schemas,
    clear_cache
)


class TestSchemaLoading:
    """Test schema loading from names and paths."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()

    def test_load_builtin_schema_by_name(self):
        """Test loading session.yaml by name 'session'."""
        schema = load_schema('session')
        assert schema is not None
        assert schema['name'] == 'Session/Workflow Schema'
        assert 'required_fields' in schema
        assert 'session_id' in schema['required_fields']
        assert 'topics' in schema['required_fields']

    def test_load_builtin_schema_with_yaml_extension(self):
        """Test loading schema with .yaml extension works."""
        schema = load_schema('session.yaml')
        assert schema is not None
        assert schema['name'] == 'Session/Workflow Schema'

    def test_load_nonexistent_schema(self):
        """Test loading nonexistent schema returns None."""
        schema = load_schema('nonexistent')
        assert schema is None

    def test_load_custom_schema_by_path(self):
        """Test loading schema from file path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            custom_schema = {
                'name': 'Custom Schema',
                'required_fields': ['title']
            }
            yaml.dump(custom_schema, f)
            temp_path = f.name

        try:
            schema = load_schema(temp_path)
            assert schema is not None
            assert schema['name'] == 'Custom Schema'
            assert schema['required_fields'] == ['title']
        finally:
            Path(temp_path).unlink()

    def test_load_custom_schema_by_relative_path(self):
        """Test loading schema from relative path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, dir='.') as f:
            custom_schema = {
                'name': 'Relative Schema',
                'required_fields': ['author']
            }
            yaml.dump(custom_schema, f)
            temp_name = Path(f.name).name

        try:
            schema = load_schema(temp_name)
            assert schema is not None
            assert schema['name'] == 'Relative Schema'
        finally:
            Path(temp_name).unlink()


class TestSchemaCaching:
    """Test schema caching behavior."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()

    def test_schema_caching(self):
        """Test schemas are cached after first load."""
        schema1 = load_schema('session')
        schema2 = load_schema('session')
        # Should be the exact same object (cached)
        assert schema1 is schema2

    def test_cache_per_name(self):
        """Test different schema names cached separately."""
        schema1 = load_schema('session')

        # Create temporary custom schema
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            custom = {'name': 'Custom', 'required_fields': ['x']}
            yaml.dump(custom, f)
            temp_path = f.name

        try:
            schema2 = load_schema(temp_path)
            assert schema1 is not schema2
            assert schema1['name'] != schema2['name']
        finally:
            Path(temp_path).unlink()

    def test_clear_cache(self):
        """Test cache can be cleared."""
        schema1 = load_schema('session')
        clear_cache()
        schema2 = load_schema('session')
        # Should be different objects after cache clear
        assert schema1 is not schema2
        # But same content
        assert schema1['name'] == schema2['name']


class TestSchemaValidation:
    """Test schema structure validation."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()

    def test_schema_missing_name_field(self):
        """Test schema without 'name' field is rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            invalid_schema = {
                'required_fields': ['title']
                # Missing 'name' field
            }
            yaml.dump(invalid_schema, f)
            temp_path = f.name

        try:
            schema = load_schema(temp_path)
            assert schema is None  # Should be rejected
        finally:
            Path(temp_path).unlink()

    def test_schema_no_constraint_fields(self):
        """Test schema without any constraint fields is rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            invalid_schema = {
                'name': 'Invalid Schema',
                'description': 'Has no constraint fields'
                # Missing required_fields, field_types, etc.
            }
            yaml.dump(invalid_schema, f)
            temp_path = f.name

        try:
            schema = load_schema(temp_path)
            assert schema is None  # Should be rejected
        finally:
            Path(temp_path).unlink()

    def test_schema_with_required_fields_only(self):
        """Test schema with only required_fields is valid."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            valid_schema = {
                'name': 'Minimal Schema',
                'required_fields': ['title']
            }
            yaml.dump(valid_schema, f)
            temp_path = f.name

        try:
            schema = load_schema(temp_path)
            assert schema is not None
            assert schema['name'] == 'Minimal Schema'
        finally:
            Path(temp_path).unlink()

    def test_schema_with_field_types_only(self):
        """Test schema with only field_types is valid."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            valid_schema = {
                'name': 'Type Schema',
                'field_types': {'title': 'string'}
            }
            yaml.dump(valid_schema, f)
            temp_path = f.name

        try:
            schema = load_schema(temp_path)
            assert schema is not None
        finally:
            Path(temp_path).unlink()

    def test_empty_schema_file(self):
        """Test empty YAML file is rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('')  # Empty file
            temp_path = f.name

        try:
            schema = load_schema(temp_path)
            assert schema is None
        finally:
            Path(temp_path).unlink()

    def test_malformed_yaml(self):
        """Test malformed YAML is rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('name: "Test\ninvalid: yaml: structure')
            temp_path = f.name

        try:
            schema = load_schema(temp_path)
            assert schema is None
        finally:
            Path(temp_path).unlink()


class TestBuiltinSchemas:
    """Test built-in schemas."""

    def test_list_builtin_schemas(self):
        """Test listing built-in schemas."""
        schemas = list_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) >= 1  # At least session
        assert 'session' in schemas
        # Should be sorted
        assert schemas == sorted(schemas)

    def test_session_schema_structure(self):
        """Test session schema has expected structure."""
        schema = load_schema('session')
        assert schema is not None
        assert schema['name'] == 'Session/Workflow Schema'
        assert 'description' in schema
        assert 'version' in schema

        # Required fields
        assert 'required_fields' in schema
        assert 'session_id' in schema['required_fields']
        assert 'topics' in schema['required_fields']

        # Field types
        assert 'field_types' in schema
        assert schema['field_types']['session_id'] == 'string'
        assert schema['field_types']['topics'] == 'list'

        # Validation rules
        assert 'validation_rules' in schema
        assert len(schema['validation_rules']) >= 2

    def test_session_schema_validation_rules(self):
        """Test session schema has proper validation rules."""
        schema = load_schema('session')
        rules = schema['validation_rules']

        # Should have session_id pattern rule
        session_id_rule = next((r for r in rules if r['field'] == 'session_id'), None)
        assert session_id_rule is not None
        assert session_id_rule['code'] == 'F005'
        assert 're.match' in session_id_rule['check']

        # Should have topics length rule
        topics_rule = next((r for r in rules if r['field'] == 'topics'), None)
        assert topics_rule is not None
        assert topics_rule['code'] == 'F005'
        assert 'len(value)' in topics_rule['check']


class TestSchemaLoaderClass:
    """Test SchemaLoader class methods."""

    def setup_method(self):
        """Clear cache before each test."""
        SchemaLoader.clear_cache()

    def test_resolve_schema_path_builtin(self):
        """Test resolving built-in schema name to path."""
        path = SchemaLoader._resolve_schema_path('session')
        assert path is not None
        assert path.exists()
        assert path.name == 'session.yaml'

    def test_resolve_schema_path_with_extension(self):
        """Test resolving schema name with .yaml extension."""
        path = SchemaLoader._resolve_schema_path('session.yaml')
        assert path is not None
        assert path.exists()

    def test_resolve_schema_path_absolute(self):
        """Test resolving absolute file path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('name: Test\nrequired_fields: [x]')
            temp_path = f.name

        try:
            path = SchemaLoader._resolve_schema_path(temp_path)
            assert path is not None
            assert path.exists()
            assert path == Path(temp_path).resolve()
        finally:
            Path(temp_path).unlink()

    def test_resolve_schema_path_nonexistent(self):
        """Test resolving nonexistent schema returns None."""
        path = SchemaLoader._resolve_schema_path('does-not-exist')
        assert path is None

    def test_validate_schema_structure_valid(self):
        """Test valid schema passes structure validation."""
        valid_schema = {
            'name': 'Test Schema',
            'required_fields': ['title']
        }
        assert SchemaLoader._validate_schema_structure(valid_schema)

    def test_validate_schema_structure_missing_name(self):
        """Test schema missing name fails validation."""
        invalid_schema = {
            'required_fields': ['title']
        }
        assert not SchemaLoader._validate_schema_structure(invalid_schema)

    def test_validate_schema_structure_no_constraints(self):
        """Test schema with no constraints fails validation."""
        invalid_schema = {
            'name': 'Test Schema',
            'description': 'No constraints'
        }
        assert not SchemaLoader._validate_schema_structure(invalid_schema)


class TestPublicAPI:
    """Test public API functions."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()

    def test_load_schema_function(self):
        """Test public load_schema function."""
        schema = load_schema('session')
        assert schema is not None
        assert isinstance(schema, dict)

    def test_list_schemas_function(self):
        """Test public list_schemas function."""
        schemas = list_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) >= 1

    def test_clear_cache_function(self):
        """Test public clear_cache function."""
        schema1 = load_schema('session')
        clear_cache()
        schema2 = load_schema('session')
        assert schema1 is not schema2
