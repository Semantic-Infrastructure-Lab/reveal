"""Result building utilities for Output Contract v1.x compliance.

This module provides utilities for building standardized result dictionaries
that comply with the reveal Output Contract specification versions 1.0 and 1.1.

The ResultBuilder class eliminates ~200 lines of duplicate result construction
code across 15+ adapters by centralizing the common patterns:
- contract_version field
- type field
- source/source_type fields
- meta dict (v1.1)
- error handling

Usage:
    # Basic result (v1.0)
    result = ResultBuilder.create(
        result_type='stats_summary',
        source=Path('/path/to/dir'),
        data={'summary': {...}, 'files': [...]}
    )

    # Result with metadata (v1.1)
    result = ResultBuilder.create(
        result_type='ast_query',
        source=Path('/path/to/file.py'),
        data={'functions': [...]},
        contract_version='1.1',
        parse_mode='tree_sitter_full',
        confidence=0.95
    )

    # Error result
    result = ResultBuilder.create_error(
        result_type='stats_summary',
        source=Path('/path/to/dir'),
        error='Directory not found'
    )

An error result is a failure wherever it is rendered: ``outcome_of`` reads it, and the URI
router exits nonzero for it. An adapter returns the error; it does not exit. A cut list is
recorded with ``note_truncation``, and the router prints it; a renderer does not.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Literal, Union

from reveal.reveal_types import CONTRACT_VERSION, RevealMeta, RevealResult, WarningEntry


_CONTRACT_FIELDS: frozenset = frozenset(
    {'contract_version', 'type', 'source', 'source_type', 'meta', 'scope'}
)

Outcome = Literal['ok', 'truncated', 'not_applicable', 'failed']

# How to see what a cut left out, by what cut it. An adapter names the cause; the
# URI router prints the message once (cli/routing/uri._emit_result).
_TRUNCATION_HINTS = {
    'limit': 'raise ?limit=N or page with ?offset=N',
    'auto_cap': 'add filters, or set ?limit=N',
    'max_items': 'raise --max-items',
    'display_cap': 'use --all for everything, or --max-items N',
    'sample': 'choose others with --head/--tail/--range',
}


def outcome_of(result: Any) -> Outcome:
    """What a result says happened: the one definition the router turns into an exit code.

    - ``failed``: a top-level ``error`` is set (``ResultBuilder.create_error`` and the
      hand-built ``{'error': ...}`` dicts alike). The query did not produce its answer.
    - ``not_applicable``: ``applicable`` is False (BACK-1210). The query ran and does not
      apply to this target; that is a recorded answer, not a failure.
    - ``truncated``: a list in the answer was cut (``note_truncation``). The answer is
      correct but incomplete. It exits 0, and the router prints what was left out.
    - ``ok``: anything else, including an empty answer.

    Only the top-level key counts. ``meta.errors`` holds per-file problems inside an
    answer that was still produced (parse failures in ast/contracts/surface/patches), and
    a nested ``error`` belongs to one item of a list, not to the result (BACK-1059).
    """
    if not isinstance(result, dict):
        return 'ok'
    if result.get('error'):
        return 'failed'
    if result.get('applicable') is False:
        return 'not_applicable'
    if truncations_of(result):
        return 'truncated'
    return 'ok'


def note_truncation(result: Any, field: str, shown: int, total: int,
                    cause: str, hint: Optional[str] = None, exact: bool = True) -> None:
    """Record that ``result[field]`` holds ``shown`` of ``total`` items (BACK-1059).

    This is the one way to say a list was cut. It writes one ``meta.warnings`` entry per
    field: ``{'type': 'truncated', 'field', 'shown', 'total', 'exact', 'cause', 'message'}``.
    Before
    it, truncation was spelled six ways (a ``truncated`` or ``auto_capped`` meta warning,
    a top-level ``warnings`` list, ``meta.budget``, ``pagination``, a ``warning``
    string), and text renderers that didn't know a given spelling showed a cut list as
    complete.

    A second cut of the same field updates its entry: the adapter's own ``?limit``, then
    the router's ``--max-items``, is one disclosure of the smaller ``shown`` against the
    larger ``total``. Nothing is recorded when nothing was cut.

    ``exact=False``: the reader stopped once it had enough, so ``total`` is a lower bound
    (BACK-1547). git:// walks history until it holds one commit past ``?limit``; it knows
    more exist, not how many, and says "showing 50 of 51+". When two cuts of one field
    merge, the larger total wins, and on a tie the exact one does.
    """
    if shown >= total:
        return
    meta = result.get('meta')
    if not isinstance(meta, dict):
        meta = result['meta'] = {}
    if not isinstance(meta.get('warnings'), list):
        meta['warnings'] = []
    entry = next((w for w in meta['warnings']
                  if w.get('type') == 'truncated' and w.get('field') == field), None)
    if entry is None:
        entry = {'type': 'truncated', 'field': field}
        meta['warnings'].append(entry)
    else:
        shown = min(shown, entry['shown'])
        total, exact = max((total, exact), (entry['total'], entry.get('exact', True)))
    if hint is None:
        hint = _TRUNCATION_HINTS.get(cause, '')
    entry.update(shown=shown, total=total, exact=exact, cause=cause,
                 message=_truncation_message(field, shown, total, hint, exact))


def relabel_truncations(result: Any, field: str, hint: str) -> None:
    """Restate a composed child's cuts as the parent's (``ResourceAdapter.compose``).

    overview:// shows ast://'s ``results`` as its ``complex_functions``, cut by its own
    ``?top=N``; the child's "results ... raise ?limit=N" names a list and a knob the
    parent's reader doesn't have.
    """
    for entry in truncations_of(result):
        entry['field'] = field
        entry['message'] = _truncation_message(field, entry['shown'], entry['total'], hint,
                                               entry.get('exact', True))


def _truncation_message(field: str, shown: int, total: int, hint: str,
                        exact: bool = True) -> str:
    of = f'{total}' if exact else f'{total}+'
    return f'{field}: showing {shown} of {of}' + (f' — {hint}' if hint else '')


def slice_items(items: list, head: Optional[int] = None, tail: Optional[int] = None,
                range_: Optional[tuple] = None) -> list:
    """``--head``/``--tail``/``--range`` on one list; ``range_`` is 1-indexed and inclusive."""
    if head:
        return items[:head]
    if tail:
        return items[-tail:]
    if range_:
        start, end = range_
        return items[max(start - 1, 0):end]
    return items


def slice_structure(structure: Any, head: Optional[int] = None, tail: Optional[int] = None,
                    range_: Optional[tuple] = None, fields: Optional[tuple] = None,
                    default_head: Optional[int] = None) -> List[str]:
    """Cut a file's structure for ``--head``/``--tail``/``--range``, once, and disclose it.

    File mode's one slicer (BACK-1548). Each analyzer used to slice its own lists, eleven
    through ``_apply_semantic_slice`` and five by hand, and none could record the cut:
    ``reveal f.py --head 2`` returned 2 of 12 functions as the whole list, and seven
    analyzers accepted the flag and dropped it. Every list in ``fields`` is cut
    independently (``--head 5`` is the first 5 functions and the first 5 classes). With
    ``fields=None`` that is every top-level list, except ``meta`` and ``_``-prefixed keys.

    ``default_head`` is an analyzer's sample size when no flag is given (csv's 5 rows,
    jsonl's 10 records), disclosed the same way. Returns the fields present, cut or not;
    none means the flag had nothing to apply to.
    """
    if not isinstance(structure, dict):
        return []
    cause = 'head' if head else 'tail' if tail else 'range' if range_ else None
    if cause is None:
        if not default_head:
            return []
        head, cause = default_head, 'sample'
    names = fields if fields is not None else [
        k for k in structure if not k.startswith('_') and k != 'meta']
    present = [k for k in names if isinstance(structure.get(k), list)]
    for field in present:
        total = len(structure[field])
        structure[field] = slice_items(structure[field], head, tail, range_)
        note_truncation(structure, field, len(structure[field]), total, cause)
    return present


def truncations_of(result: Any) -> List[Dict[str, Any]]:
    """The lists a result says were cut: its ``truncated`` meta warnings (``note_truncation``)."""
    meta = result.get('meta') if isinstance(result, dict) else None
    warnings = meta.get('warnings') if isinstance(meta, dict) else None
    return [w for w in warnings or []
            if isinstance(w, dict) and w.get('type') == 'truncated']


class ResultBuilder:
    """Build Output Contract v1.x compliant results."""

    @staticmethod
    def create(
        result_type: str,
        source: Union[str, Path],
        data: Optional[Dict[str, Any]] = None,
        contract_version: str = '1.0',
        source_type: Optional[str] = None,
        parse_mode: Optional[str] = None,
        confidence: Optional[float] = None,
        warnings: Optional[List[WarningEntry]] = None,
        errors: Optional[List[WarningEntry]] = None,
        **extra_fields
    ) -> RevealResult:
        """Build standard Output Contract v1.x result dictionary.

        Args:
            result_type: Type identifier (e.g., 'stats_summary', 'ast_query')
            source: Source path (file or directory)
            data: Adapter-specific data fields to include
            contract_version: Contract version ('1.0' or '1.1')
            source_type: Explicit source-type override. When ``None`` (default)
                it is auto-detected as ``'directory'`` / ``'file'`` from whether
                ``source`` is a real directory. Adapters whose ``source`` is not
                a plain filesystem path (e.g. git's ``path@ref`` sources, or a
                non-filesystem value like ``'repository'`` / ``'network'``) must
                pass this explicitly — auto-detection would mislabel them.
            parse_mode: Parse mode for v1.1 meta (tree_sitter_full, regex, etc.)
            confidence: Confidence score 0.0-1.0 for v1.1 meta
            warnings: Warning list for v1.1 meta
            errors: Error list for v1.1 meta
            **extra_fields: Additional fields to include in result

        Returns:
            Dict with contract_version, type, source, source_type, and data

        Example:
            >>> result = ResultBuilder.create(
            ...     result_type='stats_summary',
            ...     source=Path('/src'),
            ...     data={'summary': {'total_files': 10}, 'files': []},
            ...     contract_version='1.0'
            ... )
            >>> result['contract_version']
            '1.0'
            >>> result['type']
            'stats_summary'
        """
        source_path = Path(source) if isinstance(source, str) else source

        # Explicit override wins; otherwise auto-detect directory vs file.
        # Auto-detection only sees real filesystem paths — adapters with
        # synthetic sources (git's `path@ref`, 'repository', 'network', ...)
        # must pass source_type explicitly or they'd be mislabeled 'file'.
        resolved_source_type = source_type if source_type is not None else (
            'directory' if source_path.is_dir() else 'file'
        )

        # Build base result
        result: Dict[str, Any] = {
            'contract_version': contract_version,
            'type': result_type,
            'source': str(source),
            'source_type': resolved_source_type,
        }

        # Add v1.1 meta if metadata provided
        if contract_version == CONTRACT_VERSION and any([parse_mode, confidence is not None, warnings, errors]):
            result['meta'] = ResultBuilder.create_meta(
                parse_mode=parse_mode,
                confidence=confidence,
                warnings=warnings,
                errors=errors
            )

        # Add adapter-specific data
        if data:
            result.update(data)

        # Add extra fields — guard against overwriting contract fields
        if extra_fields:
            collision = _CONTRACT_FIELDS & extra_fields.keys()
            if collision:
                raise ValueError(
                    f"extra_fields collides with contract fields: {sorted(collision)}"
                )
            result.update(extra_fields)

        return result

    @staticmethod
    def create_error(
        result_type: str,
        source: Union[str, Path],
        error: str,
        contract_version: str = '1.0',
        **extra_fields
    ) -> RevealResult:
        """Build error result dictionary.

        Args:
            result_type: Type identifier
            source: Source path
            error: Error message
            contract_version: Contract version
            **extra_fields: Additional fields

        Returns:
            Dict with error field

        Example:
            >>> result = ResultBuilder.create_error(
            ...     result_type='stats_summary',
            ...     source='/missing',
            ...     error='Directory not found'
            ... )
            >>> result['error']
            'Directory not found'
        """
        source_path = Path(source) if isinstance(source, str) else source

        result: Dict[str, Any] = {
            'contract_version': contract_version,
            'type': result_type,
            'source': str(source),
            'source_type': 'directory' if source_path.is_dir() else 'file',
            'error': error,
        }

        if extra_fields:
            collision = _CONTRACT_FIELDS & extra_fields.keys()
            if collision:
                raise ValueError(
                    f"extra_fields collides with contract fields: {sorted(collision)}"
                )
            result.update(extra_fields)

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
        """
        meta: Dict[str, Any] = {}

        if parse_mode is not None:
            meta['parse_mode'] = parse_mode

        if confidence is not None:
            # Clamp to [0.0, 1.0]
            meta['confidence'] = max(0.0, min(1.0, confidence))

        if warnings is not None:
            meta['warnings'] = warnings
        else:
            meta['warnings'] = []

        if errors is not None:
            meta['errors'] = errors
        else:
            meta['errors'] = []

        return meta

    # BACK-447: back-compat alias — `create_meta` is the public name now;
    # older internal call sites and tests may still reference `_create_meta`.
    _create_meta = create_meta


