"""Rendering functions for diff:// adapter output."""

import json
from typing import Dict, Any


def render_diff(diff_result: Dict[str, Any], format: str = 'text',
                is_element: bool = False) -> None:
    """Render diff result in specified format.

    Args:
        diff_result: Output from DiffAdapter.get_structure() or get_element()
        format: 'text' or 'json'
        is_element: True if this is an element-specific diff
    """
    if format == 'json':
        render_diff_json(diff_result)
    else:
        if is_element:
            render_element_diff_text(diff_result)
        else:
            render_diff_text(diff_result)


def render_diff_text(diff_result: Dict[str, Any]) -> None:
    """Render diff in human-readable text format.

    Args:
        diff_result: Diff result from DiffAdapter
    """
    left = diff_result.get('left', {})
    right = diff_result.get('right', {})
    summary = diff_result.get('summary', {})
    details = diff_result.get('diff', {})

    _render_diff_header(left, right)

    has_changes = _render_diff_summary(summary)
    if not has_changes:
        return

    print()

    # Detailed changes
    _render_functions_section(details.get('functions', []))
    _render_classes_section(details.get('classes', []))
    _render_imports_section(details.get('imports', []))


def _render_diff_header(left: Dict[str, Any], right: Dict[str, Any]) -> None:
    """Render diff header."""
    print()
    print("=" * 70)
    print(f"Structure Diff: {left.get('uri', '?')} → {right.get('uri', '?')}")
    print("=" * 70)
    print()


def _has_changes(data: Dict[str, int]) -> bool:
    """Check if category has any changes."""
    return any(data.get(key, 0) > 0 for key in ['added', 'removed', 'modified'])


def _render_category_summary(category_name: str, data: Dict[str, int], show_modified: bool = True) -> bool:
    """Render summary for a single category.

    Args:
        category_name: Name of category (e.g., 'Functions', 'Classes')
        data: Dict with 'added', 'removed', and optionally 'modified' counts
        show_modified: Whether to include modified count in output

    Returns:
        True if category has changes, False otherwise
    """
    if not _has_changes(data):
        return False

    if show_modified and data.get('modified', 0) > 0:
        print(f"  {category_name}:  +{data['added']} -{data['removed']} ~{data['modified']}")
    else:
        print(f"  {category_name}:  +{data['added']} -{data['removed']}")

    return True


def _render_diff_summary(summary: Dict[str, Any]) -> bool:
    """Render summary section.

    Returns:
        True if changes detected, False otherwise
    """
    print("📊 Summary:")
    print()

    has_changes = False

    if summary.get('functions'):
        has_changes |= _render_category_summary('Functions', summary['functions'])

    if summary.get('classes'):
        has_changes |= _render_category_summary('Classes', summary['classes'])

    if summary.get('imports'):
        has_changes |= _render_category_summary('Imports', summary['imports'], show_modified=False)

    if not has_changes:
        print("  No structural changes detected")
        print()

    return has_changes


def _render_functions_section(functions: list) -> None:
    """Render functions detail section."""
    if not functions:
        return

    print("🔧 Functions:")
    print()
    for func in functions:
        _render_function_change(func)


def _render_function_change(func: Dict[str, Any]) -> None:
    """Render a single function change."""
    change_type = func['type']
    name = func['name']

    if change_type == 'added':
        print(f"  + {name}")
        _render_function_metadata(func)
        line_count = func.get('line_count', '?')
        complexity = func.get('complexity', '?')
        print(f"      [NEW - {line_count} lines, complexity {complexity}]")
        print()

    elif change_type == 'removed':
        print(f"  - {name}")
        _render_function_metadata(func)
        print(f"      [REMOVED]")
        print()

    elif change_type == 'modified':
        print(f"  ~ {name}")
        _render_function_modifications(func.get('changes', {}))
        print()


def _render_function_metadata(func: Dict[str, Any]) -> None:
    """Render function metadata (line, signature)."""
    line = func.get('line')
    sig = func.get('signature', '')
    if line:
        print(f"      Line {line}")
    if sig:
        print(f"      {sig}")


def _render_function_modifications(changes: Dict[str, Any]) -> None:
    """Render function modifications."""
    if 'signature' in changes:
        print(f"      Signature:")
        print(f"        - {changes['signature']['old']}")
        print(f"        + {changes['signature']['new']}")

    if 'complexity' in changes:
        old_cx = changes['complexity']['old']
        new_cx = changes['complexity']['new']
        delta = changes['complexity']['delta']
        sign = '+' if delta > 0 else ''
        print(f"      Complexity: {old_cx} → {new_cx} ({sign}{delta})")

    if 'line_count' in changes:
        old_lines = changes['line_count']['old']
        new_lines = changes['line_count']['new']
        delta = changes['line_count']['delta']
        sign = '+' if delta > 0 else ''
        print(f"      Lines: {old_lines} → {new_lines} ({sign}{delta})")

    if 'line' in changes:
        print(f"      Line: {changes['line']['old']} → {changes['line']['new']}")


