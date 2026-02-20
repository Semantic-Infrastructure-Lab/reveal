"""Core diff adapter for comparing two reveal resources."""

from typing import Dict, Any, Optional, Tuple, cast

from .parsing import parse_diff_uris
from .resolution import resolve_uri, extract_metadata, find_element
from .help import get_schema as _get_schema, get_help as _get_help
from ..base import ResourceAdapter, register_adapter, register_renderer
from .renderer import DiffRenderer


@register_adapter('diff')
@register_renderer(DiffRenderer)
class DiffAdapter(ResourceAdapter):
    """Compare two reveal-compatible resources.

    URI Syntax:
        diff://<left-uri>:<right-uri>[/element]

    Examples:
        diff://app.py:backup/app.py               # File comparison
        diff://env://:env://production            # Environment comparison
        diff://mysql://prod/db:mysql://staging/db # Database schema drift
        diff://app.py:old.py/handle_request       # Element-specific diff
    """

    left_uri: str
    right_uri: str
    left_structure: Optional[Dict[str, Any]]
    right_structure: Optional[Dict[str, Any]]

    def __init__(self, resource: Optional[str] = None, right_uri: Optional[str] = None):
        """Initialize with either a combined resource string or two URIs.

        Args:
            resource: Either combined "left:right" string or left_uri
            right_uri: Right URI (if resource is left_uri)

        The adapter supports two initialization styles:
        1. DiffAdapter("left:right") - single combined string (new style, for generic handler)
        2. DiffAdapter("left", "right") - two separate URIs (old style, backward compatibility)

        Raises:
            TypeError: When called with no arguments (wrong initialization pattern)
            ValueError: When resource format is invalid
        """
        # No args provided - wrong initialization pattern
        if resource is None and right_uri is None:
            raise TypeError(
                "DiffAdapter requires arguments. "
                "Use DiffAdapter('left:right') or DiffAdapter('left', 'right')"
            )

        if right_uri is not None:
            # Old style: two arguments
            self.left_uri = cast(str, resource)  # resource must be provided with right_uri
            self.right_uri = right_uri
        elif resource:
            # New style: parse combined resource string
            # parse_diff_uris handles Windows drive letters and all URI schemes
            try:
                self.left_uri, self.right_uri = parse_diff_uris(resource)
            except ValueError:
                raise ValueError(
                    "DiffAdapter requires 'left:right' format. "
                    "Got: {!r}. Example: diff://app.py:backup/app.py".format(resource)
                )
        else:
            # Resource provided but invalid format
            raise ValueError(
                "DiffAdapter requires 'left:right' format. "
                "Got: {!r}. Example: diff://app.py:backup/app.py".format(resource)
            )
        self.left_structure = None
        self.right_structure = None

    @staticmethod
    def _parse_diff_uris(resource: str) -> Tuple[str, str]:
        """Parse left:right from diff resource string.

        Delegates to parsing.parse_diff_uris for backward compatibility.
        Tests may call this as DiffAdapter._parse_diff_uris().

        Args:
            resource: The resource string to parse

        Returns:
            Tuple of (left_uri, right_uri)

        Raises:
            ValueError: If parsing fails
        """
        return parse_diff_uris(resource)

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for diff:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return _get_schema()

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for diff:// adapter.

        Help data loaded from reveal/adapters/help_data/diff.yaml
        to reduce function complexity.
        """
        return _get_help()

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get diff summary between two resources.

        Returns:
            {
                'type': 'diff',
                'left': {'uri': ..., 'type': ...},
                'right': {'uri': ..., 'type': ...},
                'summary': {
                    'functions': {'added': 2, 'removed': 1, 'modified': 3},
                    'classes': {'added': 0, 'removed': 0, 'modified': 1},
                    'imports': {'added': 5, 'removed': 2},
                },
                'diff': {
                    'functions': [...],  # Detailed function diffs
                    'classes': [...],    # Detailed class diffs
                    'imports': [...]     # Import changes
                }
            }
        """
        from ...diff import compute_structure_diff

        # Resolve both URIs using existing adapter infrastructure
        left_struct = resolve_uri(self.left_uri, **kwargs)
        right_struct = resolve_uri(self.right_uri, **kwargs)

        # Compute semantic diff
        diff_result = compute_structure_diff(left_struct, right_struct)

        return {
            'contract_version': '1.0',
            'type': 'diff_comparison',
            'source': f"{self.left_uri} vs {self.right_uri}",
            'source_type': 'runtime',
            'left': extract_metadata(left_struct, self.left_uri),
            'right': extract_metadata(right_struct, self.right_uri),
            'summary': diff_result['summary'],
            'diff': diff_result['details']
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get diff for a specific element (function, class, etc.).

        Args:
            element_name: Name of element to compare (e.g., 'handle_request')

        Returns:
            Detailed diff for that specific element
        """
        from ...diff import compute_element_diff

        left_struct = resolve_uri(self.left_uri, **kwargs)
        right_struct = resolve_uri(self.right_uri, **kwargs)

        left_elem = find_element(left_struct, element_name)
        right_elem = find_element(right_struct, element_name)

        return compute_element_diff(left_elem, right_elem, element_name)

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the diff operation.

        Returns:
            Dict with diff metadata
        """
        return {
            'type': 'diff',
            'left_uri': self.left_uri,
            'right_uri': self.right_uri
        }
