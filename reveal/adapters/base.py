"""Base adapter interface for URI resources."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class ResourceAdapter(ABC):
    """Base class for all resource adapters."""

    @abstractmethod
    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get the structure/overview of the resource.

        Returns:
            Dict containing structured representation of the resource
        """
        pass

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get details about a specific element within the resource.

        Args:
            element_name: Name/identifier of the element to retrieve

        Returns:
            Dict containing element details, or None if not found
        """
        return None

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the resource.

        Returns:
            Dict containing metadata (type, size, etc.)
        """
        return {'type': self.__class__.__name__}

    @staticmethod
    def get_help() -> Optional[Dict[str, Any]]:
        """Get help documentation for this adapter (optional).

        For extension authors: Implement this method to provide discoverable help.
        Your help will automatically appear in `reveal help://` and `reveal help://yourscheme`

        Returns:
            Dict containing help metadata, or None if no help available.

            Required keys:
                - name (str): Adapter scheme name (e.g., 'python', 'ast')
                - description (str): One-line summary (< 80 chars)

            Recommended keys:
                - syntax (str): Usage pattern (e.g., 'scheme://<resource>[?<filters>]')
                - examples (List[Dict]): Example URIs with descriptions
                  [{'uri': 'scheme://example', 'description': 'What it does'}]
                - notes (List[str]): Important notes, gotchas, limitations
                - see_also (List[str]): Related adapters, tools, documentation

            Optional keys (for advanced adapters):
                - operators (Dict[str, str]): Query operators (e.g., '>', '<', '==')
                - filters (Dict[str, str]): Available filters with descriptions
                - elements (Dict[str, str]): Available elements (for element-based adapters)
                - features (List[str]): Feature list
                - use_cases (List[str]): Common use cases
                - output_formats (List[str]): Supported formats ('text', 'json', 'grep')
                - coming_soon (List[str]): Planned features

        Best Practices:
            - Provide 3-7 examples (simple → complex)
            - Include multi-shot examples (input + expected output) for LLMs
            - Add breadcrumbs in see_also to guide users
            - Create comprehensive guide (ADAPTER_GUIDE.md) for complex adapters
            - Link guide in see_also: 'reveal help://yourscheme-guide - Comprehensive guide'

        For detailed guidance:
            reveal help://adapter-authoring - Complete adapter authoring guide

        Examples:
            See reveal/adapters/python.py, ast.py, env.py for reference implementations
        """
        return None


# Registry for URI scheme adapters
_ADAPTER_REGISTRY: Dict[str, type] = {}


def register_adapter(scheme: str):
    """Decorator to register an adapter for a URI scheme.

    Usage:
        @register_adapter('postgres')
        class PostgresAdapter(ResourceAdapter):
            ...

    Args:
        scheme: URI scheme to register (e.g., 'env', 'ast', 'postgres')
    """
    def decorator(cls):
        _ADAPTER_REGISTRY[scheme.lower()] = cls
        cls.scheme = scheme
        return cls
    return decorator


def get_adapter_class(scheme: str) -> Optional[type]:
    """Get adapter class for a URI scheme.

    Args:
        scheme: URI scheme (e.g., 'env', 'ast')

    Returns:
        Adapter class or None if not found
    """
    return _ADAPTER_REGISTRY.get(scheme.lower())


def list_supported_schemes() -> list:
    """Get list of supported URI schemes.

    Returns:
        List of registered scheme names
    """
    return sorted(_ADAPTER_REGISTRY.keys())
