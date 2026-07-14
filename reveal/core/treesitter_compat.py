"""
Tree-sitter compatibility layer.

This module centralizes tree-sitter compatibility concerns, primarily
managing deprecation warnings from the tree-sitter library.

Background:
-----------
The tree-sitter Python bindings emit FutureWarning messages about API changes.
These warnings are external to reveal and don't affect functionality, but they
clutter output and confuse users.

Rather than scattering warning suppression across multiple files, we centralize
it here for:
1. DRY principle - single source of truth
2. Easy maintenance - one place to update when tree-sitter stabilizes
3. Clear documentation - explicit reasoning for suppression
4. Future migration path - when tree-sitter API stabilizes, remove this

Usage:
------
Import at the top of any module that uses tree-sitter:

    from reveal.core import suppress_treesitter_warnings
    suppress_treesitter_warnings()

Previous Locations (before centralization):
- reveal/treesitter.py:8
- reveal/adapters/ast.py:12
- reveal/registry.py:194

Related Issues:
- Tree-sitter-language-pack v0.33.0 migration (2026-01-11)
- Mobile platform test fixes (session: interstellar-blackhole-0113)
"""

import warnings


def suppress_treesitter_warnings():
    """
    Suppress FutureWarning messages from tree-sitter library.

    The tree-sitter Python bindings emit deprecation warnings that don't
    affect reveal's functionality. We suppress them to keep output clean.

    This is safe because:
    1. Warnings are about tree-sitter's internal API changes
    2. tree-sitter-language-pack handles compatibility
    3. Our usage is stable and tested
    4. We'll update if tree-sitter makes breaking changes

    Call this once at module initialization in any module using tree-sitter.

    Example:
        from reveal.core import suppress_treesitter_warnings
        suppress_treesitter_warnings()

        import tree_sitter_language_pack as tslp  # Now warning-free
    """
    warnings.filterwarnings(
        'ignore',
        category=FutureWarning,
        module='tree_sitter'
    )


# ─── 1.x API helpers ────────────────────────────────────────────────────────
# tree-sitter-language-pack 1.x is a Rust/PyO3 rewrite that exposes node
# attributes as methods (kind(), child_count(), parent(), start_byte(), ...)
# on versions before 1.12.5, and as plain properties from 1.12.5 on (see
# `_zero_arg` below and BACK-573). It also removes node.children,
# node.prev_sibling, node.next_sibling, and node equality by value. These
# helpers restore ergonomic access patterns without inlining list
# comprehensions and parent-walking everywhere.


def _zero_arg(obj, name):
    """Read a zero-argument Node/TreeCursor accessor, tolerant of the 1.12.5
    method→property flip (BACK-573): `child_count`, `parent`, `start_byte`,
    `root_node`, `cursor.node`, etc. are bound methods pre-1.12.5 and plain
    properties from 1.12.5 on. `child(i)` (takes an index) is unaffected —
    it stays a real method in both — so callers use `node.child(i)` directly.
    """
    val = getattr(obj, name)
    return val() if callable(val) else val


def node_children(node):
    """Return all children of a tree-sitter 1.x node as a list.

    Replaces 0.x `node.children` (removed in 1.x).
    """
    return [node.child(i) for i in range(_zero_arg(node, 'child_count'))]


def iter_tree(node):
    """Yield `node` and every descendant in pre-order (document order).

    Uses a `TreeCursor` (`node.walk()`), which traverses the subtree in the
    native layer without materializing a Python child-list per node the way a
    `node_children`-based stack walk does. Measured ~1.79x faster than the
    equivalent `[node.child(i) ...]` stack walk on a real 250KB TypeScript
    file (48,953 nodes), with an identical node set and order — see BACK-489
    design doc §8.2/§8.3 (P2). Pre-order means the sequence of nodes matches a
    `stack=[root]; pop; push reversed(children)` walk exactly, so callers that
    bucket nodes by kind get byte-identical document-ordered lists.

    Note: a cursor from `node.walk()` will not ascend above `node` itself
    (`goto_parent()` returns False at the starting node), so this correctly
    yields only `node`'s own subtree even when `node` is not the tree root.
    """
    cursor = node.walk()
    reached_root = False
    while not reached_root:
        yield _zero_arg(cursor, 'node')
        if cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        retracing = True
        while retracing:
            if not cursor.goto_parent():
                retracing = False
                reached_root = True
            elif cursor.goto_next_sibling():
                retracing = False


def node_prev_sibling(node):
    """Return the previous sibling of a tree-sitter 1.x node, or None.

    Replaces 0.x `node.prev_sibling` (removed in 1.x). Locates the node in
    its parent's child list by start_byte (node equality is unreliable in
    1.x — same node returns False under `==`).
    """
    parent = _zero_arg(node, 'parent')
    if parent is None:
        return None
    sb = _zero_arg(node, 'start_byte')
    for i in range(_zero_arg(parent, 'child_count')):
        if _zero_arg(parent.child(i), 'start_byte') == sb:
            return parent.child(i - 1) if i > 0 else None
    return None


def node_next_sibling(node):
    """Return the next sibling of a tree-sitter 1.x node, or None.

    Replaces 0.x `node.next_sibling` (removed in 1.x). See node_prev_sibling
    for the rationale behind start_byte-based matching.
    """
    parent = _zero_arg(node, 'parent')
    if parent is None:
        return None
    sb = _zero_arg(node, 'start_byte')
    for i in range(_zero_arg(parent, 'child_count')):
        if _zero_arg(parent.child(i), 'start_byte') == sb:
            idx = i + 1
            return parent.child(idx) if idx < _zero_arg(parent, 'child_count') else None
    return None


# ─── 1.12.5+ forward-compat helpers (BACK-573) ─────────────────────────────
# tree-sitter-language-pack 1.12.5 changed two calling conventions within the
# 1.x line: `Tree.root_node` flipped from a callable method to a property,
# and `Parser.parse()` started requiring `bytes` instead of `str`. reveal is
# pinned to `<1.12.5` (BACK-574) as the durable stopgap; these two helpers
# are the real forward-compat fix, tolerant of both conventions, so the
# ceiling can eventually be lifted without a flag-day rewrite of every call
# site. Verified against both tree-sitter-language-pack==1.8.1 (method/str,
# the pinned floor) and ==1.12.5 (property/bytes) in isolated venvs.


def tree_root(tree):
    """Return a parsed Tree's root node, across the 1.12.5 method→property change.

    `tree.root_node` is a bound method pre-1.12.5 (call it) and a Node
    property from 1.12.5 on (use it directly). Accessing the attribute is
    side-effect-free either way — only a plain method reference is returned
    pre-1.12.5, never invoked, until `_zero_arg` checks `callable()`.
    """
    return _zero_arg(tree, 'root_node')


def ts_parse(parser, source):
    """Parse `source` (str) with a tree-sitter 1.x parser, across the
    1.12.5 str→bytes change in `Parser.parse()`.

    Tries the pre-1.12.5 `str` calling convention first (the pinned floor,
    1.8.1, in normal operation), falling back to UTF-8-encoded `bytes` on
    the `TypeError` 1.12.5+ raises for a `str` argument.
    """
    try:
        return parser.parse(source)
    except TypeError:
        return parser.parse(source.encode('utf-8'))
