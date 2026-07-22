"""--grep flag implementation: text search with structural context.

Groups matching lines by their enclosing structural element:
  - Markdown  → nearest preceding heading
  - Code       → enclosing function or class
  - Flat files → bare line numbers
"""

import os
import re
import sys
from pathlib import Path
from argparse import Namespace
from typing import Any, Dict, List, Optional

from .utils import safe_json_dumps
from .utils.path_utils import is_skippable_dir

_BINARY_EXTENSIONS = frozenset({
    '.pyc', '.pyo', '.pyd', '.so', '.dylib', '.dll', '.exe', '.bin', '.o', '.a',
})

_BINARY_SNIFF_SIZE = 8192


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


def handle_grep(path: str, pattern: str, args: Namespace) -> None:
    """Text search over a single file, grouped by enclosing structural element."""
    output_format = getattr(args, 'format', 'text')
    ignore_case = getattr(args, 'ignore_case', False)

    file_path = Path(path)
    try:
        content = file_path.read_text(errors='replace')
    except OSError as e:
        print(f"Error: cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)

    flags = re.IGNORECASE if ignore_case else 0
    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        print(f"Error: invalid pattern '{pattern}': {e}", file=sys.stderr)
        sys.exit(1)

    lines = content.splitlines()
    hit_lines = [i for i, line in enumerate(lines, 1) if compiled.search(line)]

    elements = _get_structural_elements(path)
    groups = _group_by_element(hit_lines, elements)

    if output_format == 'json':
        _render_json(path, pattern, hit_lines, groups)
    else:
        _render_text(path, pattern, hit_lines, groups)


# ── structural context ──────────────────────────────────────────────────────

def _get_structural_elements(path: str) -> List[Dict[str, Any]]:
    """Return named structural elements with line ranges for a file."""
    try:
        from .registry import get_analyzer  # noqa: I006  # deferred: cli.routing → grep_handler cycle
        analyzer_class = get_analyzer(path)
        if analyzer_class is None:
            return []
        structure = analyzer_class(path).get_structure()
    except Exception:
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
    hit_lines: List[int],
    elements: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Map each hit line to its nearest enclosing element; return grouped list."""
    if not hit_lines:
        return []

    # Key: (name, kind) to preserve insertion order per element
    seen: Dict[tuple, Dict[str, Any]] = {}
    ungrouped: List[int] = []

    for hit in hit_lines:
        best: Optional[Dict[str, Any]] = None

        # Prefer tightest containing range (largest start-line that still covers hit)
        for elem in elements:
            end = elem['line_end'] if elem['line_end'] is not None else elem['line']
            if elem['line'] <= hit <= end:
                if best is None or elem['line'] > best['line']:
                    best = elem

        # Markdown fallback: nearest preceding heading even if no line_end match
        if best is None:
            for elem in reversed(elements):
                if elem['line'] <= hit:
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
                    'lines': [],
                }
            seen[key]['lines'].append(hit)

    all_groups = list(seen.values())
    if ungrouped:
        all_groups.append({
            'name': None, 'kind': None, 'level': None,
            'elem_line': ungrouped[0], 'lines': ungrouped,
        })
    return sorted(all_groups, key=lambda g: g['elem_line'])


# ── renderers ───────────────────────────────────────────────────────────────

def _render_text(
    path: str,
    pattern: str,
    hit_lines: List[int],
    groups: List[Dict[str, Any]],
) -> None:
    total = len(hit_lines)
    named_groups = [g for g in groups if g['name']]

    print(f"Text search: {path}  —  pattern: {pattern}")

    if not hit_lines:
        print("No matches found.")
        if not re.search(r'[|+*?\\[\]{}()]', pattern):
            print(f"  Tip: --grep searches literal/regex text. "
                  f"For named elements use: reveal {path} --name '{pattern}'")
        return

    hit_word = "hit" if total == 1 else "hits"
    if named_groups:
        first_kind = named_groups[0].get('kind')
        unit = "section" if first_kind == 'section' else "element"
        if len(named_groups) != 1:
            unit += "s"
        print(f"{total} {hit_word} in {len(named_groups)} {unit}")
    else:
        print(f"{total} {hit_word}")
    print()

    for group in groups:
        name = group['name']
        lines = group['lines']
        line_label = _format_lines(lines)

        if name:
            kind = group.get('kind')
            if kind == 'section':
                level = group.get('level') or 1
                prefix = '#' * level + ' '
                label = f"{prefix}{name}"
            else:
                label = f"{name}()"
            col_width = max(52, len(label) + 2)
            print(f"  {label:<{col_width}}  {line_label}")
        else:
            for ln in lines:
                print(f"  line {ln}")
    print()


def _render_json(
    path: str,
    pattern: str,
    hit_lines: List[int],
    groups: List[Dict[str, Any]],
) -> None:
    print(safe_json_dumps({
        'type': 'grep_results',
        'path': path,
        'pattern': pattern,
        'total_hits': len(hit_lines),
        'groups': [
            {'name': g['name'], 'kind': g['kind'], 'lines': g['lines']}
            for g in groups
        ],
    }))


def handle_grep_directory(path: str, pattern: str, args: Namespace) -> None:
    """Text search across all files in a directory, grouped by file then element."""
    output_format = getattr(args, 'format', 'text')
    ignore_case = getattr(args, 'ignore_case', False)
    respect_gitignore = getattr(args, 'respect_gitignore', True)
    exclude_patterns = getattr(args, 'exclude', [])

    flags = re.IGNORECASE if ignore_case else 0
    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        print(f"Error: invalid pattern '{pattern}': {e}", file=sys.stderr)
        sys.exit(1)

    dir_path = Path(path)
    file_results, total_hits = _collect_dir_results(dir_path, compiled, respect_gitignore)

    if output_format == 'json':
        _render_dir_json(file_results, path, pattern, total_hits)
    else:
        _render_dir_text(file_results, dir_path, total_hits, path, pattern)


def _collect_dir_results(
    dir_path: Path,
    compiled: 're.Pattern[str]',
    respect_gitignore: bool = True,
) -> 'tuple[List[Dict[str, Any]], int]':
    """Walk dir_path and return (file_results, total_hits)."""
    from .cli.file_checker import load_gitignore_patterns, should_skip_file  # noqa: I006  # deferred: cli cycle
    gitignore_patterns = load_gitignore_patterns(dir_path) if respect_gitignore else []

    file_results: List[Dict[str, Any]] = []
    total_hits = 0
    for root, dirs, files in os.walk(str(dir_path)):
        dirs[:] = sorted(
            d for d in dirs
            if not is_skippable_dir(Path(root), d) and not d.startswith('.')
        )
        for fname in sorted(files):
            fpath = Path(root) / fname
            if fpath.suffix in _BINARY_EXTENSIONS:
                continue
            if fpath.suffix == '' and _looks_binary(fpath):
                continue
            if gitignore_patterns:
                try:
                    if should_skip_file(fpath.relative_to(dir_path), gitignore_patterns):
                        continue
                except ValueError:
                    pass
            try:
                content = fpath.read_text(errors='replace')
            except (OSError, UnicodeDecodeError):
                continue
            lines = content.splitlines()
            hit_lines = [i for i, line in enumerate(lines, 1) if compiled.search(line)]
            if not hit_lines:
                continue
            total_hits += len(hit_lines)
            elements = _get_structural_elements(str(fpath))
            groups = _group_by_element(hit_lines, elements)
            file_results.append({'path': str(fpath), 'hits': hit_lines, 'groups': groups})
    return file_results, total_hits


def _render_dir_text(
    file_results: List[Dict[str, Any]],
    dir_path: Path,
    total_hits: int,
    path: str,
    pattern: str,
) -> None:
    file_word = "file" if len(file_results) == 1 else "files"
    hit_word = "hit" if total_hits == 1 else "hits"
    print(f"Text search: {path}  —  pattern: {pattern}")
    if not file_results:
        print("No matches found.")
        return
    print(f"{total_hits} {hit_word} across {len(file_results)} {file_word}")
    print()
    for result in file_results:
        rel = Path(result['path']).relative_to(dir_path)
        print(f"File: {rel}")
        for group in result['groups']:
            name = group['name']
            line_label = _format_lines(group['lines'])
            if name:
                kind = group.get('kind')
                if kind == 'section':
                    level = group.get('level') or 1
                    label = '#' * level + ' ' + name
                else:
                    label = f"{name}()"
                col_width = max(52, len(label) + 2)
                print(f"  {label:<{col_width}}  {line_label}")
            else:
                for ln in group['lines']:
                    print(f"  line {ln}")
        print()


def _render_dir_json(
    file_results: List[Dict[str, Any]],
    path: str,
    pattern: str,
    total_hits: int,
) -> None:
    print(safe_json_dumps({
        'type': 'grep_results',
        'path': path,
        'pattern': pattern,
        'total_hits': total_hits,
        'files': [
            {
                'path': r['path'],
                'hits': len(r['hits']),
                'groups': [
                    {'name': g['name'], 'kind': g['kind'], 'lines': g['lines']}
                    for g in r['groups']
                ],
            }
            for r in file_results
        ],
    }))


def _format_lines(lines: List[int]) -> str:
    if len(lines) == 1:
        return f"line {lines[0]}"
    if len(lines) <= 4:
        return "lines " + ", ".join(str(l) for l in lines)
    return f"lines {lines[0]}, {lines[1]} … {lines[-1]} ({len(lines)} hits)"
