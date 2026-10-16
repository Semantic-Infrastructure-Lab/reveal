"""BACK-1865 / BACK-1866: the perf rewrites must not change an answer.

BACK-1865: `_complexity_depth_and_calls` reads each node's kind once and takes
its accessor from `zero_arg_getter` instead of `_zero_arg` per read.
BACK-1866: `_code_line_count` bisects a per-file blank/comment index instead of
rescanning every line and comment per function.

Each is pinned against the retired implementation, run on real parsed code.
"""

from pathlib import Path
from unittest import mock

import pytest

from reveal.analyzers.python import PythonAnalyzer
from reveal.core.treesitter_compat import _zero_arg, zero_arg_getter

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component

SAMPLE = '''\
"""module docstring"""

# own-line comment before f


def f(a):
    """Docstring
    spanning rows.
    """
    x = a  # trailing comment keeps this row as code

    # own-line comment inside
    if x:
        def inner():
            # nested comment
            return 1

        return inner()
    return 0


def g():
    return f(1)  # trailing
'''


def _analyzer(tmp_path: Path) -> PythonAnalyzer:
    path = tmp_path / "sample.py"
    path.write_text(SAMPLE, encoding="utf-8")
    return PythonAnalyzer(str(path))


def _old_code_line_count(analyzer, body_node, line_start, line_end):
    """The pre-BACK-1866 algorithm, verbatim."""
    lo, hi = line_start - 1, line_end - 1
    non_code_rows = {
        row for row in range(lo, min(hi, len(analyzer.lines) - 1) + 1)
        if not analyzer.lines[row].strip()
    }
    analyzer._find_nodes_by_type('comment')
    for kind, nodes in (analyzer._node_cache or {}).items():
        if 'comment' not in kind:
            continue
        for comment_node in nodes:
            row = _zero_arg(comment_node, 'start_position').row
            if lo <= row <= hi:
                analyzer._mark_non_code_rows(comment_node, non_code_rows)
    docstring = analyzer._leading_docstring_node(body_node)
    if docstring is not None:
        analyzer._mark_non_code_rows(docstring, non_code_rows)
    return (hi - lo + 1) - len(non_code_rows)


def test_code_line_count_matches_the_retired_scan_for_every_span(tmp_path):
    analyzer = _analyzer(tmp_path)
    body = next(iter(analyzer._find_nodes_by_type('function_definition')))
    total = len(analyzer.lines)
    checked = 0
    for start in range(1, total + 1):
        for end in range(start, total + 3):  # includes spans past EOF
            assert analyzer._code_line_count(body, start, end) == _old_code_line_count(
                analyzer, body, start, end), (start, end)
            checked += 1
    assert checked > 200


def test_code_line_count_negative_control_detects_a_wrong_index(tmp_path):
    analyzer = _analyzer(tmp_path)
    body = next(iter(analyzer._find_nodes_by_type('function_definition')))
    analyzer._line_index = ([], [], [])  # an index that forgot every blank row and comment
    assert analyzer._code_line_count(body, 1, len(analyzer.lines)) != _old_code_line_count(
        analyzer, body, 1, len(analyzer.lines))


def test_function_entries_carry_the_same_complexity_depth_calls(tmp_path):
    items = {f['name']: f for f in _analyzer(tmp_path).get_structure()['functions']}
    assert items['f']['calls'] == ['inner']
    # values the retired implementation reported for this sample (HEAD 18c02c80)
    assert (items['f']['complexity'], items['f']['depth'], items['f']['code_line_count']) == (2, 2, 7)
    assert (items['inner']['complexity'], items['inner']['depth'], items['inner']['code_line_count']) == (1, 0, 2)
    assert items['g']['calls'] == ['f']


def test_zero_arg_getter_equals_zero_arg_on_real_nodes(tmp_path):
    analyzer = _analyzer(tmp_path)
    nodes = analyzer._find_nodes_by_type('function_definition')
    assert nodes
    for name in ('kind', 'start_byte', 'child_count'):
        getter = zero_arg_getter(type(nodes[0]), name)
        for node in nodes:
            assert getter(node) == _zero_arg(node, name)


def test_zero_arg_getter_falls_back_per_call_for_unclassifiable_classes():
    fake = mock.Mock()
    fake.kind = 'identifier'
    assert zero_arg_getter(type(fake), 'kind')(fake) == _zero_arg(fake, 'kind') == 'identifier'


def test_find_uncalled_collects_structures_once_back1868(tmp_path):
    """find_uncalled used to build every file's structure twice (once itself, once in build_callers_index)."""
    from reveal.adapters.calls import index as calls_index

    (tmp_path / "m.py").write_text("def used():\n    return 1\n\ndef dead():\n    return used()\n", encoding="utf-8")
    calls_index._INDEX_CACHE.clear()
    with mock.patch.object(calls_index, "collect_structures", wraps=calls_index.collect_structures) as spy:
        result = calls_index.find_uncalled(str(tmp_path))
    assert spy.call_count == 1
    assert [e["name"] for e in result["entries"]] == ["dead"]


def test_extract_function_body_splits_a_file_once_back1869():
    """D001/D002 ask for every function body of one file; the file used to be re-split per function."""
    from reveal.rules.duplicates import _bodies

    content = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    _bodies._file_lines.cache_clear()
    with mock.patch.object(_bodies, "split_lines", wraps=_bodies.split_lines) as spy:
        bodies = [
            _bodies.extract_function_body({'line': 1, 'line_end': 2}, content),
            _bodies.extract_function_body({'line': 4, 'line_end': 5}, content),
            _bodies.extract_function_body({'line': 1, 'line_end': 2}, content),
        ]
    assert bodies == ["    return 1", "    return 2", "    return 1"]
    assert spy.call_count == 1
