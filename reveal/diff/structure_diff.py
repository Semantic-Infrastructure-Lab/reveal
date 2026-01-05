"""Core diff algorithm for comparing reveal structures."""

from typing import Dict, Any, List, Optional


def compute_structure_diff(left: Dict[str, Any],
                          right: Dict[str, Any]) -> Dict[str, Any]:
    """Compute semantic diff between two structures.

    Args:
        left: Structure from left URI
        right: Structure from right URI

    Returns:
        {
            'summary': {
                'functions': {'added': N, 'removed': M, 'modified': K},
                'classes': {...},
                'imports': {...}
            },
            'details': {
                'functions': [
                    {'type': 'added', 'name': 'foo', 'line': 42, ...},
                    {'type': 'removed', 'name': 'bar', ...},
                    {'type': 'modified', 'name': 'baz', 'changes': {...}}
                ],
                ...
            }
        }
    """
    # Handle both nested and flat structure formats
    # Some adapters return {'structure': {...}}, others return {...} directly
    left_struct = left.get('structure', left)
    right_struct = right.get('structure', right)

    # Get summary counts
    func_summary, func_details = diff_functions(
        left_struct.get('functions', []),
        right_struct.get('functions', [])
    )

    class_summary, class_details = diff_classes(
        left_struct.get('classes', []),
        right_struct.get('classes', [])
    )

    import_summary, import_details = diff_imports(
        left_struct.get('imports', []),
        right_struct.get('imports', [])
    )

    return {
        'summary': {
            'functions': func_summary,
            'classes': class_summary,
            'imports': import_summary
        },
        'details': {
            'functions': func_details,
            'classes': class_details,
            'imports': import_details
        }
    }


def compute_element_diff(left_elem: Optional[Dict[str, Any]],
                        right_elem: Optional[Dict[str, Any]],
                        element_name: str) -> Dict[str, Any]:
    """Compute diff for a specific element.

    Args:
        left_elem: Element from left structure (or None if not found)
        right_elem: Element from right structure (or None if not found)
        element_name: Name of the element

    Returns:
        Detailed diff for the element
    """
    if left_elem is None and right_elem is None:
        return {
            'type': 'not_found',
            'name': element_name,
            'message': f"Element '{element_name}' not found in either resource"
        }

    if left_elem is None:
        return {
            'type': 'added',
            'name': element_name,
            'element': right_elem
        }

    if right_elem is None:
        return {
            'type': 'removed',
            'name': element_name,
            'element': left_elem
        }

    # Both exist - check if modified
    changes = _compute_element_changes(left_elem, right_elem)

    if not changes:
        return {
            'type': 'unchanged',
            'name': element_name,
            'message': f"Element '{element_name}' is identical in both resources"
        }

    return {
        'type': 'modified',
        'name': element_name,
        'changes': changes,
        'left': left_elem,
        'right': right_elem
    }


def diff_functions(left_funcs: List[Dict],
                   right_funcs: List[Dict]) -> tuple[Dict[str, int], List[Dict]]:
    """Compare function lists and return summary counts + details.

    Args:
        left_funcs: List of functions from left structure
        right_funcs: List of functions from right structure

    Returns:
        Tuple of (summary_dict, details_list)
    """
    left_names = {f['name']: f for f in left_funcs}
    right_names = {f['name']: f for f in right_funcs}

    added_names = right_names.keys() - left_names.keys()
    removed_names = left_names.keys() - right_names.keys()
    common_names = left_names.keys() & right_names.keys()

    # Build detailed diff list
    details = []

    # Added functions
    for name in sorted(added_names):
        func = right_names[name]
        details.append({
            'type': 'added',
            'name': name,
            'line': func.get('line'),
            'signature': func.get('signature'),
            'complexity': func.get('complexity'),
            'line_count': func.get('line_count')
        })

    # Removed functions
    for name in sorted(removed_names):
        func = left_names[name]
        details.append({
            'type': 'removed',
            'name': name,
            'line': func.get('line'),
            'signature': func.get('signature'),
            'complexity': func.get('complexity'),
            'line_count': func.get('line_count')
        })

    # Modified functions
    modified_count = 0
    for name in sorted(common_names):
        left_func = left_names[name]
        right_func = right_names[name]

        if function_changed(left_func, right_func):
            modified_count += 1
            changes = _compute_function_changes(left_func, right_func)
            details.append({
                'type': 'modified',
                'name': name,
                'changes': changes,
                'left': left_func,
                'right': right_func
            })

    summary = {
        'added': len(added_names),
        'removed': len(removed_names),
        'modified': modified_count
    }

    return summary, details


