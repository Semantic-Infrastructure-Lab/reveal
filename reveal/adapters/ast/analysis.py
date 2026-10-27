"""File analysis and structure extraction for AST adapter."""


import builtins
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Sequence, Tuple, cast

from ...complexity import fallback_complexity
from ...reveal_types import StructureItem, WarningEntry, PathFailure
from ...utils.path_utils import (
    _walk_code_files,
    to_posix,
    to_relative_display,
    traversal_failed_warning as traversal_failed_warning,
    failure_of,
)
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
        self.traversal_failures: List[PathFailure] = []


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


def dropped_values_summary(structures: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The declarations bound to a call that no file's rule listed as a function (BACK-2229), counted over
    *structures*: ``count``, up to five ``files``, and the callees, an import of the file apart from the rest.
    ``names`` (every declared name, for the absence check; not in the warning) is private. None when nothing was
    left out."""
    files: List[str] = []
    imported: Dict[str, int] = {}
    other: Dict[str, int] = {}
    names: List[str] = []
    count = 0
    for file_struct in structures:
        records = file_struct.get('function_values_dropped')
        if not records:
            continue
        files.append(to_posix(file_struct['file']))
        for record in records:
            count += 1
            names.append(record['name'])
            tally = imported if record['imported'] else other
            tally[record['callee']] = tally.get(record['callee'], 0) + 1
    if not count:
        return None
    def top(tally: Dict[str, int]) -> Dict[str, int]:
        return dict(sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:10])
    return {'count': count, 'file_count': len(files), 'files': sorted(files)[:5],
            'imported_callees': top(imported), 'other_callees': top(other), 'names': sorted(set(names))}


def function_values_dropped_warning(summary: Optional[Dict[str, Any]]) -> Optional[WarningEntry]:
    """One ``function_values_dropped`` meta warning from a ``dropped_values_summary``: not a loss of evidence,
    a statement of what the function-value rule left out, so a name that is missing may be one of them."""
    if not summary:
        return None
    named = ', '.join(f"{name} x{n}" for name, n in summary['imported_callees'].items())
    detail = f"; imported callees: {named}" if named else ''
    shown = ', '.join(summary['files'])
    more = f" and {summary['file_count'] - len(summary['files'])} more" if summary['file_count'] > len(summary['files']) else ''
    return cast(WarningEntry, {
        'type': 'function_values_dropped',
        'count': summary['count'],
        'files': summary['files'],
        'imported_callees': summary['imported_callees'],
        'other_callees': summary['other_callees'],
        'message': f"{summary['count']} declaration(s) bound to a call were not treated as functions in "
                   f"{summary['file_count']} file(s) ({shown}{more}){detail}; a function they define is missing "
                   f"from this answer (`const NAME = callee(fn)` is listed only when the file calls NAME)",
    })


def try_add_file_structure(file_path: str, structures: StructureList, outline: bool = False,
                           needle: Optional[str] = None) -> None:
    """Keep usable structure and attribute required loss in ``structures.skipped``.

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
                             consequence: str = "analysis is incomplete; some observations may be missing from the result"
                             ) -> Optional[WarningEntry]:
    """One ``analysis_failed`` warning for required analysis loss, partial or total."""
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
        'message': f"{len(paths)} file(s) could not be analyzed completely ({causes}) -- {consequence}: "
                   f"{', '.join(shown)}{more}",
    }


def environmental_failure(cause: str) -> bool:
    """Whether an ``"ErrorType: message"`` failure (``StructureList.skipped``) came from the
    environment, not the file's content: an ``OSError`` such as a denied permission, or a
    lost pool worker. A later run can succeed with the file's mtime and size unchanged
    (``chmod`` moves only ctime), so no stat-validated cache may keep it (BACK-2093)."""
    name = cause.split(':', 1)[0].strip()
    if name == 'BrokenProcessPool':
        return True
    error_type = getattr(builtins, name, None)
    return isinstance(error_type, type) and issubclass(error_type, OSError)


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
        def on_error(error: OSError) -> None:
            structures.traversal_failures.append(failure_of(error))

        for fp in _walk_code_files(path_obj, on_error=on_error):
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
# Families whose anonymous functions no listed scope owns count as the module's (Ruby blocks never were skipped).
_ANONYMOUS_SCOPE_FAMILIES = frozenset({'js', 'python', 'php'})


