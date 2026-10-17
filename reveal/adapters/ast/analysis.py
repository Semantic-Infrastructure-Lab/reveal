"""File analysis and structure extraction for AST adapter."""


import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Sequence, Tuple, cast

from ...complexity import fallback_complexity
from ...reveal_types import StructureItem, WarningEntry
from ...utils.path_utils import _walk_code_files, to_posix, to_relative_display
from ...utils.results import outcome_of
from .call_graph import build_symbol_map, resolve_callees

logger = logging.getLogger(__name__)



def _warn_failed(file_path: str, failure: str) -> None:
    """The per-file stderr line; the disclosure that reaches a result is the caller's
    (StructureList.skipped, ImportAnalysis.structure_failures)."""
    print(f"Warning: Failed to analyze {file_path}: {failure}", file=sys.stderr)


class StructureList(List[Dict[str, Any]]):
    """The structures ``collect_structures`` found, plus ``skipped``: ``(file, cause)``
    for every file whose analysis failed. A plain list read as "these are all the
    files", which a file missing for a failure also satisfies (BACK-1856)."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.skipped: List[Tuple[str, str]] = []


def parse_recovered_warning(structures: Sequence[Dict[str, Any]]) -> Optional[WarningEntry]:
    """One ``parse_recovered`` meta warning for files whose syntax tree-sitter recovered
    from (BACK-1847): their elements are what survived, so the list may be incomplete.
    None when every file parsed cleanly."""
    paths = sorted(s['file'] for s in structures if s.get('parse_recovered'))
    if not paths:
        return None
    shown = [to_posix(f) for f in paths[:5]]
    more = f" and {len(paths) - len(shown)} more" if len(paths) > len(shown) else ''
    return {
        'type': 'parse_recovered',
        'count': len(paths),
        'files': shown,
        'message': f"{len(paths)} file(s) contain syntax tree-sitter could not read; their "
                   f"elements may be incomplete or wrong: {', '.join(shown)}{more}",
    }


def try_add_file_structure(file_path: str, structures: StructureList, outline: bool = False,
                           needle: Optional[str] = None) -> None:
    """Analyze file and add its structure to list if successful; a failure is recorded
    in ``structures.skipped`` (and warned on stderr, as before).

    Args:
        file_path: Path to file to analyze
        structures: List to append structure to
    """
    structure, failure = analyze_file_outcome(file_path, outline, needle)
    if failure:
        _warn_failed(file_path, failure)
        structures.skipped.append((file_path, failure))
    if structure:
        structures.append(structure)


def analysis_skipped_warning(skipped: List[Tuple[str, str]], base: Optional[Path] = None,
                             consequence: str = "they are missing from the result"
                             ) -> Optional[WarningEntry]:
    """One ``analysis_failed`` meta warning for files whose structure analysis raised
    (BACK-1856); None when nothing failed. *consequence* says what is missing."""
    if not skipped:
        return None
    paths = sorted(skipped)
    shown = [to_relative_display(f, base) if base else to_posix(f) for f, _ in paths[:5]]
    more = f" and {len(paths) - len(shown)} more" if len(paths) > len(shown) else ''
    causes = ', '.join(sorted({cause.split(':', 1)[0] for _, cause in paths}))
    return {
        'type': 'analysis_failed',
        'count': len(paths),
        'files': shown,
        'message': f"{len(paths)} file(s) could not be analyzed ({causes}) -- {consequence}: "
                   f"{', '.join(shown)}{more}",
    }


def collect_structures(path: str, outline: bool = False, needle: Optional[str] = None) -> StructureList:
    """Collect structure data from file(s).

    Args:
        path: File or directory path

    Returns:
        StructureList of structure dicts with file metadata; ``.skipped`` names the
        files whose analysis failed
    """
    structures = StructureList()
    path_obj = Path(path)

    if path_obj.is_file():
        try_add_file_structure(str(path_obj), structures, outline, needle)
    elif path_obj.is_dir():
        # The shared walk (BACK-1223): well-known non-project dirs, what git ignores
        # (BACK-1386; --no-gitignore turns that off), REVEAL_IGNORE and --exclude. Its own
        # os.walk also skipped *.egg-info, which holds packaging metadata, no code files.
        for fp in _walk_code_files(path_obj):
            if is_code_file(fp):
                try_add_file_structure(str(fp), structures, outline, needle)

    return structures


def is_code_file(path: Path) -> bool:
    """Check if file is a code file we can analyze.

    Args:
        path: File path to check

    Returns:
        True if file has a code extension
    """
    # Derived from the analyzer registry — extensions whose CATEGORY == 'code'
    # plus all TREESITTER_EXTENSION_MAP keys (always programming languages).
    # Data/doc/config formats (.md, .json, .yaml, .toml, .csv, etc.) are
    # intentionally excluded — ast:// is for code structure, not data.
    from ...registry import get_code_extensions
    # BACK-1257: the shared walker applies --exclude to every walk; a single file
    # handed in directly (not walked) still needs the check at the yield site. This is the one for ast://, and via collect_structures for
    # calls:// and hotspots://'s function list.
    from ...utils.exclusions import path_is_excluded
    if path_is_excluded(path):
        return False
    return path.suffix.lower() in get_code_extensions()


def _add_function_metrics(element: Dict[str, Any], category: str, item: StructureItem, line: int,
                          line_count: int, analyzer, symbol_map: Optional[Dict[str, Any]]) -> None:
    """Complexity, depth and call-graph fields of a function-like element, in place."""
    # Add complexity for functions/methods (and 'tests' — currently only Zig's
    # TestDecl blocks, which now carry 'calls' too; see zig.py/BACK-660 follow-on).
    if category not in ('functions', 'methods', 'tests'):
        return
    # Use complexity from item if available (tree-sitter calculated)
    # Otherwise calculate with heuristic
    element['complexity'] = item.get('complexity') or fallback_complexity(
        {'line': line, 'line_end': line + line_count - 1 if line_count else line,
         'line_count': line_count},
        getattr(analyzer, 'content', ''))
    element['depth'] = item.get('depth', 0)
    # Propagate call graph fields (Phase 1 data from tree-sitter)
    calls = item.get('calls', [])
    element['calls'] = calls
    element['called_by'] = item.get('called_by', [])
    # Phase 3: resolve calls against import symbol map
    if symbol_map is not None and calls:
        resolved = resolve_callees(calls, symbol_map)
        if any('resolved_file' in entry for entry in resolved):
            element['resolved_calls'] = resolved


def create_element_dict(
    file_path: str,
    category: str,
    item: StructureItem,
    analyzer,
    symbol_map: Optional[Dict[str, Any]] = None,
    metrics: bool = True,
) -> Dict[str, Any]:
    """Create element dict from analyzer item.

    Args:
        file_path: Source file path
        category: Element category (functions, classes, etc.)
        item: Item dict from analyzer
        analyzer: Analyzer instance for complexity calculation
        symbol_map: Optional import-symbol map from build_symbol_map() for
            cross-file call resolution.  When provided, functions/methods gain
            a ``resolved_calls`` field alongside the plain ``calls`` list.
        metrics: False for an outline item (BACK-1867), which carries no complexity, depth
            or calls: leave those fields out rather than computing a fallback.

    Returns:
        Element dict with standardized fields
    """
    # Format analyzers (TOML, ...) key their first line 'line_start'; reading only
    # 'line' put every TOML section at line 0 (BACK-1416).
    line = item.get('line') or item.get('line_start') or 0
    # Calculate line_count - functions have it, classes need computation
    line_count = item.get('line_count')
    if not line_count and item.get('line_end'):
        line_count = item.get('line_end', 0) - line + 1
    else:
        line_count = line_count or 0

    # For imports, use 'content' as the name since they don't have a 'name' field
    name = item.get('name', '')
    if category == 'imports' and not name and 'content' in item:
        name = item['content']

    element = {
        'file': file_path,
        'category': category,
        'name': name,
        'line': line,
        'line_count': line_count,
        'signature': item.get('signature', ''),
        'decorators': item.get('decorators', []),
        'bases': item.get('bases', []),
    }
    # Propagate optional flags from the analyzer (e.g. TypeScript abstract classes).
    if item.get('is_abstract'):
        element['is_abstract'] = True
    # BACK-1286: implicit-invocation markers read by calls://?uncalled.
    for flag in ('is_test_callback', 'accessor', 'trait_impl'):
        if item.get(flag):
            element[flag] = cast(Dict[str, Any], item)[flag]

    if metrics:
        _add_function_metrics(element, category, item, line, line_count, analyzer, symbol_map)

    return element



_MODULE_CALL_FAMILIES = frozenset({'python', 'js', 'php', 'ruby'})


def module_call_sites(file_path: str, analyzer) -> List[Dict[str, Any]]:
    """Script/block calls through the shared call collector; definitions keep their scopes."""
    from ...conventions import family_for_path
    from ...registry import language_for_extension
    from ...core import get_tree, _zero_arg
    from ...core.nav_calls import range_calls, DEFERRED_SCOPE_KINDS
    if family_for_path(file_path) not in _MODULE_CALL_FAMILIES:
        return []
    language = language_for_extension(Path(file_path).suffix)
    if language is None:
        return []
    tree = getattr(analyzer, 'tree', None) or get_tree(language, analyzer.content, filename=file_path)
    root = _zero_arg(tree, 'root_node')
    content = analyzer.content.encode('utf-8')
    def text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8', errors='replace')
    implicit = analyzer._implicit_call_nodes(root) if hasattr(analyzer, '_implicit_call_nodes') else ()
    # Python's root node is 'module'; only children are excluded by range_calls.
    return range_calls(root, 1, _zero_arg(root, 'end_position').row + 1, text,
                       implicit_nodes=implicit, skip_kinds=DEFERRED_SCOPE_KINDS, include_jsx=True)


def _owner_call_lines(file_struct: Dict[str, Any], elem: Dict[str, Any]) -> Dict[str, List[int]]:
    """callee -> lines of its calls inside *elem*, for the names the element also renders."""
    lines: Dict[str, set] = {}
    for site in file_struct.get('jsx_call_sites', []):
        if site['owner'] == elem.get('name') and site['owner_line'] == elem.get('line'):
            lines.setdefault(site['callee'], set()).add(site['line'])
    return {callee: sorted(found) for callee, found in lines.items()}


def call_sources(file_struct: Dict[str, Any]):
    """Call/reference projection shared by callers, callees and trace."""
    refs = file_struct.get('jsx_references', [])
    for elem in file_struct.get('elements', []):
        references = [r for r in refs if r['owner'] == elem.get('name') and r['owner_line'] == elem.get('line')]
        if references:
            yield {**elem, 'calls': list(dict.fromkeys([*elem.get('calls', []), *(r['callee'] for r in references)])),
                   'references': references, 'reference_only_calls': [r['callee'] for r in references if r['callee'] not in elem.get('calls', [])],
                   'call_lines': _owner_call_lines(file_struct, elem)}
        else:
            yield elem
    sites = [s for s in file_struct.get('module_call_sites', []) if s.get('relationship') != 'jsx_reference']
    references = [r for r in refs if r['owner'] == '<module>']
    if sites or references:
        # The scope line of a module is its first call or reference: what callers report per callee.
        yield {'category': 'modules', 'name': '<module>', 'line': min(s['line'] for s in [*sites, *references]),
               'caller_kind': 'module', 'calls': list(dict.fromkeys(s['callee'] for s in [*sites, *references])),
               'call_sites': [*sites, *references], 'references': references,
               'reference_only_calls': [r['callee'] for r in references if r['callee'] not in {s['callee'] for s in sites}]}


def unattributed_references(file_struct: Dict[str, Any]) -> List[Dict[str, Any]]:
    """JSX uses that call_sources attributes to no caller (``<anonymous>``: deferred body with no
    tracked element). A caller graph cannot name them, but a file-level dependency does not
    depend on which scope owns the use (BACK-1831)."""
    owners = {(e.get('name'), e.get('line')) for e in file_struct.get('elements', [])}
    return [r for r in file_struct.get('jsx_references', [])
            if r['owner'] != '<module>' and (r['owner'], r['owner_line']) not in owners]


def analyze_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Analyze a single file and extract structure.

    A failure is warned on stderr and returns None, like a file with no analyzer; a
    caller that must tell the two apart uses ``analyze_file_outcome``.

    Args:
        file_path: Path to file

    Returns:
        Dict with file structure, or None if analysis fails
    """
    structure, failure = analyze_file_outcome(file_path)
    if failure:
        _warn_failed(file_path, failure)
    return structure


