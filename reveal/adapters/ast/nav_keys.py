"""Dynamic key/property access surface: collect_keys (--keys VAR).

BACK-439d: dict/object/array shape assumptions are a major source of agent
mistakes, and no existing nav flag exposes them. Dogfood-confirmed blind
spot on reveal/config.py's _check_rule_enabled: `--varflow rules` collapses
`rules.get('enabled', ...)`, `rules.get('disable', ...)`, and
`rules.get('select', ...)` into generic READ lines on the enclosing
statement — the actual keys never appear in the output. An agent has to
open the file and read the literals by eye today.

Recognizes, for a given base variable name:
  subscript access  -- config['x'], $row['id'], payload["id"] (any language's
                        subscript/index node, field-based or PHP's fieldless
                        positional shape)
  member access     -- payload.id, $obj->x, config.enabled (any language's
                        attribute/member-access node)
  .get(key, default) call -- config.get('x'), row.get('id') (Python/JS dict-get
                        idiom; the key is the call's first argument, not the
                        method name)
  isset()/empty() wrapping a subscript -- PHP's existence-check idiom

Classifies each access as READ, WRITE (assignment target), or COND (used
directly in an if/while condition — including isset()/empty()). _walk()
independently mirrors the same READ/WRITE/COND context-propagation *shape*
as nav_varflow.VarFlowWalker (assignment targets flip to WRITE, condition
subtrees flip to COND) rather than subclassing it directly — VarFlowWalker's
own dispatch is built around matching bare variable identifiers and
excluding member-access/JSX/annotation nodes from descent, which is the
opposite of what --keys needs (it must inspect member-access/subscript/call
nodes themselves, not skip over them). What *is* genuinely shared, not
reimplemented, is resolve_assignment_sides() (BACK-456) — including Lua's
fieldless assignment_statement fallback — imported directly from
nav_varflow.py so the two modules can't drift on that one grammar edge case.

Reuses _ASSIGNMENT_NODES/_SUBSCRIPT_NODES from nav_statewrites.py and the
fuller _MEMBER_ACCESS_KINDS from nav_varflow.py (which also covers Rust
scoped_identifier, Kotlin navigation_expression, and Lua's dot/method index
shapes) rather than redeclaring the same grammar-shape literals a second time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ...core import node_children as _children
from .nav_statewrites import _ASSIGNMENT_NODES, _SUBSCRIPT_NODES
from .nav_varflow import _MEMBER_ACCESS_KINDS as _MEMBER_ACCESS_NODES
from .nav_varflow import resolve_assignment_sides

_CALL_NODES: frozenset = frozenset({
    'call', 'call_expression', 'function_call_expression', 'method_invocation',
})

# PHP's method-call node (unlike the _CALL_NODES shapes above) has no nested
# 'function' node to unwrap: 'object'/'name'/'arguments' sit directly on the
# call node itself (BACK-458 item 4 — $row->get('id') was previously
# invisible to the .get() idiom below because member_call_expression was
# absent from _CALL_NODES and its shape doesn't fit that branch anyway).
_METHOD_CALL_NODES: frozenset = frozenset({'member_call_expression'})

_ISSET_LIKE: frozenset = frozenset({'isset', 'empty'})

_QUOTE_CHARS = ('"', "'", '`')


def _base_text(base: Any, get_text: Callable) -> str:
    return get_text(base).strip().lstrip('$')


def _base_matches(base: Any, var_name: str, get_text: Callable) -> bool:
    return _base_text(base, get_text) == var_name.lstrip('$')


def _clean_literal(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in _QUOTE_CHARS and text[-1] == text[0]:
        return text[1:-1]
    return text


def _unwrap_indexing_suffix(key: Optional[Any]) -> Optional[Any]:
    """Kotlin's key sits one level deeper, inside a sibling `indexing_suffix`
    (`m["port"]` -> indexing_expression[simple_identifier, indexing_suffix['[', string_literal, ']']]) —
    drill in to the suffix's one named child (BACK-458 item 1 cont'd)."""
    if key is None or key.kind() != 'indexing_suffix':
        return key
    for child in _children(key):
        if child.is_named():
            return child
    return None


def _subscript_parts(node: Any) -> tuple:
    """Return (base_node, key_node) for a subscript/index node.

    Field-based grammars (Python 'value'/'subscript', JS/TS 'object'/'index')
    expose both directly. PHP's subscript_expression exposes no fields at
    all — base is the first child, key is the first named child after '['.
    Kotlin's 'indexing_expression' is likewise fieldless/positional but its
    "key" is a wrapper node, not the literal itself — unwrapped below.
    """
    base = node.child_by_field_name('value') or node.child_by_field_name('object')
    key = node.child_by_field_name('subscript') or node.child_by_field_name('index')
    if base is not None:
        return base, _unwrap_indexing_suffix(key)
    children = _children(node)
    if not children:
        return None, None
    base = children[0]
    key = None
    for child in children[1:]:
        if child.is_named():
            key = child
            break
    return base, _unwrap_indexing_suffix(key)


def _directly_assignable_subscript_parts(node: Any) -> tuple:
    """Return (base, key) if a Kotlin `directly_assignable_expression` wraps
    a subscript write (`m["host"] = 1`), else (None, None).

    This wrapper is heavily overloaded — it also carries bare-identifier
    (`total = ...`) and member-access (`this.total = ...`) targets — so it
    can't join _SUBSCRIPT_NODES outright (would misclassify those as
    subscripts with a bogus '?' key). Only the [base, indexing_suffix]
    positional shape counts (BACK-458 item 1 cont'd).
    """
    children = _children(node)
    if len(children) != 2 or children[1].kind() != 'indexing_suffix':
        return None, None
    return children[0], _unwrap_indexing_suffix(children[1])


def _swift_subscript_parts(node: Any) -> tuple:
    """Return (base, key) if a Swift `call_expression` is actually a
    dict/array subscript (`m["port"]`), else (None, None).

    Swift's subscript parses to the same `call_expression` node kind as a
    real function call — `m["port"]` and `m(x)` are indistinguishable by
    node kind alone. The discriminator is the `value_arguments` node's own
    opening delimiter: '[' for a subscript, '(' for a real call (BACK-458
    item 1 cont'd).
    """
    children = _children(node)
    if len(children) != 2 or children[1].kind() != 'call_suffix':
        return None, None
    suffix_children = _children(children[1])
    if len(suffix_children) != 1 or suffix_children[0].kind() != 'value_arguments':
        return None, None
    value_args = _children(suffix_children[0])
    if not value_args or value_args[0].kind() != '[':
        return None, None
    base = children[0]
    key = next((c for c in value_args if c.is_named()), None)
    return base, key


def _member_parts(node: Any) -> tuple:
    """Return (object_node, property_node) for a member/attribute-access node.

    The base/receiver field is named 'object' in most grammars, but Rust's
    field_expression uses 'value', Go's selector_expression uses 'operand',
    C#'s member_access_expression uses 'expression', C++'s field_expression
    uses 'argument', and Lua's dot_index_expression uses 'table' (BACK-456,
    found while regression-testing the assignment-sides fix — cfg.x silently
    produced zero --keys events) — try each before giving up. Field-based
    grammars expose 'property'/'name'/'attribute'/'field' for the property
    side; Python's 'attribute' node exposes only the base — the property
    identifier has no field name, so it falls back to the last named
    non-object child.
    """
    obj = (
        node.child_by_field_name('object')
        or node.child_by_field_name('value')
        or node.child_by_field_name('operand')
        or node.child_by_field_name('expression')
        or node.child_by_field_name('argument')
        or node.child_by_field_name('table')
    )
    if obj is None:
        return None, None
    prop = (
        node.child_by_field_name('property')
        or node.child_by_field_name('name')
        or node.child_by_field_name('attribute')
        or node.child_by_field_name('field')
    )
    if prop is not None:
        return obj, prop
    obj_span = (obj.start_byte(), obj.end_byte())
    candidates = [c for c in _children(node) if c.is_named() and (c.start_byte(), c.end_byte()) != obj_span]
    if candidates:
        return obj, candidates[-1]
    return None, None


def _first_call_arg(call_node: Any, get_text: Callable) -> Optional[Any]:
    args = call_node.child_by_field_name('arguments')
    if args is None:
        return None
    for child in _children(args):
        if child.is_named():
            return child
    return None


@dataclass
class _KeysWalker:
    """Recursive dynamic-key-access walker with READ/WRITE/COND context
    propagation, mirroring VarFlowWalker's shape (nav_varflow.py): a `walk()`
    entry point dispatching to independently-testable branch handlers, each
    returning True when it fully consumed the node (caller returns without
    descending further)."""

    var_name: str
    from_line: int
    to_line: int
    get_text: Callable
    results: List[Dict[str, Any]] = field(default_factory=list)

    def walk(self, node: Any, context: str) -> None:
        start = node.start_position().row + 1
        end = node.end_position().row + 1
        if end < self.from_line or start > self.to_line:
            return
        ntype = node.kind()

        if ntype in _ASSIGNMENT_NODES:
            self._walk_assignment(node, ntype, context)
            return

        cond = self._condition_of(node, ntype)
        if cond is not None:
            self._walk_condition(node, cond, context)
            return

        if ntype in _CALL_NODES and self._walk_call(node, start, context):
            return
        if ntype in _METHOD_CALL_NODES and self._walk_method_call(node, start, context):
            return
        if ntype in _SUBSCRIPT_NODES and self._walk_subscript(node, start, context):
            return
        if ntype in _MEMBER_ACCESS_NODES and self._walk_member_access(node, start, context):
            return
        # Kotlin write target (`m["host"] = 1`) — indistinguishable from a
        # bare-identifier/member-access write by node kind alone, so it can't
        # join _SUBSCRIPT_NODES; checked structurally instead (BACK-458).
        if ntype == 'directly_assignable_expression' and self._walk_directly_assignable_subscript(node, start, context):
            return
        # Swift subscript (`m["port"]`) parses as the same node kind as a
        # real call and was already routed through _walk_call above, which
        # returns False for it (no 'function' field in Swift's grammar) —
        # checked structurally here instead (BACK-458).
        if ntype == 'call_expression' and self._walk_swift_subscript(node, start, context):
            return

        for child in _children(node):
            self.walk(child, context)

    def _walk_assignment(self, node: Any, ntype: str, context: str) -> None:
        left, right = resolve_assignment_sides(node, ntype)
        processed = set()
        if left is not None:
            processed.add((left.start_byte(), left.end_byte()))
            self.walk(left, 'WRITE')
        if right is not None:
            processed.add((right.start_byte(), right.end_byte()))
            self.walk(right, 'READ')
        for child in _children(node):
            if (child.start_byte(), child.end_byte()) not in processed:
                self.walk(child, context)

    def _condition_of(self, node: Any, ntype: str) -> Optional[Any]:
        cond = node.child_by_field_name('condition')
        if cond is not None:
            return cond
        if ntype == 'conditional_expression':
            # Python's ternary (`a if cond else b`) is fieldless — the
            # condition is the middle named child.
            named = [c for c in _children(node) if c.is_named()]
            if len(named) == 3:
                return named[1]
        return None

    def _walk_condition(self, node: Any, cond: Any, context: str) -> None:
        self.walk(cond, 'COND')
        cond_span = (cond.start_byte(), cond.end_byte())
        for child in _children(node):
            if (child.start_byte(), child.end_byte()) != cond_span:
                self.walk(child, context)

    def _walk_call(self, node: Any, start: int, context: str) -> bool:
        func = node.child_by_field_name('function')
        if func is None:
            return False
        if func.kind() in ('name', 'identifier') and self.get_text(func) in _ISSET_LIKE:
            args = node.child_by_field_name('arguments')
            if args is not None:
                for child in _children(args):
                    if child.is_named():
                        self.walk(child, 'COND')
            return True
        if func.kind() in _MEMBER_ACCESS_NODES:
            obj, prop = _member_parts(func)
            if (
                obj is not None and prop is not None and self.get_text(prop) == 'get'
                and _base_matches(obj, self.var_name, self.get_text)
            ):
                self._record_call_key(node, start, context)
                return True
        return False

    def _walk_method_call(self, node: Any, start: int, context: str) -> bool:
        obj = node.child_by_field_name('object')
        name = node.child_by_field_name('name')
        if not (
            obj is not None and name is not None
            and self.get_text(name) == 'get' and _base_matches(obj, self.var_name, self.get_text)
        ):
            return False
        self._record_call_key(node, start, context)
        return True

    def _record_call_key(self, node: Any, start: int, context: str) -> None:
        key_node = _first_call_arg(node, self.get_text)
        if key_node is not None:
            self.results.append({
                'key': _clean_literal(self.get_text(key_node)), 'kind': context,
                'line': start, 'access': 'call',
            })

    def _walk_subscript(self, node: Any, start: int, context: str) -> bool:
        base, key_node = _subscript_parts(node)
        if base is None or not _base_matches(base, self.var_name, self.get_text):
            return False
        key = _clean_literal(self.get_text(key_node)) if key_node is not None else '?'
        self.results.append({'key': key, 'kind': context, 'line': start, 'access': 'subscript'})
        return True

    def _walk_directly_assignable_subscript(self, node: Any, start: int, context: str) -> bool:
        base, key_node = _directly_assignable_subscript_parts(node)
        if base is None or not _base_matches(base, self.var_name, self.get_text):
            return False
        key = _clean_literal(self.get_text(key_node)) if key_node is not None else '?'
        self.results.append({'key': key, 'kind': context, 'line': start, 'access': 'subscript'})
        return True

    def _walk_swift_subscript(self, node: Any, start: int, context: str) -> bool:
        base, key_node = _swift_subscript_parts(node)
        if base is None or not _base_matches(base, self.var_name, self.get_text):
            return False
        key = _clean_literal(self.get_text(key_node)) if key_node is not None else '?'
        self.results.append({'key': key, 'kind': context, 'line': start, 'access': 'subscript'})
        return True

    def _walk_member_access(self, node: Any, start: int, context: str) -> bool:
        obj, prop = _member_parts(node)
        if obj is None or prop is None or not _base_matches(obj, self.var_name, self.get_text):
            return False
        self.results.append({'key': self.get_text(prop), 'kind': context, 'line': start, 'access': 'attribute'})
        return True


def collect_keys(
    func_node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Return dict/object/array key accesses on ``var_name`` in a line range.

    Each result: {key, kind (READ/WRITE/COND), line, access (subscript/attribute/call)}.
    """
    walker = _KeysWalker(var_name, from_line, to_line, get_text)
    walker.walk(func_node, 'READ')
    walker.results.sort(key=lambda r: r['line'])
    return walker.results


def render_keys(var_name: str, events: List[Dict[str, Any]], from_line: int, to_line: int) -> str:
    """Render collect_keys output, grouped by key in first-seen order."""
    if not events:
        return f'No key access found for {var_name} in lines {from_line}–{to_line}'
    order: List[str] = []
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for e in events:
        if e['key'] not in groups:
            groups[e['key']] = []
            order.append(e['key'])
        groups[e['key']].append(e)
    key_width = max(len(k) for k in order)
    lines = []
    for key in order:
        accesses = ', '.join(f"{a['kind']} L{a['line']}" for a in groups[key])
        lines.append(f'{key:<{key_width}}  {accesses}')
    return '\n'.join(lines)
