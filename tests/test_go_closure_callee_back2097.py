"""A Go closure invoked where it is written names no callee (BACK-2097).

``defer func() { ... }()``, ``go func(n int) { ... }(3)`` and ``v := func() int { ... }()`` call a
``func_literal``: calls listed the closure's whole source as an unresolved callee (callees, the walk and
rank). The closure has no name; its body's calls are their own nodes and stay listed. Same class and the
same seam as Swift's ``{ ... }()`` (BACK-2074, ``core/callees/generic.callee_name_from_node``).
"""
import pytest

from reveal.adapters.calls import CallsAdapter

pytestmark = pytest.mark.component

GO = '''package main

import "fmt"

func cleanup() {}

func helper(x int) int { return x }

func run() {
\tdefer func() {
\t\tcleanup()
\t}()
\tgo func(n int) {
\t\thelper(n)
\t}(3)
\tv := func() int { return helper(1) }()
\t(func() { cleanup() })()
\tfn := helper
\tfn(2)
\tfmt.Println(v)
}
'''

JS = '''function boot() {
  (function () { setup(); })();
  (() => teardown())();
  start();
}

function setup() {}
function teardown() {}
function start() {}
'''


def write(root, name, text):
    (root / name).write_text(text, encoding='utf-8')
    return root


@pytest.fixture
def go_root(tmp_path):
    return str(write(tmp_path, 'm.go', GO))


def closure_text(name):
    return 'func(' in name or 'func ' in name or '\n' in name


def test_callees_name_no_closure_and_keep_its_body_calls(go_root):
    result = CallsAdapter(go_root, 'callees=run').get_structure()
    calls = result['matches'][0]['calls']
    assert not [c for c in calls if closure_text(c)], calls
    # The closure bodies' calls, a function value and an ordinary call keep their names.
    assert {'cleanup', 'helper', 'fn', 'fmt.Println'} <= set(calls), calls


@pytest.mark.parametrize('query', ['callees=run&depth=2', 'root=run'])
def test_walk_has_no_closure_edge(go_root, query):
    result = CallsAdapter(go_root, query).get_structure()
    callees = [edge['callee'] for level in result['levels'] for edge in level['callees']]
    assert not [c for c in callees if closure_text(c)], callees
    assert {'cleanup', 'helper', 'fmt.Println'} <= set(callees), callees


def test_rank_has_no_closure_entry(go_root):
    result = CallsAdapter(go_root, 'rank=callers&top=50').get_structure()
    names = [entry['name'] for entry in result['entries']]
    assert not [n for n in names if closure_text(n)], names
    assert {'cleanup', 'helper'} <= set(names), names


def test_callers_of_a_closure_body_call_are_unchanged(go_root):
    result = CallsAdapter(go_root, 'callers=cleanup').get_structure()
    assert [rec['caller'] for level in result['levels'] for rec in level['callers']] == ['run']


def test_js_iife_control_is_unchanged(tmp_path):
    """Another language's immediately invoked function: already named nothing, still names nothing."""
    root = str(write(tmp_path, 'boot.js', JS))
    calls = CallsAdapter(root, 'callees=boot').get_structure()['matches'][0]['calls']
    assert sorted(calls) == ['setup', 'start', 'teardown'], calls


# The same class in the other grammars whose closure literal can be invoked where it is written: the
# literal's source was the callee name (found while fixing Go; one seam, so one change).
SIBLINGS = {
    'a.rs': 'fn outer() {\n    (|| inner())();\n}\nfn inner() {}\n',
    'b.cpp': 'void inner() {}\nvoid outer() {\n    [](){ inner(); }();\n}\n',
    'c.kt': 'fun inner() {}\nfun outer() {\n    (fun() { inner() })()\n}\n',
    'd.php': '<?php\nfunction inner() {}\nfunction outer() {\n    (function() { inner(); })();\n}\n',
}


@pytest.mark.parametrize('name', sorted(SIBLINGS))
def test_sibling_language_closure_names_no_callee(tmp_path, name):
    root = str(write(tmp_path, name, SIBLINGS[name]))
    calls = CallsAdapter(root, 'callees=outer').get_structure()['matches'][0]['calls']
    assert calls == ['inner'], calls
