"""calls:// adapter — cross-file call graph queries.

Supported URIs:

    calls://src/?target=validate_item           # who calls validate_item?
    calls://src/?target=validate_item&depth=2  # callers-of-callers too
    calls://src/?target=validate_item&format=dot  # graphviz dot output

The adapter builds a project-level callers index from the code under *path*,
then looks up the requested *target*.  Results are cached per-directory with
mtime-based invalidation.

Limitations (static analysis):
- Dynamic dispatch (callbacks, metaclasses) is not resolved.
- Method resolution order (MRO) is not considered.
- Builtins and stdlib calls appear in raw call lists but will rarely be
  targets anyone queries for.
"""

import os
from typing import Any, Dict, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from .index import find_callers
from .renderer import render_calls_structure
from ...utils.results import ResultBuilder

_HELP: Dict[str, Any] = {
    'name': 'calls',
    'description': 'Cross-file call graph queries — find callers of any function across your project.',
    'syntax': 'calls://<path>?target=<function>[&depth=N][&format=dot]',
    'parameters': {
        'target': 'Function name to find callers of (required)',
        'depth': 'Transitive depth (default 1, max 5)',
        'format': 'Output format: text (default) or dot (Graphviz)',
    },
    'examples': [
        {'uri': 'calls://src/?target=validate_item',
         'description': 'Find all callers of validate_item across the project'},
        {'uri': 'calls://src/?target=process_batch&depth=2',
         'description': 'Include callers-of-callers (transitive, 2 levels)'},
        {'uri': 'calls://src/?target=main&format=dot',
         'description': 'Output as Graphviz dot (pipe to dot -Tsvg)'},
    ],
    'notes': [
        'Static analysis only — dynamic dispatch (callbacks, metaclasses) is not resolved.',
        'Results are cached per-directory; any file change triggers a full rebuild.',
        'Callee names are normalised: "self.foo" → "foo" for index lookup.',
        'depth=N expands callers transitively up to N levels (capped at 5).',
    ],
}

_SCHEMA: Dict[str, Any] = {
    'adapter': 'calls',
    'description': 'Cross-file callers index — who calls a given function?',
    'uri_syntax': 'calls://<path>?target=<name>',
    'query_params': {
        'target': {'type': 'string',  'description': 'Function name to find callers of (required)'},
        'depth':  {'type': 'integer', 'description': 'Transitive depth 1-5 (default 1)'},
        'format': {'type': 'string',  'description': 'Output format: text (default) or dot'},
    },
    'elements': {},
    'supports_batch': False,
    'supports_advanced': False,
}


class CallsRenderer:
    """Renderer shim so the adapter works with the standard render pipeline."""

    def render_structure(self, data: Dict[str, Any], **kwargs) -> None:
        output_format = kwargs.get('format', 'text')
        render_calls_structure(data, output_format)

    def render_element(self, data: Dict[str, Any], **kwargs) -> None:
        render_calls_structure(data, kwargs.get('format', 'text'))

    def render_error(self, error: Exception) -> None:
        print(f"Error: {error}")


@register_adapter('calls')
@register_renderer(CallsRenderer)
class CallsAdapter(ResourceAdapter):
    """Adapter for cross-file call graph queries via calls:// URIs.

    Examples:
        calls://src/?target=validate_item
        calls://src/?target=process_batch&depth=2
        calls://src/?target=main&format=dot
    """

    BUDGET_LIST_FIELD = 'levels'

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for calls:// adapter."""
        return _HELP

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for calls:// adapter."""
        return _SCHEMA

    def __init__(self, path: str, query_string: Optional[str] = None):
        self.path = os.path.expanduser(path)
        self.query_params = _parse_calls_query(query_string or '')

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        target = self.query_params.get('target', '')
        depth = int(self.query_params.get('depth', '1'))
        depth = max(1, min(depth, 5))  # cap at 5 to avoid runaway transitive walks

        if not target:
            return ResultBuilder.create(
                result_type='calls_query',
                source=self.path,
                contract_version='1.1',
                data={
                    'path': self.path,
                    'error': "Missing required parameter: target=<function_name>",
                    'example': f"calls://{self.path}?target=my_function",
                }
            )

        result_data = find_callers(self.path, target, depth=depth)
        result_data['path'] = self.path

        return ResultBuilder.create(
            result_type='calls_query',
            source=self.path,
            contract_version='1.1',
            data=result_data,
        )


def _parse_calls_query(query_string: str) -> Dict[str, str]:
    """Parse simple key=value query params from a calls:// query string."""
    params: Dict[str, str] = {}
    if not query_string:
        return params
    for part in query_string.split('&'):
        part = part.strip()
        if '=' in part:
            key, _, value = part.partition('=')
            params[key.strip()] = value.strip()
    return params
