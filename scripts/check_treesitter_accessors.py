"""Guard: tree-sitter Node accessors are read through ``_zero_arg``, never bare.

``node.start_byte`` is a bound METHOD on the tree-sitter-language-pack 1.8.1 floor (the vendored
``builtins.Node``) and a plain property from 1.12.5 on. A bare read passes on every runner that
installs a recent pack and fails only on CI's compat leg pinned to the floor -- exactly how
BACK-1406's test helper (``data[node.start_byte:node.end_byte]``) reached CI red after a green
3-version ``ci-local.sh --matrix``. ``reveal.core.treesitter_compat._zero_arg(node, 'start_byte')``
is the seam that reads either shape.

Flagged: any read of ``.start_byte`` / ``.end_byte`` / ``.start_point`` / ``.end_point`` /
``.child_count`` / ``.has_error`` / ``.is_missing`` / ``.to_sexp`` in ``reveal/`` and ``tests/``.
Not flagged: writes, and ``mock.<name>.return_value`` / ``.side_effect`` (a MagicMock standing in
for a method). Suppress a deliberate bare read with ``# noqa: ts-accessor`` on that line -- the seam
itself (``treesitter_compat.py``) is the intended user.

Also flagged (BACK-1700; each reached CI red on the floor leg after a green local run):
  - ``.field_name_for_child`` / ``.field_name_for_named_child`` -- absent on the floor; use
    ``child_by_field_name(...)`` per field and compare spans.
  - bare ``.children`` on a tree-sitter node -- absent on the floor; use
    ``node_children(node)``. Python ``.children`` also exists on reveal's Element model, so this is
    receiver-restricted: only in a file that imports tree-sitter machinery
    (``treesitter_compat`` / ``tree_sitter`` / ``ts_parse`` / ``tree_root``), and only on a node-named
    receiver (``node``, ``child``, ``n``, ``root``, ``*_node``, ...) or a call that returns a node
    (``tree_root(...)``, ``.child(...)``, ``.root_node``, ``.child_by_field_name(...)``).
  - ``node_a == node_b`` / ``!=`` between two node-named operands -- the floor's vendored Node
    compares by identity, so two handles on the same node differ; compare
    ``(_zero_arg(n, 'start_byte'), _zero_arg(n, 'end_byte'))`` spans. ``in`` over a list of nodes
    is the same hazard and is not detected (no type information); sets hash, so they are not it.

This is strict, not a baseline: the tree has no other offenders, so any new one is a regression.

Run:
    python scripts/check_treesitter_accessors.py       # exits 1 on any offender
"""

import ast
import re
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
TREES = ('reveal', 'tests')
NAMES = frozenset({
    'start_byte', 'end_byte', 'start_point', 'end_point',
    'child_count', 'has_error', 'is_missing', 'to_sexp',
})
MOCK_ATTRS = frozenset({'return_value', 'side_effect'})
NOQA = 'noqa: ts-accessor'

# BACK-1700: methods the 1.8.1 floor's vendored Node lacks (unique names, so any read is a hit).
MISSING_ON_FLOOR = frozenset({'field_name_for_child', 'field_name_for_named_child'})
# A file that touches tree-sitter nodes at all; gates the receiver-name heuristics below.
TS_FILE = re.compile(r'treesitter_compat|tree_sitter|\bts_parse\b|\btree_root\b|\bnode_children\b')
NODE_NAME = re.compile(r'^(node|child|n|root|root_node|cur|current|sibling|\w+_node)$')
NODE_CALLS = frozenset({'tree_root', 'child', 'child_by_field_name', 'named_child', 'root_node'})


def _is_node_expr(expr: ast.AST) -> bool:
    """A receiver that is, by its name or by what produced it, a tree-sitter node."""
    if isinstance(expr, ast.Name):
        return bool(NODE_NAME.match(expr.id))
    if isinstance(expr, ast.Call):
        func = expr.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')
        return name in NODE_CALLS
    return isinstance(expr, ast.Attribute) and expr.attr == 'root_node'


def find_offenders(source: str) -> List[Tuple[int, str]]:
    """(line, kind) for every floor hazard in `source`: a bare read of a guarded accessor
    (kind = its name), ``field_name_for_child``, a node ``.children`` or a node ``==``."""
    tree = ast.parse(source)
    lines = source.splitlines()
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    ts_file = bool(TS_FILE.search(source))
    found = []

    def suppressed(node: ast.AST) -> bool:
        span = lines[node.lineno - 1:(node.end_lineno or node.lineno)]
        return any(NOQA in line for line in span)

    for node in ast.walk(tree):
        kind = None
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            parent = parents.get(node)
            if node.attr in NAMES and not (isinstance(parent, ast.Attribute) and parent.attr in MOCK_ATTRS):
                kind = node.attr
            elif node.attr in MISSING_ON_FLOOR:
                kind = node.attr
            elif node.attr == 'children' and ts_file and _is_node_expr(node.value):
                kind = 'children'
        elif isinstance(node, ast.Compare) and ts_file:
            operands = [node.left, *node.comparators]
            for op, left, right in zip(node.ops, operands, operands[1:]):
                if isinstance(op, (ast.Eq, ast.NotEq)) and _is_node_expr(left) and _is_node_expr(right):
                    kind = '=='
        if kind and not suppressed(node):
            found.append((node.lineno, kind))
    return sorted(found)


_ADVICE = {
    'field_name_for_child': "absent on language-pack 1.8.1 -- use child_by_field_name(...) and compare spans",
    'field_name_for_named_child': "absent on language-pack 1.8.1 -- use child_by_field_name(...) and compare spans",
    'children': "absent on language-pack 1.8.1 -- use node_children(node) (reveal.core.treesitter_compat)",
    '==': "the 1.8.1 vendored Node compares by identity -- compare (_zero_arg(n, 'start_byte'), "
          "_zero_arg(n, 'end_byte')) spans",
}


def main() -> int:
    failures = 0
    for tree in TREES:
        for path in sorted((ROOT / tree).rglob('*.py')):
            try:
                source = path.read_text(encoding='utf-8')
                offenders = find_offenders(source)
            except (SyntaxError, UnicodeDecodeError):
                continue
            for line, name in offenders:
                advice = _ADVICE.get(name) or (
                    f"use _zero_arg(node, '{name}') (a method on language-pack 1.8.1, a property later)")
                label = 'Node ==' if name == '==' else f"bare .{name}"
                print(f"{path.relative_to(ROOT)}:{line}: {label} -- {advice}")
                failures += 1
    if failures:
        print(f"\n{failures} tree-sitter floor hazard(s). See scripts/check_treesitter_accessors.py.")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
