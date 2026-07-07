"""Persistent/shared-state mutation surface: collect_statewrites (--statewrites).

BACK-439c: --mutations is local-variable/refactor oriented (read-after-write
hazards); --sideeffects is call-oriented. Neither answers "what shared state
does this code mutate" — dogfood-confirmed blind spot on
GitRefResource._parse_and_initialize_attributes (reveal/adapters/git/adapter.py),
which writes self.path/self.ref/self.subpath/self.query six times while both
existing flags report clean.

Two write shapes, both invisible to --mutations/--sideeffects:
  field   -- assignment target is a member-access node (self.x=, $obj->x=,
             this.x=) — any receiver, not just self/this.
  env/session -- assignment target is a subscript on a known superglobal
             base ($_SESSION[...], os.environ[...], process.env[...]).

Call-based writes (cache/db/file/env/session) are not reclassified here —
they're collect_effects()'s existing taxonomy, merged in by kind. DB
column/table extraction and true global-vs-local distinction are out of
this slice (see design doc); 'db' inherits collect_effects()'s existing
imprecision (query calls are included alongside true writes) rather than
inventing a separate CRUD-verb classifier.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ...core import node_children as _children
from .nav_effects import collect_effects
from .nav_varflow import resolve_assignment_sides
from .node_taxonomy import MEMBER_ACCESS_NODES as _MEMBER_ACCESS_NODES

_ASSIGNMENT_NODES: frozenset = frozenset({
    'assignment', 'augmented_assignment', 'assignment_expression',
    'augmented_assignment_expression', 'assignment_statement', 'compound_assignment_expr',
    # Ruby's compound assignment (`@count += 1`, `@x ||= y`) is `operator_assignment`,
    # not `augmented_assignment` — so ivar compound-writes were invisible to
    # --statewrites while simple `@count = 1` (assignment) worked. Found via
    # discourse deep-conformance dogfooding.
    'operator_assignment',
})

# _MEMBER_ACCESS_NODES: promoted to node_taxonomy.MEMBER_ACCESS_NODES
# (BACK-478 move 1 step 2) — this used to be an independent copy, missing
# 'scoped_identifier'/'dot_index_expression'/'method_index_expression'
# relative to nav_varflow.py's fuller version. On an assignment *target*,
# Kotlin/Swift wrap the real member-access shape (and the bare-identifier
# case) in 'directly_assignable_expression' instead of exposing it
# directly — see the unwrap in _target_kind below.

_SUBSCRIPT_NODES: frozenset = frozenset({
    'subscript', 'subscript_expression', 'index_expression', 'element_access_expression',
    # Lua's `t["k"]` (BACK-458 item 1). Python-shaped: base is child 0, the
    # key literal the first named child after '['. Kotlin/Swift/Dart subscript
    # shapes are NOT this shape (sibling base / call_expression collision /
    # nested selectors) and need bespoke base extraction, not a set entry.
    'bracket_index_expression',
})

_SESSION_BASES = ('_session', '_cookie', 'session')

# Kinds collect_effects() already classifies that also count as shared-state
# writes when they occur as calls rather than assignments (cache set/delete,
# db insert/update/query, file write, env put, session start/write).
_CALL_KINDS: frozenset = frozenset({'db', 'cache', 'file', 'env', 'session'})


def _member_kind(full_text: str) -> str:
    lower = full_text.lower()
    if lower.startswith('process.env.') or lower.startswith('os.environ.'):
        return 'env'
    return 'field'


def _subscript_kind(base_text: str) -> Optional[str]:
    lower = base_text.lower().lstrip('$')
    if lower in _SESSION_BASES:
        return 'session'
    if lower.endswith('.environ') or lower.endswith('.env'):
        return 'env'
    return None


def _target_kind(left: Any, get_text: Callable) -> Optional[str]:
    """Classify an assignment's left-hand target, or None if not state-relevant."""
    ltype = left.kind()
    if ltype == 'directly_assignable_expression':
        # BACK-478 Finding 2: Kotlin/Swift wrap every assignment target in
        # this node — a bare reassignment (`total = ...`) and a member
        # write (`this.total = ...` for Kotlin; `self.total = ...` for
        # Swift, one level deeper via a nested navigation_expression) are
        # otherwise indistinguishable from the outside. Kotlin's member
        # shape is flat (a navigation_suffix child directly); Swift's
        # nests a navigation_expression child. A bare-identifier target
        # has neither and correctly falls through un-classified, same as
        # every other language's bare-identifier write.
        children = _children(left)
        if any(c.kind() == 'navigation_suffix' for c in children):
            return _member_kind(get_text(left))
        for child in children:
            if child.kind() == 'navigation_expression':
                return _target_kind(child, get_text)
        return None
    if ltype == 'instance_variable':
        # Ruby `@total = ...` — a single sigil-prefixed token, not an
        # "obj.attr" member-access shape at all (unlike Python's `self.x`),
        # so it's invisible to _MEMBER_ACCESS_NODES/_member_kind's text-prefix
        # check. Always a field write regardless of receiver, same as every
        # other language's self/this-style member write (BACK-477).
        return 'field'
    if ltype in _MEMBER_ACCESS_NODES:
        return _member_kind(get_text(left))
    if ltype in _SUBSCRIPT_NODES:
        base = left.child(0)
        if base is not None:
            return _subscript_kind(get_text(base))
    return None


