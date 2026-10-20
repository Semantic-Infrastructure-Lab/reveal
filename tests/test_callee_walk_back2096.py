"""One forward call walk for calls://?root= and trace (BACK-2096, BACK-2066 slice B).

Two recursive callee walks answered the same question differently, each wrong in its own way:
- trace walked depth-first and never expanded a definition a second time, so a definition first
  reached deep in the walk was never expanded at the shallower level that reaches it later
  (fixture a: f calls a and c, a->b->c, c->d; at depth 3 c's callee d vanished);
- ?root dropped the edge, not only the expansion, once its target had been seen, and shared that
  set across root definitions (fixture b: two definitions of X each call helper; one edge).

Each test asserts the answer (an edge or frame set), not the presence of a field.
"""

from pathlib import Path

import pytest

from reveal.adapters.calls.adapter import CallsAdapter
from reveal.adapters.calls.index import _bare_callee_name, find_callees
from reveal.adapters.trace import TraceAdapter
from reveal.utils.path_utils import to_posix

# Fixtures copied from the manager's repro (colliding-asteroid-1019/repro/d2066/{a,b}).
FIXTURE_A = {'m.py': 'def f():\n    a()\n    c()\n\ndef a():\n    b()\n\ndef b():\n    c()\n\n'
                     'def c():\n    d()\n\ndef d():\n    pass\n'}
FIXTURE_B = {'one.py': 'def X():\n    helper()\n\ndef helper():\n    pass\n',
             'two.py': 'def X():\n    helper()\n'}
CYCLE = {'m.py': 'def f():\n    g()\n\ndef g():\n    f()\n'}


def _tree(tmp_path: Path, files: dict) -> str:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    return str(tmp_path)


def _root_edges(path: str, root: str, depth: int) -> set:
    """(caller file, caller, callee, level) for every ?root edge."""
    result = CallsAdapter(path, f'root={root}&depth={depth}').get_structure()
    assert result['type'] == 'calls_callees_recursive'
    return {(Path(e['caller_file']).name, e['caller'], e['callee'], level['level'])
            for level in result['levels'] for e in level['callees']}


def _trace(path: str, root: str, depth: int) -> dict:
    result = TraceAdapter(path, f'from={root}&depth={depth}').get_structure()
    assert result['type'] == 'trace'
    return result


def _trace_edges(result: dict) -> set:
    """(caller file, caller, callee label) for every call listed by an expanded frame."""
    return {(Path(f['file']).name, f['name'], label) for f in result['frames'] for label in f['calls']}


def _trace_nodes(result: dict) -> set:
    return {(f['name'], f['depth']) for f in result['frames']}


# --- red: fixture a at depth 3 -------------------------------------------------------------

def test_trace_expands_a_definition_at_its_shallowest_level(tmp_path):
    # Old trace: c was first reached at depth 3 (f->a->b->c) and so never expanded at depth 1
    # (f->c): frames f@0 a@1 b@2 c@3, and c->d was missing.
    result = _trace(_tree(tmp_path, FIXTURE_A), 'f', 3)
    assert _trace_nodes(result) == {('f', 0), ('a', 1), ('b', 2), ('c', 1), ('d', 2)}
    assert _trace_edges(result) == {('m.py', 'f', 'a'), ('m.py', 'f', 'c'), ('m.py', 'a', 'b'),
                                    ('m.py', 'b', 'c'), ('m.py', 'c', 'd')}


def test_root_lists_an_edge_to_an_already_reached_definition(tmp_path):
    # Old ?root: b->c (level 3) was dropped because c had been seen at level 1.
    assert _root_edges(_tree(tmp_path, FIXTURE_A), 'f', 3) == {
        ('m.py', 'f', 'a', 1), ('m.py', 'f', 'c', 1),
        ('m.py', 'a', 'b', 2), ('m.py', 'c', 'd', 2),
        ('m.py', 'b', 'c', 3)}


# --- red: fixture b at depth 1 -------------------------------------------------------------

def test_root_lists_each_root_definitions_edges(tmp_path):
    # Old ?root: two.py's X -> helper was dropped because one.py's X had reached helper first.
    assert _root_edges(_tree(tmp_path, FIXTURE_B), 'X', 1) == {
        ('one.py', 'X', 'helper', 1), ('two.py', 'X', 'helper', 1)}


def test_trace_lists_each_root_definitions_edges(tmp_path):
    # Already right in the old trace; it must stay right on the shared walker.
    result = _trace(_tree(tmp_path, FIXTURE_B), 'X', 1)
    assert _trace_edges(result) == {('one.py', 'X', 'helper'), ('two.py', 'X', 'helper')}


# --- cycle: terminates and lists both edges -------------------------------------------------

def test_root_cycle_terminates_and_lists_both_edges(tmp_path):
    # Old ?root dropped g->f: f is a root, so it was in the seen set from the start.
    assert _root_edges(_tree(tmp_path, CYCLE), 'f', 5) == {('m.py', 'f', 'g', 1), ('m.py', 'g', 'f', 2)}


def test_trace_cycle_terminates_and_lists_both_edges(tmp_path):
    result = _trace(_tree(tmp_path, CYCLE), 'f', 5)
    assert _trace_nodes(result) == {('f', 0), ('g', 1)}
    assert _trace_edges(result) == {('m.py', 'f', 'g'), ('m.py', 'g', 'f')}


