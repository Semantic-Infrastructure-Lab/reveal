"""Core AST query adapter."""

import os
from pathlib import Path
from typing import Dict, List, Any, Optional

from .queries import parse_query, format_query
from .analysis import collect_structures
from .filtering import apply_filters, matches_decorator
from .help import get_help as _get_help, get_schema as _get_schema
from .renderer import AstRenderer
from ..base import ResourceAdapter, register_adapter, register_renderer
from ...core import suppress_treesitter_warnings
from ...utils.query import (
    parse_result_control,
    apply_result_control,
    ResultControl
)
from ...utils.results import ResultBuilder

# Suppress tree-sitter warnings (centralized in core module)
suppress_treesitter_warnings()


@register_adapter('ast')
@register_renderer(AstRenderer)
class AstAdapter(ResourceAdapter):
    """Adapter for querying code as an AST database via ast:// URIs.

    Examples:
        ast://./src                      # All code structure
        ast://./src?lines>50             # Functions with >50 lines
        ast://./src?complexity>10        # Complex functions
        ast://app.py?type=function       # Only functions
        ast://.?lines>20&complexity<5    # Long but simple functions
        ast://.?type!=function           # All non-functions (NEW: != operator)
        ast://.?name~=^test_             # Regex match (NEW: ~= operator)
        ast://.?lines=50..200            # Range filter (NEW: .. operator)
        ast://.?complexity>10&sort=-complexity&limit=10  # Top 10 most complex (NEW: sort, limit)
    """

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for ast:// adapter."""
        return _get_help()

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for ast:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return _get_schema()

    def __init__(self, path: str, query_string: Optional[str] = None):
        """Initialize AST adapter.

        Args:
            path: File or directory path to analyze
            query_string: Query parameters (e.g., "lines>50&complexity>10&sort=-lines&limit=20")
        """
        # Expand ~ to home directory
        self.path = os.path.expanduser(path)

        # Extract result control parameters (sort, limit, offset)
        if query_string:
            cleaned_query, self.result_control = parse_result_control(query_string)
            self.query = parse_query(cleaned_query)
        else:
            self.query = {}
            self.result_control = ResultControl()

        self.results: List[Any] = []

    def _matches_decorator(self, decorators: List[str], condition: Dict[str, Any]) -> bool:
        """Check if any decorator matches the condition.

        Delegates to filtering.matches_decorator for backward compatibility.
        Tests may call this as adapter._matches_decorator().

        Args:
            decorators: List of decorator strings
            condition: Condition dict with 'op' and 'value'

        Returns:
            True if any decorator matches
        """
        return matches_decorator(decorators, condition)

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get filtered AST structure based on query.

        Returns:
            Dict containing query results with metadata
        """
        # Collect all structures from path (file or directory)
        structures = collect_structures(self.path)

        # Apply filters
        filtered = apply_filters(structures, self.query)

        # Apply result control (sort, limit, offset)
        controlled = apply_result_control(filtered, self.result_control)

        # Create trust metadata (v1.1)
        # AST adapter uses tree-sitter for parsing
        meta = self.create_meta(
            parse_mode='tree_sitter_full',
            confidence=1.0 if structures else 0.0,
            warnings=[],
            errors=[]
        )

        # Add truncation metadata if results were limited
        if self.result_control.limit or self.result_control.offset:
            if not meta.get('warnings'):
                meta['warnings'] = []
            if len(filtered) > len(controlled):
                meta['warnings'].append({
                    'type': 'truncated',
                    'message': f'Results truncated: showing {len(controlled)} of {len(filtered)} total matches'
                })

        # Build result using ResultBuilder (automatically handles contract_version, source, source_type)
        result = ResultBuilder.create(
            result_type='ast_query',
            source=self.path,
            contract_version='1.1',
            data={
                'path': self.path,
                'query': format_query(self.query),
                'total_files': len(structures),
                'total_results': len(filtered),
                'displayed_results': len(controlled),
                'results': controlled
            }
        )
        result['meta'] = meta
        return result
