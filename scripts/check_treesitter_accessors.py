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

This is strict, not a baseline: the tree has no other offenders, so any new one is a regression.

Run:
    python scripts/check_treesitter_accessors.py       # exits 1 on any offender
"""

import ast
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


def find_offenders(source: str) -> List[Tuple[int, str]]:
    """(line, accessor) for every bare read of a guarded accessor in `source`."""
    tree = ast.parse(source)
    lines = source.splitlines()
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr not in NAMES:
            continue
        if not isinstance(node.ctx, ast.Load):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.attr in MOCK_ATTRS:
            continue
        span = lines[node.lineno - 1:(node.end_lineno or node.lineno)]
        if any(NOQA in line for line in span):
            continue
        found.append((node.lineno, node.attr))
    return sorted(found)


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
                print(f"{path.relative_to(ROOT)}:{line}: bare .{name} -- use "
                      f"_zero_arg(node, '{name}') (a method on language-pack 1.8.1, a property later)")
                failures += 1
    if failures:
        print(f"\n{failures} bare tree-sitter accessor read(s). See scripts/check_treesitter_accessors.py.")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