# --- negative control: level-1 edges are find_callees' call lists, per language -------------

LANGUAGES = {
    'python': ('root', {'m.py': 'def root():\n    helper()\n    obj.method()\n    print("x")\n'
                                '    sorted([])\n\ndef helper():\n    pass\n'}),
    'javascript': ('root', {'m.js': 'function root() {\n  helper();\n  this.other();\n  console.log(1);\n}\n'
                                    'function helper() {}\n'}),
    'go': ('root', {'m.go': 'package main\n\nimport "fmt"\n\nfunc root() {\n\thelper()\n\tfmt.Println("x")\n'
                            '\tlen("x")\n}\n\nfunc helper() {}\n'}),
    'cpp': ('run', {'m.cpp': 'namespace ns { void helper() {} }\nvoid Widget::run() {\n    ns::helper();\n'
                             '    this->draw();\n    std::move(x);\n}\n'}),
    'lua': ('root', {'m.lua': 'local M = {}\nfunction M:root()\n  self:helper()\n  print("x")\n'
                              '  string.format("%d", 1)\nend\nfunction M:helper()\nend\nreturn M\n'}),
    'php': ('root', {'m.php': '<?php\nclass A {\n    function root() {\n        $this->helper();\n'
                              '        strlen("x");\n        B::make();\n    }\n    function helper() {}\n}\n'}),
}


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_level_one_edges_equal_find_callees_call_lists(tmp_path, language):
    root, files = LANGUAGES[language]
    path = _tree(tmp_path, files)
    matches = find_callees(path, root)['matches']
    assert len(matches) == 1 and matches[0]['calls'], 'fixture must define one root with calls'
    expected = sorted(_bare_callee_name(call) for call in matches[0]['calls'])
    edges = _root_edges(path, root, 1)
    assert sorted(_bare_callee_name(callee) for _, _, callee, _ in edges) == expected
    trace = _trace(path, root, 1)
    assert sorted(_bare_callee_name(label) for label in trace['frames'][0]['calls']) == expected


# --- the shared walk's own contract ----------------------------------------------------------

def test_root_marks_which_edge_expands_its_target(tmp_path):
    # Fixture a: f->c places c at level 1 (expanded); b->c at level 3 is the later edge.
    result = CallsAdapter(_tree(tmp_path, FIXTURE_A), 'root=f&depth=3').get_structure()
    marks = {(e['caller'], e['callee'], level['level']): e['expanded']
             for level in result['levels'] for e in level['callees']}
    assert marks == {('f', 'a', 1): True, ('f', 'c', 1): True, ('a', 'b', 2): True,
                     ('c', 'd', 2): True, ('b', 'c', 3): False}
    assert (result['total_edges'], result['total_resolved'], result['total_unresolved'],
            result['total_ambiguous']) == (5, 5, 0, 0)


def test_root_marks_an_edge_to_a_target_reached_at_the_same_level(tmp_path):
    result = CallsAdapter(_tree(tmp_path, FIXTURE_B), 'root=X&depth=2').get_structure()
    marks = [(Path(e['caller_file']).name, e['expanded']) for e in result['levels'][0]['callees']]
    assert marks == [('one.py', True), ('two.py', False)]


def test_root_file_selector_picks_one_definition(tmp_path):
    path = _tree(tmp_path, FIXTURE_B)
    assert _root_edges(path, 'two.py:X', 1) == {('two.py', 'X', 'helper', 1)}


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_level_one_call_text_is_find_callees_per_definition(tmp_path, language):
    # Exact call text per definition, builtins hidden and shown, against find_callees.
    from reveal.adapters.calls.index import walk_callees
    root, files = LANGUAGES[language]
    path = _tree(tmp_path, files)
    for builtins in (False, True):
        expected = {(to_posix(m['file']), m['line']): m['calls']  # find_callees keeps the OS spelling
                    for m in find_callees(path, root, include_builtins=builtins)['matches']}
        walk = walk_callees(path, root, depth=1, include_builtins=builtins)
        assert {(n.file, n.line): [e['call_expr'] for e, _ in n.edges] for n in walk.roots} == expected


def test_trace_keeps_params_and_effects_from_the_walk(tmp_path):
    path = _tree(tmp_path, {'m.py': 'import shutil\n\ndef run(src, dst):\n    copy(src, dst)\n\n'
                                    'def copy(a, b):\n    shutil.copy(a, b)\n'})
    frames = {f['name']: f for f in _trace(path, 'run', 2)['frames']}
    assert frames['run']['params'] == ['src', 'dst']
    assert frames['copy']['params'] == ['a', 'b']
    assert frames['copy']['effects'] == ['file:copy'] and frames['copy']['depth'] == 1


def test_root_text_names_the_already_expanded_edge_and_counts_edges(tmp_path, capsys):
    from reveal.adapters.calls.renderer import render_calls_structure
    result = CallsAdapter(_tree(tmp_path, FIXTURE_B), 'root=X&depth=2').get_structure()
    render_calls_structure(result, 'text')
    out = capsys.readouterr().out
    assert 'Total:      2 call edges: 2 resolved, 0 external/unresolved' in out
    assert [line.strip() for line in out.splitlines() if '→' in line] == [
        f'X → helper  ✓  {(tmp_path / "one.py").as_posix()}:1',
        f'X → helper  ✓ (already expanded)  {(tmp_path / "two.py").as_posix()}:1']
