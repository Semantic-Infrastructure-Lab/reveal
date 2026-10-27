"""M104 must not recurse once per tree level (BACK-2252).

`reveal overview` on a Go tree printed a raw traceback ("maximum recursion
depth exceeded") for a vendored table whose composite literal nests deeper
than the interpreter's recursion limit. The source is generated here; no
large fixture is committed.
"""

import os
import sys
import tempfile

import pytest

from reveal.core.treesitter_compat import _zero_arg, tree_root
from reveal.core.treesitter_parse import get_tree
from reveal.rules.maintainability import _m104_treesitter
from reveal.rules.maintainability.M104 import M104

pytestmark = pytest.mark.component

_EXTS = '[]string{".py", ".js", ".ts", ".go", ".rs", ".java"}'


def _deep_go(depth: int) -> str:
    """A Go file: a constant string concatenated from `depth` operands (a left-nested
    `binary_expression` chain `depth` levels deep, as in x/text's packed tables, with no
    composite literal to stop the search), then an ordinary risky list."""
    chain = ' + '.join(['"ab"'] * depth)
    return (
        'package p\n\n'
        f'const Deep = {chain}\n\n'
        f'var Extensions = {_EXTS}\n'
    )


def _check_go(source: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'tables.go')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(source)
        return M104().check(path, None, source)


def test_expression_nested_past_recursion_limit_is_checked():
    depth = sys.getrecursionlimit() + 500
    detections = _check_go(_deep_go(depth))
    assert [d.line for d in detections] == [5], detections
    assert "Extensions" in detections[0].message


def test_shallow_file_detects_the_same_list():
    """Negative control: a file under the limit reports the same collection."""
    detections = _check_go(_deep_go(3))
    assert [d.line for d in detections] == [5], detections
    assert "Extensions" in detections[0].message


def test_find_descendant_returns_first_match_in_document_order():
    """Negative control: the first descendant in pre-order wins, not the shallowest."""
    source = 'package p\n\nvar X = f([]string{"a"}, [][]int{{1}})\n'
    tree = get_tree('go', source, filename='x.go')
    root = tree_root(tree)
    found = _m104_treesitter._find_descendant(root, frozenset({'composite_literal'}))
    assert found is not None
    text = source.encode('utf-8')[_zero_arg(found, 'start_byte'):_zero_arg(found, 'end_byte')].decode('utf-8')
    assert text.startswith('[]string')
