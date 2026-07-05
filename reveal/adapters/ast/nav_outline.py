"""Outline and scope-chain navigation: element_outline, scope_chain, renderers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List
from ...core import node_children as _children
from ...core import node_prev_sibling as _prev_sibling
from .node_taxonomy import (  # noqa: F401 — re-exported for nav.py/back-compat
    SCOPE_NODES,
    ALTERNATIVE_NODES,
    FUNCTION_TYPES,
    EXIT_NODES,
    GATE_NODES,
    KEYWORD_LABEL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_label(node: Any, get_text: Callable) -> str:
    """Return 'KEYWORD  condition_text' for a scope or exit node."""
    keyword = KEYWORD_LABEL.get(node.kind(), node.kind().upper())
    first_line = get_text(node).splitlines()[0].strip().rstrip(':').rstrip('{').strip()
    lower = first_line.lower()
    kw_lower = keyword.lower()
    if lower.startswith(kw_lower):
        condition = first_line[len(kw_lower):].strip()
    else:
        condition = first_line
    if len(condition) > 80:
        condition = condition[:77] + '...'
    if condition:
        return f'{keyword}  {condition}'
    return keyword


def _make_item(
    node: Any,
    depth: int,
    get_text: Callable,
    is_exit: bool = False,
) -> Dict[str, Any]:
    return {
        'type': node.kind(),
        'keyword': KEYWORD_LABEL.get(node.kind(), node.kind().upper()),
        'label': _node_label(node, get_text),
        'line_start': node.start_position().row + 1,
        'line_end': node.end_position().row + 1,
        'depth': depth,
        'is_exit': is_exit,
    }


# ---------------------------------------------------------------------------
# Feature 1: element_outline
# ---------------------------------------------------------------------------

def element_outline(
    func_node: Any,
    get_text: Callable,
    max_depth: int = 3,
) -> List[Dict[str, Any]]:
    """Return a flat list of outline items for a function's control-flow skeleton."""
    items: List[Dict[str, Any]] = []
    _collect_outline(func_node, depth=1, items=items, get_text=get_text, max_depth=max_depth)
    return items


def _collect_outline(
    node: Any,
    depth: int,
    items: List[Dict[str, Any]],
    get_text: Callable,
    max_depth: int,
) -> None:
    """Walk node's children, appending scope/exit items at the given depth."""
    for child in _children(node):
        ctype = child.kind()
        if not child.is_named():
            continue
        if ctype in FUNCTION_TYPES:
            items.append(_make_item(child, depth, get_text))
            if depth < max_depth:
                _collect_scope_interior(child, depth, items, get_text, max_depth)
            continue
        if ctype in ALTERNATIVE_NODES:
            items.append(_make_item(child, depth, get_text))
            if depth < max_depth:
                _collect_outline(child, depth + 1, items, get_text, max_depth)
        elif ctype in SCOPE_NODES:
            items.append(_make_item(child, depth, get_text))
            if depth < max_depth:
                _collect_scope_interior(child, depth, items, get_text, max_depth)
        elif ctype in EXIT_NODES:
            items.append(_make_item(child, depth, get_text, is_exit=True))
        else:
            if depth <= max_depth:
                _collect_outline(child, depth, items, get_text, max_depth)


def _collect_scope_interior(
    scope_node: Any,
    scope_depth: int,
    items: List[Dict[str, Any]],
    get_text: Callable,
    max_depth: int,
) -> None:
    """Process the interior of a scope node."""
    for child in _children(scope_node):
        ctype = child.kind()
        if not child.is_named():
            continue
        if ctype in FUNCTION_TYPES:
            items.append(_make_item(child, scope_depth + 1, get_text))
            if scope_depth + 1 < max_depth:
                _collect_scope_interior(child, scope_depth + 1, items, get_text, max_depth)
            continue
        if ctype in ALTERNATIVE_NODES:
            items.append(_make_item(child, scope_depth, get_text))
            if scope_depth < max_depth:
                _collect_outline(child, scope_depth + 1, items, get_text, max_depth)
        elif ctype in SCOPE_NODES:
            items.append(_make_item(child, scope_depth + 1, get_text))
            if scope_depth + 1 < max_depth:
                _collect_scope_interior(child, scope_depth + 1, items, get_text, max_depth)
        elif ctype in EXIT_NODES:
            items.append(_make_item(child, scope_depth + 1, get_text, is_exit=True))
        else:
            if scope_depth < max_depth:
                _collect_outline(child, scope_depth + 1, items, get_text, max_depth)


# ---------------------------------------------------------------------------
# Feature 2: scope_chain
# ---------------------------------------------------------------------------

