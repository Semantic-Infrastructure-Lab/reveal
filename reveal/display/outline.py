"""Outline and hierarchy building for file structure display."""

from pathlib import Path
from typing import Any, Dict, List


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
        for item in items:
            item = item.copy()  # Don't mutate original
            item['category'] = category
            item['children'] = []
            all_items.append(item)

    # Sort by line number
    all_items.sort(key=lambda x: x.get('line', 0))

    # Build parent-child relationships based on line ranges
    # An item is a child if it's within another item's line range
    for i, item in enumerate(all_items):
        item_start = item.get('line', 0)
        item_end = item.get('line_end', item_start)

        # Find potential parent (previous item that contains this one)
        parent = None
        for j in range(i - 1, -1, -1):
            candidate = all_items[j]
            candidate_start = candidate.get('line', 0)
            candidate_end = candidate.get('line_end', candidate_start)

            # Check if candidate contains this item
            if candidate_start < item_start and candidate_end >= item_end:
                # Found a containing item - use most recent (closest parent)
                parent = candidate
                break

        # Add to parent's children or mark as root
        if parent:
            parent['children'].append(item)
            item['is_child'] = True
        else:
            item['is_child'] = False

    # Return only root-level items
    return [item for item in all_items if not item.get('is_child', False)]


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
    stack = []  # Stack of (level, item) for finding parents

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


def render_outline(items: List[Dict[str, Any]], path: Path, indent: str = '', is_root: bool = True) -> None:
    """Render hierarchical outline with tree characters.

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

        # Format item
        line = item.get('line', '?')
        name = item.get('name', '')
        signature = item.get('signature', '')

        # Build metrics display
        metrics = ''
        if 'line_count' in item or 'depth' in item:
            parts = []
            if 'line_count' in item:
                parts.append(f"{item['line_count']} lines")
            if 'depth' in item:
                parts.append(f"depth:{item['depth']}")
            if parts:
                metrics = f" [{', '.join(parts)}]"

        # Format output
        if signature and name:
            display = f"{name}{signature}{metrics}"
        elif name:
            display = f"{name}{metrics}"
        else:
            display = item.get('content', '?')

        # Print item with appropriate prefix
        if is_root:
            # Root items - no tree chars, show full path
            print(f"{display} ({path}:{line})")
        else:
            # Child items - use tree chars
            tree_char = '└─ ' if is_last_item else '├─ '
            print(f"{indent}{tree_char}{display} (line {line})")

        # Recursively render children
        if item.get('children'):
            if is_root:
                # Children of root get minimal indent
                child_indent = '  '
            else:
                # Children of nested items continue the tree
                child_indent = indent + ('   ' if is_last_item else '│  ')
            render_outline(item['children'], path, child_indent, is_root=False)
