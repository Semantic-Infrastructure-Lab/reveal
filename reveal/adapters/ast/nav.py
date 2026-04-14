"""Sub-function progressive disclosure — navigation inside large functions.

Nine functions that close the gap between "here's the function signature" and
"here are all 200 lines":

  element_outline()  -- control-flow skeleton (top-down map of a function)
  scope_chain()      -- ancestor scope chain for a specific line (bottom-up)
  var_flow()         -- variable read/write trace within a function
  range_calls()      -- call sites within a specific line range
  collect_exits()    -- exit nodes (return/raise/die/break) in a line range
  all_var_flow()     -- single-pass all-variable events (for deps/mutations)
  collect_deps()     -- variables flowing INTO a range (potential params)
  collect_mutations()-- variables written in range and read after (potential returns)

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
    # Function/class definition nodes
    'function_definition': 'DEF', 'function_declaration': 'DEF',
    'function_item': 'DEF', 'function': 'DEF',
    'method_definition': 'DEF', 'method_declaration': 'DEF',
    'arrow_function': 'DEF',
    'lambda': 'LAMBDA',
    'class_definition': 'CLASS', 'class_declaration': 'CLASS', 'class': 'CLASS',
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
            # Nested def/class: emit a labeled entry so closure-heavy functions
            # aren't silently blank; recurse into the body at the next depth level.
            items.append(_make_item(child, depth, get_text))
            if depth < max_depth:
                _collect_scope_interior(child, depth, items, get_text, max_depth)
            continue
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
            items.append(_make_item(child, scope_depth + 1, get_text))
            if scope_depth + 1 < max_depth:
                _collect_scope_interior(child, scope_depth + 1, items, get_text, max_depth)
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

    if node.is_named and (node.type in SCOPE_NODES or node.type in FUNCTION_TYPES):
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


def render_scope_chain(line_no: int, chain: List[Dict[str, Any]], line_text: str = '') -> str:
    """Render a scope_chain result as text."""
    if not chain:
        suffix = f': {line_text}' if line_text else ' is at module/function top level (no enclosing scope blocks)'
        return f'▶ L{line_no}{suffix}'

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
    indent = '  ' * innermost_depth
    lines.append('')
    if line_text:
        lines.append(f'{indent}▶ L{line_no}: {line_text}')
    else:
        lines.append(f'{indent}▶ L{line_no} is here')
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


# ---------------------------------------------------------------------------
# Feature: collect_exits  (--exits / --flowto)
# ---------------------------------------------------------------------------

# Language-construct names treated as hard exits even when represented as calls
_EXIT_CALL_NAMES: frozenset = frozenset({'die', 'exit'})

# Mapping from exit node type to kind label
_EXIT_KIND: Dict[str, str] = {
    'return_statement': 'RETURN', 'return': 'RETURN',
    'raise_statement': 'RAISE',   'raise': 'RAISE',
    'throw_statement': 'THROW',
    'yield_statement': 'YIELD',   'yield': 'YIELD',
    'break_statement': 'BREAK',   'break': 'BREAK',
    'continue_statement': 'CONTINUE', 'continue': 'CONTINUE',
}

# Kinds that unconditionally prevent reaching a subsequent line
_HARD_EXIT_KINDS: frozenset = frozenset({'RETURN', 'RAISE', 'THROW', 'EXIT'})

# Kinds that interrupt flow without hard-terminating the function.
# YIELD suspends the generator and hands control to the caller — it is not a
# hard exit (the function can resume on the next next() call) but it does
# transfer control out of the current scope, so treating it as CLEAR would be
# misleading for --flowto analysis.
_SOFT_EXIT_KINDS: frozenset = frozenset({'BREAK', 'CONTINUE', 'YIELD'})


def collect_exits(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    call_node_types: Optional[frozenset] = None,
) -> List[Dict[str, Any]]:
    """Collect exit nodes within a line range.

    Handles both AST exit nodes (return_statement, raise_statement, etc.) and
    language-construct calls like die()/exit() in PHP that tree-sitter may
    represent as call expressions.

    Each item is a dict:
        kind -- 'RETURN', 'RAISE', 'THROW', 'YIELD', 'BREAK', 'CONTINUE', or 'EXIT'
        line -- 1-indexed line number
        text -- first line of the node's source text (truncated to 80 chars)

    Args:
        scope_node:      Tree-sitter node to search within.
        from_line:       Start of range (1-indexed, inclusive).
        to_line:         End of range (1-indexed, inclusive).
        get_text:        Callable(node) -> str.
        call_node_types: Override the standard call node type set.

    Returns:
        List of exit dicts sorted by line number.
    """
    if call_node_types is None:
        from ...treesitter import CALL_NODE_TYPES  # noqa: PLC0415
        call_node_types = CALL_NODE_TYPES

    results: List[Dict[str, Any]] = []
    stack = list(reversed(scope_node.children))
    while stack:
        node = stack.pop()
        line = node.start_point[0] + 1
        # Prune subtrees entirely outside range
        if node.end_point[0] + 1 < from_line or line > to_line:
            continue

        if from_line <= line <= to_line:
            if node.type in _EXIT_KIND:
                kind = _EXIT_KIND[node.type]
                text = get_text(node).splitlines()[0].strip()
                if len(text) > 80:
                    text = text[:77] + '...'
                results.append({'kind': kind, 'line': line, 'text': text})
                # Don't recurse into exit nodes — they are leaves conceptually
                continue
            if node.type in call_node_types:
                callee = _extract_callee(node, get_text)
                if callee in _EXIT_CALL_NAMES:
                    text = get_text(node).splitlines()[0].strip()
                    if len(text) > 80:
                        text = text[:77] + '...'
                    results.append({'kind': 'EXIT', 'line': line, 'text': text})

        stack.extend(reversed(node.children))

    results.sort(key=lambda r: r['line'])
    return results


def render_exits(
    exits: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
    verdict: bool = False,
) -> str:
    """Render collect_exits results.

    Args:
        exits:    Output of collect_exits().
        from_line, to_line: Range that was searched.
        verdict:  If True, append a --flowto reachability verdict after the list.

    Returns:
        Multi-line string suitable for printing.
    """
    lines: List[str] = []
    if not exits:
        lines.append(f'No exits in L{from_line}→L{to_line}')
    else:
        for e in exits:
            lines.append(f'{e["kind"]:<10}L{e["line"]}:  {e["text"]}')

    if verdict:
        has_hard = any(e['kind'] in _HARD_EXIT_KINDS for e in exits)
        has_soft = any(e['kind'] in _SOFT_EXIT_KINDS for e in exits)
        if has_hard:
            v = '⚠ BLOCKED'
        elif has_soft:
            v = '~ CONDITIONAL'
        else:
            v = '✓ CLEAR'
        lines.append(f'\nflowto L{to_line}: {v}')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Feature: all_var_flow, collect_deps, collect_mutations  (--deps / --mutations)
# ---------------------------------------------------------------------------


def _collect_identifier_names(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> frozenset:
    """Return the set of identifier names that appear in a line range.

    Used to pre-scan before running var_flow for each name.
    """
    names: set = set()
    stack = list(reversed(scope_node.children))
    while stack:
        node = stack.pop()
        line = node.start_point[0] + 1
        if node.end_point[0] + 1 < from_line or line > to_line:
            continue
        if node.type == 'identifier' and from_line <= line <= to_line:
            text = get_text(node)
            if text:
                names.add(text)
        stack.extend(reversed(node.children))
    return frozenset(names)


def all_var_flow(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    full_from: int = 1,
    full_to: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Collect var_flow events for every identifier that appears in a line range.

    Pre-scans ``from_line``→``to_line`` for identifier names, then runs
    var_flow(full_from, full_to) for each — capturing events outside the range
    so that deps/mutations analysis can see what came before and after.

    Args:
        scope_node: Tree-sitter node to search within (function node or root).
        from_line:  Start of the analysis range (1-indexed, inclusive).
        to_line:    End of the analysis range (1-indexed, inclusive).
        get_text:   Callable(node) -> str.
        full_from:  Start of the broader search for each variable (default 1).
        full_to:    End of the broader search. Defaults to the last line of scope_node.

    Returns:
        Dict mapping var_name -> list of var_flow events (sorted, deduplicated).
    """
    if full_to is None:
        full_to = scope_node.end_point[0] + 1

    names = _collect_identifier_names(scope_node, from_line, to_line, get_text)
    result: Dict[str, List[Dict[str, Any]]] = {}
    for name in sorted(names):
        events = var_flow(scope_node, name, full_from, full_to, get_text)
        if events:
            result[name] = events
    return result


