"""Tests for demo adapter."""

import pytest
from reveal.adapters.demo import DemoAdapter, DemoRenderer


class TestDemoAdapterInit:
    """Tests for adapter initialization."""

    def test_init_no_params(self):
        """Test adapter initialization without parameters."""
        adapter = DemoAdapter()
        assert adapter.resource is None
        assert adapter.query_params == {}

    def test_init_with_resource(self):
        """Test adapter initialization with resource."""
        adapter = DemoAdapter(resource='test_resource')
        assert adapter.resource == 'test_resource'

    def test_init_with_query_params(self):
        """Test adapter initialization with query parameters."""
        adapter = DemoAdapter(resource='test', limit=10, sort='name')
        assert adapter.resource == 'test'
        assert adapter.query_params['limit'] == 10
        assert adapter.query_params['sort'] == 'name'


class TestDemoAdapterSchema:
    """Tests for adapter schema."""

    def test_get_schema_returns_dict(self):
        """Test that get_schema returns a dictionary."""
        schema = DemoAdapter.get_schema()
        assert isinstance(schema, dict)

    def test_schema_has_required_fields(self):
        """Test that schema contains required fields."""
        schema = DemoAdapter.get_schema()
        assert 'adapter' in schema
        assert 'description' in schema
        assert 'uri_syntax' in schema
        assert schema['adapter'] == 'demo'

    def test_schema_has_examples(self):
        """Test that schema includes example queries."""
        schema = DemoAdapter.get_schema()
        assert 'example_queries' in schema
        assert len(schema['example_queries']) > 0


class TestDemoAdapterHelp:
    """Tests for adapter help system."""

    def test_get_help_returns_dict(self):
        """Test that get_help returns a dictionary."""
        help_doc = DemoAdapter.get_help()
        assert isinstance(help_doc, dict)

    def test_help_has_required_fields(self):
        """Test that help contains required fields."""
        help_doc = DemoAdapter.get_help()
        assert 'name' in help_doc
        assert 'description' in help_doc
        assert 'syntax' in help_doc
        assert 'examples' in help_doc

    def test_help_has_try_now_examples(self):
        """Test that help includes executable examples."""
        help_doc = DemoAdapter.get_help()
        assert 'try_now' in help_doc
        assert len(help_doc['try_now']) > 0


class TestDemoAdapterStructure:
    """Tests for get_structure method."""

    def test_get_structure_returns_dict(self):
        """Test that get_structure returns a dictionary."""
        adapter = DemoAdapter()
        result = adapter.get_structure()
        assert isinstance(result, dict)

    def test_structure_has_contract_version(self):
        """Test that structure includes contract version."""
        adapter = DemoAdapter()
        result = adapter.get_structure()
        assert 'contract_version' in result

    def test_structure_has_type_field(self):
        """Test that structure includes type field."""
        adapter = DemoAdapter()
        result = adapter.get_structure()
        assert 'type' in result
        assert result['type'] == 'demo_structure'


class TestDemoAdapterElement:
    """Tests for get_element method."""

    def test_get_element_returns_dict_or_none(self):
        """Test that get_element returns dict or None."""
        adapter = DemoAdapter()
        result = adapter.get_element('test_element')
        assert result is None or isinstance(result, dict)

    # TODO: Add tests for actual element retrieval
    # def test_get_element_valid_name(self):
    #     adapter = DemoAdapter()
    #     result = adapter.get_element('known_element')
    #     assert result is not None
    #     assert result['name'] == 'known_element'


class TestDemoAdapterMetadata:
    """Tests for get_metadata method."""

    def test_get_metadata_returns_dict(self):
        """Test that get_metadata returns a dictionary."""
        adapter = DemoAdapter()
        metadata = adapter.get_metadata()
        assert isinstance(metadata, dict)

    def test_metadata_has_type(self):
        """Test that metadata includes type field."""
        adapter = DemoAdapter()
        metadata = adapter.get_metadata()
        assert 'type' in metadata


class TestDemoRenderer:
    """Tests for renderer methods."""

    def test_render_structure_text_format(self, capsys):
        """Test text format rendering."""
        result = {
            'type': 'demo_structure',
            'items': [{'name': 'test'}]
        }
        DemoRenderer.render_structure(result, 'text')
        captured = capsys.readouterr()
        assert 'Demo' in captured.out

    def test_render_structure_json_format(self, capsys):
        """Test JSON format rendering."""
        result = {
            'type': 'demo_structure',
            'items': []
        }
        DemoRenderer.render_structure(result, 'json')
        captured = capsys.readouterr()
        assert '{' in captured.out  # JSON output


# TODO: Add integration tests
# class TestDemoAdapterIntegration:
#     """Integration tests for demo adapter."""
#
#     def test_full_workflow(self):
#         """Test complete adapter workflow."""
#         adapter = DemoAdapter()
#         structure = adapter.get_structure()
#         assert len(structure['items']) > 0