def function_changed(left: Dict, right: Dict) -> bool:
    """Determine if a function has meaningfully changed.

    Args:
        left: Left function dict
        right: Right function dict

    Returns:
        True if function has meaningful changes
    """
    # Compare signature
    if left.get('signature') != right.get('signature'):
        return True

    # Compare complexity (significant change = ±2 or more)
    left_cx = left.get('complexity', 0)
    right_cx = right.get('complexity', 0)
    if abs(left_cx - right_cx) >= 2:
        return True

    # Compare line count (significant change = ±10% or more)
    left_lines = left.get('line_count', 0)
    right_lines = right.get('line_count', 0)
    if left_lines > 0:
        change_pct = abs(right_lines - left_lines) / left_lines
        if change_pct >= 0.10:
            return True

    return False


def _compute_function_changes(left: Dict, right: Dict) -> Dict[str, Any]:
    """Compute detailed changes for a function.

    Args:
        left: Left function dict
        right: Right function dict

    Returns:
        Dict of changes with old/new values
    """
    changes = {}

    # Signature change
    if left.get('signature') != right.get('signature'):
        changes['signature'] = {
            'old': left.get('signature'),
            'new': right.get('signature')
        }

    # Complexity change
    left_cx = left.get('complexity', 0)
    right_cx = right.get('complexity', 0)
    if left_cx != right_cx:
        changes['complexity'] = {
            'old': left_cx,
            'new': right_cx,
            'delta': right_cx - left_cx
        }

    # Line count change
    left_lines = left.get('line_count', 0)
    right_lines = right.get('line_count', 0)
    if left_lines != right_lines:
        changes['line_count'] = {
            'old': left_lines,
            'new': right_lines,
            'delta': right_lines - left_lines
        }

    # Line number change
    if left.get('line') != right.get('line'):
        changes['line'] = {
            'old': left.get('line'),
            'new': right.get('line')
        }

    return changes


def diff_classes(left_classes: List[Dict],
                 right_classes: List[Dict]) -> tuple[Dict[str, int], List[Dict]]:
    """Compare class lists and return summary counts + details.

    Args:
        left_classes: List of classes from left structure
        right_classes: List of classes from right structure

    Returns:
        Tuple of (summary_dict, details_list)
    """
    left_names = {c['name']: c for c in left_classes}
    right_names = {c['name']: c for c in right_classes}

    added_names = right_names.keys() - left_names.keys()
    removed_names = left_names.keys() - right_names.keys()
    common_names = left_names.keys() & right_names.keys()

    details = []

    # Added classes
    for name in sorted(added_names):
        cls = right_names[name]
        details.append({
            'type': 'added',
            'name': name,
            'line': cls.get('line'),
            'bases': cls.get('bases', []),
            'method_count': len(cls.get('methods', []))
        })

    # Removed classes
    for name in sorted(removed_names):
        cls = left_names[name]
        details.append({
            'type': 'removed',
            'name': name,
            'line': cls.get('line'),
            'bases': cls.get('bases', []),
            'method_count': len(cls.get('methods', []))
        })

    # Modified classes
    modified_count = 0
    for name in sorted(common_names):
        left_cls = left_names[name]
        right_cls = right_names[name]

        if class_changed(left_cls, right_cls):
            modified_count += 1
            changes = _compute_class_changes(left_cls, right_cls)
            details.append({
                'type': 'modified',
                'name': name,
                'changes': changes,
                'left': left_cls,
                'right': right_cls
            })

    summary = {
        'added': len(added_names),
        'removed': len(removed_names),
        'modified': modified_count
    }

    return summary, details


