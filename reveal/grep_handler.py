"""--grep flag implementation: text search with structural context.

Groups matching lines by their enclosing structural element:
  - Markdown  → nearest preceding heading
  - Code       → enclosing function or class
  - Flat files → bare line numbers

This module builds the result; ``reveal.display.grep`` renders it and
``reveal.cli.routing.grep`` prints it and acts on its outcome (BACK-1602). Each hit carries
its line's text. The hits shown are cut once, here: ``--head``/``--tail``/``--range``, then
``--max-items`` or the text view's default cap (``DisplayDefaults.GREP_MAX_HITS``), each
recorded with ``note_truncation``. Text and structure are read only for the hits shown, so
a capped search of a large tree parses only the files it shows.
"""

import logging
import re
from collections import Counter
from pathlib import Path
from argparse import Namespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .defaults import DisplayDefaults
from .utils.lines import split_lines
from .utils.results import note_truncation, slice_items

logger = logging.getLogger(__name__)

_BINARY_EXTENSIONS = frozenset({
    '.pyc', '.pyo', '.pyd', '.so', '.dylib', '.dll', '.exe', '.bin', '.o', '.a',
})

_BINARY_SNIFF_SIZE = 8192


_BRE_ALTERNATION_RE = re.compile(r'\\\|')


def _looks_like_bre_alternation_mistake(pattern: str) -> bool:
    """Detect the common '\\|' (BRE-style alternation) mistake.

    Python re treats '\\|' as a literal escaped pipe, not alternation —
    unlike POSIX BRE grep, where '\\|' means "or". A pattern containing
    '\\|' almost always means the author wanted alternation and got a
    silently-never-matching literal instead.
    """
    return bool(_BRE_ALTERNATION_RE.search(pattern))


def _bre_alternation_hint(pattern: str) -> Optional[str]:
    """Tip text for a '\\|' pattern that found nothing, else None."""
    if not _looks_like_bre_alternation_mistake(pattern):
        return None
    fixed = pattern.replace('\\|', '|')
    return (f"--grep uses Python regex, where '\\|' is a literal pipe, not "
            f"alternation. Did you mean: '{fixed}' (no backslash)?")


def _looks_binary(fpath: Path) -> bool:
    """Heuristic binary detection: a NUL byte in the leading chunk (the same
    signal git/grep use). Catches compiled binaries with no distinguishing
    extension, e.g. extensionless ELF executables, that _BINARY_EXTENSIONS misses.
    """
    try:
        with open(fpath, 'rb') as f:
            chunk = f.read(_BINARY_SNIFF_SIZE)
    except OSError:
        return False
    return b'\x00' in chunk


def _compile(pattern: str, args: Namespace) -> 're.Pattern[str] | str':
    """The compiled pattern, or the error message for an invalid one."""
    flags = re.IGNORECASE if getattr(args, 'ignore_case', False) else 0
    try:
        return re.compile(pattern, flags)
    except re.error as e:
        return f"invalid pattern '{pattern}': {e}"


def _read_lines(fpath: Path) -> List[str]:
    return split_lines(fpath.read_text(encoding='utf-8', errors='replace'))


def _hit_lines(lines: Sequence[str], compiled: 're.Pattern[str]') -> List[int]:
    return [i for i, line in enumerate(lines, 1) if compiled.search(line)]


