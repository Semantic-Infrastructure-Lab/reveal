"""Type evidence collector for ast://...?reveal_type=<var>.

For each file at path, finds every place var_name appears as:
  - A function parameter (with annotation if present)
  - An assignment LHS (with RHS shape inferred from literal/call)
  - A for-loop target variable

Returns a list of evidence dicts:
  {
      'file': str,
      'function': str,      # enclosing function name, '' for module level
      'func_line': int,     # line of the function definition (0 for module level)
      'line': int,          # line of the evidence
      'kind': 'param' | 'assign' | 'for',
      'annotation': str,    # type annotation if present, else ''
      'shape': str,         # inferred RHS shape (for assign), else ''
  }
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ...core import suppress_treesitter_warnings  # noqa: F401 — called at scan time


# ─────────────────────────── public entry point ──────────────────────────────

def collect_type_evidence(path: str, var_name: str) -> List[Dict[str, Any]]:
    """Collect all type evidence for var_name at path (file or directory)."""
    path_obj = Path(path)
    evidence: List[Dict[str, Any]] = []

    _SKIP_DIRS = {
        '.git', '__pycache__', 'node_modules', '.tox', '.venv', 'venv',
        '.mypy_cache', '.pytest_cache', 'dist', 'build', '.eggs',
    }

    if path_obj.is_file():
        _scan_file(str(path_obj), var_name, evidence)
    elif path_obj.is_dir():
        for root, dirs, files in os.walk(str(path_obj)):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.endswith('.egg-info')]
            for name in files:
                fp = str(Path(root) / name)
                if _is_python_file(fp):
                    _scan_file(fp, var_name, evidence)

    return evidence


# ─────────────────────────── file scanner ────────────────────────────────────

def _is_python_file(path: str) -> bool:
    return path.endswith('.py') or path.endswith('.pyi')


def _scan_file(file_path: str, var_name: str, evidence: List[Dict[str, Any]]) -> None:
    from ...registry import get_analyzer
    suppress_treesitter_warnings()
    try:
        analyzer_class = get_analyzer(file_path)
        if not analyzer_class:
            return
        analyzer = analyzer_class(file_path)
        if not hasattr(analyzer, 'tree') or not analyzer.tree:
            return
        get_text: Callable = analyzer._get_node_text
        root = analyzer.tree.root_node
        _walk(root, var_name, get_text, file_path, evidence, func_stack=[])
    except Exception:  # noqa: BLE001
        pass


# ─────────────────────────── tree walker ─────────────────────────────────────

def _walk(
    node: Any,
    var_name: str,
    get_text: Callable,
    file_path: str,
    evidence: List[Dict[str, Any]],
    func_stack: List[str],
) -> None:
    ntype = node.type

    if ntype in ('function_definition', 'async_function_definition'):
        name_node = node.child_by_field_name('name')
        func_name = get_text(name_node) if name_node else '?'
        func_line = node.start_point[0] + 1

        params_node = node.child_by_field_name('parameters')
        if params_node:
            _check_parameters(params_node, var_name, get_text, file_path,
                               func_name, func_line, evidence)

        # Walk body with this function on the stack
        func_stack.append(func_name)
        body = node.child_by_field_name('body')
        if body:
            for child in body.children:
                _walk(child, var_name, get_text, file_path, evidence, func_stack)
        func_stack.pop()
        return  # body already walked above

    elif ntype in ('assignment', 'augmented_assignment'):
        _check_assignment(node, var_name, get_text, file_path, func_stack, evidence)

    elif ntype == 'named_expression':
        # walrus operator: name := value
        name_node = node.child_by_field_name('name')
        if name_node and get_text(name_node) == var_name:
            value_node = node.child_by_field_name('value')
            _add_assign(node, var_name, get_text, file_path, func_stack, evidence,
                        value_node=value_node)

    elif ntype in ('for_statement', 'foreach_statement'):
        _check_for(node, var_name, get_text, file_path, func_stack, evidence)
        # Still walk the body
        body = node.child_by_field_name('body')
        if body:
            for child in body.children:
                _walk(child, var_name, get_text, file_path, evidence, func_stack)
        return

    # Generic recursion for all other nodes
    for child in node.children:
        _walk(child, var_name, get_text, file_path, evidence, func_stack)


# ─────────────────────────── parameter checking ──────────────────────────────

def _check_parameters(
    params_node: Any,
    var_name: str,
    get_text: Callable,
    file_path: str,
    func_name: str,
    func_line: int,
    evidence: List[Dict[str, Any]],
) -> None:
    for child in params_node.children:
        ctype = child.type
        if ctype == 'identifier':
            if get_text(child) == var_name:
                evidence.append({
                    'file': file_path,
                    'function': func_name,
                    'func_line': func_line,
                    'line': child.start_point[0] + 1,
                    'kind': 'param',
                    'annotation': '',
                    'shape': '',
                })
        elif ctype in ('typed_parameter', 'typed_default_parameter'):
            ident = _first_identifier(child, get_text)
            if ident and ident[0] == var_name:
                annotation = _extract_annotation(child, get_text)
                evidence.append({
                    'file': file_path,
                    'function': func_name,
                    'func_line': func_line,
                    'line': child.start_point[0] + 1,
                    'kind': 'param',
                    'annotation': annotation,
                    'shape': '',
                })
        elif ctype == 'default_parameter':
            ident = child.child_by_field_name('name')
            if ident and get_text(ident) == var_name:
                evidence.append({
                    'file': file_path,
                    'function': func_name,
                    'func_line': func_line,
                    'line': child.start_point[0] + 1,
                    'kind': 'param',
                    'annotation': '',
                    'shape': '',
                })


def _first_identifier(node: Any, get_text: Callable) -> Optional[tuple]:
    """Return (name, node) of the first identifier child, or None."""
    for child in node.children:
        if child.type == 'identifier':
            return (get_text(child), child)
    return None


def _extract_annotation(typed_node: Any, get_text: Callable) -> str:
    """Extract annotation text from typed_parameter or typed_default_parameter."""
    # typed_parameter: identifier ":" type
    # Children: identifier, ":", type_node
    found_colon = False
    for child in typed_node.children:
        if child.type == ':':
            found_colon = True
        elif found_colon and child.type not in ('=', 'comment'):
            return get_text(child).strip()
    return ''


# ─────────────────────────── assignment checking ─────────────────────────────

def _check_assignment(
    node: Any,
    var_name: str,
    get_text: Callable,
    file_path: str,
    func_stack: List[str],
    evidence: List[Dict[str, Any]],
) -> None:
    left = node.child_by_field_name('left')
    if left is None:
        return

    # Check if LHS is the var or a pattern containing the var
    matched = _lhs_contains_var(left, var_name, get_text)
    if not matched:
        return

    right = node.child_by_field_name('right')
    _add_assign(node, var_name, get_text, file_path, func_stack, evidence, value_node=right)


def _lhs_contains_var(node: Any, var_name: str, get_text: Callable) -> bool:
    if node.type == 'identifier' and get_text(node) == var_name:
        return True
    # tuple/list unpacking: a, b = ...
    for child in node.children:
        if _lhs_contains_var(child, var_name, get_text):
            return True
    return False


def _add_assign(
    node: Any,
    var_name: str,
    get_text: Callable,
    file_path: str,
    func_stack: List[str],
    evidence: List[Dict[str, Any]],
    value_node: Optional[Any],
) -> None:
    # Check for inline type annotation: var: type = value
    annotation = ''
    type_node = node.child_by_field_name('type')
    if type_node:
        annotation = get_text(type_node).strip()

    shape = _infer_shape(value_node, get_text) if value_node else ''
    evidence.append({
        'file': file_path,
        'function': func_stack[-1] if func_stack else '',
        'func_line': 0,
        'line': node.start_point[0] + 1,
        'kind': 'assign',
        'annotation': annotation,
        'shape': shape,
    })


# ─────────────────────────── for-loop checking ───────────────────────────────

def _check_for(
    node: Any,
    var_name: str,
    get_text: Callable,
    file_path: str,
    func_stack: List[str],
    evidence: List[Dict[str, Any]],
) -> None:
    left = node.child_by_field_name('left')
    if left is None:
        return
    if not _lhs_contains_var(left, var_name, get_text):
        return

    right = node.child_by_field_name('right')
    shape = ''
    if right:
        iterable_shape = _infer_shape(right, get_text)
        shape = f'item from {iterable_shape}' if iterable_shape else 'loop variable'

    evidence.append({
        'file': file_path,
        'function': func_stack[-1] if func_stack else '',
        'func_line': 0,
        'line': node.start_point[0] + 1,
        'kind': 'for',
        'annotation': '',
        'shape': shape,
    })


# ─────────────────────────── RHS shape inference ─────────────────────────────

def _infer_shape(node: Any, get_text: Callable) -> str:
    if node is None:
        return ''
    ntype = node.type

    if ntype == 'dictionary':
        keys = []
        for child in node.children:
            if child.type == 'pair':
                key_node = child.child_by_field_name('key')
                if key_node:
                    k = get_text(key_node).strip('"\'')
                    if len(k) <= 30:
                        keys.append(k)
        if keys:
            key_str = ', '.join(keys[:6])
            suffix = ', …' if len(keys) > 6 else ''
            return f'dict literal {{{key_str}{suffix}}}'
        return 'dict literal {}'

    elif ntype == 'list':
        return 'list literal'

    elif ntype == 'tuple':
        return 'tuple literal'

    elif ntype == 'set':
        return 'set literal'

    elif ntype == 'call':
        func_node = node.child_by_field_name('function')
        if func_node:
            name = get_text(func_node)
            return f'return of {name}()'
        return 'return of call()'

    elif ntype == 'identifier':
        return f'from {get_text(node)}'

    elif ntype == 'attribute':
        return f'from {get_text(node)}'

    elif ntype == 'subscript':
        return f'from subscript'

    elif ntype in ('none', 'true', 'false', 'integer', 'float', 'string'):
        return f'{ntype} literal'

    elif ntype == 'conditional_expression':
        return 'conditional expression'

    elif ntype == 'await':
        inner = node.children[-1] if node.children else None
        inner_shape = _infer_shape(inner, get_text) if inner else ''
        return f'await {inner_shape}' if inner_shape else 'await expression'

    return get_text(node)[:40] if len(get_text(node)) <= 40 else get_text(node)[:37] + '…'


# ─────────────────────────── renderer ────────────────────────────────────────

def render_type_evidence(
    var_name: str,
    evidence: List[Dict[str, Any]],
    path: str,
) -> str:
    if not evidence:
        return f"reveal_type({var_name}): no occurrences found in {path}"

    lines = [f"reveal_type({var_name})  —  {path}", '']

    # Group by file
    by_file: Dict[str, List[Dict]] = {}
    for ev in evidence:
        fp = ev['file']
        by_file.setdefault(fp, []).append(ev)

    for fp, items in sorted(by_file.items()):
        if len(by_file) > 1:
            lines.append(f"  {fp}")

        for ev in sorted(items, key=lambda e: e['line']):
            kind = ev['kind']
            line = ev['line']
            func = ev['function']
            annotation = ev['annotation']
            shape = ev['shape']

            if kind == 'param':
                loc = f"L{line}  PARAM    {func}({var_name}: {annotation or '?'})"
                if annotation:
                    detail = f"annotated: {annotation}"
                else:
                    detail = 'unannotated'
                lines.append(f"    {loc:<50}  {detail}")

            elif kind == 'assign':
                context = f"in {func}" if func else 'module level'
                loc = f"L{line}  ASSIGN   {var_name} = ...  ({context})"
                detail_parts = []
                if annotation:
                    detail_parts.append(f"annotated: {annotation}")
                if shape:
                    detail_parts.append(shape)
                detail = ',  '.join(detail_parts) if detail_parts else 'unresolved'
                lines.append(f"    {loc:<50}  {detail}")

            elif kind == 'for':
                context = f"in {func}" if func else 'module level'
                loc = f"L{line}  FOR      for {var_name} in ...  ({context})"
                lines.append(f"    {loc:<50}  {shape or 'loop variable'}")

        if len(by_file) > 1:
            lines.append('')

    return '\n'.join(lines)
