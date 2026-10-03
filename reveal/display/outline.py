"""Outline and hierarchy building for file structure display."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reveal.utils.formatting import lines_label
from reveal.utils.path_utils import to_posix

from .formatting import _build_item_metrics


def build_hierarchy(structure: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Build hierarchical tree from flat structure.

    Args:
        structure: Flat structure from analyzer (imports, functions, classes)

    Returns:
        List of root-level items with 'children' added
    """
    # Collect all items with parent info
    all_items = []

    for category, items in structure.items():
        if not isinstance(items, list):
            continue  # Skip contract metadata fields (strings, ints, etc.)
        for item in items:
            if not isinstance(item, dict):
                continue
            item = item.copy()  # Don't mutate original
            item['category'] = category
            item['children'] = []
            all_items.append(item)

    # Sort by line number
    all_items.sort(key=lambda x: x.get('line', 0))
    by_path = _items_by_path(all_items)

    for i, item in enumerate(all_items):
        parent = _choose_parent(_line_parent(all_items, i), by_path.get(item.get('owner', '')), item)
        if parent:
            parent['children'].append(item)
            item['is_child'] = True
        else:
            item['is_child'] = False

    # Return only root-level items
    return [item for item in all_items if not item.get('is_child', False)]


def _span(item: Dict[str, Any]) -> Tuple[int, int]:
    start = item.get('line_start', item.get('line', 0))
    return start, item.get('line_end', start)


def _items_by_path(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Each item under its dotted path (`owner.name`), first in source order wins."""
    by_path: Dict[str, Dict[str, Any]] = {}
    for item in items:
        name = item.get('name')
        if name:
            owner = item.get('owner')
            by_path.setdefault(f'{owner}.{name}' if owner else name, item)
    return by_path


def _line_parent(items: List[Dict[str, Any]], i: int) -> Optional[Dict[str, Any]]:
    """The closest earlier item whose line range contains items[i]."""
    start, end = _span(items[i])
    for j in range(i - 1, -1, -1):
        candidate_start, candidate_end = _span(items[j])
        if candidate_start < start and candidate_end >= end:
            return items[j]
    return None


def _choose_parent(line_parent: Optional[Dict[str, Any]], owner: Optional[Dict[str, Any]],
                   item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The owner the tree names (BACK-1632, BACK-1649), unless the line parent sits
    inside that owner: a function nested in a method keeps the method as parent,
    though the tree's owner is the method's class."""
    if owner is None or owner is item:
        return line_parent
    if line_parent is None or line_parent is owner:
        return owner
    owner_start, owner_end = _span(owner)
    parent_start, parent_end = _span(line_parent)
    if owner_start <= parent_start and parent_end <= owner_end:
        return line_parent
    return owner


def build_heading_hierarchy(headings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build hierarchical tree from flat heading list with levels.

    Args:
        headings: List of heading dicts with 'level', 'name', 'line' fields

    Returns:
        List of root-level headings with 'children' added

    Example:
        Input:  [{'level': 1, 'name': 'A'}, {'level': 2, 'name': 'B'}]
        Output: [{'level': 1, 'name': 'A', 'children': [{'level': 2, 'name': 'B', 'children': []}]}]
    """
    if not headings:
        return []

    # Add children field to all items
    items = [h.copy() for h in headings]
    for item in items:
        item['children'] = []

    # Build parent-child relationships based on level hierarchy
    root_items = []
    stack: List[Tuple[int, Dict[str, Any]]] = []  # Stack of (level, item) for finding parents

    for item in items:
        level = item.get('level', 1)

        # Pop stack until we find the parent level (level - 1)
        while stack and stack[-1][0] >= level:
            stack.pop()

        if not stack:
            # This is a root item
            root_items.append(item)
        else:
            # Add to parent's children
            parent_item = stack[-1][1]
            parent_item['children'].append(item)

        # Push current item onto stack
        stack.append((level, item))

    return root_items


def _build_metrics_display(item: Dict[str, Any]) -> str:
    """Build metrics display string for an item.

    Args:
        item: Item dict potentially containing line_count, depth

    Returns:
        Formatted metrics string (e.g., " [10 lines, depth:3]") or empty string
    """
    return _build_item_metrics(item)


def _build_item_display(item: Dict[str, Any]) -> str:
    """Build display string for an item.

    Args:
        item: Item dict containing name, signature, content

    Returns:
        Formatted display string
    """
    name = item.get('name', '')
    signature = item.get('signature', '')
    metrics = _build_metrics_display(item)

    if signature and name:
        return f"{name}{signature}{metrics}"
    elif name:
        return f"{name}{metrics}"
    else:
        return str(item.get('content', '?'))


def _print_outline_item(item: Dict[str, Any], path: Path,
                        indent: str, is_root: bool, is_last_item: bool) -> None:
    """Print a single outline item with appropriate formatting.

    Args:
        item: Item to print
        path: File path for line number display
        indent: Current indentation prefix
        is_root: Whether this is a root-level item
        is_last_item: Whether this is the last item in its list
    """
    line = item.get('line_start', item.get('line', '?'))
    display = _build_item_display(item)
    size = item.get('size')
    size_str = f", {lines_label(size)}" if size is not None else ""

    if is_root:
        # Root items - no tree chars, show full path
        print(f"{display} ({to_posix(path)}:{line}{size_str})")
    else:
        # Child items - use tree chars
        tree_char = '└─ ' if is_last_item else '├─ '
        print(f"{indent}{tree_char}{display} (line {line}{size_str})")


def _get_child_indent(indent: str, is_root: bool, is_last_item: bool) -> str:
    """Calculate indentation for child items.

    Args:
        indent: Current indentation prefix
        is_root: Whether parent is a root item
        is_last_item: Whether parent is the last item in its list

    Returns:
        Indentation string for children
    """
    if is_root:
        # Children of root get minimal indent
        return '  '
    else:
        # Children of nested items continue the tree
        return indent + ('   ' if is_last_item else '│  ')


def render_outline(items: List[Dict[str, Any]], path: Path, indent: str = '', is_root: bool = True) -> None:
    """Render hierarchical outline with tree characters.

    Refactored to reduce complexity from 34 → ~12 by extracting helpers.

    Args:
        items: List of items (potentially with children)
        path: File path for line number display
        indent: Current indentation prefix
        is_root: Whether these are root-level items
    """
    if not items:
        return

    for i, item in enumerate(items):
        is_last_item = (i == len(items) - 1)

        # Print this item
        _print_outline_item(item, path, indent, is_root, is_last_item)

        # Recursively render children
        if item.get('children'):
            child_indent = _get_child_indent(indent, is_root, is_last_item)
            render_outline(item['children'], path, child_indent, is_root=False)