def module_call_sites(file_path: str, analyzer, elements: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    """Script/block calls through the shared call collector; definitions keep their scopes.

    JS/TS, Python, PHP: an anonymous callback no listed function, method or class contains
    (``app.get('/', (req) => ...)``, ``setTimeout(() => ...)``, ``register(lambda: ...)``) is not a scope anyone
    reports, so its calls are the module's (BACK-2191, BACK-2232)."""
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
    owned = _listed_scope_test(elements) if family_for_path(file_path) in _ANONYMOUS_SCOPE_FAMILIES else None
    return range_calls(root, 1, _zero_arg(root, 'end_position').row + 1, text,
                       implicit_nodes=implicit, skip_kinds=DEFERRED_SCOPE_KINDS, include_jsx=True, owned_scope=owned)


_CLASS_FIELD_KINDS = frozenset({'public_field_definition', 'field_definition'})
_FUNCTION_VALUE_KINDS = frozenset({'arrow_function', 'function_expression', 'function', 'generator_function'})


def class_field_call_sites(file_path: str, analyzer) -> List[Dict[str, Any]]:
    """JS/TS: one record per class field whose initializer calls something (BACK-2230).

    A field holding a function is already listed as a method; any other field (``x = helper()``,
    ``_save = debounce(async () => ...)``) is a scope no one lists, so its calls had no caller."""
    from ...conventions import family_for_path
    from ...registry import language_for_extension
    from ...core import get_tree, _zero_arg, node_children
    from ...core.nav_calls import range_calls
    if family_for_path(file_path) != 'js':
        return []
    language = language_for_extension(Path(file_path).suffix)
    if language is None:
        return []
    tree = getattr(analyzer, 'tree', None) or get_tree(language, analyzer.content, filename=file_path)
    content = analyzer.content.encode('utf-8')
    def text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8', errors='replace')
    out: List[Dict[str, Any]] = []
    stack = [_zero_arg(tree, 'root_node')]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') in _CLASS_FIELD_KINDS:
            value = node.child_by_field_name('value')
            name = node.child_by_field_name('name') or node.child_by_field_name('property')
            if value is not None and name is not None and _zero_arg(value, 'kind') not in _FUNCTION_VALUE_KINDS:
                start = _zero_arg(node, 'start_position').row + 1
                sites = range_calls(node, start, _zero_arg(node, 'end_position').row + 1, text)
                if sites:
                    out.append({'name': text(name), 'line': start, 'sites': sites})
            continue
        stack.extend(node_children(node))
    return out


def _listed_scope_test(elements: Sequence[Dict[str, Any]]):
    """Whether a deferred scope starts inside a listed function, method or class (its calls are that element's)."""
    from ...core import _zero_arg
    spans = [(e['line'], e['line'] + max(e.get('line_count', 1), 1)) for e in elements
             if e.get('category') in ('functions', 'methods', 'classes') and 'line' in e]
    def owned(node) -> bool:
        line = _zero_arg(node, 'start_position').row + 1
        return any(start <= line < end for start, end in spans)
    return owned


def _owner_call_lines(file_struct: Dict[str, Any], elem: Dict[str, Any]) -> Dict[str, List[int]]:
    """callee -> lines of its calls inside *elem*, for the names the element also renders."""
    lines: Dict[str, set] = {}
    for site in file_struct.get('jsx_call_sites', []):
        if site['owner'] == elem.get('name') and site['owner_line'] == elem.get('line'):
            lines.setdefault(site['callee'], set()).add(site['line'])
    return {callee: sorted(found) for callee, found in lines.items()}


def _class_field_sources(file_struct: Dict[str, Any]):
    """One caller per class field whose initializer calls something (BACK-2230)."""
    for field in file_struct.get('class_field_call_sites', []):
        yield {'category': 'class_fields', 'name': field['name'], 'line': field['line'], 'caller_kind': 'class_field',
               'calls': list(dict.fromkeys(s['callee'] for s in field['sites'])), 'call_sites': field['sites']}


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
    yield from _class_field_sources(file_struct)
    sites = [s for s in file_struct.get('module_call_sites', []) if s.get('relationship') != 'jsx_reference']
    references = [r for r in refs if r['owner'] == '<module>']
    if sites or references:
        # The scope line of a module is its first call or reference: what callers report per callee.
        yield {'category': 'modules', 'name': '<module>', 'line': min(s['line'] for s in [*sites, *references]),
               'caller_kind': 'module', 'calls': list(dict.fromkeys(s['callee'] for s in [*sites, *references])),
               'call_sites': [*sites, *references], 'references': references,
               'reference_only_calls': [r['callee'] for r in references if r['callee'] not in {s['callee'] for s in sites}]}


def analyze_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Analyze a single file and extract structure.

    Required loss is warned on stderr; surviving observations are retained. A
    caller that needs the failure alongside them uses ``analyze_file_outcome``.

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
    if structure.get('_dropped_function_values'):
        result['function_values_dropped'] = structure['_dropped_function_values']  # BACK-2229

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


def _call_site_layer_complete(layer: Dict[str, Any], family: Optional[str]) -> bool:
    """A stored layer is whole: JS carries its JSX extras in the same entry or the layer is a miss."""
    if not isinstance(layer.get('module_call_sites'), list):
        return False
    if family == 'js' and not isinstance(layer.get('class_field_call_sites'), list):
        return False
    return family != 'js' or all(isinstance(layer.get(k), list) for k in ('jsx_references', 'jsx_call_sites'))


def _add_call_sites(result: Dict[str, Any], file_path: str, analyzer) -> None:
    """Module-level and JSX call sites, for the adapters that read them (full scans only).

    The sites are file-local (content, language, grammar), so the structure entry that already
    persists this file's structure carries them too (BACK-1890): a hit parses nothing. Only a
    collection that finished without a recorded parse failure is stored."""
    from ...conventions import family_for_path
    family = family_for_path(file_path)
    persist = family in _MODULE_CALL_FAMILIES and hasattr(analyzer, 'load_call_site_layer')
    form = analyzer.call_site_form() if persist else ''
    if persist:
        layer = analyzer.load_call_site_layer(form)
        if layer is not None and _call_site_layer_complete(layer, family):
            result['module_call_sites'] = layer['module_call_sites']
            if family == 'js':
                result['jsx_references'] = layer['jsx_references']
                result['jsx_call_sites'] = layer['jsx_call_sites']
                result['class_field_call_sites'] = layer['class_field_call_sites']
            return
    result['module_call_sites'] = module_call_sites(file_path, analyzer, result['elements'])
    if family == 'js':
        result['class_field_call_sites'] = class_field_call_sites(file_path, analyzer)
        from ..calls.references import jsx_component_references, jsx_owner_call_sites
        result['jsx_references'] = jsx_component_references(analyzer, result['elements'])
        result['jsx_call_sites'] = jsx_owner_call_sites(analyzer, result['elements'], result['jsx_references'])
    if persist:
        stored = {'module_call_sites': result['module_call_sites']}
        if family == 'js':
            stored.update(jsx_references=result['jsx_references'], jsx_call_sites=result['jsx_call_sites'],
                          class_field_call_sites=result['class_field_call_sites'])
        analyzer.store_call_site_layer(form, stored)


def _parser_failure(analyzer) -> Optional[str]:
    error = getattr(analyzer, 'parse_error', None)
    if error is None:
        return None
    return f"ParseError: {error or 'required parser failed without a message'}"


def _required_metadata_failures(structure: Dict[str, Any]) -> List[str]:
    if 'meta' not in structure:
        return []
    meta = structure['meta']
    if not isinstance(meta, dict) or not isinstance(meta.get('errors', []), list):
        return ['AnalysisError: malformed required analyzer metadata']
    failures = []
    for entry in meta.get('errors', []):
        if not isinstance(entry, dict) or not isinstance(entry.get('message'), str) or not entry['message'].strip():
            failures.append('AnalysisError: malformed required analyzer diagnostic')
        else:
            failures.append(f"AnalysisError: {entry['message']}")
    return failures


def _required_categories(analyzer) -> set[str]:
    from ...structure import _CATEGORY_MAP
    return set(_CATEGORY_MAP) | set(getattr(analyzer, 'DECLARATION_CATEGORIES', {}))


def _prepare_required_structure(structure: Any, analyzer) -> Tuple[Dict[str, Any], List[str]]:
    """Keep valid consumed records; metadata is not another element schema."""
    if not isinstance(structure, dict):
        return {}, [f'AnalysisError: analyzer returned {type(structure).__name__}, expected a structure mapping']
    prepared = dict(structure)
    failures = _required_metadata_failures(structure)
    for category in sorted(_required_categories(analyzer).intersection(structure)):
        items = structure[category]
        if not isinstance(items, list):
            prepared[category] = []
            failures.append(f'AnalysisError: required {category} collection is malformed')
            continue
        valid = [item for item in items if isinstance(item, dict)]
        if len(valid) != len(items):
            failures.append(f'AnalysisError: required {category} collection contains malformed records')
            prepared[category] = valid
    return prepared, failures


def _has_usable_observations(result: Dict[str, Any], analyzer) -> bool:
    categories = _required_categories(analyzer)
    named = any(item['category'] in categories and isinstance(item.get('name'), str) and item['name']
                for item in result['elements'])
    calls = any(isinstance(site.get('callee'), str) and site['callee']
                for site in result.get('module_call_sites', []))
    return named or calls


def _complete_structure(result: Dict[str, Any], file_path: str, analyzer,
                        outline: bool, needle: Optional[str]) -> Optional[str]:
    """Finish required projections without losing already extracted observations."""
    from ...core.treesitter_parse import GrammarUnavailable
    if outline:
        if needle is not None:
            result['name_in_text'] = needle in getattr(analyzer, 'content', '')
        return None
    try:
        _add_call_sites(result, file_path, analyzer)
    except GrammarUnavailable as exc:
        return _parser_failure(analyzer) or f'GrammarUnavailable: {exc}'
    return None


def _script_only_structure(file_path: str, analyzer) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """A file that lists no element can still call: a script of ``app.get(...)`` / ``setTimeout(...)`` lines holds
    module calls only (BACK-2191). Its structure is the module call sites, or nothing when it has none."""
    result: Dict[str, Any] = {'file': file_path, 'elements': []}
    failure = _complete_structure(result, file_path, analyzer, False, None)
    return (result if result.get('module_call_sites') else None), failure


def _analyzer_outcome(file_path: str, analyzer, outline: bool,
                      needle: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    structure = analyzer.get_outline() if outline else analyzer.get_structure()
    if outcome_of(structure) == 'failed':
        return None, str(structure['error'])
    structure, failures = _prepare_required_structure(structure, analyzer)
    parse_failure = _parser_failure(analyzer)
    if parse_failure is not None:
        failures.append(parse_failure)
    if not structure:
        if failures:
            return None, '; '.join(failures)
        # Empty outlines may omit imports that the existing full scan counts.
        return analyze_file_outcome(file_path) if outline else _script_only_structure(file_path, analyzer)
    result = _flatten_structure(file_path, structure, analyzer, outline)
    completion_failure = _complete_structure(result, file_path, analyzer, outline, needle)
    if completion_failure is not None:
        failures.append(completion_failure)
    parse_failure = _parser_failure(analyzer)
    if parse_failure is not None and parse_failure not in failures:
        failures.append(parse_failure)
    failure = '; '.join(failures) or None
    return (result if failure is None or _has_usable_observations(result, analyzer) else None), failure


def analyze_file_outcome(file_path: str, outline: bool = False,
                         needle: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(structure, failure)`` for one file, including returned required failures.

    A failure is attributed as ``"ErrorType: message"``. Usable observations may
    coexist with it; None without a failure means unsupported or clean empty work.

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
        try:
            return _analyzer_outcome(file_path, analyzer, outline, needle)
        finally:
            _release_buffers(analyzer)

    except Exception as e:  # boundary-ok: broad-except -- any analyzer, any file: one file that cannot be analyzed must not end a directory scan; the failure is returned to the caller, which records the file (StructureList.skipped, ImportAnalysis.structure_failures) so its result can disclose the omission (BACK-1856)
        return None, f"{type(e).__name__}: {e}"
