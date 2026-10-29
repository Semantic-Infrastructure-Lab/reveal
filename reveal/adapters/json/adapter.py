"""JSON navigation adapter (json://) - Core adapter logic."""

from typing import Dict, Any, Optional
from reveal.reveal_types import CONTRACT_VERSION
from ...errors import RequestValidationError

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.results import (AnalysisCompleteness, FailureCause, ResultBuilder, note_truncation,
                             note_warning, result_execution_facts)
from ...utils.path_utils import to_posix
from ...utils.query_parser import note_query_parsed
from ...utils.query import (
    parse_query_filters,
    parse_result_control,
    ResultControl
)

# Import modular functions
from .renderer import JsonRenderer
from .help import get_help, get_schema
from .parsing import parse_path, split_path, load_json
from .queries import (
    get_field_value,
    compare,
    filter_array,
    find_unknown_filter_fields,
    apply_result_control,
    navigate_to_path
)
def _parse_filters_safe(filter_query: str) -> list:
    """Parse query filters. A key counts as used only when ``_process_value`` applies
    the filters (an array), not when parsed (BACK-1542). A filter that doesn't parse
    raises, as in every other adapter, rather than being dropped so the whole array
    reads as the filtered answer (BACK-1614)."""
    if not filter_query:
        return []
    return parse_query_filters(filter_query, record=False)


from .introspection import (
    get_type_str,
    get_schema_result,
    get_flatten_result,
    get_type_info_result,
    get_keys_result,
    get_length_result
)


_LEGACY_QUERY_MODES = frozenset({'schema', 'flatten', 'gron', 'type', 'keys', 'length'})


def _legacy_query(query: str) -> bool:
    return query.lower().split('&')[0] in _LEGACY_QUERY_MODES


def _request_rejection(result) -> bool:
    """Only an authored rejection, never repaired/malformed output, is usage."""
    codes = {entry.get('code') for entry in result.get('meta', {}).get('errors', [])}
    return (isinstance(result.get('error'), str) and bool(result['error'])
            and 'invalid_request' in codes and 'invalid_adapter_answer' not in codes)