def _release_buffers(analyzer) -> None:
    """Free large per-file buffers held by the analyzer so directory scans (ast://, overview)
    don't accumulate memory proportional to all files."""
    analyzer.lines = []
    analyzer.content = ''
    if hasattr(analyzer, '_content_bytes'):
        analyzer._content_bytes = None


def _flatten_structure(file_path: str, structure: Dict[str, Any], analyzer, outline: bool) -> Dict[str, Any]:
    """A file's structure as the ``{'file', 'elements', ...}`` dict the ast:// and calls://
    adapters share. An outline carries no metrics, so it skips the symbol map too."""
    result: Dict[str, Any] = {'file': file_path, 'elements': []}
    if structure.get('_has_errors'):
        result['parse_recovered'] = True  # BACK-1847: the tree has syntax it could not read

    # Build import symbol map for cross-file call resolution (Phase 3).
    # build_symbol_map is cheap for already-parsed files (import extractor caches).
    try:
        symbol_map: Optional[Dict[str, Any]] = None if outline else build_symbol_map(file_path)
    except Exception as e:  # boundary-ok: broad-except -- cross-file call resolution is an optional enrichment run through per-language import extractors (arbitrary parser code); without it calls stay unresolved but the file's own structure is still right, and the failure is logged at warning
        logger.warning("cross-file call resolution failed for %s: %s", file_path, e)
        symbol_map = None

    for category, items in structure.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            result['elements'].append(create_element_dict(
                file_path, category, cast(StructureItem, item), analyzer, symbol_map,
                metrics=not outline))
    return result


