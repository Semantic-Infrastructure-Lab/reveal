"""JSON navigation adapter (json://) - Core adapter logic."""

from pathlib import Path
from typing import Dict, List, Any, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.query import (
    parse_query_filters,
    parse_result_control,
    ResultControl
)

# Import modular functions
from .renderer import JsonRenderer
from .help import get_help, get_schema
from .parsing import parse_path, load_json
from .queries import (
    get_field_value,
    compare,
    matches_all_filters,
    filter_array,
    apply_result_control,
    navigate_to_path
)
from .introspection import (
    get_type_str,
    get_schema_result,
    get_flatten_result,
    get_type_info_result,
    get_keys_result,
    get_length_result
)


@register_adapter('json')
@register_renderer(JsonRenderer)
class JsonAdapter(ResourceAdapter):
    """Adapter for navigating and querying JSON files."""

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for json:// adapter."""
        return get_help()

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for json:// adapter."""
        return get_schema()

    def __init__(self, path: str, query_string: Optional[str] = None):
        """Initialize JSON adapter.

        Args:
            path: File path, optionally with JSON path (file.json/path/to/key)
            query_string: Query parameters (schema, gron, type, keys, length, or filters)
        """
        self.query_string = query_string
        self.query_filters = []
        self.result_control = ResultControl()

        # Parse file path and JSON path
        self.file_path, self.json_path, self.slice_spec = parse_path(path)

        # Load JSON data
        self.data = load_json(self.file_path)

        # Parse query filters and result control
        if query_string:
            # Detect if this is a legacy query mode (single word flag)
            legacy_modes = {'schema', 'flatten', 'gron', 'type', 'keys', 'length'}
            is_legacy_mode = query_string.lower() in legacy_modes

            if not is_legacy_mode:
                # Parse result control first (removes sort/limit/offset from query)
                filter_query, self.result_control = parse_result_control(query_string)

                # Parse query filters if there's a filter query
                # (JSON adapter has no legacy filter syntax, so parse all non-legacy queries)
                if filter_query:
                    try:
                        self.query_filters = parse_query_filters(filter_query)
                    except Exception:
                        # If parsing fails, fall back to empty filters
                        self.query_filters = []

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get JSON data with optional query processing.

        Returns:
            Dict containing JSON data or query result
        """
        # Navigate to requested path
        try:
            value = navigate_to_path(self.data, self.json_path, self.slice_spec)
        except (KeyError, IndexError, TypeError) as e:
            return self._build_error_result(str(e))

        # Handle legacy query modes
        if self._is_legacy_query():
            return self._handle_query(value)

        # Validate query syntax
        validation_error = self._validate_query_syntax()
        if validation_error:
            return validation_error

        # Process array values with filters/sorting
        value, metadata = self._process_value(value)

        # Build and return result
        return self._build_success_result(value, metadata)

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific element by name (for direct key access).

        Args:
            element_name: Key name to access

        Returns:
            Dict with element info or None if not found
        """
        try:
            if isinstance(self.data, dict) and element_name in self.data:
                return {
                    'name': element_name,
                    'value': self.data[element_name],
                    'type': get_type_str(self.data[element_name])
                }
        except Exception:
            pass
        return None

    def get_metadata(self) -> Dict[str, Any]:
        """Get JSON file metadata.

        Returns:
            Dict with file metadata
        """
        return {
            'file': str(self.file_path),
            'exists': self.file_path.exists(),
            'size': self.file_path.stat().st_size if self.file_path.exists() else 0,
            'root_type': get_type_str(self.data)
        }

    # Private helper methods

    def _build_error_result(self, error_msg: str) -> Dict[str, Any]:
        """Build error result dict.

        Args:
            error_msg: Error message

        Returns:
            Error result dict
        """
        return {
            'contract_version': '1.0',
            'type': 'json_error',
            'source': str(self.file_path),
            'source_type': 'file',
            'file': str(self.file_path),
            'path': '/'.join(str(p) for p in self.json_path),
            'error': error_msg
        }

    def _build_success_result(self, value: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Build success result dict.

        Args:
            value: JSON value
            metadata: Additional metadata

        Returns:
            Success result dict
        """
        result = {
            'contract_version': '1.0',
            'type': 'json_value',
            'source': str(self.file_path),
            'source_type': 'file',
            'file': str(self.file_path),
            'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
            'value_type': get_type_str(value),
            'value': value
        }

        # Add metadata if present
        if metadata:
            result.update(metadata)

        return result

    def _is_legacy_query(self) -> bool:
        """Check if query uses legacy mode.

        Returns:
            True if legacy query mode
        """
        legacy_modes = {'schema', 'flatten', 'gron', 'type', 'keys', 'length'}
        return bool(self.query_string and self.query_string.lower() in legacy_modes)

    def _validate_query_syntax(self) -> Optional[Dict[str, Any]]:
        """Validate query syntax, return error dict if invalid.

        Returns:
            Error dict if invalid, None if valid
        """
        if not self.query_string:
            return None

        has_only_existence_checks = (
            self.query_filters and
            all(qf.op == '?' for qf in self.query_filters)
        )
        has_no_result_control = (
            not self.result_control.sort_field and
            self.result_control.limit is None and
            (self.result_control.offset is None or self.result_control.offset == 0)
        )

        if has_only_existence_checks or (not self.query_filters and has_no_result_control):
            legacy_modes = {'schema', 'flatten', 'gron', 'type', 'keys', 'length'}
            return {
                'contract_version': '1.0',
                'type': 'json_error',
                'source': str(self.file_path),
                'source_type': 'file',
                'file': str(self.file_path),
                'error': f"Unknown query: {self.query_string}",
                'valid_queries': list(legacy_modes) + ['field=value', 'field>value', 'sort=field', 'limit=N']
            }

        return None

    def _handle_query(self, value: Any) -> Dict[str, Any]:
        """Handle query parameters like ?schema, ?gron, ?type.

        Args:
            value: JSON value to query

        Returns:
            Query result dict
        """
        assert self.query_string is not None
        query = self.query_string.lower()

        if query == 'schema':
            return get_schema_result(value, self.file_path, self.json_path)
        elif query in ('flatten', 'gron'):  # gron is alias for flatten
            return get_flatten_result(value, self.file_path, self.json_path)
        elif query == 'type':
            return get_type_info_result(value, self.file_path, self.json_path)
        elif query == 'keys':
            return get_keys_result(value, self.file_path, self.json_path)
        elif query == 'length':
            return get_length_result(value, self.file_path, self.json_path)
        else:
            return {
                'type': 'json_error',
                'error': f"Unknown query: {query}",
                'valid_queries': ['schema', 'flatten', 'gron', 'type', 'keys', 'length']
            }

    def _process_value(self, value: Any):
        """Process value with filters and result control.

        Args:
            value: JSON value to process

        Returns:
            Tuple of (processed value, metadata)
        """
        metadata: Dict[str, Any] = {}

        # Only process arrays with filters or result control
        if not isinstance(value, list):
            return value, metadata

        has_result_control = self._has_result_control()
        if not (self.query_filters or has_result_control):
            return value, metadata

        # Apply filters
        if self.query_filters:
            value = filter_array(value, self.query_filters, get_field_value, compare)

        # Apply result control (sort, limit, offset)
        if has_result_control:
            value, metadata = apply_result_control(value, self.result_control, get_field_value)

        return value, metadata

    def _has_result_control(self) -> bool:
        """Check if result control is specified.

        Returns:
            True if any result control parameters set
        """
        return (
            self.result_control.sort_field is not None or
            self.result_control.limit is not None or
            (self.result_control.offset is not None and self.result_control.offset > 0)
        )
