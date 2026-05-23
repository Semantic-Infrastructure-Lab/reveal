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
# attributes as methods (kind(), child_count(), parent(), start_byte(), ...).
# It also removes node.children, node.prev_sibling, node.next_sibling, and
# node equality by value. These helpers restore ergonomic access patterns
# without inlining list comprehensions and parent-walking everywhere.


def node_children(node):
    """Return all children of a tree-sitter 1.x node as a list.

    Replaces 0.x `node.children` (removed in 1.x).
    """
    return [node.child(i) for i in range(node.child_count())]


def node_prev_sibling(node):
    """Return the previous sibling of a tree-sitter 1.x node, or None.

    Replaces 0.x `node.prev_sibling` (removed in 1.x). Locates the node in
    its parent's child list by start_byte (node equality is unreliable in
    1.x — same node returns False under `==`).
    """
    parent = node.parent()
    if parent is None:
        return None
    sb = node.start_byte()
    for i in range(parent.child_count()):
        if parent.child(i).start_byte() == sb:
            return parent.child(i - 1) if i > 0 else None
    return None


def node_next_sibling(node):
    """Return the next sibling of a tree-sitter 1.x node, or None.

    Replaces 0.x `node.next_sibling` (removed in 1.x). See node_prev_sibling
    for the rationale behind start_byte-based matching.
    """
    parent = node.parent()
    if parent is None:
        return None
    sb = node.start_byte()
    for i in range(parent.child_count()):
        if parent.child(i).start_byte() == sb:
            idx = i + 1
            return parent.child(idx) if idx < parent.child_count() else None
    return None
