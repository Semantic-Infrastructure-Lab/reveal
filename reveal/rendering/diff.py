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

    # Header
    print()
    print("=" * 70)
    print(f"Structure Diff: {left.get('uri', '?')} → {right.get('uri', '?')}")
    print("=" * 70)
    print()

    # Summary
    print("📊 Summary:")
    print()

    has_changes = False

    if summary.get('functions'):
        f = summary['functions']
        if f['added'] > 0 or f['removed'] > 0 or f['modified'] > 0:
            has_changes = True
            print(f"  Functions:  +{f['added']} -{f['removed']} ~{f['modified']}")

    if summary.get('classes'):
        c = summary['classes']
        if c['added'] > 0 or c['removed'] > 0 or c['modified'] > 0:
            has_changes = True
            print(f"  Classes:    +{c['added']} -{c['removed']} ~{c['modified']}")

    if summary.get('imports'):
        i = summary['imports']
        if i['added'] > 0 or i['removed'] > 0:
            has_changes = True
            print(f"  Imports:    +{i['added']} -{i['removed']}")

    if not has_changes:
        print("  No structural changes detected")
        print()
        return

    print()

    # Detailed changes - Functions
    func_details = details.get('functions', [])
    if func_details:
        print("🔧 Functions:")
        print()
        for func in func_details:
            if func['type'] == 'added':
                print(f"  + {func['name']}")
                line = func.get('line')
                line_count = func.get('line_count', '?')
                complexity = func.get('complexity', '?')
                sig = func.get('signature', '')
                if line:
                    print(f"      Line {line}")
                if sig:
                    print(f"      {sig}")
                print(f"      [NEW - {line_count} lines, complexity {complexity}]")
                print()

            elif func['type'] == 'removed':
                print(f"  - {func['name']}")
                line = func.get('line')
                sig = func.get('signature', '')
                if line:
                    print(f"      Line {line}")
                if sig:
                    print(f"      {sig}")
                print(f"      [REMOVED]")
                print()

            elif func['type'] == 'modified':
                print(f"  ~ {func['name']}")
                changes = func.get('changes', {})

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

                print()

    # Detailed changes - Classes
    class_details = details.get('classes', [])
    if class_details:
        print("📦 Classes:")
        print()
        for cls in class_details:
            if cls['type'] == 'added':
                print(f"  + {cls['name']}")
                line = cls.get('line')
                bases = cls.get('bases', [])
                method_count = cls.get('method_count', 0)
                if line:
                    print(f"      Line {line}")
                if bases:
                    print(f"      Bases: {', '.join(bases)}")
                print(f"      [NEW - {method_count} methods]")
                print()

            elif cls['type'] == 'removed':
                print(f"  - {cls['name']}")
                line = cls.get('line')
                if line:
                    print(f"      Line {line}")
                print(f"      [REMOVED]")
                print()

            elif cls['type'] == 'modified':
                print(f"  ~ {cls['name']}")
                changes = cls.get('changes', {})

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

                print()

    # Detailed changes - Imports
    import_details = details.get('imports', [])
    if import_details:
        print("📥 Imports:")
        print()
        for imp in import_details:
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