def collect_deps(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Identify variables that flow INTO a line range (potential function parameters).

    A variable is a dep if its first event in the range is a READ, meaning it
    was set before the range began.  Equivalent to probe's ``deps`` section.

    Each item is a dict:
        var             -- variable name
        first_read_line -- line of first read inside the range
        first_write_line-- line of first write inside the range (or None)

    Args:
        scope_node: Tree-sitter node to search within.
        from_line:  Start of range (1-indexed, inclusive).
        to_line:    End of range (1-indexed, inclusive).
        get_text:   Callable(node) -> str.

    Returns:
        List of dep dicts sorted by first_read_line.
    """
    all_events = all_var_flow(scope_node, from_line, to_line, get_text)
    deps: List[Dict[str, Any]] = []
    for var_name, events in all_events.items():
        in_range = [e for e in events if from_line <= e['line'] <= to_line]
        if not in_range:
            continue
        first_in_range = min(in_range, key=lambda e: e['line'])
        if first_in_range['kind'].startswith('READ'):
            first_write = next(
                (e for e in in_range if e['kind'] == 'WRITE'), None
            )
            deps.append({
                'var': var_name,
                'first_read_line': first_in_range['line'],
                'first_write_line': first_write['line'] if first_write else None,
            })
    deps.sort(key=lambda d: d['first_read_line'])
    return deps


def collect_mutations(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Identify variables written in a range that are read after it.

    These are potential return values if the range were extracted into a
    function.  Equivalent to probe's ``mutations`` section.

    Each item is a dict:
        var             -- variable name
        last_write_line -- line of last write inside the range
        next_read_line  -- line of next read after the range

    Args:
        scope_node: Tree-sitter node to search within.
        from_line:  Start of range (1-indexed, inclusive).
        to_line:    End of range (1-indexed, inclusive).
        get_text:   Callable(node) -> str.

    Returns:
        List of mutation dicts sorted by last_write_line.
    """
    full_to = scope_node.end_point[0] + 1
    all_events = all_var_flow(
        scope_node, from_line, to_line, get_text, full_to=full_to
    )
    mutations: List[Dict[str, Any]] = []
    for var_name, events in all_events.items():
        in_range = [e for e in events if from_line <= e['line'] <= to_line]
        after_range = [e for e in events if e['line'] > to_line]
        writes_in = [e for e in in_range if e['kind'] == 'WRITE']
        if writes_in and after_range:
            last_write = max(writes_in, key=lambda e: e['line'])
            next_read = min(after_range, key=lambda e: e['line'])
            mutations.append({
                'var': var_name,
                'last_write_line': last_write['line'],
                'next_read_line': next_read['line'],
            })
    mutations.sort(key=lambda m: m['last_write_line'])
    return mutations


# ---------------------------------------------------------------------------
# Additional renderers
# ---------------------------------------------------------------------------


def render_branchmap(
    items: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render filtered element_outline items as a branch/exception map.

    Used by --ifmap and --catchmap.  Items are already filtered to only the
    relevant keyword set (IF/ELIF/ELSE/... or TRY/CATCH/...).

    Args:
        items:    Filtered subset of element_outline() output.
        from_line, to_line: Range that was searched (for empty-result message).

    Returns:
        Multi-line string suitable for printing.
    """
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


def render_deps(
    deps: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render collect_deps results.

    Args:
        deps:     Output of collect_deps().
        from_line, to_line: Range that was analyzed.

    Returns:
        Multi-line string suitable for printing.
    """
    if not deps:
        return f'No dependencies flowing into L{from_line}→L{to_line}'
    lines: List[str] = []
    for d in deps:
        write_info = (
            f'  (first write L{d["first_write_line"]})'
            if d['first_write_line'] is not None
            else '  (never written in range)'
        )
        lines.append(
            f'PARAM  {d["var"]:<30}  first read L{d["first_read_line"]}{write_info}'
        )
    return '\n'.join(lines)


def render_mutations(
    mutations: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render collect_mutations results.

    Args:
        mutations: Output of collect_mutations().
        from_line, to_line: Range that was analyzed.

    Returns:
        Multi-line string suitable for printing.
    """
    if not mutations:
        return f'No mutations in L{from_line}→L{to_line} that are read after'
    lines: List[str] = []
    for m in mutations:
        lines.append(
            f'RETURN {m["var"]:<30}  written L{m["last_write_line"]},'
            f' next read L{m["next_read_line"]}'
        )
    return '\n'.join(lines)
