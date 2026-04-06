"""Sub-function progressive disclosure — navigation inside large functions.

Four functions that close the gap between "here's the function signature" and
"here are all 200 lines":

  element_outline()  -- control-flow skeleton (top-down map of a function)
  scope_chain()      -- ancestor scope chain for a specific line (bottom-up)
  var_flow()         -- variable read/write trace within a function
  range_calls()      -- call sites within a specific line range

All functions are pure: they take tree-sitter node objects and a callable
``get_text(node) -> str``. No I/O, no side effects — callers handle rendering.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Node type constants
# ---------------------------------------------------------------------------

# Scope-forming control-flow nodes (create new nesting depth).
# Excludes function/class definitions — those are top-level elements already.
SCOPE_NODES: frozenset = frozenset({
    # Python
    'if_statement', 'for_statement', 'while_statement',
    'try_statement', 'with_statement',
    'match_statement', 'case_clause',
    # Python alternatives — also in ALTERNATIVE_NODES; included here so
    # _find_ancestors captures elif/except/finally in scope chains.
    'elif_clause', 'else_clause', 'except_clause', 'finally_clause',
    # JS / TS / Go / C++ / Java
    'do_statement', 'switch_statement',
    'catch_clause',
    # Generic
    'if', 'for', 'while', 'try', 'switch',
})

# Alternative-branch nodes: shown at the SAME visual depth as their parent
# scope (else is parallel to if, except is parallel to try).
ALTERNATIVE_NODES: frozenset = frozenset({
    'elif_clause', 'else_clause',
    'except_clause', 'finally_clause',
    'else', 'catch_clause', 'catch', 'finally',
    'switch_default', 'default',
})

# Function/class definitions inside a function body — skip these so they
# appear in the top-level element list rather than inside the outline.
FUNCTION_TYPES: frozenset = frozenset({
    'function_definition', 'function_declaration', 'function_item',
    'method_definition', 'method_declaration', 'function',
    'class_definition', 'class_declaration', 'class',
    'arrow_function', 'lambda',
})

# Exit/return nodes worth showing in the outline.
EXIT_NODES: frozenset = frozenset({
    'return_statement', 'raise_statement', 'yield_statement',
    'return', 'raise', 'throw_statement', 'yield',
    'break_statement', 'continue_statement',
})

# Human-readable keyword labels for node types.
KEYWORD_LABEL: Dict[str, str] = {
    'if_statement': 'IF', 'if': 'IF',
    'elif_clause': 'ELIF',
    'else_clause': 'ELSE', 'else': 'ELSE',
    'for_statement': 'FOR', 'for': 'FOR',
    'while_statement': 'WHILE', 'while': 'WHILE',
    'try_statement': 'TRY', 'try': 'TRY',
    'except_clause': 'EXCEPT',
    'finally_clause': 'FINALLY', 'finally': 'FINALLY',
    'with_statement': 'WITH', 'with': 'WITH',
    'match_statement': 'MATCH',
    'case_clause': 'CASE',
    'do_statement': 'DO',
    'switch_statement': 'SWITCH', 'switch': 'SWITCH',
    'catch_clause': 'CATCH', 'catch': 'CATCH',
    'switch_case': 'CASE',
    'switch_default': 'DEFAULT', 'default': 'DEFAULT',
    # Exit nodes
    'return_statement': 'RETURN', 'return': 'RETURN',
    'raise_statement': 'RAISE', 'raise': 'RAISE',
    'throw_statement': 'THROW',
    'yield_statement': 'YIELD', 'yield': 'YIELD',
    'break_statement': 'BREAK', 'break': 'BREAK',
    'continue_statement': 'CONTINUE', 'continue': 'CONTINUE',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_label(node: Any, get_text: Callable) -> str:
    """Return 'KEYWORD  condition_text' for a scope or exit node.

    The keyword comes from KEYWORD_LABEL; everything after the keyword on
    the first source line is the condition text.
    """
    keyword = KEYWORD_LABEL.get(node.type, node.type.upper())
    first_line = get_text(node).splitlines()[0].strip().rstrip(':').rstrip('{').strip()
    # Strip the leading keyword (case-insensitive) to get just the condition
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


# ---------------------------------------------------------------------------
# Feature 1: element_outline
# ---------------------------------------------------------------------------

def element_outline(
    func_node: Any,
    get_text: Callable,
    max_depth: int = 3,
) -> List[Dict[str, Any]]:
    """Return a flat list of outline items for a function's control-flow skeleton.

    Each item is a dict:
        type       -- tree-sitter node type string
        keyword    -- uppercase label (IF, FOR, TRY, ...)
        label      -- 'KEYWORD  condition_text'
        line_start -- 1-indexed start line
        line_end   -- 1-indexed end line
        depth      -- nesting depth (1 = top-level inside the function body)
        is_exit    -- True for return/raise/yield nodes

    Args:
        func_node: Tree-sitter node for the function definition.
        get_text:  Callable(node) -> str returning node source text.
        max_depth: Maximum nesting depth to descend (default 3).

    Returns:
        Flat list of outline items in document order.
    """
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
    for child in node.children:
        ctype = child.type
        # Skip anonymous leaf tokens (keyword tokens like 'for', 'if', 'else'
        # that appear inside compound statements).  Named nodes are compound.
        if not child.is_named:
            continue
        if ctype in FUNCTION_TYPES:
            continue  # skip nested function/class definitions
        if ctype in ALTERNATIVE_NODES:
            # else/elif/except/finally: add at SAME depth as the parent scope
            items.append(_make_item(child, depth, get_text))
            if depth < max_depth:
                # Interior of the alternative branch is one level deeper
                _collect_outline(child, depth + 1, items, get_text, max_depth)
        elif ctype in SCOPE_NODES:
            # New scope: add at current depth, recurse into its interior at depth+1
            items.append(_make_item(child, depth, get_text))
            if depth < max_depth:
                _collect_scope_interior(child, depth, items, get_text, max_depth)
        elif ctype in EXIT_NODES:
            items.append(_make_item(child, depth, get_text, is_exit=True))
        else:
            # Non-scope container (block, body, condition, keyword tokens): look through it
            if depth <= max_depth:
                _collect_outline(child, depth, items, get_text, max_depth)


def _collect_scope_interior(
    scope_node: Any,
    scope_depth: int,
    items: List[Dict[str, Any]],
    get_text: Callable,
    max_depth: int,
) -> None:
    """Process the interior of a scope node.

    Direct alternative children (else, elif, except, finally) are placed at
    scope_depth — the same visual level as the if/try they belong to.

    Body content (inside 'block' or equivalent) is explored at scope_depth+1.
    """
    for child in scope_node.children:
        ctype = child.type
        if not child.is_named:
            continue  # skip anonymous keyword tokens
        if ctype in FUNCTION_TYPES:
            continue
        if ctype in ALTERNATIVE_NODES:
            # Alternative at same level as the if/try
            items.append(_make_item(child, scope_depth, get_text))
            if scope_depth < max_depth:
                _collect_outline(child, scope_depth + 1, items, get_text, max_depth)
        elif ctype in SCOPE_NODES:
            # Nested scope directly inside a scope node (without an intermediate block)
            items.append(_make_item(child, scope_depth + 1, get_text))
            if scope_depth + 1 < max_depth:
                _collect_scope_interior(child, scope_depth + 1, items, get_text, max_depth)
        elif ctype in EXIT_NODES:
            items.append(_make_item(child, scope_depth + 1, get_text, is_exit=True))
        else:
            # block, body, or keyword token: look through at scope_depth+1
            if scope_depth < max_depth:
                _collect_outline(child, scope_depth + 1, items, get_text, max_depth)


def _make_item(
    node: Any,
    depth: int,
    get_text: Callable,
    is_exit: bool = False,
) -> Dict[str, Any]:
    return {
        'type': node.type,
        'keyword': KEYWORD_LABEL.get(node.type, node.type.upper()),
        'label': _node_label(node, get_text),
        'line_start': node.start_point[0] + 1,
        'line_end': node.end_point[0] + 1,
        'depth': depth,
        'is_exit': is_exit,
    }


# ---------------------------------------------------------------------------
# Feature 2: scope_chain
# ---------------------------------------------------------------------------

def scope_chain(
    root_node: Any,
    line_no: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Return the ancestor scope chain for a specific line (outermost first).

    Each item is a dict:
        type       -- tree-sitter node type
        keyword    -- uppercase label
        label      -- 'KEYWORD  condition_text'
        line_start -- 1-indexed start line
        line_end   -- 1-indexed end line
        depth      -- depth in the chain (0 = outermost)

    Args:
        root_node: Tree-sitter root node (or function node for scoped search).
        line_no:   Target line number (1-indexed).
        get_text:  Callable(node) -> str.

    Returns:
        List of ancestor scope items from outermost to innermost.
    """
    chain: List[Dict[str, Any]] = []
    _find_ancestors(root_node, line_no, get_text, chain, depth=0)
    return chain


