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

        Returns:
            Dict containing help metadata, or None if no help available.
            Expected keys:
                - name: Adapter scheme name
                - description: One-line summary
                - syntax: Usage pattern (optional)
                - examples: List of example URIs (optional)
                - filters: Available query filters (optional)
                - notes: Additional notes or gotchas (optional)
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
