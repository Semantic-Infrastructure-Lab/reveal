"""Demo adapter for demo:// URIs."""

import sys
from typing import Dict, Any, Optional
from .base import ResourceAdapter, register_adapter, register_renderer


class DemoRenderer:
    """Renderer for demo adapter results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render demo structure overview.

        Args:
            result: Structure dict from DemoAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        # TODO: Implement custom rendering or use generic renderer
        from ..main import safe_json_dumps

        if format == 'json':
            print(safe_json_dumps(result))
        else:
            # TODO: Implement text rendering
            print(f"Demo Structure:")
            print(f"  Type: {result.get('type', 'unknown')}")
            print(f"  Items: {len(result.get('items', []))}")

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific demo element.

        Args:
            result: Element dict from DemoAdapter.get_element()
            format: Output format ('text', 'json', 'grep')
        """
        from ..main import safe_json_dumps

        if format == 'json':
            print(safe_json_dumps(result))
        else:
            # TODO: Implement element rendering
            print(f"Element: {result.get('name', 'unknown')}")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error accessing demo: {error}", file=sys.stderr)


@register_adapter('demo')
@register_renderer(DemoRenderer)
class DemoAdapter(ResourceAdapter):
    """Adapter for exploring demo resources via demo:// URIs.

    Example URIs:
        demo://                 # Overview of all items
        demo://item_name       # Specific item details
        demo://item_name?param=value  # Item with query parameters
    """

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for demo:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'demo',
            'description': 'Demo adapter for demo:// URIs',
            'uri_syntax': 'demo://[resource_name][?query_params]',
            'query_params': {
                # TODO: Define query parameters
                # 'limit': {'type': 'integer', 'description': 'Max items to return'},
                # 'sort': {'type': 'string', 'description': 'Sort field'},
            },
            'elements': {
                # TODO: Define fixed elements (or leave empty for dynamic)
                # 'overview': {'description': 'System overview'},
                # 'stats': {'description': 'Statistics'},
            },
            'cli_flags': [
                # TODO: Define CLI-specific flags
                # {'name': '--check', 'description': 'Run health checks'},
            ],
            'supports_batch': False,  # TODO: Enable if batch processing supported
            'supports_advanced': False,  # TODO: Enable if --advanced flag supported
            'output_types': [
                {
                    'type': 'demo_structure',
                    'description': 'Overview of demo resources',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'demo_structure'},
                            'items': {'type': 'array'},
                            # TODO: Add more schema properties
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'demo://',
                    'description': 'List all demo resources',
                    'output_type': 'demo_structure'
                },
                # TODO: Add more examples
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for demo:// adapter."""
        return {
            'name': 'demo',
            'description': 'Explore demo resources',
            'syntax': 'demo://[resource_name][?query_params]',
            'examples': [
                {
                    'uri': 'demo://',
                    'description': 'List all resources'
                },
                {
                    'uri': 'demo://resource_name',
                    'description': 'Get specific resource details'
                },
                # TODO: Add more examples
            ],
            'features': [
                # TODO: List key features
                'Resource discovery and inspection',
                'JSON and text output formats',
            ],
            'try_now': [
                "reveal demo://",
                # TODO: Add executable examples
            ],
            'workflows': [
                # TODO: Add workflow examples
                {
                    'name': 'Basic Workflow',
                    'scenario': 'Inspect demo resources',
                    'steps': [
                        "reveal demo://              # List all",
                        "reveal demo://item         # Get specific item",
                    ],
                },
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                # TODO: Add related adapters/help topics
            ]
        }

    def __init__(self, resource: Optional[str] = None, **query_params):
        """Initialize demo adapter.

        Args:
            resource: Optional resource identifier from URI
            **query_params: Query parameters from URI
        """
        self.resource = resource
        self.query_params = query_params
        # TODO: Initialize adapter-specific state

    def get_structure(self) -> Dict[str, Any]:
        """Get overview of demo resources.

        Returns:
            Dict containing structure information
        """
        # TODO: Implement structure retrieval
        return {
            'contract_version': '1.0',
            'type': 'demo_structure',
            'source': 'demo://',
            'items': [
                # TODO: Populate with actual items
                {'name': 'example_item', 'type': 'item'},
            ],
            'metadata': {
                'total_count': 1,
                # TODO: Add metadata
            }
        }

    def get_element(self, element_name: str) -> Optional[Dict[str, Any]]:
        """Get details about a specific resource.

        Args:
            element_name: Name/ID of the resource

        Returns:
            Dict with resource details, or None if not found
        """
        # TODO: Implement element retrieval
        return {
            'name': element_name,
            'type': 'demo_item',
            # TODO: Add element properties
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the demo adapter.

        Returns:
            Dict with adapter metadata
        """
        return {
            'type': 'demo',
            'adapter_version': '1.0',
            # TODO: Add metadata
        }