def _find_ancestors(
    node: Any,
    line_no: int,
    get_text: Callable,
    chain: List[Dict[str, Any]],
    depth: int,
) -> None:
    """Recursively find scope nodes that contain line_no."""
    start = node.start_point[0] + 1
    end = node.end_point[0] + 1
    if not (start <= line_no <= end):
        return  # prune: this node doesn't contain the target line

    if node.is_named and node.type in SCOPE_NODES and node.type not in FUNCTION_TYPES:
        chain.append({
            'type': node.type,
            'keyword': KEYWORD_LABEL.get(node.type, node.type.upper()),
            'label': _node_label(node, get_text),
            'line_start': start,
            'line_end': end,
            'depth': depth,
        })
        depth += 1

    for child in node.children:
        _find_ancestors(child, line_no, get_text, chain, depth)


# ---------------------------------------------------------------------------
# Feature 3: var_flow
# ---------------------------------------------------------------------------

def var_flow(
    func_node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Return all reads and writes of var_name within a line range.

    Each event is a dict:
        kind       -- 'WRITE', 'READ/COND', or 'READ'
        line       -- 1-indexed line number of the identifier
        node       -- the identifier tree-sitter node

    Events are returned in document (line) order.

    Args:
        func_node: Function definition node to search within.
        var_name:  Variable name to track.
        from_line: Start of line range (1-indexed, inclusive).
        to_line:   End of line range (1-indexed, inclusive).
        get_text:  Callable(node) -> str.

    Returns:
        List of var-flow event dicts in document order.
    """
    events: List[Dict[str, Any]] = []
    _walk_var(func_node, var_name, from_line, to_line, get_text, events, ctx='READ')
    events.sort(key=lambda e: (e['line'], e['node'].start_point[1]))
    # Deduplicate by (line, col, kind) — same identifier can emit READ+WRITE
    # (e.g. augmented assign x += 1), so kind must be part of the key.
    seen: set = set()
    unique = []
    for ev in events:
        key = (ev['line'], ev['node'].start_point[1], ev['kind'])
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    return unique


def _walk_var(
    node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
    events: List[Dict[str, Any]],
    ctx: str,
) -> None:
    """Recursive var-flow walker with write/condition context propagation.

    Uses a closure so helpers share (var_name, from_line, to_line, get_text,
    events) without threading them through every call.
    """

    def walk(n: Any, c: str) -> None:
        """Dispatch one node, inheriting or overriding context c."""
        ntype = n.type
        line = n.start_point[0] + 1

        # Prune nodes entirely outside range (perf: skip large out-of-range subtrees)
        if n.end_point[0] + 1 < from_line or line > to_line:
            return

        if ntype == 'identifier' and get_text(n) == var_name:
            if from_line <= line <= to_line:
                events.append({'kind': c, 'line': line, 'node': n})
            return

        if ntype in ('assignment', 'augmented_assignment'):
            _walk_assignment(n, ntype, c)
        elif ntype == 'named_expression':
            _walk_named_expression(n)
        elif ntype == 'for_statement':
            _walk_for(n, c)
        elif ntype == 'with_statement':
            _walk_with(n, c)
        elif ntype in ('if_statement', 'elif_clause', 'while_statement'):
            _walk_if_while(n, c)
        else:
            for child in n.children:
                walk(child, c)

    def _walk_assignment(n: Any, ntype: str, c: str) -> None:
        """x = expr  or  x += expr — LHS is WRITE (augmented also READs first)."""
        left = n.child_by_field_name('left')
        right = n.child_by_field_name('right')
        if left:
            if ntype == 'augmented_assignment':
                walk(left, 'READ')   # x += 1 consumes the current value
            walk(left, 'WRITE')
        if right:
            walk(right, 'READ')
        # Walk remaining children (e.g. type annotation) without double-visiting.
        # Use byte span as node identity — tree-sitter creates new wrappers on each access.
        processed = {
            (left.start_byte, left.end_byte) if left else None,
            (right.start_byte, right.end_byte) if right else None,
        }
        for child in n.children:
            if (child.start_byte, child.end_byte) not in processed:
                walk(child, c)

    def _walk_named_expression(n: Any) -> None:
        """x := expr — first child is the name (WRITE), rest is value (READ)."""
        if n.children:
            walk(n.children[0], 'WRITE')
            for child in n.children[1:]:
                walk(child, 'READ')

    def _walk_for(n: Any, c: str) -> None:
        """for left in right: body — loop variable is a WRITE."""
        left = n.child_by_field_name('left')
        right = n.child_by_field_name('right')
        body = n.child_by_field_name('body')
        processed: set = set()
        if left:
            processed.add((left.start_byte, left.end_byte))
            walk(left, 'WRITE')
        if right:
            processed.add((right.start_byte, right.end_byte))
            walk(right, 'READ')
        if body:
            processed.add((body.start_byte, body.end_byte))
            walk(body, 'READ')
        for child in n.children:
            if (child.start_byte, child.end_byte) not in processed:
                walk(child, c)

    def _walk_with(n: Any, c: str) -> None:
        """with expr as alias — alias target is a WRITE."""
        for child in n.children:
            if child.type == 'with_clause':
                for item in child.children:
                    if item.type == 'with_item':
                        value = item.child_by_field_name('value')
                        alias = item.child_by_field_name('alias')
                        if value:
                            walk(value, 'READ')
                        if alias:
                            walk(alias, 'WRITE')
                    else:
                        walk(item, c)
            elif child.type == 'as_pattern':
                # 'with expr as name' — children: [expr, 'as', name]
                children = child.children
                if children:
                    walk(children[0], 'READ')
                    if len(children) > 2:
                        walk(children[-1], 'WRITE')
            else:
                walk(child, c)

    def _walk_if_while(n: Any, c: str) -> None:
        """if/elif/while — condition is READ/COND; body inherits context."""
        cond = n.child_by_field_name('condition')
        processed: set = set()
        if cond:
            processed.add((cond.start_byte, cond.end_byte))
            walk(cond, 'READ/COND')
        for child in n.children:
            if (child.start_byte, child.end_byte) not in processed:
                walk(child, c)

    walk(node, ctx)


# ---------------------------------------------------------------------------
# Feature 4: range_calls
# ---------------------------------------------------------------------------

def range_calls(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    call_node_types: Optional[frozenset] = None,
) -> List[Dict[str, Any]]:
    """Return call sites within a line range.

    Each item is a dict:
        line      -- 1-indexed line of the call
        callee    -- callee name string (e.g. 'self.validate', 'logger.warning')
        first_arg -- text of the first argument (or None)

    Args:
        func_node:       Function definition node to search within.
        from_line:       Start of line range (1-indexed, inclusive).
        to_line:         End of line range (1-indexed, inclusive).
        get_text:        Callable(node) -> str.
        call_node_types: Set of call node type strings. Defaults to the
                         standard set from reveal.treesitter.CALL_NODE_TYPES.

    Returns:
        List of call dicts in document (line) order.
    """
    if call_node_types is None:
        from ...treesitter import CALL_NODE_TYPES  # noqa: PLC0415
        call_node_types = CALL_NODE_TYPES

    results: List[Dict[str, Any]] = []
    stack = list(reversed(func_node.children))
    while stack:
        node = stack.pop()
        line = node.start_point[0] + 1
        # Prune subtrees entirely outside range
        if node.end_point[0] + 1 < from_line or line > to_line:
            continue
        if node.type in call_node_types and from_line <= line <= to_line:
            callee = _extract_callee(node, get_text)
            first_arg, has_more = _extract_first_arg(node, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
        stack.extend(reversed(node.children))

    results.sort(key=lambda r: r['line'])
    return results


def _extract_callee(call_node: Any, get_text: Callable) -> Optional[str]:
    """Extract callee name from a call expression node."""
    if not call_node.children:
        return None
    callee_node = call_node.children[0]
    text = get_text(callee_node).lstrip('*').strip()
    # Unwrap list_splat (*foo(args))
    if callee_node.type == 'list_splat':
        for child in callee_node.children:
            t = get_text(child).lstrip('*').strip()
            if t:
                return t
    return text if text else None


def _extract_first_arg(call_node: Any, get_text: Callable) -> tuple:
    """Extract the first argument and whether more args follow.

    Returns:
        (first_arg_text, has_more) where first_arg_text may be None.
    """
    for child in call_node.children:
        if child.type in ('argument_list', 'arguments', 'call_arguments'):
            # Children: '(', arg1, ',', arg2, ..., ')'
            real_args = [
                c for c in child.children
                if c.type not in ('(', ')', ',', 'comment') and c.is_named
            ]
            if not real_args:
                return None, False
            text = get_text(real_args[0]).splitlines()[0].strip()
            if len(text) > 40:
                text = text[:37] + '...'
            return text, len(real_args) > 1
    return None, False


# ---------------------------------------------------------------------------
# Text renderers
# ---------------------------------------------------------------------------

def render_outline(
    func_name: str,
    func_start: int,
    func_end: int,
    items: List[Dict[str, Any]],
    depth: int = 3,
) -> str:
    """Render an element_outline result as text.

    Returns a multi-line string suitable for printing.
    """
    lines = [f'DEF {func_name}  L{func_start}→L{func_end}']
    for item in items:
        if item['depth'] > depth:
            continue
        indent = '  ' * item['depth']
        lrange = f'L{item["line_start"]}→L{item["line_end"]}' if item['line_start'] != item['line_end'] else f'L{item["line_start"]}'
        lines.append(f'{indent}{item["label"]}  {lrange}')
    return '\n'.join(lines)


def render_scope_chain(line_no: int, chain: List[Dict[str, Any]]) -> str:
    """Render a scope_chain result as text."""
    if not chain:
        return f'L{line_no} is at module/function top level (no enclosing scope blocks)'

    MAX_CHAIN = 8
    lines = []
    truncated = len(chain) > MAX_CHAIN
    visible = chain[:MAX_CHAIN] if truncated else chain
    if truncated:
        hidden = len(chain) - MAX_CHAIN
        # Show outermost 2 and innermost (MAX_CHAIN - 2)
        outer = chain[:2]
        inner = chain[-(MAX_CHAIN - 2):]
        visible_chain = outer + inner
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
        for item in visible:
            indent = '  ' * item['depth']
            lrange = f'L{item["line_start"]}→L{item["line_end"]}'
            lines.append(f'{indent}{item["keyword"]:<8}{lrange:<16}{item["label"]}')

    innermost_depth = chain[-1]['depth'] + 1
    lines.append('')
    lines.append(f'{"  " * innermost_depth}▶ L{line_no} is here')
    return '\n'.join(lines)


def render_var_flow(
    var_name: str,
    events: List[Dict[str, Any]],
    content_lines: List[str],
) -> str:
    """Render a var_flow result as text.

    Args:
        var_name:      The variable name that was traced.
        events:        Output of var_flow().
        content_lines: File content split into lines (0-indexed).
    """
    if not events:
        return f'No references to {var_name!r} found in range'

    lines = []
    for ev in events:
        kind = ev['kind']
        lineno = ev['line']
        snippet = content_lines[lineno - 1].strip() if lineno <= len(content_lines) else ''
        if len(snippet) > 80:
            snippet = snippet[:77] + '...'
        lines.append(f'{kind:<10}L{lineno}:  {snippet}')
    return '\n'.join(lines)


def render_range_calls(
    calls: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render a range_calls result as text."""
    if not calls:
        return f'No calls found in L{from_line}→L{to_line}'

    lines = []
    for call in calls:
        callee = call['callee'] or '?'
        if call['first_arg']:
            arg_part = f'({call["first_arg"]}, ...)' if call['has_more_args'] else f'({call["first_arg"]})'
        else:
            arg_part = '(...)'
        lines.append(f'L{call["line"]}:  {callee}{arg_part}')
    return '\n'.join(lines)
