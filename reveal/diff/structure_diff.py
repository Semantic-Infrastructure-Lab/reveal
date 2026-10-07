"""Core diff algorithm for comparing reveal structures."""

from typing import Any, Callable, Dict, List, Optional, Tuple

# Fields that say where an element is, not what it is: an element pushed down the file by
# an edit above it has moved, not changed. 'file' is part of an element's identity instead.
_POSITION_FIELDS = frozenset({'line', 'line_end', 'line_start', 'file'})


def element_categories(struct: Dict[str, Any]) -> List[str]:
    """The element categories of an analyzer's structure, in the order it emits them.

    A category is any list-valued key: functions, classes, imports, and whatever else the
    analyzer extracts (interfaces, structs, enums, types, namespaces, variables, ...). This
    is the one place that decides it, so a new category is compared without a new list
    (BACK-1732). Scalars and dicts are not elements: an envelope's type, source and meta,
    a batch file's stats, a ``_has_errors`` flag.
    """
    return [key for key, value in struct.items() if isinstance(value, list)]


def compute_structure_diff(left: Dict[str, Any],
                          right: Dict[str, Any]) -> Dict[str, Any]:
    """Compute semantic diff between two structures.

    Functions, classes and imports have comparisons of their own and are always in the
    summary. Every other category either side has (``element_categories``) is compared by
    element name (``diff_named_elements``). A category whose items carry no name cannot be
    matched item by item; if the two sides differ there it is listed in ``not_compared``
    for the caller to disclose, never dropped (BACK-1732).

    Args:
        left: Structure from left URI
        right: Structure from right URI

    Returns:
        {
            'summary': {
                'functions': {'added': N, 'removed': M, 'modified': K},
                'classes': {...},
                'imports': {...},
                'interfaces': {...},   # any other category either side has
            },
            'details': {
                'functions': [
                    {'type': 'added', 'name': 'foo', 'line': 42, ...},
                    {'type': 'removed', 'name': 'bar', ...},
                    {'type': 'modified', 'name': 'baz', 'changes': {...}}
                ],
                ...
            },
            'not_compared': ['widgets'],  # differing categories with unnamed items
        }
    """
    # Handle both nested and flat structure formats
    # Some adapters return {'structure': {...}}, others return {...} directly
    left_struct = left.get('structure', left)
    right_struct = right.get('structure', right)

    summary: Dict[str, Dict[str, int]] = {}
    details: Dict[str, List[Dict]] = {}
    not_compared: List[str] = []
    for category, differ in _OWN_COMPARISONS.items():
        summary[category], details[category] = differ(
            _items(left_struct, category), _items(right_struct, category))

    categories = element_categories(left_struct) + element_categories(right_struct)
    for category in dict.fromkeys(categories):
        if category in _OWN_COMPARISONS:
            continue
        left_items, right_items = _items(left_struct, category), _items(right_struct, category)
        if _is_named(left_items) and _is_named(right_items):
            summary[category], details[category] = diff_named_elements(left_items, right_items)
        elif left_items != right_items:
            not_compared.append(category)

    return {'summary': summary, 'details': details, 'not_compared': not_compared}


def _items(struct: Dict[str, Any], category: str) -> List[Any]:
    value = struct.get(category)
    return value if isinstance(value, list) else []


def _is_named(items: List[Any]) -> bool:
    return all(isinstance(item, dict) and isinstance(item.get('name'), str) for item in items)


