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

import re
import warnings
from typing import List, Tuple


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

    `kind`, `start_position`, and `end_position` don't just flip
    method→property: they're Rust `tree_sitter::Node` method names that the
    pre-1.12.5 vendored `builtins.Node` leaked straight into Python, but the
    real core `tree_sitter.Node` binding (>=1.12.5) has never exposed by
    those names at all — confirmed live in isolated venvs
    (torrential-breeze-0821, tree-sitter 0.23.0 through 0.26.0) and via
    upstream release notes (BACK-1158's root-cause note: this is a naming
    seam between two independently-named official tree-sitter APIs, not a
    deprecation). The core binding's real Python-side names are `.type`,
    `.start_point`, and `.end_point` (same values, different names, present
    in both eras). So `getattr(obj, name)` raises AttributeError
    unconditionally once the ceiling lifts for these three; fall back to the
    renamed equivalent rather than pushing this asymmetry onto every call
    site.
    """
    try:
        val = getattr(obj, name)
    except AttributeError:
        if name == 'kind':
            return obj.type
        if name == 'start_position':
            return obj.start_point  # noqa: ts-accessor (the seam)
        if name == 'end_position':
            return obj.end_point  # noqa: ts-accessor (the seam)
        raise
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


def node_sexp(node) -> str:
    """S-expression of `node`, tolerant of the binding split (same seam as `_zero_arg`).

    The vendored `builtins.Node` exposes `to_sexp()`; the real core `tree_sitter.Node`
    (what CI's Python 3.12/3.14 matrix installs) has no such method -- `str(node)` is its
    s-expression. Calling `to_sexp()` directly passed locally and failed on every CI job.
    """
    for name in ('to_sexp', 'sexp'):
        fn = getattr(node, name, None)
        if callable(fn):
            return str(fn())
    return str(node)


def error_node_spans(root) -> List[Tuple[int, int]]:
    """1-based (first_line, last_line) of every outermost ERROR node under `root`.

    Only subtrees whose `has_error` flag is set are entered, so a clean tree costs
    one flag read. A nested ERROR is covered by its outermost one. BACK-1480: a
    scanner that walks the whole tree needs to know which lines lie in a region
    where tree-sitter lost its place and recovered with a guess.
    """
    spans: List[Tuple[int, int]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if not _zero_arg(node, 'has_error'):
            continue
        if _zero_arg(node, 'kind') == 'ERROR':
            spans.append((_zero_arg(node, 'start_position').row + 1,
                          _zero_arg(node, 'end_position').row + 1))
            continue
        stack.extend(node_children(node))
    return spans


def tree_has_recovery_artifacts(tree) -> bool:
    """True if the parse was not fully clean: an ERROR node OR a MISSING token
    inserted during error recovery (BACK-1084; see
    `TreeSitterAnalyzer._has_recovery_artifacts` for why this is wider than an
    ERROR-node check). A lone trailing end-of-file MISSING quirk is not flagged.
    """
    root = tree_root(tree)
    if not _zero_arg(root, 'has_error'):
        return False
    if error_node_spans(root):
        return True
    # No ERROR node: only MISSING tokens remain. A lone MISSING at the very end
    # of the tree, named like an anonymous `<rule>_token<N>` (Go: a file ending
    # in an interface type; C: an #include-only unit), is the same benign
    # end-of-file grammar quirk -- the structure is complete, so don't alarm.
    # Zero-width MISSING nodes are not reachable through child(), so read the
    # s-expression (only ever built for an already-flagged tree).
    sexp = node_sexp(root).strip()
    missing = re.findall(r'\(MISSING\b', sexp)
    return not (len(missing) == 1 and re.search(r'\(MISSING "?\w*_token\d+"?\)\)$', sexp))
