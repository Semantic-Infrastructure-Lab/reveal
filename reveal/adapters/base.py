"""Base adapter interface for URI resources.

This module defines the ResourceAdapter ABC and re-exports the factory and
registry helpers so existing importers continue to work unchanged.

Internal layout:
  factory.py  — _try_* constructor patterns and _default_from_uri
  registry.py — _ADAPTER_REGISTRY, _RENDERER_REGISTRY, decorators, plugin discovery
  base.py     — ResourceAdapter ABC (this file)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Iterable, Optional, List, Tuple

from reveal.types import RevealMeta, RevealResult, WarningEntry

# Re-exported for backward compatibility — existing importers need not change.
from .factory import (  # noqa: F401
    _is_constructor_error,
    _try_no_args_init,
    _try_query_parsing_init,
    _try_keyword_args_init,
    _try_resource_arg_init,
    _try_full_uri_init,
    _default_from_uri,
)
from .registry import (  # noqa: F401
    _ADAPTER_REGISTRY,
    _RENDERER_REGISTRY,
    _adapter_plugins_loaded,
    _load_adapter_plugin_dir,
    discover_adapter_plugins,
    _reset_adapter_plugin_discovery,
    register_adapter,
    get_adapter_class,
    list_supported_schemes,
    register_renderer,
    get_renderer_class,
    list_renderer_schemes,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdapterFlag:
    """A CLI flag an adapter owns, used by generic file routing to reject the
    flag on plain file paths without hard-coding per-adapter tables.

    attr:     argparse dest checked on the parsed args namespace.
    flag:     display form shown in the error, e.g. '--expiring-within'.
    examples: exact stderr example block printed under 'Examples:' — kept
              verbatim per-flag because some flags intentionally omit the
              URI-param form (BACK-162).
    """
    attr: str
    flag: str
    examples: str


class ResourceAdapter(ABC):
    """Base class for all resource adapters."""

    # Override in subclasses to name the top-level list field that budget
    # constraints (--max-items, --max-snippet-chars) should apply to.
    # None = this adapter has no budget-limitable list field.
    BUDGET_LIST_FIELD: Optional[str] = None

    # Set True in subclasses where scheme://RESOURCE means "get element RESOURCE"
    # rather than "analyze path RESOURCE" (e.g. env, python, help).
    ELEMENT_NAMESPACE_ADAPTER: bool = False

    # True for adapters that only ever inspect reveal's own source tree
    # (e.g. reveal://), never an external user's resources. Excluded from
    # default --adapters/--discover listings; shown with --all.
    internal: bool = False

    # CLI flags this adapter owns. Generic file routing rejects these flags on
    # plain file paths (see cli/routing/file.py:_guard_adapter_flags) instead
    # of hard-coding per-adapter tables. Empty = adapter owns no guarded flags.
    GUARDED_FLAGS: Tuple[AdapterFlag, ...] = ()

    # File extensions on which this adapter's GUARDED_FLAGS are valid (the guard
    # is skipped for these). Empty set = the flags are never valid on a plain
    # path, so the guard always fires (e.g. ssl:// has no file form).
    GUARDED_FLAG_EXTENSIONS: frozenset = frozenset()

    # Trailing noun in the guard error "... only works with {context}", plus the
    # help:// topic. Only consulted when GUARDED_FLAGS is non-empty.
    GUARDED_FLAG_CONTEXT: str = ''
    GUARDED_FLAG_HELP: str = ''

    @classmethod
    def from_uri(cls, scheme: str, resource: str,
                 element: Optional[str]) -> 'ResourceAdapter':
        """Initialize adapter from URI components.

        Tries multiple constructor conventions in order. Override in subclasses
        for deterministic, single-call initialization without a fallback chain.

        Different adapters have different conventions:
        - No-arg: env, python (take no resource in __init__)
        - Resource-arg: help, reveal (take resource string as first arg)
        - Query-parsing: ast, json (parse resource to extract path/query)
        - URI: mysql (expect full URI like mysql://host:port)

        Raises:
            ImportError: If initialization failed due to a missing optional dependency.
            RuntimeError: If all initialization attempts failed.
        """
        return _default_from_uri(cls, scheme, resource, element)

    @abstractmethod
    def get_structure(self, **kwargs) -> RevealResult:
        """Get the structure/overview of the resource.

        Returns:
            Dict containing structured representation of the resource
        """
        pass

    def post_process(self, result: RevealResult, args: Any) -> RevealResult:
        """Post-process adapter result. Override in subclasses to transform output."""
        return result

    @staticmethod
    def create_meta(
        parse_mode: Optional[str] = None,
        confidence: Optional[float] = None,
        warnings: Optional[List[WarningEntry]] = None,
        errors: Optional[List[WarningEntry]] = None
    ) -> RevealMeta:
        """Create Output Contract v1.1 meta dict with trust metadata.

        For adapters that use parsing (tree-sitter, regex, heuristics) to provide
        quality/confidence information to AI agents.

        Args:
            parse_mode: How parsing was performed
                - "tree_sitter_full" - Complete AST parsing (high confidence)
                - "tree_sitter_partial" - Partial AST parsing (some errors)
                - "fallback" - Tree-sitter failed, used fallback
                - "regex" - Regular expression extraction
                - "heuristic" - Pattern-based heuristics
            confidence: Overall confidence (0.0-1.0)
                - 1.0 = Perfect parse
                - 0.95-0.99 = High confidence
                - 0.80-0.94 = Good confidence
                - 0.50-0.79 = Partial results
                - < 0.50 = Low confidence
            warnings: Non-fatal issues
                [{'code': 'W001', 'message': '...', 'file': '...'}]
            errors: Fatal errors with fallback info
                [{'code': 'E002', 'message': '...', 'file': '...', 'fallback': '...'}]

        Returns:
            Meta dict for Output Contract v1.1

        Example:
            meta = ResourceAdapter.create_meta(
                parse_mode='tree_sitter_full',
                confidence=0.95,
                warnings=[{
                    'code': 'W001',
                    'message': 'File encoding uncertain',
                    'file': 'legacy.py'
                }]
            )
            return {
                'contract_version': '1.1',
                'type': 'ast_query',
                'source': 'src/',
                'source_type': 'directory',
                'meta': meta,  # <- Include meta
                'results': [...]
            }
        """
        # BACK-447: delegate to ResultBuilder — the sole output-contract
        # constructor. Kept as a thin passthrough so existing adapters that
        # call `self.create_meta(...)` keep working while the contract logic
        # lives in exactly one place.
        from reveal.utils.results import ResultBuilder
        return ResultBuilder.create_meta(parse_mode, confidence, warnings, errors)

    def get_element(self, element_name: str, **kwargs) -> Optional[RevealResult]:
        """Get details about a specific element within the resource.

        Args:
            element_name: Name/identifier of the element to retrieve

        Returns:
            Dict containing element details, or None if not found
        """
        return None

    def get_available_elements(self) -> List[Dict[str, str]]:
        """Get list of available elements for this resource.

        Returns list of available elements that can be accessed via get_element().
        Each element includes name, description, and example usage.

        Returns:
            List of dicts with keys:
                - name (str): Element identifier (e.g., 'san', 'chain')
                - description (str): Human-readable description
                - example (str): Example usage (e.g., 'reveal ssl://example.com/san')

        Example:
            [
                {
                    'name': 'san',
                    'description': 'Subject Alternative Names (3 domains)',
                    'example': 'reveal ssl://example.com/san'
                },
                {
                    'name': 'chain',
                    'description': 'Certificate chain (2 certificates)',
                    'example': 'reveal ssl://example.com/chain'
                }
            ]

        Note:
            Default implementation returns empty list. Adapters with element support
            should override this method to provide discoverable elements.

            For adapters with dynamic elements (e.g., env:// with variable names,
            json:// with keys), consider returning:
                - Empty list (no static elements)
                - Sample/common elements with note
                - Top N most relevant elements from current data
        """
        return []

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

    @staticmethod
    def get_schema() -> Optional[Dict[str, Any]]:
        """Get machine-readable schema for this adapter (optional).

        For AI agent integration: Implement this method to provide discoverable
        schemas that enable agents to auto-generate valid queries.

        Returns:
            Dict containing schema metadata, or None if no schema available.

            Required keys:
                - adapter (str): Adapter scheme name (e.g., 'ssl', 'ast')
                - description (str): One-line summary
                - uri_syntax (str): URI pattern (e.g., 'ssl://<host>[:<port>][/<element>]')

            Recommended keys:
                - query_params (Dict[str, Dict]): Query parameters with type/description
                  {'param_name': {'type': 'string', 'description': '...', 'required': bool}}
                - elements (List[str]): Available elements for element-based queries
                - output_types (List[Dict]): Output structure definitions
                  [{'type': 'ssl_certificate', 'schema': {...}, 'example': {...}}]
                - cli_flags (List[str]): Available CLI flags
                - example_queries (List[Dict]): Canonical query examples
                  [{'uri': '...', 'description': '...', 'output_type': '...'}]

            Optional keys:
                - operators (Dict[str, str]): Supported query operators (>, <, =, etc.)
                - filters (Dict[str, Dict]): Available filters with type info
                - supports_batch (bool): Whether adapter supports stdin batch mode
                - supports_advanced (bool): Whether --advanced flag is supported

        Purpose:
            - AI agents discover capabilities programmatically
            - Auto-generate valid queries without hardcoding
            - Understand expected output structure
            - Generate correct query parameters

        Best Practices:
            - Include JSON Schema definitions for complex output types
            - Provide example outputs (small, realistic samples)
            - Document all query parameters with types
            - Include 3-5 example queries covering common use cases

        For detailed guidance:
            reveal help://adapter-authoring - Schema authoring guide

        Examples:
            See reveal/adapters/ssl.py, ast.py for reference implementations
        """
        return None

    def _warn_unknown_query_params(self, query_params: Dict[str, Any], *,
                                   skip_filter_keys: bool = False,
                                   extra_known_keys: Optional[Iterable[str]] = None) -> None:
        """Warn (stderr) about query params not in this adapter's schema.

        Closed-param adapters read a fixed key set via ``.get()`` and silently
        ignore the rest, so a typo'd or unsupported param (e.g.
        ``stats://?complexity=true``) returns a valid-looking-but-wrong result
        with no signal (BACK-507). Call this once, after parsing, from adapters
        that consume a *closed* param set. The recognized set is derived from
        this adapter's own ``get_schema()['query_params']`` so it stays in sync
        automatically; fails open (no schema / no declared params → no check),
        and warns without raising — the result is still produced.

        Do NOT call from filter-based adapters (``ast://``, ``markdown://``,
        ``json://``) whose query accepts arbitrary field names — every valid
        filter would be flagged. Mixed adapters (``stats://``, ``git://``) that
        parse the same query string as both params and filters should pass
        ``skip_filter_keys=True`` so filter expressions aren't flagged.

        Args:
            query_params: parsed ``{key: value}`` dict.
            skip_filter_keys: skip keys carrying a filter operator (mixed adapters).
            extra_known_keys: additional recognized keys not in the schema —
                e.g. an adapter that also honors the cross-cutting result-control
                params (``sort``/``limit``/``offset``) passes those here so they
                aren't flagged. Adapters that do *not* support them omit this, so
                an unsupported ``?limit=5`` still warns.
        """
        schema = type(self).get_schema()
        if not isinstance(schema, dict):
            return
        declared = schema.get('query_params')
        if not declared:
            return
        known = set(declared.keys())
        if extra_known_keys:
            known |= set(extra_known_keys)
        from ..utils.query import warn_unknown_query_params
        warn_unknown_query_params(
            query_params,
            known,
            adapter=schema.get('adapter', ''),
            skip_filter_keys=skip_filter_keys,
        )
