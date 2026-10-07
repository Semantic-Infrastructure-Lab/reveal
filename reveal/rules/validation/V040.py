"""
V040: Tree-sitter Node accessor that breaks on the language-pack 1.8.1 floor.

Flags, in ``reveal/`` and ``tests/``, a read of a tree-sitter Node member that is a
bound METHOD on the tree-sitter-language-pack 1.8.1 floor (the vendored
``builtins.Node``) and a plain property from 1.12.5 on, or that the floor lacks:

* a bare ``.start_byte`` / ``.end_byte`` / ``.start_point`` / ``.end_point`` /
  ``.child_count`` / ``.has_error`` / ``.is_missing`` / ``.to_sexp`` read -- go
  through ``reveal.core.treesitter_compat._zero_arg(node, 'start_byte')``;
* ``.field_name_for_child`` / ``.field_name_for_named_child`` -- absent on the floor;
* a bare ``.children`` on a node (receiver-restricted, in a file that touches
  tree-sitter) -- use ``node_children(node)``;
* ``node_a == node_b`` / ``!=`` between two node-named operands -- the floor's Node
  compares by identity; compare ``(start_byte, end_byte)`` spans.

Such code passes on every runner that installs a recent pack and fails only on CI's
compat leg pinned to the floor (BACK-1406, BACK-1700). This is
``scripts/check_treesitter_accessors.py`` moved into the V-series (BACK-1707): same
patterns, same suppression, same findings. It is strict, not baselined.

Suppress a deliberate bare read (the seam itself) with ``# noqa: ts-accessor`` (the
spelling the repo already uses) or ``# noqa: V040`` on any line of the expression.

Examples:
    reveal reveal:// --check --select V040
"""

import ast
import re
from typing import Any, Dict, List, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import has_noqa, load_sources, parse_test_module
from reveal.utils.lines import split_lines

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


def find_offenders(source: str, tree: ast.Module) -> List[Tuple[int, str]]:
    """(line, kind) for every floor hazard in `source` (whose parse is `tree`): a bare read
    of a guarded accessor (kind = its name), ``field_name_for_child``, a node ``.children``
    or a node ``==``."""
    lines = split_lines(source)
    # An Attribute's only child expression is its .value, so `mock.<name>.return_value` is
    # found from the outer Attribute (no whole-tree parent map: that cost ~8s over the repo).
    mock_stubs = {id(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Attribute) and n.attr in MOCK_ATTRS}
    ts_file = bool(TS_FILE.search(source))
    found = []

    def suppressed(node: ast.AST) -> bool:
        span = lines[node.lineno - 1:(node.end_lineno or node.lineno)]
        return any(NOQA in line or has_noqa(line, 'V040') for line in span)

    for node in ast.walk(tree):
        kind = None
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            if node.attr in NAMES and id(node) not in mock_stubs:
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


def _accessor_advice(name: str) -> str:
    return _ADVICE.get(name) or (
        f"use _zero_arg(node, '{name}') (a method on language-pack 1.8.1, a property later)")


class V040(BaseRule):
    """Detect tree-sitter Node accessors that break on the language-pack 1.8.1 floor.

    Severity: MEDIUM -- green on every runner with a recent pack, red on CI's floor leg.
    Category: Validation

    Detects (in ``reveal/`` and ``tests/``):
    - bare ``.start_byte``/``.end_byte``/``.start_point``/``.end_point``/``.child_count``/
      ``.has_error``/``.is_missing``/``.to_sexp`` reads
    - ``.field_name_for_child``/``.field_name_for_named_child``
    - ``.children`` on a node-named receiver and ``==``/``!=`` between node-named operands,
      in a file that touches tree-sitter

    Passes:
    - ``_zero_arg(node, 'start_byte')``, ``node_children(node)``, span comparisons
    - writes, ``mock.<name>.return_value``/``.side_effect``
    - ``# noqa: ts-accessor`` (or ``# noqa: V040``) on a line of the expression
    """

    code = "V040"
    message = "Tree-sitter Node accessor that breaks on the language-pack 1.8.1 floor"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    uri_patterns = ['^reveal://.*']
    internal = True
    version = "1.0.0"

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        if not file_path.startswith('reveal://'):
            return []
        detections: List[Detection] = []
        for display, source in load_sources(self, TREES, lambda path: True):
            tree = parse_test_module(self, display, source)
            if tree is None:
                continue
            lines = split_lines(source)
            for lineno, name in find_offenders(source, tree):
                label = 'Node ==' if name == '==' else f"bare .{name}"
                detections.append(self.create_detection(
                    display, lineno,
                    message=f"{label} breaks on tree-sitter-language-pack 1.8.1",
                    suggestion=_accessor_advice(name),
                    context=lines[lineno - 1].strip(),
                ))
        return detections
