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

_ASSIGNMENT_NODES: frozenset = frozenset({
    'assignment', 'augmented_assignment', 'assignment_expression',
    'augmented_assignment_expression', 'assignment_statement', 'compound_assignment_expr',
})

_MEMBER_ACCESS_NODES: frozenset = frozenset({
    'attribute', 'member_access_expression', 'field_expression',
    'selector_expression', 'member_expression',
    # Java's `this.x`/`obj.x` (BACK-439c conformance-matrix pass) — distinct
    # kind from every other Tier 1 language's member-access shape.
    'field_access',
})

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
        left = node.child_by_field_name('left')
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
