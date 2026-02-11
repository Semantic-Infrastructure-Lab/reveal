"""Templates for adapter scaffolding."""

ADAPTER_TEMPLATE = '''"""{description}."""

import sys
from typing import Dict, Any, Optional
from .base import ResourceAdapter, register_adapter, register_renderer


class {class_name}Renderer:
    """Renderer for {adapter_name} adapter results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render {adapter_name} structure overview.

        Args:
            result: Structure dict from {class_name}Adapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        # TODO: Implement custom rendering or use generic renderer
        from ..main import safe_json_dumps

        if format == 'json':
            print(safe_json_dumps(result))
        else:
            # TODO: Implement text rendering
            print(f"{class_name} Structure:")
            print(f"  Type: {{result.get('type', 'unknown')}}")
            print(f"  Items: {{len(result.get('items', []))}}")

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific {adapter_name} element.

        Args:
            result: Element dict from {class_name}Adapter.get_element()
            format: Output format ('text', 'json', 'grep')
        """
        from ..main import safe_json_dumps

        if format == 'json':
            print(safe_json_dumps(result))
        else:
            # TODO: Implement element rendering
            print(f"Element: {{result.get('name', 'unknown')}}")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error accessing {adapter_name}: {{error}}", file=sys.stderr)


@register_adapter('{scheme}')
@register_renderer({class_name}Renderer)
class {class_name}Adapter(ResourceAdapter):
    """Adapter for exploring {adapter_name} resources via {scheme}:// URIs.

    Example URIs:
        {scheme}://                 # Overview of all items
        {scheme}://item_name       # Specific item details
        {scheme}://item_name?param=value  # Item with query parameters
    """

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for {scheme}:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {{
            'adapter': '{scheme}',
            'description': '{description}',
            'uri_syntax': '{scheme}://[resource_name][?query_params]',
            'query_params': {{
                # TODO: Define query parameters
                # 'limit': {{'type': 'integer', 'description': 'Max items to return'}},
                # 'sort': {{'type': 'string', 'description': 'Sort field'}},
            }},
            'elements': {{
                # TODO: Define fixed elements (or leave empty for dynamic)
                # 'overview': {{'description': 'System overview'}},
                # 'stats': {{'description': 'Statistics'}},
            }},
            'cli_flags': [
                # TODO: Define CLI-specific flags
                # {{'name': '--check', 'description': 'Run health checks'}},
            ],
            'supports_batch': False,  # TODO: Enable if batch processing supported
            'supports_advanced': False,  # TODO: Enable if --advanced flag supported
            'output_types': [
                {{
                    'type': '{adapter_name}_structure',
                    'description': 'Overview of {adapter_name} resources',
                    'schema': {{
                        'type': 'object',
                        'properties': {{
                            'type': {{'type': 'string', 'const': '{adapter_name}_structure'}},
                            'items': {{'type': 'array'}},
                            # TODO: Add more schema properties
                        }}
                    }}
                }}
            ],
            'example_queries': [
                {{
                    'uri': '{scheme}://',
                    'description': 'List all {adapter_name} resources',
                    'output_type': '{adapter_name}_structure'
                }},
                # TODO: Add more examples
            ]
        }}

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for {scheme}:// adapter."""
        return {{
            'name': '{scheme}',
            'description': 'Explore {adapter_name} resources',
            'syntax': '{scheme}://[resource_name][?query_params]',
            'examples': [
                {{
                    'uri': '{scheme}://',
                    'description': 'List all resources'
                }},
                {{
                    'uri': '{scheme}://resource_name',
                    'description': 'Get specific resource details'
                }},
                # TODO: Add more examples
            ],
            'features': [
                # TODO: List key features
                'Resource discovery and inspection',
                'JSON and text output formats',
            ],
            'try_now': [
                "reveal {scheme}://",
                # TODO: Add executable examples
            ],
            'workflows': [
                # TODO: Add workflow examples
                {{
                    'name': 'Basic Workflow',
                    'scenario': 'Inspect {adapter_name} resources',
                    'steps': [
                        "reveal {scheme}://              # List all",
                        "reveal {scheme}://item         # Get specific item",
                    ],
                }},
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                # TODO: Add related adapters/help topics
            ]
        }}

    def __init__(self, resource: Optional[str] = None, **query_params):
        """Initialize {adapter_name} adapter.

        Args:
            resource: Optional resource identifier from URI
            **query_params: Query parameters from URI
        """
        self.resource = resource
        self.query_params = query_params
        # TODO: Initialize adapter-specific state

    def get_structure(self) -> Dict[str, Any]:
        """Get overview of {adapter_name} resources.

        Returns:
            Dict containing structure information
        """
        # TODO: Implement structure retrieval
        return {{
            'contract_version': '1.0',
            'type': '{adapter_name}_structure',
            'source': '{scheme}://',
            'items': [
                # TODO: Populate with actual items
                {{'name': 'example_item', 'type': 'item'}},
            ],
            'metadata': {{
                'total_count': 1,
                # TODO: Add metadata
            }}
        }}

    def get_element(self, element_name: str) -> Optional[Dict[str, Any]]:
        """Get details about a specific resource.

        Args:
            element_name: Name/ID of the resource

        Returns:
            Dict with resource details, or None if not found
        """
        # TODO: Implement element retrieval
        return {{
            'name': element_name,
            'type': '{adapter_name}_item',
            # TODO: Add element properties
        }}

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the {adapter_name} adapter.

        Returns:
            Dict with adapter metadata
        """
        return {{
            'type': '{adapter_name}',
            'adapter_version': '1.0',
            # TODO: Add metadata
        }}
'''