def _assignment_targets(left: Any) -> List[Any]:
    """Unwrap Go's `expression_list` assignment-target wrapper.

    Go's assignment_statement always wraps its 'left' field in an
    expression_list (to support multi-assign `a, b = 1, 2`) even for a
    single target — found via the BACK-439b/c conformance-matrix
    cross-language pass: `b.Total = ...` was silently invisible to
    --statewrites because `left.kind()` was 'expression_list', never
    matching _MEMBER_ACCESS_NODES/_SUBSCRIPT_NODES directly.
    """
    if left.kind() == 'expression_list':
        return [c for c in _children(left) if c.is_named()]
    return [left]


def _walk_assignments(
    node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    results: List[Dict[str, Any]],
) -> None:
    start = node.start_position().row + 1
    end = node.end_position().row + 1
    if start > to_line or end < from_line:
        return
    if node.is_named() and node.kind() in _ASSIGNMENT_NODES:
        # BACK-478 Finding 2: was `node.child_by_field_name('left')` directly —
        # blind to Kotlin/Swift's fieldless `assignment` node (positional
        # children only, the same shape BACK-476 fixed for --varflow/--keys).
        # resolve_assignment_sides is the shared fallback (BACK-456/476).
        left, _right = resolve_assignment_sides(node, node.kind())
        line = start
        if left is not None and from_line <= line <= to_line:
            for target in _assignment_targets(left):
                kind = _target_kind(target, get_text)
                if kind:
                    results.append({
                        'kind': kind, 'line': line, 'target': get_text(target), 'via': 'assignment',
                    })
    for child in _children(node):
        _walk_assignments(child, from_line, to_line, get_text, results)


def collect_statewrites(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return persistent/shared-state mutations in a line range, in line order."""
    results: List[Dict[str, Any]] = []
    _walk_assignments(func_node, from_line, to_line, get_text, results)
    for e in collect_effects(func_node, from_line, to_line, get_text, language):
        if e['kind'] in _CALL_KINDS:
            results.append({
                'kind': e['kind'], 'line': e['line'], 'target': e['callee'], 'via': 'call',
            })
    results.sort(key=lambda r: r['line'])
    return results


def render_statewrites(writes: List[Dict[str, Any]], from_line: int, to_line: int) -> str:
    """Render collect_statewrites output as text (flat, in line order)."""
    if not writes:
        return f'No state writes found in lines {from_line}–{to_line}'
    kind_width = max(len(w['kind']) for w in writes)
    lines = []
    for w in writes:
        lines.append(f'L{w["line"]:<6}  {w["kind"]:<{kind_width}}  {w["target"]}')
    return '\n'.join(lines)
