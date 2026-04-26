"""Core AST query adapter."""

import os

from typing import Dict, List, Any, Optional

from .queries import (
    parse_query, format_query,
    extract_show_param as _extract_show_param,
    extract_builtins_param as _extract_builtins_param,
    extract_reveal_type_param as _extract_reveal_type_param,
)
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

    BUDGET_LIST_FIELD = 'results'

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

        # Detect multi-file colon syntax (e.g. file1.py:file2.py) which is unsupported.
        # Colons in valid paths: Windows drive letters (C:\), or schemes (://). On Linux/Mac
        # a colon in a plain path almost always means the user copied diff:// syntax by mistake.
        if ':' in self.path and '://' not in self.path and not os.path.exists(self.path):
            parts = self.path.split(':', 1)
            left, right = parts[0], parts[1]
            # Raise helpful error if either side looks like a code file path
            if left.endswith(('.py', '.js', '.ts', '.go', '.rs', '.rb', '.java', '.cpp', '.c')) \
                    or right.endswith(('.py', '.js', '.ts', '.go', '.rs', '.rb', '.java', '.cpp', '.c')) \
                    or os.path.exists(left) or os.path.exists(right):
                raise ValueError(
                    f"ast:// does not support multi-file colon syntax: {path!r}\n"
                    "  Each ast:// query targets one file or directory.\n"
                    "  Run separate queries:\n"
                    f"    reveal 'ast://{left}?<filter>'\n"
                    f"    reveal 'ast://{right}?<filter>'"
                )

        # Extract result control parameters (sort, limit, offset)
        if query_string:
            cleaned_query, self.result_control = parse_result_control(query_string)
            # Extract show=, builtins=, reveal_type= before parsing filters (display modes, not filters)
            cleaned_query, self.show_mode = _extract_show_param(cleaned_query)
            cleaned_query, self.include_builtins = _extract_builtins_param(cleaned_query)
            cleaned_query, self.reveal_type_var = _extract_reveal_type_param(cleaned_query)
            self.query = parse_query(cleaned_query)
        else:
            self.query = {}
            self.result_control = ResultControl()
            self.show_mode = None
            self.include_builtins = False
            self.reveal_type_var = None

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
        # show=dict-heatmap: ranked bare-dict param heatmap
        if self.show_mode == 'dict-heatmap':
            from .nav_dict_heatmap import collect_dict_heatmap
            items = collect_dict_heatmap(self.path)
            meta = self.create_meta(parse_mode='python_ast',
                                    confidence=1.0, warnings=[], errors=[])
            result = ResultBuilder.create(
                result_type='ast_dict_heatmap',
                source=self.path,
                contract_version='1.1',
                data={
                    'path': self.path,
                    'total_results': len(items),
                    'results': items,
                },
            )
            result['meta'] = meta
            return result

        # reveal_type=<var>: type-evidence mode — entirely different result shape
        if self.reveal_type_var:
            from .nav_reveal_type import collect_type_evidence
            evidence = collect_type_evidence(self.path, self.reveal_type_var)
            meta = self.create_meta(parse_mode='tree_sitter_full',
                                    confidence=1.0, warnings=[], errors=[])
            result = ResultBuilder.create(
                result_type='ast_reveal_type',
                source=self.path,
                contract_version='1.1',
                data={
                    'path': self.path,
                    'var_name': self.reveal_type_var,
                    'total_results': len(evidence),
                    'results': evidence,
                },
            )
            result['meta'] = meta
            return result

        # Collect all structures from path (file or directory)
        structures = collect_structures(self.path)

        # Apply filters
        filtered = apply_filters(structures, self.query)

        # Apply result control (sort, limit, offset)
        controlled = apply_result_control(filtered, self.result_control)

        # Auto-cap large unfiltered result sets to prevent accidental token floods.
        # Applies only when no explicit limit was set by the user.
        DEFAULT_RESULT_CAP = 200
        auto_capped = False
        if not self.result_control.limit and len(controlled) > DEFAULT_RESULT_CAP:
            auto_capped = True
            auto_capped_total = len(controlled)
            controlled = controlled[:DEFAULT_RESULT_CAP]

        # Create trust metadata (v1.1)
        # AST adapter uses tree-sitter for parsing
        meta = self.create_meta(
            parse_mode='tree_sitter_full',
            confidence=1.0 if structures else 0.0,
            warnings=[],
            errors=[]
        )

        if not meta.get('warnings'):
            meta['warnings'] = []

        # Add truncation metadata if results were limited
        if self.result_control.limit or self.result_control.offset:
            if len(filtered) > len(controlled):
                meta['warnings'].append({
                    'type': 'truncated',
                    'message': f'Results truncated: showing {len(controlled)} of {len(filtered)} total matches'
                })

        # Warn when auto-cap kicked in
        if auto_capped:
            meta['warnings'].append({
                'type': 'auto_capped',
                'message': (
                    f'Large result set capped at {DEFAULT_RESULT_CAP} of {auto_capped_total} matches. '
                    f'Add filters to narrow results, or use ?limit=N to set an explicit cap.'
                )
            })

        # Filter builtins from calls lists unless ?builtins=true
        if not self.include_builtins:
            from ..calls.index import PYTHON_BUILTINS
            for elem in controlled:
                if elem.get('calls'):
                    elem['calls'] = [c for c in elem['calls'] if c.split('.')[-1] not in PYTHON_BUILTINS]

        # Build result using ResultBuilder (automatically handles contract_version, source, source_type)
        result = ResultBuilder.create(
            result_type='ast_query',
            source=self.path,
            contract_version='1.1',
            data={
                'path': self.path,
                'query': format_query(self.query),
                'show_mode': self.show_mode,
                'total_files': len(structures),
                'total_results': len(filtered),
                'displayed_results': len(controlled),
                'results': controlled
            }
        )
        result['meta'] = meta
        return result