RENDERER_TEMPLATE = '''"""Renderer for {adapter_name} adapter output."""

from typing import Dict, Any


def render_{adapter_name}_structure(result: Dict[str, Any], format: str) -> None:
    """Render {adapter_name} structure output.

    Args:
        result: Structure dict from adapter
        format: Output format ('text', 'json', 'grep')
    """
    if format == 'json':
        from ..main import safe_json_dumps
        print(safe_json_dumps(result))
        return

    # Text format
    print(f"{{class_name}} Structure")
    print(f"Items: {{len(result.get('items', []))}}")
    # TODO: Implement full text rendering
'''

TEST_TEMPLATE = '''"""Tests for {adapter_name} adapter."""

import pytest
from reveal.adapters.{adapter_name} import {class_name}Adapter, {class_name}Renderer


class Test{class_name}AdapterInit:
    """Tests for adapter initialization."""

    def test_init_no_params(self):
        """Test adapter initialization without parameters."""
        adapter = {class_name}Adapter()
        assert adapter.resource is None
        assert adapter.query_params == {{}}

    def test_init_with_resource(self):
        """Test adapter initialization with resource."""
        adapter = {class_name}Adapter(resource='test_resource')
        assert adapter.resource == 'test_resource'

    def test_init_with_query_params(self):
        """Test adapter initialization with query parameters."""
        adapter = {class_name}Adapter(resource='test', limit=10, sort='name')
        assert adapter.resource == 'test'
        assert adapter.query_params['limit'] == 10
        assert adapter.query_params['sort'] == 'name'


class Test{class_name}AdapterSchema:
    """Tests for adapter schema."""

    def test_get_schema_returns_dict(self):
        """Test that get_schema returns a dictionary."""
        schema = {class_name}Adapter.get_schema()
        assert isinstance(schema, dict)

    def test_schema_has_required_fields(self):
        """Test that schema contains required fields."""
        schema = {class_name}Adapter.get_schema()
        assert 'adapter' in schema
        assert 'description' in schema
        assert 'uri_syntax' in schema
        assert schema['adapter'] == '{scheme}'

    def test_schema_has_examples(self):
        """Test that schema includes example queries."""
        schema = {class_name}Adapter.get_schema()
        assert 'example_queries' in schema
        assert len(schema['example_queries']) > 0


class Test{class_name}AdapterHelp:
    """Tests for adapter help system."""

    def test_get_help_returns_dict(self):
        """Test that get_help returns a dictionary."""
        help_doc = {class_name}Adapter.get_help()
        assert isinstance(help_doc, dict)

    def test_help_has_required_fields(self):
        """Test that help contains required fields."""
        help_doc = {class_name}Adapter.get_help()
        assert 'name' in help_doc
        assert 'description' in help_doc
        assert 'syntax' in help_doc
        assert 'examples' in help_doc

    def test_help_has_try_now_examples(self):
        """Test that help includes executable examples."""
        help_doc = {class_name}Adapter.get_help()
        assert 'try_now' in help_doc
        assert len(help_doc['try_now']) > 0


class Test{class_name}AdapterStructure:
    """Tests for get_structure method."""

    def test_get_structure_returns_dict(self):
        """Test that get_structure returns a dictionary."""
        adapter = {class_name}Adapter()
        result = adapter.get_structure()
        assert isinstance(result, dict)

    def test_structure_has_contract_version(self):
        """Test that structure includes contract version."""
        adapter = {class_name}Adapter()
        result = adapter.get_structure()
        assert 'contract_version' in result

    def test_structure_has_type_field(self):
        """Test that structure includes type field."""
        adapter = {class_name}Adapter()
        result = adapter.get_structure()
        assert 'type' in result
        assert result['type'] == '{adapter_name}_structure'


class Test{class_name}AdapterElement:
    """Tests for get_element method."""

    def test_get_element_returns_dict_or_none(self):
        """Test that get_element returns dict or None."""
        adapter = {class_name}Adapter()
        result = adapter.get_element('test_element')
        assert result is None or isinstance(result, dict)

    # TODO: Add tests for actual element retrieval
    # def test_get_element_valid_name(self):
    #     adapter = {class_name}Adapter()
    #     result = adapter.get_element('known_element')
    #     assert result is not None
    #     assert result['name'] == 'known_element'


class Test{class_name}AdapterMetadata:
    """Tests for get_metadata method."""

    def test_get_metadata_returns_dict(self):
        """Test that get_metadata returns a dictionary."""
        adapter = {class_name}Adapter()
        metadata = adapter.get_metadata()
        assert isinstance(metadata, dict)

    def test_metadata_has_type(self):
        """Test that metadata includes type field."""
        adapter = {class_name}Adapter()
        metadata = adapter.get_metadata()
        assert 'type' in metadata


class Test{class_name}Renderer:
    """Tests for renderer methods."""

    def test_render_structure_text_format(self, capsys):
        """Test text format rendering."""
        result = {{
            'type': '{adapter_name}_structure',
            'items': [{{'name': 'test'}}]
        }}
        {class_name}Renderer.render_structure(result, 'text')
        captured = capsys.readouterr()
        assert '{class_name}' in captured.out

    def test_render_structure_json_format(self, capsys):
        """Test JSON format rendering."""
        result = {{
            'type': '{adapter_name}_structure',
            'items': []
        }}
        {class_name}Renderer.render_structure(result, 'json')
        captured = capsys.readouterr()
        assert '{{' in captured.out  # JSON output


# TODO: Add integration tests
# class Test{class_name}AdapterIntegration:
#     """Integration tests for {adapter_name} adapter."""
#
#     def test_full_workflow(self):
#         """Test complete adapter workflow."""
#         adapter = {class_name}Adapter()
#         structure = adapter.get_structure()
#         assert len(structure['items']) > 0
'''