# Convenience functions for backward compatibility
def create_result(
    result_type: str,
    source: Union[str, Path],
    data: Optional[Dict[str, Any]] = None,
    **kwargs
) -> RevealResult:
    """Convenience function for ResultBuilder.create().

    See ResultBuilder.create() for full documentation.
    """
    return ResultBuilder.create(result_type, source, data, **kwargs)


def create_error_result(
    result_type: str,
    source: Union[str, Path],
    error: str,
    **kwargs
) -> RevealResult:
    """Convenience function for ResultBuilder.create_error().

    See ResultBuilder.create_error() for full documentation.
    """
    return ResultBuilder.create_error(result_type, source, error, **kwargs)


def create_meta(
    parse_mode: Optional[str] = None,
    confidence: Optional[float] = None,
    warnings: Optional[List[WarningEntry]] = None,
    errors: Optional[List[WarningEntry]] = None
) -> RevealMeta:
    """Convenience function for ResultBuilder.create_meta().

    See ResultBuilder.create_meta() for full documentation.
    """
    return ResultBuilder.create_meta(parse_mode, confidence, warnings, errors)


def add_cli_contract_fields(
    report: Dict[str, Any],
    *,
    result_type: str,
    source: Union[str, Path],
    source_type: str = 'directory',
    contract_version: str = '1.0',
) -> Dict[str, Any]:
    """Prepend Output Contract envelope fields to a `cli/commands/` JSON report.

    Additive only: inserts contract_version/type/source/source_type ahead of
    the command's existing keys without renaming or nesting anything, so
    existing consumers of a command's --format json output see new keys but
    no moved/removed ones (BACK-906).

    BACK-1178: when *report* already carries a `contract_version` (it came
    straight off an adapter result), that value wins over the `contract_version`
    argument. A subcommand and its `uri://` form render the same adapter
    payload, so they must not disagree about which contract that payload
    conforms to — the argument is only the fallback for reports built by the
    command itself (check/health/review), which have no adapter version.
    """
    return {
        'contract_version': report.get('contract_version', contract_version),
        'type': result_type,
        'source': str(source),
        'source_type': source_type,
        **report,
    }