def _add_call_sites(result: Dict[str, Any], file_path: str, analyzer) -> None:
    """Module-level and JSX call sites, for the adapters that read them (full scans only)."""
    result['module_call_sites'] = module_call_sites(file_path, analyzer)
    from ...conventions import family_for_path
    if family_for_path(file_path) == 'js':
        from ..calls.references import jsx_component_references, jsx_owner_call_sites
        result['jsx_references'] = jsx_component_references(analyzer, result['elements'])
        result['jsx_call_sites'] = jsx_owner_call_sites(analyzer, result['elements'], result['jsx_references'])


def analyze_file_outcome(file_path: str, outline: bool = False,
                         needle: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(structure, failure)`` for one file: *failure* is ``"ErrorType: message"`` when
    the analysis raised, None when it ran (structure None then means no analyzer or an
    empty structure, not a failure).

    ``outline=True`` (BACK-1867) builds the cheap form: elements located by name, line and
    decorators, with no metrics, calls, imports, call sites or symbol map. It is only for
    deciding which files a query touches; ``needle`` records whether that text occurs in the
    file (``name_in_text``), for the imports an outline leaves out."""
    from ...registry import get_analyzer

    try:
        analyzer_class = get_analyzer(file_path)
        if not analyzer_class:
            return None, None

        analyzer = analyzer_class(file_path)
        structure = analyzer.get_outline() if outline else analyzer.get_structure()
        if outcome_of(structure) == 'failed':
            failure = str(structure['error'])
            _release_buffers(analyzer)
            return None, failure
        if not structure:
            # An outline leaves out imports, so an empty one may be an import-only file that a
            # full scan counts. Such a file has no functions to measure: take it whole.
            return analyze_file_outcome(file_path) if outline else (None, None)

        result = _flatten_structure(file_path, structure, analyzer, outline)
        if outline:
            if needle is not None:
                result['name_in_text'] = needle in getattr(analyzer, 'content', '')
        else:
            _add_call_sites(result, file_path, analyzer)
        _release_buffers(analyzer)
        return result, None

    except Exception as e:  # boundary-ok: broad-except -- any analyzer, any file: one file that cannot be analyzed must not end a directory scan; the failure is returned to the caller, which records the file (StructureList.skipped, ImportAnalysis.structure_failures) so its result can disclose the omission (BACK-1856)
        return None, f"{type(e).__name__}: {e}"
