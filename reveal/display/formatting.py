"""Formatting helpers for display output."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reveal.base import FileAnalyzer
from reveal.utils.formatting import lines_label
from reveal.utils.path_utils import to_posix
from reveal.utils.results import truncations_of


# The Output Contract envelope: kept whatever --fields names (BACK-1607).
ENVELOPE_FIELD_NAMES = ('contract_version', 'type', 'meta', 'source', 'source_type')

# BACK-387: above this many headings, the flat text outline auto-collapses
HEADING_COLLAPSE_THRESHOLD = 25


def set_nested(d: Dict[str, Any], keys: List[str], value: Any) -> None:
    """Set a value in a nested dictionary using a list of keys.

    Args:
        d: Dictionary to modify
        keys: List of keys representing path (e.g., ['certificate', 'expiry'])
        value: Value to set at the path

    Example:
        >>> d = {}
        >>> set_nested(d, ['a', 'b', 'c'], 42)
        >>> d
        {'a': {'b': {'c': 42}}}
    """
    for key in keys[:-1]:
        if key not in d:
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value


# Helper functions for field selection

def _extract_nested_value(obj: Dict[str, Any], field_path: str) -> Optional[Any]:
    """Extract nested field value using dot notation.

    Args:
        obj: Object to extract from
        field_path: Field path (e.g., 'certificate.expiry')

    Returns:
        Extracted value, or None if not found
    """
    parts = field_path.split('.')
    value: Any = obj
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
        if value is None:
            return None
    return value


def _filter_single_item_fields(
    item: Dict[str, Any], fields: List[str]
) -> Dict[str, Any]:
    """Filter a single item to only include specified fields.

    Args:
        item: Item dictionary to filter
        fields: List of field names (supports nested: "parent.child")

    Returns:
        Filtered item dictionary
    """
    filtered_item: Dict[str, Any] = {}
    for field in fields:
        if '.' in field:  # Nested field
            value = _extract_nested_value(item, field)
            if value is not None:
                set_nested(filtered_item, field.split('.'), value)
        else:  # Flat field
            if field in item:
                filtered_item[field] = item[field]
    return filtered_item


def _item_lists(structure: Dict[str, Any]) -> Dict[str, list]:
    """The result's top-level lists of objects -- the lists whose items --fields can select in."""
    return {key: value for key, value in structure.items()
            if key not in ENVELOPE_FIELD_NAMES and not key.startswith('_')
            and isinstance(value, list) and any(isinstance(item, dict) for item in value)}


def _has_path(obj: Any, field_path: str) -> bool:
    """Whether ``obj`` has the dotted key path, even one whose value is None."""
    for part in field_path.split('.'):
        if not isinstance(obj, dict) or part not in obj:
            return False
        obj = obj[part]
    return True


def _in_items(items: list, field: str) -> bool:
    return any(_has_path(item, field) for item in items)


def _trim_items(items: list, fields: List[str]) -> list:
    return [_filter_single_item_fields(item, fields) if isinstance(item, dict) else item
            for item in items]


def _locate_field(structure: Dict[str, Any], lists: Dict[str, list],
                  field: str) -> Optional[List[Tuple[str, str]]]:
    """Where one --fields name points: ``[]`` a top-level key, ``[(list, item key), ...]``
    keys of list items, None nothing."""
    head, _, rest = field.partition('.')
    if head in lists and rest and _in_items(lists[head], rest):
        return [(head, rest)]  # results.name: a key of each item of that list
    if not (head in lists and rest) and _has_path(structure, field):
        return []
    return [(name, field) for name, items in lists.items() if _in_items(items, field)] or None


