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
from enum import Enum
from typing import Dict, Any, Iterable, Optional, List, Tuple

from reveal.reveal_types import RevealMeta, RevealResult, WarningEntry, CONTRACT_VERSION

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


class Stability(str, Enum):
    """Maturity of an adapter, surfaced as a badge in ``help://``.

    Owned by the adapter class (``ResourceAdapter.STABILITY``) so the help
    renderer can *derive* the badge from the registry instead of hand-maintained
    STABLE/BETA/PROJECT sets — a new adapter can never silently render with the
    wrong badge (BACK-688). Values are strings so they compare and serialize
    naturally (``Stability.BETA == "beta"``).
    """

    STABLE = "stable"          # 🟢 battle-tested, stable contract
    BETA = "beta"              # 🟡 shipped and working, contract may still evolve
    PROJECT = "project"        # 🎓 production-ready example for a specific project
    EXPERIMENTAL = "experimental"  # 🔴 genuinely unfinished / use at your own risk


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

    # Adapter maturity, rendered as a stability badge in `help://`. Defaults to
    # BETA — the honest baseline for a shipped-but-evolving adapter. Override to
    # STABLE (battle-tested), PROJECT (project-specific example), or EXPERIMENTAL
    # (genuinely unfinished). Owning this on the class (not a satellite set in the
    # renderer) means a new or plugin adapter can never silently mislabel (BACK-688).
    STABILITY: Stability = Stability.BETA

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

    # False = this adapter's __init__ matches the canonical signature
    # __init__(self, resource='', query=None, **kwargs) and from_uri() should
    # construct it directly instead of guessing via the 5-strategy try-chain
    # in factory.py. All 25 production adapters have migrated (BACK-907);
    # the True default now exists only for third-party/plugin adapters and
    # test doubles, and firing it emits a one-time DeprecationWarning
    # (BACK-948) — migrate rather than rely on it. Set False only after
    # verifying the adapter's __init__ actually accepts (resource, query)
    # positionally — the canonical contract test in test_adapter_contracts.py
    # enforces this.
    LEGACY_INIT: bool = True

    # What an empty resource string means for this adapter's canonical
    # __init__ (LEGACY_INIT = False only — ignored otherwise). Default '.'
    # matches path-based adapters, where bare scheme:// means "current
    # directory" (ast, calls, json, patches, stats, depends, imports).
    # Connection-string adapters (sqlite, mysql, cpanel, ...) must override
    # to '' — they have their own empty-resource validation/fallback
    # (e.g. bare mysql:// deliberately means "read ~/.my.cnf"), and silently
    # substituting '.' would misread it as a literal host/path instead.
    CANONICAL_EMPTY_RESOURCE: str = '.'

    # help://relationships cluster membership, declared at the adapter
    # definition site so it can't drift from help.py's hand-maintained
    # dicts (BACK-1156). None = not shown in any cluster. Most adapters
    # belong to exactly one cluster (a plain str); a few genuinely span two
    # (e.g. ast:// is core to both "Code Analysis" and "Self-Describing") —
    # a tuple covers that without forcing a false single choice.
    HELP_CLUSTER: Optional['str | Tuple[str, ...]'] = None

    # Rank hint for help://quick's top command block (lower sorts first).
    # None = not part of the small ranked cheat-sheet — still fully
    # discoverable via help://relationships and help://adapters, just not
    # in the top-N. Declared here (not a satellite dict in help.py) so a
    # new adapter's absence from the cheat-sheet is a deliberate choice,
    # not a silent omission (BACK-1154/1155).
    QUICK_RANK: Optional[int] = None

    def __init__(self, resource: str = '', query: Optional[str] = None, **kwargs: Any) -> None:
        """Canonical constructor matching the signature LEGACY_INIT already
        documents (BACK-1020). Establishes the instance state int_param()/
        compose()/record_composed_error() assume but the base class never
        declared: self.resource, self.query, self.query_params (empty until
        a subclass parses it — see reveal.utils.query_parser.parse_query_params),
        and the three composition accumulators compose()/record_composed_error()
        previously had to poke into self.__dict__ via setdefault() because
        there was nowhere to initialize them.

        NOT force-called by every subclass. Most existing adapters define
        their own __init__ without calling super() — that stays safe:
        compose()/record_composed_error() still use setdefault() as a
        fallback for instances that never ran this. A subclass that DOES
        call super().__init__(resource, query, **kwargs) gets everything
        pre-declared as a normal attribute instead of a setdefault'd one.
        """
        self.resource = resource
        self.query = query
        self.query_params: Dict[str, Any] = {}
        self._composed_warnings: List[Dict[str, Any]] = []
        self._composed_errors: List[Dict[str, Any]] = []
        self._composed_confidences: List[float] = []

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
                'contract_version': CONTRACT_VERSION,
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

    def compose(self, adapter_cls: type, resource: Any, *,
                query: Optional[str] = None, default: Any = None,
                **params: Any) -> Any:
        """Run a sibling adapter in-process as part of this adapter's own scan.

        Replaces the "build a query string by hand, construct the sibling,
        swallow any exception into `[]`/`{}`" pattern that produced BACK-984:
        a crashed sub-scan rendered as an empty section, indistinguishable
        from a genuinely clean result, with the trust envelope
        (``meta.warnings``/``errors``/``confidence``) never consulted.

        ``adapter_cls`` must accept the canonical ``(resource, query)``
        constructor. Pass simple params as keywords (``hotspots=True`` becomes
        ``?hotspots=True``, safely urlencoded — no per-call-site string
        formatting); pass ``query=`` directly for adapters using a
        filter-expression or bare-flag query dialect (e.g.
        ``query='complexity>=10&sort=-complexity'``, ``query='circular'``).

        On success, the child's ``meta.warnings``/``errors`` are folded into
        this adapter's own accumulated meta, and its ``meta.confidence`` (if
        present) is tracked so the parent's composed confidence
        (``composed_meta()``) reflects the weakest part, not just the parts
        that happened to succeed. On exception, records an *attributed*
        error (child adapter name, resource, exception message) instead of
        silently discarding it, and returns ``default``.

        Call ``self.composed_meta()`` once, when building the final result,
        and pass its warnings/errors/confidence into ``ResultBuilder.create()``.
        """
        if query is None and params:
            from urllib.parse import urlencode
            query = urlencode(params)

        child_name = getattr(adapter_cls, '__name__', str(adapter_cls))
        try:
            child = adapter_cls(str(resource), query)
            result = child.get_structure()
        except Exception as exc:
            self.record_composed_error(child_name, resource, exc)
            return default

        if isinstance(result, dict):
            self.fold_meta(result.get('meta'))

        return result

    def fold_meta(self, meta: Optional[RevealMeta]) -> None:
        """Fold a raw ``meta`` dict (as returned in a result's ``meta`` key)
        into this adapter's own composed accumulators, same as ``compose()``
        does for a sibling adapter's result. Use this directly (BACK-1166)
        when a get_structure() calls an *analyzer* rather than a sibling
        adapter (e.g. xlsx.py's XlsxAdapter delegating to XlsxAnalyzer) --
        compose() only knows how to construct+call adapters, not fold an
        already-built meta dict a caller obtained some other way.
        """
        if not meta:
            return
        self.__dict__.setdefault('_composed_warnings', []).extend(
            meta.get('warnings', []))
        self.__dict__.setdefault('_composed_errors', []).extend(
            meta.get('errors', []))
        confidence = meta.get('confidence')
        if confidence is not None:
            self.__dict__.setdefault('_composed_confidences', []).append(confidence)

    def record_composed_error(self, source_name: str, resource: Any, exc: Exception) -> None:
        """Record an attributed sub-scan failure that didn't go through
        ``compose()`` — e.g. a sibling adapter driven via its private
        methods (a shared-walk perf optimization) rather than its
        ``get_structure()`` contract. Feeds the same accumulator
        ``compose()`` does, so ``composed_meta()`` sees both. Same fix as
        ``compose()`` for BACK-984, for the sites that can't use it directly.
        """
        self.__dict__.setdefault('_composed_errors', []).append({
            'code': 'E_COMPOSE',
            'message': f"{source_name}({resource!r}) failed: {exc}",
            'file': str(resource),
        })
        logger.warning("%s(%r) failed during composition: %s", source_name, resource, exc)

    def composed_meta(self) -> Optional[RevealMeta]:
        """Merge everything recorded by ``compose()``/``record_composed_error()``
        into one meta dict, or ``None`` if nothing was recorded (the common
        case — a clean scan emits no meta, unchanged from before BACK-984).
        Composed confidence is the minimum of any child confidences seen —
        a composite is only as trustworthy as its weakest part.

        Consuming: clears the accumulators after reading (BACK-1019) — a
        reused adapter instance's next ``get_structure()`` call starts clean
        instead of re-reporting this call's errors/warnings/confidence.
        Safe because every in-tree call site already follows the documented
        contract of calling this once, at the end, building the final result
        (nothing calls it twice per scan — verified by grep).
        """
        warnings_list = self.__dict__.get('_composed_warnings')
        errors_list = self.__dict__.get('_composed_errors')
        confidences_list = self.__dict__.get('_composed_confidences')
        if not warnings_list and not errors_list and not confidences_list:
            return None

        self._composed_warnings = []
        self._composed_errors = []
        self._composed_confidences = []

        from reveal.utils.results import ResultBuilder
        return ResultBuilder.create_meta(
            warnings=warnings_list or None,
            errors=errors_list or None,
            confidence=min(confidences_list) if confidences_list else None,
        )

    def int_param(self, key: str, default: int) -> int:
        """Read a numeric query param, treating an explicit 0 as present.

        The naive ``int(self.query_params.get(key) or default)`` idiom treats
        an explicit ``0`` as falsy and silently substitutes ``default`` —
        ``?top=0`` returns ``default`` results instead of zero, with no
        warning. See BACK-985.

        Precondition (BACK-1020): ``self.query_params`` must already be a
        dict — either set by ``__init__`` (empty ``{}`` if you never parse
        one) or, more usefully, populated by calling
        ``reveal.utils.query_parser.parse_query_params(query, coerce=True)``
        yourself in your subclass's ``__init__``. ``coerce=True`` is the
        convention this toolkit assumes: without it, values stay raw strings
        and a caller comparing ``== 'true'`` case-sensitively can silently
        miss ``?flag=True`` (see BACK-1018).
        """
        raw = self.query_params.get(key)
        return int(raw) if raw is not None else default

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