def class_changed(left: Dict, right: Dict) -> bool:
    """Determine if a class has meaningfully changed.

    Args:
        left: Left class dict
        right: Right class dict

    Returns:
        True if class has meaningful changes
    """
    # Compare base classes
    if left.get('bases', []) != right.get('bases', []):
        return True

    # Compare method counts (significant change = ±2 or more)
    left_methods = len(left.get('methods', []))
    right_methods = len(right.get('methods', []))
    if abs(left_methods - right_methods) >= 2:
        return True

    # Compare method names (added/removed methods)
    left_method_names = {m['name'] for m in left.get('methods', [])}
    right_method_names = {m['name'] for m in right.get('methods', [])}
    if left_method_names != right_method_names:
        return True

    return False


def _compute_class_changes(left: Dict, right: Dict) -> Dict[str, Any]:
    """Compute detailed changes for a class.

    Args:
        left: Left class dict
        right: Right class dict

    Returns:
        Dict of changes with old/new values
    """
    changes = {}

    # Base class changes
    left_bases = left.get('bases', [])
    right_bases = right.get('bases', [])
    if left_bases != right_bases:
        changes['bases'] = {
            'old': left_bases,
            'new': right_bases
        }

    # Method changes
    left_methods = left.get('methods', [])
    right_methods = right.get('methods', [])
    left_method_names = {m['name'] for m in left_methods}
    right_method_names = {m['name'] for m in right_methods}

    added_methods = right_method_names - left_method_names
    removed_methods = left_method_names - right_method_names

    if added_methods or removed_methods:
        changes['methods'] = {
            'added': sorted(added_methods),
            'removed': sorted(removed_methods),
            'count_old': len(left_methods),
            'count_new': len(right_methods)
        }

    return changes


def diff_imports(left_imports: List[Dict],
                 right_imports: List[Dict]) -> tuple[Dict[str, int], List[Dict]]:
    """Compare import lists and return summary counts + details.

    Args:
        left_imports: List of imports from left structure
        right_imports: List of imports from right structure

    Returns:
        Tuple of (summary_dict, details_list)
    """
    # Normalize imports for comparison (use content field)
    left_contents = {imp.get('content', ''): imp for imp in left_imports}
    right_contents = {imp.get('content', ''): imp for imp in right_imports}

    added_contents = right_contents.keys() - left_contents.keys()
    removed_contents = left_contents.keys() - right_contents.keys()

    details = []

    # Added imports
    for content in sorted(added_contents):
        imp = right_contents[content]
        details.append({
            'type': 'added',
            'content': content,
            'line': imp.get('line')
        })

    # Removed imports
    for content in sorted(removed_contents):
        imp = left_contents[content]
        details.append({
            'type': 'removed',
            'content': content,
            'line': imp.get('line')
        })

    summary = {
        'added': len(added_contents),
        'removed': len(removed_contents)
    }

    return summary, details


def _compute_element_changes(left: Dict, right: Dict) -> Dict[str, Any]:
    """Compute changes for a generic element.

    Args:
        left: Left element dict
        right: Right element dict

    Returns:
        Dict of changes
    """
    changes = {}

    # Compare all keys
    all_keys = set(left.keys()) | set(right.keys())

    for key in all_keys:
        left_val = left.get(key)
        right_val = right.get(key)

        if left_val != right_val:
            changes[key] = {
                'old': left_val,
                'new': right_val
            }

    return changes