def _shape(value: Any) -> Any:
    """``value`` without position fields, at any depth: what an element is, not where."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items() if k not in _POSITION_FIELDS}
    if isinstance(value, list):
        return [_shape(v) for v in value]
    return value


def diff_named_elements(left_items: List[Dict],
                        right_items: List[Dict]) -> Tuple[Dict[str, int], List[Dict]]:
    """Compare a category that has no comparison of its own (interfaces, structs, enums,
    types, ...) by element name.

    An element is keyed by (file, name, n): the n-th element of that name, so a second
    element sharing a name (a variable assigned twice) is an addition, not a collision.
    A pair is modified when any field other than its position differs (BACK-1732).

    Returns:
        Tuple of (summary_dict, details_list)
    """
    def keyed(items: List[Dict]) -> Dict[Tuple[Any, str, int], Dict]:
        seen: Dict[Tuple[Any, str], int] = {}
        out = {}
        for item in items:
            ident = (item.get('file'), item['name'])
            seen[ident] = seen.get(ident, 0) + 1
            out[ident + (seen[ident],)] = item
        return out

    def order(key: Tuple[Any, str, int]) -> Tuple[str, str, int]:
        return (key[1], key[0] or '', key[2])

    left_keyed, right_keyed = keyed(left_items), keyed(right_items)
    details: List[Dict] = []
    for change, keys, side in (('added', right_keyed.keys() - left_keyed.keys(), right_keyed),
                               ('removed', left_keyed.keys() - right_keyed.keys(), left_keyed)):
        for key in sorted(keys, key=order):
            details.append({'type': change, 'name': key[1], 'line': side[key].get('line')})

    modified = 0
    for key in sorted(left_keyed.keys() & right_keyed.keys(), key=order):
        old, new = _shape(left_keyed[key]), _shape(right_keyed[key])
        changes = {field: {'old': old.get(field), 'new': new.get(field)}
                   for field in sorted(old.keys() | new.keys())
                   if old.get(field) != new.get(field)}
        if changes:
            modified += 1
            details.append({'type': 'modified', 'name': key[1],
                            'line': right_keyed[key].get('line'), 'changes': changes})

    summary = {'added': len(right_keyed.keys() - left_keyed.keys()),
               'removed': len(left_keyed.keys() - right_keyed.keys()),
               'modified': modified}
    return summary, details


def compute_element_diff(left_elem: Optional[Dict[str, Any]],
                        right_elem: Optional[Dict[str, Any]],
                        element_name: str) -> Dict[str, Any]:
    """Compute diff for a specific element.

    Args:
        left_elem: Element from left structure (or None if not found)
        right_elem: Element from right structure (or None if not found)
        element_name: Name of the element

    Returns:
        Detailed diff for the element: ``type`` is always ``diff_element`` (the
        result type), ``change`` is the verdict (added, removed, unchanged, modified).

    Raises:
        ValueError: neither side has the element. That is a failed lookup, not a
            verdict; the diff adapter answers it before calling this (BACK-1639).
    """
    if left_elem is None and right_elem is None:
        raise ValueError(f"Element '{element_name}' not found in either resource")

    if left_elem is None:
        return {
            'type': 'diff_element',
            'change': 'added',
            'name': element_name,
            'element': right_elem
        }

    if right_elem is None:
        return {
            'type': 'diff_element',
            'change': 'removed',
            'name': element_name,
            'element': left_elem
        }

    # Both exist - check if modified
    changes = _compute_element_changes(left_elem, right_elem)

    if not changes:
        return {
            'type': 'diff_element',
            'change': 'unchanged',
            'name': element_name,
            'message': f"Element '{element_name}' is identical in both resources"
        }

    return {
        'type': 'diff_element',
            'change': 'modified',
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
    # Key by (file, name), not name alone — otherwise unrelated functions that
    # happen to share a name in different files (common across a directory
    # diff) get matched as "modified" instead of removed+added.
    left_names = {(f.get('file'), f['name']): f for f in left_funcs}
    right_names = {(f.get('file'), f['name']): f for f in right_funcs}

    added_names = right_names.keys() - left_names.keys()
    removed_names = left_names.keys() - right_names.keys()
    common_names = left_names.keys() & right_names.keys()

    # Build detailed diff list
    details = []

    # Added functions
    for key in sorted(added_names, key=lambda k: (k[1], k[0] or '')):
        name = key[1]
        func = right_names[key]
        cx_after = func.get('complexity')
        details.append({
            'type': 'added',
            'name': name,
            'line': func.get('line'),
            'signature': func.get('signature'),
            'complexity': func.get('complexity'),
            'line_count': func.get('line_count'),
            'complexity_before': None,
            'complexity_after': cx_after,
            'complexity_delta': cx_after,
        })

    # Removed functions
    for key in sorted(removed_names, key=lambda k: (k[1], k[0] or '')):
        name = key[1]
        func = left_names[key]
        cx_before = func.get('complexity')
        details.append({
            'type': 'removed',
            'name': name,
            'line': func.get('line'),
            'signature': func.get('signature'),
            'complexity': func.get('complexity'),
            'line_count': func.get('line_count'),
            'complexity_before': cx_before,
            'complexity_after': None,
            'complexity_delta': -cx_before if cx_before is not None else None,
        })

    # Modified functions
    modified_count = 0
    for key in sorted(common_names, key=lambda k: (k[1], k[0] or '')):
        name = key[1]
        left_func = left_names[key]
        right_func = right_names[key]

        if function_changed(left_func, right_func):
            modified_count += 1
            changes = _compute_function_changes(left_func, right_func)
            cx_before = left_func.get('complexity', 0)
            cx_after = right_func.get('complexity', 0)
            details.append({
                'type': 'modified',
                'name': name,
                'changes': changes,
                'left': left_func,
                'right': right_func,
                'complexity_before': cx_before,
                'complexity_after': cx_after,
                'complexity_delta': cx_after - cx_before,
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
    # Key by (file, name), not name alone — see diff_functions for why.
    left_names = {(c.get('file'), c['name']): c for c in left_classes}
    right_names = {(c.get('file'), c['name']): c for c in right_classes}

    added_names = right_names.keys() - left_names.keys()
    removed_names = left_names.keys() - right_names.keys()
    common_names = left_names.keys() & right_names.keys()

    details = []

    # Added classes
    for key in sorted(added_names, key=lambda k: (k[1], k[0] or '')):
        name = key[1]
        cls = right_names[key]
        details.append({
            'type': 'added',
            'name': name,
            'line': cls.get('line'),
            'bases': cls.get('bases', []),
            'method_count': len(cls.get('methods', []))
        })

    # Removed classes
    for key in sorted(removed_names, key=lambda k: (k[1], k[0] or '')):
        name = key[1]
        cls = left_names[key]
        details.append({
            'type': 'removed',
            'name': name,
            'line': cls.get('line'),
            'bases': cls.get('bases', []),
            'method_count': len(cls.get('methods', []))
        })

    # Modified classes
    modified_count = 0
    for key in sorted(common_names, key=lambda k: (k[1], k[0] or '')):
        name = key[1]
        left_cls = left_names[key]
        right_cls = right_names[key]

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


# The categories with a comparison of their own, always in the summary, in this order.
_OWN_COMPARISONS: Dict[str, Callable[[List[Dict], List[Dict]], Tuple[Dict[str, int], List[Dict]]]] = {
    'functions': diff_functions,
    'classes': diff_classes,
    'imports': diff_imports,
}


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