def select_fields(structure: Dict[str, Any], fields: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    """Keep only the named fields of a result: the one rule ``--fields`` uses (BACK-1607).

    Each name is looked up at the top level first, then in the items of the result's
    lists of objects:

    - ``total_results``, ``summary.total_files``: that top-level key;
    - ``results``: that whole list; ``results.name``: ``name`` in each item of ``results``;
    - ``name`` (not a top-level key): ``name`` in the items of every list whose items have it.

    The Output Contract envelope (``contract_version``, ``type``, ``source``,
    ``source_type``, ``meta``) and ``_``-prefixed renderer hints are always kept. Returns
    the selection and the names that matched nothing, which the caller discloses. An
    empty list has no items to check a name against: when the result has no list with
    items, a name that is not a top-level key keeps the empty lists and is not reported
    (``?lines>1000`` matching no file is not a misspelt ``--fields``).

    Before, the level depended on the adapter: a result holding one of six hand-listed
    list names had only its items filtered (so ``--fields=type,total_results,results`` on
    ast:// gave ``results: [{}, ...]``); any other result had only its top level filtered
    (so ``--fields=hash,author`` on git:// gave ``{}``); and a name that matched nothing was
    dropped in silence.

    Examples:
        >>> select_fields({'type': 't', 'n': 1, 'x': 2}, ['n'])
        ({'type': 't', 'n': 1}, [])
        >>> select_fields({'type': 't', 'results': [{'a': 1, 'b': 2}]}, ['a', 'zz'])
        ({'type': 't', 'results': [{'a': 1}]}, ['zz'])
    """
    selected: Dict[str, Any] = {key: value for key, value in structure.items()
                                if key in ENVELOPE_FIELD_NAMES or key.startswith('_')}
    lists = _item_lists(structure)
    empty = [key for key, value in structure.items()
             if value == [] and key not in ENVELOPE_FIELD_NAMES and not key.startswith('_')]
    item_fields: Dict[str, List[str]] = {}
    unmatched: List[str] = []
    for field in fields:
        where = _locate_field(structure, lists, field)
        if where == []:
            if field.partition('.')[0] not in ENVELOPE_FIELD_NAMES:
                set_nested(selected, field.split('.'), _extract_nested_value(structure, field))
        elif where:
            for name, key in where:
                item_fields.setdefault(name, []).append(key)
        elif empty and not lists:  # nothing to check the name against
            selected.update((key, []) for key in empty)
        else:
            unmatched.append(field)
    for name, names in item_fields.items():
        selected[name] = _trim_items(lists[name], names)
    return selected, unmatched


def available_fields(structure: Dict[str, Any]) -> str:
    """The names ``--fields`` can select in this result, for a note about one that matched nothing."""
    top = [key for key in structure if key not in ENVELOPE_FIELD_NAMES and not key.startswith('_')]
    parts = [', '.join(top) or '(none)']
    for name, items in _item_lists(structure).items():
        keys = sorted({key for item in items if isinstance(item, dict) for key in item})
        parts.append(f"items of {name}: {', '.join(keys)}")
    return '; '.join(parts)


def _format_frontmatter(fm: Optional[Dict[str, Any]]) -> None:
    """Format and display YAML front matter."""
    if fm is None:
        print("  (No front matter found)")
        return

    data = fm.get('data', {})
    lines = f"{fm.get('line_start', '?')}-{fm.get('line_end', '?')}"

    # Display key fields
    if not data:
        print("  (Empty front matter)")
        return

    print(f"  Lines {lines}:")
    for key, value in data.items():
        # Format value based on type
        if isinstance(value, list):
            print(f"    {key}:")
            for item in value:
                print(f"      - {item}")
        elif isinstance(value, dict):
            print(f"    {key}:")
            for sub_key, sub_value in value.items():
                print(f"      {sub_key}: {sub_value}")
        else:
            print(f"    {key}: {value}")


def _format_single_link(
    item: Dict[str, Any],
    link_type: str,
    path: Path,
    output_format: str
) -> None:
    """Format and display a single link.

    Args:
        item: Link item dict
        link_type: Type of link (external, internal, email)
        path: File path (for grep output)
        output_format: Output format ('grep' or default)
    """
    line = item.get('line', '?')
    text = item.get('text', '')
    url = item.get('url', '')
    broken = item.get('broken', False)

    if output_format == 'grep':
        print(f"{to_posix(path)}:{line}:{url}")
        return

    if broken:
        print(f"    X Line {line:<4} [{text}]({url}) [BROKEN]")
        return

    # Normal link display
    print(f"    Line {line:<4} [{text}]({url})")

    # Show domain for external links
    if link_type == 'external':
        domain = item.get('domain', '')
        if domain:
            print(f"             -> {domain}")


def _format_links(
    items: List[Dict[str, Any]], path: Path, output_format: str
) -> None:
    """Format and display link items grouped by type."""
    # Group by type
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        link_type = item.get('type', 'unknown')
        by_type.setdefault(link_type, []).append(item)

    # Display each type
    for link_type in ['external', 'internal', 'email']:
        if link_type not in by_type:
            continue

        type_items = by_type[link_type]
        print(f"\n  {link_type.capitalize()} ({len(type_items)}):")

        for item in type_items:
            _format_single_link(item, link_type, path, output_format)


def _format_fenced_block(
    item: Dict[str, Any], path: Path, output_format: str
) -> None:
    """Format and display a single fenced code block.

    Args:
        item: Code block item dict
        path: File path (for grep output)
        output_format: Output format ('grep' or default)
    """
    line_start = item.get('line_start', '?')
    line_end = item.get('line_end', '?')
    line_count = item.get('line_count', 0)
    source = item.get('source', '')

    if output_format == 'grep':
        first_line = source.split('\n')[0] if source else ''
        print(f"{to_posix(path)}:{line_start}:{first_line}")
        return

    print(f"    Lines {line_start}-{line_end} ({lines_label(line_count)})")
    preview_lines = source.split('\n')[:3]
    for preview_line in preview_lines:
        print(f"      {preview_line}")
    if line_count > 3:
        print(f"      ... ({line_count - 3} more lines)")


def _format_inline_code_items(
    items: List[Dict[str, Any]], path: Path, output_format: str
) -> None:
    """Format and display inline code items.

    Args:
        items: List of inline code items
        path: File path (for grep output)
        output_format: Output format ('grep' or default)
    """
    print(f"\n  Inline code ({len(items)} snippets):")

    for item in items[:10]:
        line = item.get('line', '?')
        source = item.get('source', '')

        if output_format == 'grep':
            print(f"{to_posix(path)}:{line}:{source}")
        else:
            print(f"    Line {line:<4} `{source}`")

    if len(items) > 10:
        print(f"    ... and {len(items) - 10} more")


def _format_code_blocks(
    items: List[Dict[str, Any]], path: Path, output_format: str
) -> None:
    """Format and display code block items grouped by language."""
    # Group by language
    by_lang: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        lang = item.get('language', 'unknown')
        by_lang.setdefault(lang, []).append(item)

    # Show fenced blocks grouped by language
    for lang in sorted(by_lang.keys()):
        if lang == 'inline':
            continue

        lang_items = by_lang[lang]
        print(f"\n  {lang.capitalize()} ({len(lang_items)} blocks):")

        for item in lang_items:
            _format_fenced_block(item, path, output_format)

    # Show inline code if present
    if 'inline' in by_lang:
        _format_inline_code_items(by_lang['inline'], path, output_format)


def _format_related_item(
    item: Dict[str, Any],
    indent: str = "  ",
    output_format: str = "text"
) -> None:
    """Format and display a single related document.

    Args:
        item: Related document info dict
        indent: Indentation prefix
        output_format: Output format ('grep' or default)
    """
    path = item.get('path', '?')
    exists = item.get('exists', False)
    headings = item.get('headings', [])
    error = item.get('error')
    nested_related = item.get('related', [])

    # Status indicator
    if not exists:
        status = "✗ NOT FOUND"
    elif error:
        status = f"⚠ {error}"
    else:
        status = "✓"

    print(f"{indent}{to_posix(path)} {status}")

    # Show headings if available
    if headings and exists and not error:
        print(f"{indent}  Headings ({len(headings)}):")
        for heading in headings[:5]:
            print(f"{indent}    - {heading}")
        if len(headings) > 5:
            print(f"{indent}    ... and {len(headings) - 5} more")

    # Show nested related docs (for depth=2)
    if nested_related:
        print(f"{indent}  Related ({len(nested_related)}):")
        for nested in nested_related:
            _format_related_item(nested, indent=indent + "    ", output_format=output_format)


def _count_related_stats(items: List[Dict[str, Any]], depth: int = 1) -> Dict[str, int]:
    """Count total docs and max depth in related tree.

    Args:
        items: List of related document info dicts
        depth: Current depth level

    Returns:
        Dict with 'total' count and 'max_depth'
    """
    total = len(items)
    max_depth = depth if items else 0

    for item in items:
        nested = item.get('related', [])
        if nested:
            nested_stats = _count_related_stats(nested, depth + 1)
            total += nested_stats['total']
            max_depth = max(max_depth, nested_stats['max_depth'])

    return {'total': total, 'max_depth': max_depth}


def _format_related_flat(
    items: List[Dict[str, Any]], seen: Optional[set] = None
) -> List[str]:
    """Extract flat list of paths from related tree (grep-friendly).

    Args:
        items: List of related document info dicts
        seen: Set of already-seen paths (for deduplication)

    Returns:
        List of unique resolved paths
    """
    if seen is None:
        seen = set()

    paths = []
    for item in items:
        resolved = item.get('resolved_path') or item.get('path', '')
        if resolved and resolved not in seen:
            seen.add(resolved)
            paths.append(resolved)
            nested = item.get('related', [])
            if nested:
                paths.extend(_format_related_flat(nested, seen))

    return paths


def _format_related(
    items: List[Dict[str, Any]], path: Path, output_format: str,
    flat: bool = False, show_summary: bool = True
) -> None:
    """Format and display related documents from front matter.

    Args:
        items: List of related document info dicts
        path: Source file path
        output_format: Output format ('grep', 'json', or default)
        flat: If True, output only paths (grep-friendly)
        show_summary: If True, show summary header for multi-level trees
    """
    if not items:
        print("  (No related documents found in front matter)")
        return

    # Flat output mode - just paths
    if flat:
        paths = _format_related_flat(items)
        for p in paths:
            print(p)
        return

    if output_format == 'grep':
        for item in items:
            rel_path = item.get('path', '?')
            exists = "EXISTS" if item.get('exists', False) else "MISSING"
            print(f"{to_posix(path)}:related:{rel_path}:{exists}")
        return

    # Show summary header for deep traversals
    stats = _count_related_stats(items)
    if show_summary and stats['max_depth'] > 1:
        print(f"  ({stats['total']} docs across {stats['max_depth']} levels)")

    # Default text format
    for i, item in enumerate(items, 1):
        print(f"\n  {i}. ", end="")
        _format_related_item(item, indent="     ", output_format=output_format)


def _format_script_summary(script: Dict[str, Any]) -> None:
    """Format and display a single script summary.

    Args:
        script: Script dict with type, src, and preview
    """
    if script['type'] == 'external':
        print(f"    [external] {script['src']}")
        return

    preview = script.get('preview', '')
    if preview:
        print(f"    [inline] {preview[:60]}...")
    else:
        print("    [inline]")


def _format_html_overview(structure: Dict[str, Any], path: Path) -> None:
    """HTML's default view: its document/head/body/stats summary (BACK-1416).

    Those are dicts, not located item lists, so the category loop skips them and
    `reveal page.html` printed only the file header while --format json had the
    whole summary. The drill-down line names the views that list located items.
    """
    document = structure.get('document') or {}
    head = structure.get('head') or {}
    body = structure.get('body') or {}
    stats = structure.get('stats') or {}
    template = structure.get('template') or {}

    doc_parts = []
    if document.get('doctype'):
        doc_parts.append(f"<!DOCTYPE {document['doctype']}>")
    if document.get('language'):
        doc_parts.append(f"lang={document['language']}")
    if doc_parts:
        print(f"Document: {', '.join(doc_parts)}")
    if head.get('title'):
        print(f"Title: {head['title']}")
    if head.get('meta'):
        print(f"Meta tags: {len(head['meta'])} ({', '.join(list(head['meta'])[:6])})")
    if body.get('semantic'):
        print(f"Sections: {', '.join(body['semantic'])}")
    counts = [f"{stats[k]} {k}" for k in ('links', 'images', 'forms', 'tables') if isinstance(stats.get(k), int)]
    if counts:
        print(f"Elements: {', '.join(counts)}")
    if template.get('type'):
        variables = template.get('variables') or []
        print(f"Template: {template['type']}" + (f" ({len(variables)} variables)" if variables else ''))
    print(f"\nDrill down: reveal {path.name} --metadata | --semantic navigation|content|forms"
          f" | --links | --scripts all | --styles all")
    print()


def _format_html_metadata(
    metadata: Dict[str, Any], path: Path, output_format: str
) -> None:
    """Format and display HTML metadata (SEO, social, etc.)."""
    # Title
    if 'title' in metadata:
        print(f"  Title: {metadata['title']}")

    # Meta tags
    if 'meta' in metadata:
        print(f"\n  Meta Tags ({len(metadata['meta'])}):")
        for name, content in metadata['meta'].items():
            if len(content) > 80:
                print(f"    {name}: {content[:77]}...")
            else:
                print(f"    {name}: {content}")

    # Canonical URL
    if 'canonical' in metadata:
        print(f"\n  Canonical: {metadata['canonical']}")

    # Stylesheets
    if 'stylesheets' in metadata:
        print(f"\n  Stylesheets ({len(metadata['stylesheets'])}):")
        for stylesheet in metadata['stylesheets']:
            print(f"    {stylesheet}")

    # Scripts
    if 'scripts' in metadata:
        print(f"\n  Scripts ({len(metadata['scripts'])}):")
        for script in metadata['scripts']:
            _format_script_summary(script)


def _format_script_element(
    elem: Dict[str, Any], path: Path, line: int
) -> None:
    """Format and display a script element.

    Args:
        elem: Script element dict
        path: File path (kept for API compatibility, not displayed - shown in header)
        line: Line number
    """
    if elem['type'] == 'external':
        print(f"  :{line:<6} [external] {elem['src']}")
        return

    preview = elem.get('preview', '')
    if preview:
        print(f"  :{line:<6} [inline] {preview[:60]}...")
    else:
        print(f"  :{line:<6} [inline]")


def _format_style_element(
    elem: Dict[str, Any], path: Path, line: int
) -> None:
    """Format and display a style element.

    Args:
        elem: Style element dict
        path: File path (kept for API compatibility, not displayed - shown in header)
        line: Line number
    """
    if elem['type'] == 'external':
        print(f"  :{line:<6} [external] {elem['href']}")
        return

    preview = elem.get('preview', '')
    if preview:
        print(f"  :{line:<6} [inline] {preview[:60]}...")
    else:
        print(f"  :{line:<6} [inline]")


def _format_semantic_element(
    elem: Dict[str, Any], path: Path, line: int
) -> None:
    """Format and display a semantic element.

    Args:
        elem: Semantic element dict
        path: File path (kept for API compatibility, not displayed - shown in header)
        line: Line number
    """
    tag = elem.get('tag', '')
    attrs = elem.get('attributes', {})
    elem_id = attrs.get('id', '')
    elem_class_attr = attrs.get('class', '')

    # Build class string
    if isinstance(elem_class_attr, list):
        elem_class = ' '.join(elem_class_attr)
    else:
        elem_class = elem_class_attr

    # Build label
    label = f"<{tag}>"
    if elem_id:
        label += f" #{elem_id}"
    elif elem_class:
        first_class = elem_class.split()[0] if elem_class else ''
        label += f" .{first_class}"

    print(f"  :{line:<6} {label}")


def _format_html_elements(
    elements: List[Dict[str, Any]],
    path: Path,
    output_format: str,
    category: str
) -> None:
    """Format and display HTML elements (scripts, styles, semantic)."""
    for elem in elements:
        line = elem.get('line', '?')

        if category == 'scripts':
            _format_script_element(elem, path, line)
        elif category == 'styles':
            _format_style_element(elem, path, line)
        elif category == 'semantic':
            _format_semantic_element(elem, path, line)


def _build_item_metrics(item: Dict[str, Any]) -> str:
    """Build the metrics display string for an item (line_count, depth)."""
    parts = []
    if 'line_count' in item:
        parts.append(lines_label(item['line_count']))
    if 'depth' in item:
        parts.append(f"depth:{item['depth']}")
    return f" [{', '.join(parts)}]" if parts else ''


def _print_item_line(line, name: str, signature: str, content: str,
                     target_suffix: str, metrics: str, path: Path, output_format: str) -> None:
    """Print a single item in the appropriate output format."""
    if signature and name:
        if output_format == 'grep':
            print(f"{to_posix(path)}:{line}:{name}{signature}")
        else:
            print(f"  :{line:<6} {name}{signature}{metrics}")
    elif name:
        if output_format == 'grep':
            print(f"{to_posix(path)}:{line}:{name}{target_suffix.replace(' → ', ':')}")
        else:
            print(f"  :{line:<6} {name}{target_suffix}{metrics}")
    elif content:
        if output_format == 'grep':
            print(f"{to_posix(path)}:{line}:{content}")
        else:
            print(f"  :{line:<6} {content}")


def _format_standard_items(
    items: List[Dict[str, Any]], path: Path, output_format: str
) -> None:
    """Format and display standard items (functions, classes, etc.)."""
    for item in items:
        _print_item_line(
            line=item.get('line', item.get('line_start', '?')),
            name=item.get('name', ''),
            signature=item.get('signature', ''),
            content=item.get('content', ''),
            target_suffix=f" → {item['target']}" if item.get('target') else '',
            metrics=_build_item_metrics(item),
            path=path,
            output_format=output_format,
        )


def _discriminating_level(items: List[Dict[str, Any]]) -> int:
    """Pick the shallowest heading level with more than one entry.

    A lone H1 title is not a useful collapse point, so we skip past any
    level that has exactly one heading until we find one that actually
    discriminates between sections. Falls back to the shallowest level
    present if no level has more than one entry.
    """
    levels_present = sorted({item.get('level', 1) for item in items})
    counts = {lvl: sum(1 for item in items if item.get('level', 1) == lvl) for lvl in levels_present}
    for lvl in levels_present:
        if counts[lvl] > 1:
            return lvl
    return levels_present[0]


def _print_heading_line(item: Dict[str, Any], indent: str, suffix: str, path: Path, output_format: str) -> None:
    """Print a single heading line, indented by level, with an optional suffix."""
    line = item.get('line', '?')
    name = item.get('name', '')
    if output_format == 'grep':
        print(f"{to_posix(path)}:{line}:{name}{suffix}")
    else:
        print(f"  {indent}:{line:<6} {name}{suffix}")


def _format_markdown_headings(
    items: List[Dict[str, Any]], path: Path, output_format: str, depth_override: Optional[int] = None
) -> None:
    """Format markdown headings, indented by level.

    Above HEADING_COLLAPSE_THRESHOLD headings, collapses to the shallowest
    discriminating level (see _discriminating_level) and shows a
    "(+N subheadings)" count on each collapsed entry, unless depth_override
    (from --depth) pins the collapse level explicitly. Below the threshold,
    every heading is shown, indented by its level.
    """
    if not items:
        return

    min_level = min(item.get('level', 1) for item in items)

    if depth_override is not None:
        collapse_level = min_level + depth_override
    elif len(items) > HEADING_COLLAPSE_THRESHOLD:
        collapse_level = _discriminating_level(items)
    else:
        collapse_level = None

    if collapse_level is None:
        for item in items:
            level = item.get('level', 1)
            indent = '  ' * (level - min_level)
            _print_heading_line(item, indent, '', path, output_format)
        return

    visible = [(idx, item) for idx, item in enumerate(items) if item.get('level', 1) <= collapse_level]
    for i, (idx, item) in enumerate(visible):
        next_idx = visible[i + 1][0] if i + 1 < len(visible) else len(items)
        hidden_count = next_idx - idx - 1
        suffix = f" (+{hidden_count} subheadings)" if hidden_count > 0 else ''

        level = item.get('level', 1)
        indent = '  ' * (level - min_level)
        _print_heading_line(item, indent, suffix, path, output_format)


def _format_csv_schema(items: List[Dict[str, Any]]) -> None:
    """Format CSV schema with column types and stats."""
    for item in items:
        name = item.get('name', '?')
        dtype = item.get('type', 'unknown')
        missing_pct = item.get('missing_pct', 0)
        unique = item.get('unique_count', '?')

        # Build info string
        info_parts = [dtype]
        if missing_pct > 0:
            info_parts.append(f"{missing_pct}% missing")
        info_parts.append(f"{unique} unique")

        samples = item.get('sample_values', [])
        sample_str = ''
        if samples:
            # Truncate long sample values
            truncated = [s[:20] + '...' if len(str(s)) > 20 else str(s) for s in samples[:3]]
            sample_str = f" → {', '.join(truncated)}"

        print(f"  {name:<20} ({', '.join(info_parts)}){sample_str}")


def _format_csv_sample_rows(items: List[Dict[str, Any]]) -> None:
    """Format CSV sample rows as one numbered line per row, values truncated."""
    for i, row in enumerate(items, start=1):
        parts = []
        for key, value in row.items():
            display = str(value)
            if len(display) > 20:
                display = display[:20] + '...'
            parts.append(f"{key}={display}")
        print(f"  {i}. {', '.join(parts)}")


def _format_xml_children(items: List[Dict[str, Any]], indent: int = 1) -> None:
    """Format XML children with nested structure."""
    for item in items:
        tag = item.get('tag', '?')
        attrs = item.get('attributes', {})
        text = item.get('text', '')
        children = item.get('children', [])
        child_count = item.get('child_count', 0)

        # Build attribute string
        attr_str = ''
        if attrs:
            attr_parts = [f'{k}="{v}"' for k, v in list(attrs.items())[:3]]
            if len(attrs) > 3:
                attr_parts.append('...')
            attr_str = ' ' + ' '.join(attr_parts)

        # Build content hint
        content_hint = ''
        if text:
            # Show truncated text content
            text_preview = text[:30] + '...' if len(text) > 30 else text
            content_hint = f' → "{text_preview}"'
        elif child_count > 0:
            content_hint = f' ({child_count} children)'

        prefix = '  ' * indent
        print(f"{prefix}<{tag}{attr_str}>{content_hint}")

        # Recursively show nested children (limit depth)
        if children and indent < 3:
            _format_xml_children(children, indent + 1)


def _add_markdown_link_kwargs(kwargs: Dict[str, Any], args) -> None:
    """Add markdown link extraction arguments to kwargs.

    Args:
        kwargs: Dict to update with link args
        args: Command-line arguments
    """
    broken_only = getattr(args, 'broken_only', False)
    if not (args.links or args.link_type or args.domain or broken_only):
        return

    kwargs['extract_links'] = True
    if args.link_type:
        kwargs['link_type'] = args.link_type
    if args.domain:
        kwargs['domain'] = args.domain
    if broken_only:
        kwargs['broken_only'] = True


def _add_markdown_code_kwargs(kwargs: Dict[str, Any], args) -> None:
    """Add markdown code extraction arguments to kwargs.

    Args:
        kwargs: Dict to update with code args
        args: Command-line arguments
    """
    if not (args.code or args.language or args.inline):
        return

    kwargs['extract_code'] = True
    if args.language:
        kwargs['language'] = args.language
    if args.inline:
        kwargs['inline_code'] = args.inline


def _add_html_kwargs(kwargs: Dict[str, Any], args) -> None:
    """Add HTML-specific arguments to kwargs.

    Args:
        kwargs: Dict to update with HTML args
        args: Command-line arguments
    """
    if not (args.metadata or args.semantic or args.scripts or args.styles):
        return

    if args.metadata:
        kwargs['metadata'] = True
    if args.semantic:
        kwargs['semantic'] = args.semantic
    if args.scripts:
        kwargs['scripts'] = args.scripts
    if args.styles:
        kwargs['styles'] = args.styles


def _build_analyzer_kwargs(analyzer: FileAnalyzer, args) -> Dict[str, Any]:
    """Build kwargs for get_structure() based on analyzer type and args.

    Refactored to reduce complexity from 40 → ~10 by extracting helpers.

    Args:
        analyzer: File analyzer instance
        args: Command-line arguments

    Returns:
        Dict of kwargs for get_structure()
    """
    kwargs: Dict[str, Any] = {}

    # --head/--tail/--range are not an analyzer's: show_structure cuts the result (BACK-1548).

    # Markdown-specific filters
    if args and hasattr(analyzer, '_extract_links'):
        _add_markdown_link_kwargs(kwargs, args)
        _add_markdown_code_kwargs(kwargs, args)
        if getattr(args, 'head', None) or getattr(args, 'tail', None) or getattr(args, 'range', None):
            kwargs['navigate'] = True

        if args.frontmatter:
            kwargs['extract_frontmatter'] = True

        # Handle --related-all shorthand
        if getattr(args, 'related_all', False):
            kwargs['extract_related'] = True
            kwargs['related_depth'] = int(0)  # unlimited
            kwargs['related_limit'] = int(getattr(args, 'related_limit', 100))
        elif getattr(args, 'related', False):
            kwargs['extract_related'] = True
            kwargs['related_depth'] = int(getattr(args, 'related_depth', 1))
            kwargs['related_limit'] = int(getattr(args, 'related_limit', 100))

    # HTML-specific filters
    if args and hasattr(analyzer, '_extract_metadata'):
        _add_html_kwargs(kwargs, args)

        # HTML also supports --links (reuse from markdown)
        if args.links or args.link_type or args.domain:
            kwargs['links'] = True
            if args.link_type:
                kwargs['link_type'] = args.link_type
            if args.domain:
                kwargs['domain'] = args.domain

    # nginx-specific: --server-name filters to a single server block (N3)
    if args and hasattr(analyzer, '_filter_structure_by_domain') and getattr(args, 'server_name', None):
        kwargs['server_name'] = args.server_name

    return kwargs


def print_truncations(result: dict, output_format: str) -> None:
    """Say, once, which lists the rendered answer shows only part of (BACK-1059).

    Shared with the subcommand seam (subcommand.emit_subcommand_result), so ``reveal
    overview`` and ``overview://`` disclose a cut the same way (BACK-1544).

    Truncation was disclosed by whichever renderer knew the adapter's spelling of it, so
    ``stats://?limit=2`` and ``markdown://?limit=2`` printed a cut list as the whole
    answer. Renderers leave ``truncated`` warnings to this. JSON already carries them in
    ``meta.warnings``; text gets them after the body, on stdout with it; any other format
    (grep) gets them on stderr, so its lines stay parseable.

    A result that chose its own format (xlsx ``?format=csv``, ``preferred_format``) is
    rendered in it whatever ``--format`` says, so it decides the stream: a CSV export's
    cut goes to stderr, not into the CSV (BACK-1608).
    """
    output_format = result.get('preferred_format') or output_format
    if output_format == 'json':
        return
    stream = sys.stdout if output_format == 'text' else sys.stderr
    print(file=stream)
    for entry in truncations_of(result):
        print(f"⚠ Truncated {entry['message']}", file=stream)
