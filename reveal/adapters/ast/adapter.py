"""Core AST query adapter."""

import os
from reveal.reveal_types import CONTRACT_VERSION

from pathlib import Path
from typing import Dict, List, Any, Optional

from .queries import (
    parse_query, format_query,
    extract_show_param as _extract_show_param,
    extract_builtins_param as _extract_builtins_param,
    extract_reveal_type_param as _extract_reveal_type_param,
)
from .analysis import collect_structures, PYTHON_BUILTINS
from .filtering import apply_filters, matches_decorator, find_unknown_filter_keys
from .help import get_help as _get_help, get_schema as _get_schema
from .renderer import AstRenderer
from ..base import ResourceAdapter, Stability, register_adapter, register_renderer
from ...core import suppress_treesitter_warnings
from ...registry import language_for_extension, get_code_extensions
from ...utils.query import (
    parse_result_control,
    apply_result_control,
    ResultControl
)
from ...utils.results import ResultBuilder

# Suppress tree-sitter warnings (centralized in core module)
suppress_treesitter_warnings()


def _degraded_conformance_warning(elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """BACK-1086: ast:// hardcodes confidence=1.0 for any non-empty result,
    regardless of how much the scanned language's analyzer actually
    extracts — a caller sees the same confidence:1.0 for a Python scan
    (tier1-verified) as for a language with only smoke-tested or
    structure-only support. Surface which languages among the *returned*
    elements are below tier1-verified so that gap is disclosed instead of
    silently uniform, matching the warnings-array pattern already used for
    truncation/auto-cap in get_structure() below.

    Deliberately does not touch the numeric `confidence` field itself —
    deriving one scalar confidence for a directory scan spanning multiple
    languages of different conformance tiers is a separate design question
    (see BACK-1086's notes), not resolved by this disclosure.
    """
    from ...capabilities import get_capability_for_extension, CONFORMANCE_TIER1_VERIFIED

    degraded: Dict[str, str] = {}
    seen_exts = set()
    for elem in elements:
        ext = os.path.splitext(elem.get('file', ''))[1].lower()
        if not ext or ext in seen_exts:
            continue
        seen_exts.add(ext)
        profile = get_capability_for_extension(ext)
        if profile is not None and profile.conformance_level != CONFORMANCE_TIER1_VERIFIED:
            degraded[profile.language] = profile.conformance_level

    if not degraded:
        return None
    languages = ', '.join(f"{lang} ({level})" for lang, level in sorted(degraded.items()))
    return {
        'type': 'degraded_language_conformance',
        'message': (
            f"Results include language(s) below tier1-verified conformance: "
            f"{languages}. Structure extraction may be incomplete for these "
            f"files — see reveal --language-info <ext> for details."
        ),
    }


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
    HELP_CLUSTER = ('Code Analysis', 'Self-Describing')
    QUICK_RANK = 0

    STABILITY = Stability.STABLE
    BUDGET_LIST_FIELD = 'results'
    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907

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

    def __init__(self, resource: str, query: Optional[str] = None):
        """Initialize AST adapter.

        Args:
            resource: File or directory path to analyze
            query: Query parameters (e.g., "lines>50&complexity>10&sort=-lines&limit=20")
        """
        path, query_string = resource, query
        # Expand ~ to home directory
        self.path = os.path.expanduser(path)

        # Detect multi-file colon syntax (e.g. file1.py:file2.py) which is unsupported.
        # Colons in valid paths: Windows drive letters (C:\), or schemes (://). On Linux/Mac
        # a colon in a plain path almost always means the user copied diff:// syntax by mistake.
        if ':' in self.path and '://' not in self.path and not os.path.exists(self.path):
            parts = self.path.split(':', 1)
            left, right = parts[0], parts[1]
            # Raise helpful error if either side looks like a code file path
            code_extensions = tuple(get_code_extensions())
            if left.endswith(code_extensions) \
                    or right.endswith(code_extensions) \
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

    def get_structure(self, structures: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:
        """Get filtered AST structure based on query.

        Args:
            structures: Optional pre-collected structure list, bypassing this
                method's own `collect_structures(self.path)` walk+parse. Lets a
                caller that already walked and parsed the same files for
                another purpose (`reveal architecture`, BACK-489) share that
                work instead of triggering a second full-repo walk.

        Returns:
            Dict containing query results with metadata
        """
        # show=dict-heatmap: ranked bare-dict param heatmap
        if self.show_mode == 'dict-heatmap':
            from .nav_dict_heatmap import collect_dict_heatmap, has_python_files
            items = collect_dict_heatmap(self.path)
            unsupported_language = ''
            if not items and not has_python_files(self.path):
                from ...utils.path_utils import detect_non_python_language
                unsupported_language = detect_non_python_language(Path(self.path))
            meta = self.create_meta(parse_mode='python_ast',
                                    confidence=1.0, warnings=[], errors=[])
            result = ResultBuilder.create(
                result_type='ast_dict_heatmap',
                source=self.path,
                contract_version=CONTRACT_VERSION,
                data={
                    'path': self.path,
                    'total_results': len(items),
                    'results': items,
                    'unsupported_language': unsupported_language,
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
                contract_version=CONTRACT_VERSION,
                data={
                    'path': self.path,
                    'var_name': self.reveal_type_var,
                    'total_results': len(evidence),
                    'results': evidence,
                },
            )
            result['meta'] = meta
            return result

        # Collect all structures from path (file or directory), unless the
        # caller already collected them (see `structures` param docstring above)
        if structures is None:
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

        degraded_warning = _degraded_conformance_warning(controlled)
        if degraded_warning:
            meta['warnings'].append(degraded_warning)

        # Disclose when a zero-result query traces to a filter key that never
        # appeared on any scanned element — typo vs. genuine zero (BACK-1111)
        if not filtered and self.query:
            unknown_keys = find_unknown_filter_keys(structures, self.query)
            if unknown_keys:
                keys_str = ', '.join(f"'{k}'" for k in unknown_keys)
                meta['warnings'].append({
                    'type': 'unknown_filter_key',
                    'message': (
                        f"Filter key(s) {keys_str} never appear on any scanned element — "
                        f"this may be a typo rather than a genuine zero-match. "
                        f"See: reveal help://ast"
                    )
                })

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

        # Filter builtins from calls lists unless ?builtins=true. Python-file
        # elements only -- PYTHON_BUILTINS names (map/filter/sorted/...) can
        # collide with real methods in other languages (Scala/Ruby `.map`,
        # `.filter`), same cross-language bug class as BACK-748's calls://
        # adapter fix; this ast:// copy of the filter was missed there.
        if not self.include_builtins:
            for elem in controlled:
                if elem.get('calls') and language_for_extension(
                    os.path.splitext(elem.get('file', ''))[1].lower()
                ) == 'python':
                    elem['calls'] = [c for c in elem['calls'] if c.split('.')[-1] not in PYTHON_BUILTINS]

        # BACK-1258: tag each result test/vendor/minified, the same field
        # hotspots:// and overview:// already carry. ast://?complexity>N is a
        # ranking a reader treats as "what to look at first", and on a repo that
        # commits vendored JS it can be dominated by files nobody will ever edit
        # (8 of 19 on camaleon-cms) with nothing in the output saying so.
        # Additive and advisory -- ranking and result count are unchanged.
        from ...utils.path_utils import provenance_for_display_path
        _base = Path(self.path)
        for elem in controlled:
            elem['provenance'] = provenance_for_display_path(elem.get('file'), _base)
        _noise = sum(
            1 for e in controlled
            if e.get('provenance') in ('vendor', 'minified')
        )
        if _noise:
            meta['warnings'].append({
                'type': 'unfiltered_ranking',
                'message': (
                    f'{_noise} of {len(controlled)} results are vendored or minified '
                    f'files. Results are not filtered by provenance -- read the '
                    f'per-result "provenance" field, or exclude them with '
                    f'--exclude, before treating this as a ranking of your own code.'
                ),
            })

        # Build result using ResultBuilder (automatically handles contract_version, source, source_type)
        result = ResultBuilder.create(
            result_type='ast_query',
            source=self.path,
            contract_version=CONTRACT_VERSION,
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