def _render_classes_section(classes: list) -> None:
    """Render classes detail section."""
    if not classes:
        return

    print("📦 Classes:")
    print()
    for cls in classes:
        _render_class_change(cls)


def _render_class_change(cls: Dict[str, Any]) -> None:
    """Render a single class change."""
    change_type = cls['type']
    name = cls['name']

    if change_type == 'added':
        print(f"  + {name}")
        _render_class_metadata(cls, show_method_count=True)
        print()

    elif change_type == 'removed':
        print(f"  - {name}")
        line = cls.get('line')
        if line:
            print(f"      Line {line}")
        print(f"      [REMOVED]")
        print()

    elif change_type == 'modified':
        print(f"  ~ {name}")
        _render_class_modifications(cls.get('changes', {}))
        print()


def _render_class_metadata(cls: Dict[str, Any], show_method_count: bool = False) -> None:
    """Render class metadata."""
    line = cls.get('line')
    bases = cls.get('bases', [])

    if line:
        print(f"      Line {line}")
    if bases:
        print(f"      Bases: {', '.join(bases)}")

    if show_method_count:
        method_count = cls.get('method_count', 0)
        print(f"      [NEW - {method_count} methods]")


def _render_class_modifications(changes: Dict[str, Any]) -> None:
    """Render class modifications."""
    if 'bases' in changes:
        old_bases = changes['bases']['old']
        new_bases = changes['bases']['new']
        print(f"      Bases:")
        print(f"        - {', '.join(old_bases) if old_bases else '(none)'}")
        print(f"        + {', '.join(new_bases) if new_bases else '(none)'}")

    if 'methods' in changes:
        added = changes['methods']['added']
        removed = changes['methods']['removed']
        old_count = changes['methods']['count_old']
        new_count = changes['methods']['count_new']

        if added:
            print(f"      Methods added: {', '.join(added)}")
        if removed:
            print(f"      Methods removed: {', '.join(removed)}")
        print(f"      Method count: {old_count} → {new_count}")


def _render_imports_section(imports: list) -> None:
    """Render imports detail section."""
    if not imports:
        return

    print("📥 Imports:")
    print()
    for imp in imports:
        if imp['type'] == 'added':
            print(f"  + {imp['content']}")
        elif imp['type'] == 'removed':
            print(f"  - {imp['content']}")
    print()


def render_element_diff_text(diff_result: Dict[str, Any]) -> None:
    """Render element-specific diff in text format.

    Args:
        diff_result: Element diff result
    """
    diff_type = diff_result.get('type')
    name = diff_result.get('name')

    print()
    print("=" * 70)
    print(f"Element Diff: {name}")
    print("=" * 70)
    print()

    if diff_type == 'not_found':
        print(f"❌ Element '{name}' not found in either resource")
        print()
        return

    if diff_type == 'added':
        print(f"✅ Element '{name}' was ADDED")
        print()
        element = diff_result.get('element', {})
        _render_element_details(element)
        return

    if diff_type == 'removed':
        print(f"❌ Element '{name}' was REMOVED")
        print()
        element = diff_result.get('element', {})
        _render_element_details(element)
        return

    if diff_type == 'unchanged':
        print(f"✓ Element '{name}' is UNCHANGED")
        print()
        print(diff_result.get('message', ''))
        print()
        return

    if diff_type == 'modified':
        print(f"~ Element '{name}' was MODIFIED")
        print()
        changes = diff_result.get('changes', {})
        if not changes:
            print("No changes detected")
        else:
            for key, change in changes.items():
                old = change.get('old')
                new = change.get('new')
                print(f"  {key}:")
                print(f"    - {old}")
                print(f"    + {new}")
                print()


def _render_element_details(element: Dict[str, Any]) -> None:
    """Render element details.

    Args:
        element: Element dict
    """
    for key, value in element.items():
        if key in ['name', 'type']:
            continue
        print(f"  {key}: {value}")
    print()


def render_diff_json(diff_result: Dict[str, Any]) -> None:
    """Render diff in JSON format.

    Args:
        diff_result: Diff result
    """
    print(json.dumps(diff_result, indent=2))