@register_adapter('json')
@register_renderer(JsonRenderer)
class JsonAdapter(ResourceAdapter):
    """Adapter for navigating and querying JSON files."""
    HELP_CLUSTER = 'Data & Config'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True
    RESULT_TYPE = 'json_value'
    DEFAULT_FAIL_ON = 'none'

    @staticmethod
    def resource_path(resource: str) -> str:
        """Only the file is a filesystem resource; JSON navigation is inside it."""
        return to_posix(split_path(resource)[0])

    @classmethod
    def uri_execution_facts(cls, resource):
        """Ordinary values/queries/navigation share one policy; introspection stays legacy."""
        query = resource.partition('?')[2]
        return None if _legacy_query(query) else cls.execution_facts

    @staticmethod
    def execution_facts(result):
        """Values require a full read; navigation/query rejection is a request failure."""
        cause = FailureCause.INVALID_REQUEST if _request_rejection(result) else FailureCause.ANALYSIS
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE,
                                      failure_cause=cause)

    @staticmethod
    def answer_requirement_error(result, expected_type, prior_facts=None):
        """Presentation cannot turn prior work into a newly authored rejection."""
        if _request_rejection(result) and prior_facts is not None:
            if (prior_facts.completeness is not AnalysisCompleteness.COMPLETE
                    or prior_facts.failures != frozenset({FailureCause.INVALID_REQUEST})):
                return 'JSON postprocessing cannot establish a request rejection from prior analysis'
        if not result.get('error') and ('value' not in result or not isinstance(result.get('value_type'), str)):
            return 'JSON value answer missing its value or value type'
        return None

    @staticmethod
    def public_diagnostic(result):
        """Only owner-authored request diagnostics are safe to expose through the SDK."""
        return result['error'] if _request_rejection(result) else None


    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for json:// adapter."""
        return get_help()

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for json:// adapter."""
        return get_schema()

    def __init__(self, resource: str, query: Optional[str] = None):
        """Initialize JSON adapter.

        Args:
            resource: File path, optionally with JSON path (file.json/path/to/key)
            query: Query parameters (schema, gron, type, keys, length, or filters)
        """
        path, query_string = resource, query
        self.query_string = query_string
        self.query_filters = []
        self._filter_query = ''
        self.result_control = ResultControl()

        # Parse file path and JSON path
        self.file_path, self.json_path, self.slice_spec = parse_path(path)

        # Load JSON data
        self.data = load_json(self.file_path)

        # Parse query filters and result control
        if query_string:
            # Detect if this is a legacy query mode (single word flag or flatten&data-only)
            if not _legacy_query(query_string):
                # Parse result control first (removes sort/limit/offset from query)
                try:
                    filter_query, self.result_control = parse_result_control(query_string)
                    self.query_filters = _parse_filters_safe(filter_query)
                except ValueError as exc:
                    raise RequestValidationError(str(exc)) from exc
                self._filter_query = filter_query

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
        if isinstance(self.data, dict) and element_name in self.data:
            return {
                'name': element_name,
                'value': self.data[element_name],
                'type': get_type_str(self.data[element_name])
            }
        return None

    def get_metadata(self) -> Dict[str, Any]:
        """Get JSON file metadata.

        Returns:
            Dict with file metadata
        """
        return {
            'file': to_posix(self.file_path),
            'exists': self.file_path.exists(),
            'size': self.file_path.stat().st_size if self.file_path.exists() else 0,
            'root_type': get_type_str(self.data)
        }

    # Private helper methods

    def _build_error_result(self, error_msg: str, **extra_fields) -> Dict[str, Any]:
        """Build error result dict.

        Args:
            error_msg: Error message

        Returns:
            Error result dict
        """
        if not self._is_legacy_query():
            return ResultBuilder.create(
                result_type=self.RESULT_TYPE, source=to_posix(self.file_path),
                source_type='file', contract_version=CONTRACT_VERSION,
                meta={'errors': [{'code': 'invalid_request', 'message': error_msg}]},
                data={'error': error_msg, 'file': to_posix(self.file_path),
                      'path': '/'.join(str(p) for p in self.json_path), **extra_fields})
        return ResultBuilder.create_error(
            result_type='json_error',
            source=to_posix(self.file_path),
            error=error_msg,
            contract_version=CONTRACT_VERSION,
            file=to_posix(self.file_path),
            path='/'.join(str(p) for p in self.json_path),
        )

    def _build_success_result(self, value: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Build success result dict.

        Args:
            value: JSON value
            metadata: Additional metadata

        Returns:
            Success result dict
        """
        result = ResultBuilder.create(
            result_type='json_value',
            source=to_posix(self.file_path),
            source_type='file',
            contract_version=CONTRACT_VERSION,
            data={
                'file': to_posix(self.file_path),
                'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
                'value_type': get_type_str(value),
                'value': value,
            }
        )

        # The counts stay top-level; the warnings go to meta.warnings like every adapter's
        # (they landed top-level, where the output seam never read them, BACK-2297).
        result.update({k: v for k, v in metadata.items() if k != 'warnings'})
        for warning in metadata.get('warnings', []):
            note_warning(result, warning)
        if 'displayed_results' in metadata:
            note_truncation(result, 'value', metadata['displayed_results'],
                            metadata['total_matches'], 'limit')

        return result

    def _is_legacy_query(self) -> bool:
        """Check if query uses legacy mode.

        Returns:
            True if legacy query mode
        """
        return _legacy_query(self.query_string or '')

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
        has_no_result_control = not self.result_control.any_set()

        if has_only_existence_checks or (not self.query_filters and has_no_result_control):
            return self._build_error_result(
                f"Unknown query: {self.query_string}",
                valid_queries=sorted(_LEGACY_QUERY_MODES) + ['field=value', 'field>value', 'sort=field', 'limit=N'],
            )

        return None

    def _handle_query(self, value: Any) -> Dict[str, Any]:
        """Handle query parameters like ?schema, ?gron, ?type.

        Args:
            value: JSON value to query

        Returns:
            Query result dict
        """
        assert self.query_string is not None
        parts = [p.strip() for p in self.query_string.lower().split('&')]
        query = parts[0]
        data_only = 'data-only' in parts
        # The mode is read here, from the raw query, so tell the flag ledger (BACK-1542):
        # it noted a documented ?keys as unread. data-only means something to flatten only.
        note_query_parsed(query)
        if data_only and query in ('flatten', 'gron'):
            note_query_parsed('data-only')

        if query == 'schema':
            return get_schema_result(value, self.file_path, self.json_path)
        elif query in ('flatten', 'gron'):  # gron is alias for flatten
            return get_flatten_result(value, self.file_path, self.json_path, data_only=data_only)
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
            note_query_parsed(self._filter_query)
            original = value
            value = filter_array(value, self.query_filters, get_field_value, compare)

            # Disclose when a zero-match result traces to a filter field that
            # never resolves on any scanned item -- typo vs. genuine zero
            # (BACK-1165, same disclosure pattern as ast:///markdown:// in BACK-1111)
            if not value:
                unknown_fields = find_unknown_filter_fields(
                    original, self.query_filters, get_field_value
                )
                if unknown_fields:
                    fields_str = ', '.join(f"'{f}'" for f in unknown_fields)
                    metadata['warnings'] = [{
                        'type': 'unknown_filter_field',
                        'message': (
                            f"Filter field(s) {fields_str} never appear on any scanned item — "
                            f"this may be a typo rather than a genuine zero-match. "
                            f"See: reveal help://json"
                        )
                    }]

        # Apply result control (sort, limit, offset)
        if has_result_control:
            value, rc_metadata = apply_result_control(value, self.result_control, get_field_value)
            warnings = metadata.get('warnings', []) + rc_metadata.pop('warnings', [])
            metadata.update(rc_metadata)
            if warnings:
                metadata['warnings'] = warnings

        return value, metadata

    def _has_result_control(self) -> bool:
        """Check if result control is specified.

        Returns:
            True if any result control parameters set
        """
        return self.result_control.any_set()