def _hit_text(line: str, compiled: 're.Pattern[str]', width: int = DisplayDefaults.GREP_LINE_CHARS) -> str:
    """The matched line, stripped; a longer one is cut to *width* around the first match."""
    text = line.strip()
    if len(text) <= width:
        return text
    m = compiled.search(text)
    lo = max(0, min((m.start() if m else 0) - width // 4, len(text) - width))
    cut = text[lo:lo + width]
    if lo > 0:
        cut = '…' + cut[1:]
    if lo + width < len(text):
        cut = cut[:-1] + '…'
    return cut


def _hit_cap(args: Namespace, output_format: str) -> Tuple[Optional[int], str]:
    """``--max-items``, else the text view's default cap unless ``--all``; JSON is never
    capped implicitly (the file view's rule, ``_default_file_item_cap``)."""
    max_items = getattr(args, 'max_items', None)
    if max_items is not None:
        return max_items, 'max_items'
    if output_format == 'text' and not getattr(args, 'all', False):
        return DisplayDefaults.GREP_MAX_HITS, 'display_cap'
    return None, ''


def _cut_hits(result: Dict[str, Any], hits: list, args: Namespace, output_format: str) -> list:
    """The hits to show: ``--head``/``--tail``/``--range``, then the cap; each cut recorded."""
    rng = getattr(args, 'range', None)
    shown = slice_items(hits, getattr(args, 'head', None), getattr(args, 'tail', None),
                        rng if isinstance(rng, tuple) else None)
    note_truncation(result, 'hits', len(shown), len(hits), 'sample')
    cap, cause = _hit_cap(args, output_format)
    if cap is not None and len(shown) > cap:
        shown = shown[:cap]
        note_truncation(result, 'hits', len(shown), len(hits), cause)
    return shown


def _get_structural_elements(path: str) -> List[Dict[str, Any]]:
    """Return named structural elements with line ranges for a file."""
    try:
        from .registry import get_analyzer  # noqa: I006  # deferred: cli.routing → grep_handler cycle
        analyzer_class = get_analyzer(path)
        if analyzer_class is None:
            return []
        structure = analyzer_class(path).get_outline()
    except Exception as e:  # one file's analyzer failure must not stop a grep; its hits stay, ungrouped
        logger.warning("--grep: %s hits shown without their enclosing element (%s: %s)",
                       path, type(e).__name__, e)
        return []

    elements: List[Dict[str, Any]] = []

    # Markdown headings
    for h in structure.get('headings', []):
        elements.append({
            'name': h['name'],
            'line': h['line'],
            'line_end': None,
            'kind': 'section',
            'level': h.get('level', 1),
        })

    # Fill heading line_end = next heading line - 1 (last heading owns rest of file)
    heading_elements = [e for e in elements if e['kind'] == 'section']
    for idx, elem in enumerate(heading_elements):
        if idx + 1 < len(heading_elements):
            elem['line_end'] = heading_elements[idx + 1]['line'] - 1
        else:
            elem['line_end'] = 10 ** 9

    # Code: functions and classes
    for func in structure.get('functions', []):
        elements.append({
            'name': func['name'],
            'line': func['line'],
            'line_end': func.get('line_end', func['line']),
            'kind': 'function',
        })
    for cls in structure.get('classes', []):
        elements.append({
            'name': cls['name'],
            'line': cls['line'],
            'line_end': cls.get('line_end', cls['line']),
            'kind': 'class',
        })

    elements.sort(key=lambda e: e['line'])
    return elements


def _group_by_element(
    hits: List[Dict[str, Any]],
    elements: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Map each hit (``{'line', 'text'}``) to its nearest enclosing element; return grouped list."""
    if not hits:
        return []

    # Key: (name, kind) to preserve insertion order per element
    seen: Dict[tuple, Dict[str, Any]] = {}
    ungrouped: List[Dict[str, Any]] = []

    for hit in hits:
        line = hit['line']
        best: Optional[Dict[str, Any]] = None

        # Prefer tightest containing range (largest start-line that still covers hit)
        for elem in elements:
            end = elem['line_end'] if elem['line_end'] is not None else elem['line']
            if elem['line'] <= line <= end:
                if best is None or elem['line'] > best['line']:
                    best = elem

        # Markdown fallback: nearest preceding heading even if no line_end match
        if best is None:
            for elem in reversed(elements):
                if elem['line'] <= line:
                    best = elem
                    break

        if best is None:
            ungrouped.append(hit)
        else:
            key = (best['name'], best['kind'])
            if key not in seen:
                seen[key] = {
                    'name': best['name'],
                    'kind': best['kind'],
                    'level': best.get('level'),
                    'elem_line': best['line'],
                    'hits': [],
                }
            seen[key]['hits'].append(hit)

    all_groups = list(seen.values())
    if ungrouped:
        all_groups.append({
            'name': None, 'kind': None, 'level': None,
            'elem_line': ungrouped[0]['line'], 'hits': ungrouped,
        })
    for g in all_groups:
        g['lines'] = [h['line'] for h in g['hits']]
    return sorted(all_groups, key=lambda g: g['elem_line'])


def _groups_for(fpath: Path, line_numbers: List[int], compiled: 're.Pattern[str]',
                lines: Optional[List[str]] = None,
                elements: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """The shown hits of one file, with their text, grouped by enclosing element."""
    if elements is None:
        elements = _get_structural_elements(str(fpath))
    if lines is None:
        try:
            lines = _read_lines(fpath)
        except OSError:
            lines = []
    hits = [{'line': n, 'text': _hit_text(lines[n - 1], compiled) if n <= len(lines) else ''}
            for n in line_numbers]
    return _group_by_element(hits, elements)


def _base_result(path: str, pattern: str) -> Dict[str, Any]:
    return {'type': 'grep_results', 'path': path, 'pattern': pattern}


def grep_file(path: str, pattern: str, args: Namespace) -> Dict[str, Any]:
    """Text search over one file, grouped by enclosing structural element."""
    output_format = getattr(args, 'format', 'text')
    result = _base_result(path, pattern)
    compiled = _compile(pattern, args)
    if isinstance(compiled, str):
        result['error'] = compiled
        return result
    file_path = Path(path)
    try:
        lines = _read_lines(file_path)
    except OSError as e:
        result['error'] = f"cannot read {path}: {e}"
        return result

    hit_lines = _hit_lines(lines, compiled)
    result['total_hits'] = len(hit_lines)
    elements = _get_structural_elements(path) if hit_lines else []
    # The header's "in N elements" counts every hit's element, not only the shown ones'.
    result['elements_matched'] = sum(1 for g in _group_by_element(
        [{'line': n, 'text': ''} for n in hit_lines], elements) if g['name'])
    shown = _cut_hits(result, hit_lines, args, output_format)
    result['groups'] = _groups_for(file_path, shown, compiled, lines, elements)
    if not hit_lines and (hint := _bre_alternation_hint(pattern)):
        result['hint'] = hint
    return result


def _collect_dir_results(
    dir_path: Path,
    compiled: 're.Pattern[str]',
    respect_gitignore: Optional[bool] = None,
    exclude_patterns: Optional[List[str]] = None,
    include_extensions: Optional[List[str]] = None,
) -> 'tuple[List[Dict[str, Any]], int, Dict[str, Any]]':
    """Walk dir_path and return (file_results, total_hits, scope).

    The display walk (BACK-1581): ``reveal DIR --grep X`` searches the files ``reveal DIR``
    lists -- gitignore, REVEAL_IGNORE and ``--exclude`` (gitignore syntax) included, dot
    entries and noise left out -- in a stable, sorted order. ``--ext`` keeps the files
    ``reveal DIR --ext`` lists (BACK-1633: it was dropped, and every file type was searched).

    Each file result is ``{'path', 'file', 'hits'}``: the POSIX path, the ``Path``, and the
    hit line numbers. Text and structure are read later, for the hits shown.

    ``scope`` is what the walk searched and what it left out: ``files_searched``, and
    ``hidden``, the entries (files and pruned directories) skipped by ``.gitignore``,
    ``--exclude`` or REVEAL_IGNORE, tallied as the directory view does. A search of a
    gitignored directory said "No matches found" as if it had looked (BACK-1546).
    """
    from .utils.path_utils import DISPLAY, to_posix, walk_tree
    hidden: Counter = Counter()
    exts = {e.lower().lstrip('.') for e in include_extensions} if include_extensions else None

    def tally(_path: Path, _is_dir: bool, cause: str) -> None:
        if cause in ('gitignore', 'exclude', 'reveal_ignore'):  # what the user can act on
            hidden[cause] += 1

    file_results: List[Dict[str, Any]] = []
    total_hits = 0
    searched = 0
    for root_path, _dirs, files in walk_tree(dir_path, DISPLAY, exclude_patterns=exclude_patterns,
                                             respect_gitignore=respect_gitignore,
                                             on_hidden=tally, sort=True):
        for fname in files:
            fpath = root_path / fname
            if exts is not None and fpath.suffix.lower().lstrip('.') not in exts:
                continue
            if fpath.suffix in _BINARY_EXTENSIONS:
                continue
            if fpath.suffix == '' and _looks_binary(fpath):
                continue
            searched += 1
            try:
                hit_lines = _hit_lines(_read_lines(fpath), compiled)
            except (OSError, UnicodeDecodeError):
                continue
            if not hit_lines:
                continue
            total_hits += len(hit_lines)
            file_results.append({'path': to_posix(fpath), 'file': fpath, 'hits': hit_lines})
    return file_results, total_hits, {'files_searched': searched, 'hidden': dict(hidden)}


def grep_directory(path: str, pattern: str, args: Namespace,
                   include_extensions: Optional[List[str]] = None) -> Dict[str, Any]:
    """Text search across all files in a directory, grouped by file then element."""
    output_format = getattr(args, 'format', 'text')
    result = _base_result(path, pattern)
    compiled = _compile(pattern, args)
    if isinstance(compiled, str):
        result['error'] = compiled
        return result

    file_results, total_hits, scope = _collect_dir_results(
        Path(path), compiled, getattr(args, 'respect_gitignore', True) is not False,
        getattr(args, 'exclude', None) or [], include_extensions)
    result['total_hits'] = total_hits
    result['files_matched'] = len(file_results)
    result.update(scope)

    # One cut over every hit in walk order, then text + structure for the shown files only.
    pairs = [(i, n) for i, r in enumerate(file_results) for n in r['hits']]
    shown: Dict[int, List[int]] = {}
    for i, n in _cut_hits(result, pairs, args, output_format):
        shown.setdefault(i, []).append(n)
    result['files'] = [
        {'path': file_results[i]['path'], 'hits': len(lines),
         'groups': _groups_for(file_results[i]['file'], lines, compiled)}
        for i, lines in shown.items()
    ]
    if not file_results and (hint := _bre_alternation_hint(pattern)):
        result['hint'] = hint
    return result