def scope_chain(
    root_node: Any,
    line_no: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Return the ancestor scope chain for a specific line (outermost first)."""
    chain: List[Dict[str, Any]] = []
    _find_ancestors(root_node, line_no, get_text, chain, depth=0)
    return chain


def _dart_signature_for_body(body_node: Any) -> Any:
    """Return the `function_signature` node paired with a Dart `function_body`.

    BACK-463: Dart's grammar makes `function_signature` (name + params) and
    `function_body` DISJOINT siblings, not parent/child — so the enclosing
    function's *name* lives in a node that does NOT contain the body's lines.
    `_find_ancestors`' containment walk therefore never visits the signature
    for any line inside the body, silently dropping the DEF from `--scope`'s
    ancestor chain (the IF-but-no-DEF symptom). This resolves the signature
    from the body — the inverse of `treesitter.py:_function_end_node`, which
    resolves the body from the signature for line-range purposes.

    Two shapes (both confirmed via --show-ast):
      top-level:  program → function_signature, function_body        (siblings)
      method:     class_body → method_signature(function_signature), function_body
    """
    prev = _prev_sibling(body_node)
    if prev is None:
        return None
    if prev.kind() == 'function_signature':
        return prev
    if prev.kind() == 'method_signature':
        for child in _children(prev):
            if child.kind() == 'function_signature':
                return child
    return None


def _find_ancestors(
    node: Any,
    line_no: int,
    get_text: Callable,
    chain: List[Dict[str, Any]],
    depth: int,
) -> None:
    """Recursively find scope nodes that contain line_no."""
    start = node.start_position().row + 1
    end = node.end_position().row + 1
    if not (start <= line_no <= end):
        return

    # BACK-463: Dart's function_body is the node that contains the body's
    # lines, but it isn't itself a DEF node — the name lives in a disjoint
    # sibling signature. Synthesize the DEF entry from that signature, spanning
    # signature-start → body-end, before descending into the body's scopes.
    if node.kind() == 'function_body':
        sig = _dart_signature_for_body(node)
        # Only synthesize when the line is purely inside the body. If it falls
        # on the signature itself, the normal DEF_NODES walk already visits
        # function_signature (a sibling subtree) and adds the DEF — synthesizing
        # too would double it.
        if sig is not None and not (
            sig.start_position().row + 1 <= line_no <= sig.end_position().row + 1
        ):
            chain.append({
                'type': 'function_signature',
                'keyword': KEYWORD_LABEL.get('function_signature', 'DEF'),
                'label': _node_label(sig, get_text),
                'line_start': sig.start_position().row + 1,
                'line_end': end,
                'depth': depth,
                'condition': None,
            })
            depth += 1

    if node.is_named() and (node.kind() in SCOPE_NODES or node.kind() in FUNCTION_TYPES):
        condition = None
        if node.kind() in GATE_NODES:
            from .nav_exits import _get_condition  # noqa: PLC0415 — avoid import-time cost for non-JSON callers
            cond = _get_condition(node, get_text)
            condition = cond['text'] if cond else None
        chain.append({
            'type': node.kind(),
            'keyword': KEYWORD_LABEL.get(node.kind(), node.kind().upper()),
            'label': _node_label(node, get_text),
            'line_start': start,
            'line_end': end,
            'depth': depth,
            'condition': condition,
        })
        depth += 1

    for child in _children(node):
        _find_ancestors(child, line_no, get_text, chain, depth)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_outline(
    func_name: str,
    func_start: int,
    func_end: int,
    items: List[Dict[str, Any]],
    depth: int = 3,
) -> str:
    """Render an element_outline result as text."""
    lines = [f'DEF {func_name}  L{func_start}→L{func_end}']
    for item in items:
        if item['depth'] > depth:
            continue
        indent = '  ' * item['depth']
        lrange = f'L{item["line_start"]}→L{item["line_end"]}' if item['line_start'] != item['line_end'] else f'L{item["line_start"]}'
        lines.append(f'{indent}{item["label"]}  {lrange}')
    return '\n'.join(lines)


def render_scope_chain(line_no: int, chain: List[Dict[str, Any]], line_text: str = '') -> str:
    """Render a scope_chain result as text."""
    if not chain:
        suffix = f': {line_text}' if line_text else ' is at module/function top level (no enclosing scope blocks)'
        return f'▶ L{line_no}{suffix}'

    MAX_CHAIN = 8
    lines = []
    truncated = len(chain) > MAX_CHAIN
    if truncated:
        hidden = len(chain) - MAX_CHAIN
        outer = chain[:2]
        inner = chain[-(MAX_CHAIN - 2):]
        for item in outer:
            indent = '  ' * item['depth']
            lrange = f'L{item["line_start"]}→L{item["line_end"]}'
            lines.append(f'{indent}{item["keyword"]:<8}{lrange:<16}{item["label"]}')
        lines.append(f'  ... ({hidden} more levels)')
        for item in inner:
            indent = '  ' * item['depth']
            lrange = f'L{item["line_start"]}→L{item["line_end"]}'
            lines.append(f'{indent}{item["keyword"]:<8}{lrange:<16}{item["label"]}')
    else:
        for item in chain:
            indent = '  ' * item['depth']
            lrange = f'L{item["line_start"]}→L{item["line_end"]}'
            lines.append(f'{indent}{item["keyword"]:<8}{lrange:<16}{item["label"]}')

    innermost_depth = chain[-1]['depth'] + 1
    indent = '  ' * innermost_depth
    lines.append('')
    if line_text:
        lines.append(f'{indent}▶ L{line_no}: {line_text}')
    else:
        lines.append(f'{indent}▶ L{line_no} is here')
    return '\n'.join(lines)


def render_branchmap(
    items: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render filtered element_outline items as a branch/exception map."""
    if not items:
        return f'No branch nodes found in L{from_line}→L{to_line}'
    lines: List[str] = []
    for item in items:
        indent = '  ' * item['depth']
        if item['line_start'] != item['line_end']:
            lrange = f'L{item["line_start"]}→L{item["line_end"]}'
        else:
            lrange = f'L{item["line_start"]}'
        lines.append(f'{indent}{item["label"]}  {lrange}')
    return '\n'.join(lines)
