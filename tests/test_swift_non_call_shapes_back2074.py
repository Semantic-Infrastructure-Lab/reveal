"""Swift shapes that tree-sitter parses as `call_expression` but that call nothing (BACK-2074).

tree-sitter-swift gives a subscript, a function reference, an operator applied to a
parenthesised operand and a `defer` block the same `call_expression` node as a real call.
calls:// listed them as call edges, and named a trailing closure after `try`/`await` and an
immediately-invoked closure by their source text. Each test reads the calls:// JSON rows
(`matches[].calls` for ?callees=, `levels[].callers` for ?target=) on a small fixture and pairs
the false positive with a positive control of the same shape that must still be found.
"""

import textwrap

import pytest
import tree_sitter_language_pack as ts

from reveal.adapters.ast.nav_effects import collect_effects
from reveal.adapters.calls.adapter import CallsAdapter
from reveal.adapters.calls.index import _bare_callee_name
from reveal.core import node_children
from reveal.core.nav_calls import range_calls
from reveal.core.node_taxonomy import FUNCTION_TYPES
from reveal.core.treesitter_compat import _zero_arg, tree_root, ts_parse
from reveal.registry import get_analyzer


def _write(tmp_path, name, src):
    path = tmp_path / name
    path.write_text(textwrap.dedent(src), encoding='utf-8')
    return path


def _callees(tmp_path, function):
    result = CallsAdapter(str(tmp_path), f'callees={function}').get_structure()
    matches = [m for m in result['matches'] if m['function'] == function]
    assert len(matches) == 1, result['matches']
    return matches[0]['calls']


def _caller_names(tmp_path, target):
    result = CallsAdapter(str(tmp_path), f'target={target}').get_structure()
    return {(row['caller'], row['call_expr']) for level in result['levels'] for row in level['callers']}


def _first_function(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') in FUNCTION_TYPES:
            return node
        stack.extend(reversed(node_children(node)))
    raise AssertionError('no function node found')


def _nav_callees(path, language='swift'):
    """Callees of the first function through the ast:// nav path (range_calls)."""
    src = path.read_text(encoding='utf-8')
    content = src.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser(language), src))

    def get_text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    return [c['callee'] for c in range_calls(_first_function(root), 1, 999, get_text)]


def _both_paths_agree(path):
    analyzer_calls = get_analyzer(str(path))(str(path)).get_structure()['functions'][0]['calls']
    nav_calls = _nav_callees(path)
    assert {_bare_callee_name(c) for c in analyzer_calls} == {_bare_callee_name(c) for c in nav_calls}, (
        analyzer_calls, nav_calls)
    return analyzer_calls


# --- (1) function references with argument labels -------------------------------------------

REFS = '''
func notificationPreviewType(raw: Int?, xs: [UInt64]) -> [UInt32] {
    let a = raw.flatMap(NotificationType.init(rawValue:))
    let c = xs.map(self.convert(tx:))
    let s = #selector(handle(_:))
    let t = xs.map(pair(a:b:))
    return xs.map(UInt32.init(truncatingIfNeeded:))
}

func realCalls(x: Double, y: Int) -> Date {
    foo(1)
    let d = Date.init(timeIntervalSince1970: x)
    let e = f(x:y)
    let g = convert(tx: y)
    return Date(timeIntervalSince1970: x)
}

func literalArguments() {
    cache.set(nil)
    column.update(to: nil)
    toggle(true)
    flag(on: false)
}
'''


def test_function_references_passed_as_values_are_not_calls(tmp_path):
    _write(tmp_path, 'refs.swift', REFS)
    assert sorted(_callees(tmp_path, 'notificationPreviewType')) == ['raw.flatMap', 'xs.map']
    callers_of_init = _caller_names(tmp_path, 'init')
    assert ('notificationPreviewType', 'NotificationType.init') not in callers_of_init
    assert not [row for row in callers_of_init if row[0] == 'notificationPreviewType']


def test_labelled_calls_with_arguments_are_still_calls(tmp_path):
    _write(tmp_path, 'refs.swift', REFS)
    assert {'foo', 'Date.init', 'f', 'convert', 'Date'} <= set(_callees(tmp_path, 'realCalls'))
    assert ('realCalls', 'Date.init') in _caller_names(tmp_path, 'init')


def test_calls_whose_argument_is_a_keyword_literal_are_still_calls(tmp_path):
    # On language-pack 1.8.1 `nil` is an anonymous token, so `set(nil)` has no named value
    # child; it must not read as the label-only reference `set(_:)`.
    _write(tmp_path, 'refs.swift', REFS)
    assert sorted(_callees(tmp_path, 'literalArguments')) == ['cache.set', 'column.update', 'flag', 'toggle']


# --- (2) subscripts -------------------------------------------------------------------------

SUBSCRIPTS = '''
func subscripts(map: [String: Int], x: [Int]?, path: KeyPath<Int, Int>) {
    var m = map
    m["k"] = 1
    let y = x?[0]
    let n = matrix[1, 2]
    let p = x?[keyPath: path]
    let q = foo(1)[0]
    let r = m[key()]
}
'''


def test_subscripts_are_not_calls_but_calls_inside_them_are(tmp_path):
    _write(tmp_path, 'subs.swift', SUBSCRIPTS)
    assert sorted(_callees(tmp_path, 'subscripts')) == ['foo', 'key']
    assert _caller_names(tmp_path, 'm') == set()
    assert _caller_names(tmp_path, 'matrix') == set()


# --- (3) operators on a parenthesised operand, and `defer` -----------------------------------

OPERATORS = '''
func operators(v: Int, flag: Bool) -> Int {
    defer { cleanup() }
    if !(flag) { return negate(-(v)) }
    if !isRunning(v) { return 0 }
    return -(v + 1)
}

func escapedDefer() {
    `defer`(1)
}
'''


def test_unary_operators_and_defer_are_not_calls(tmp_path):
    _write(tmp_path, 'ops.swift', OPERATORS)
    assert sorted(_callees(tmp_path, 'operators')) == ['cleanup', 'isRunning', 'negate']
    assert _caller_names(tmp_path, 'defer') == set()


def test_a_function_named_defer_is_still_a_call(tmp_path):
    # Backticks make the keyword an ordinary identifier: that is a real call.
    _write(tmp_path, 'ops.swift', OPERATORS)
    assert _callees(tmp_path, 'escapedDefer') == ['`defer`']


def test_kotlin_defer_lambda_call_is_still_a_call(tmp_path):
    # Kotlin has no defer statement: `defer { }` there calls a function named defer. Its
    # call_suffix wraps the lambda in annotated_lambda, which the Swift check never matches.
    _write(tmp_path, 'k.kt', 'fun f() {\n    defer { cleanup() }\n}\n')
    assert sorted(_callees(tmp_path, 'f')) == ['cleanup', 'defer']


# --- (4) trailing closure after try / await --------------------------------------------------

TRAILING = '''
func trailing() async throws {
    let k = try await svc.fetch(id: 1) { done() }
    let k2 = try svc.load(1) { ok() }
    bencher.bench(.Drop) {
        work()
    }
    try bencher.measure(.Drop) { measured() }
    run { inner() }
    view.animate(withDuration: 1) { a() } completion: { _ in b() }
}
'''


def test_a_trailing_closure_call_is_listed_once(tmp_path):
    _write(tmp_path, 'trailing.swift', TRAILING)
    calls = _callees(tmp_path, 'trailing')
    assert sorted(calls) == sorted([
        'svc.fetch', 'done', 'svc.load', 'ok', 'bencher.bench', 'work',
        'bencher.measure', 'measured', 'run', 'inner', 'view.animate', 'a', 'b',
    ])
    assert not [c for c in calls if c.startswith(('try', 'await'))]


# --- arithmetic that tree-sitter-swift binds tighter than the call --------------------------

ARITHMETIC = '''
func arithmetic(d: Double, ts: UInt64) -> UInt64 {
    let a = 1000 * max(0, d)
    return ts + UInt64(a)
}
'''


def test_a_call_after_an_arithmetic_operator_is_named_by_its_callee(tmp_path):
    # `1000 * max(0, d)` parses as call(`1000 * max`, args): the callee is `max`. The old
    # text `1000 * max` matched no definition, so `max`'s callers missed this one.
    _write(tmp_path, 'arith.swift', ARITHMETIC)
    assert sorted(_callees(tmp_path, 'arithmetic')) == ['UInt64', 'max']
    assert ('arithmetic', 'max') in _caller_names(tmp_path, 'max')


# --- (5) immediately-invoked closure literals -----------------------------------------------

IIFE = '''
func iife(raw: Int?) throws {
    let d = raw ?? { compute(); return 0 }()
    let e = try { try decoder.decodeX(value: 1) }()
    let f = makeValue()
}
'''


def test_immediately_invoked_closures_are_declined_and_their_bodies_kept(tmp_path):
    _write(tmp_path, 'iife.swift', IIFE)
    calls = _callees(tmp_path, 'iife')
    assert sorted(calls) == ['compute', 'decoder.decodeX', 'makeValue']
    assert not [c for c in calls if '{' in c]


# --- both extractors agree on every shape above ---------------------------------------------

@pytest.mark.parametrize('src', [REFS, SUBSCRIPTS, OPERATORS, TRAILING, ARITHMETIC, IIFE],
                         ids=['refs', 'subscripts', 'operators', 'trailing', 'arithmetic', 'iife'])
def test_analyzer_and_nav_paths_agree(tmp_path, src):
    calls = _both_paths_agree(_write(tmp_path, 't.swift', src))
    assert calls, 'positive control: the first function has real calls'


# --- the env read that used to ride on subscript-as-call keeps its classification -----------

def test_bundle_info_dictionary_subscript_is_still_an_env_read(tmp_path):
    # BACK-728 reached `Bundle.main.infoDictionary?[...]` through the call channel because the
    # subscript was call-shaped. It now goes through the property channel like Python's
    # `os.environ['X']`.
    path = _write(tmp_path, 'env.swift', '''
        func version() -> String? {
            let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
            let w = settings["k"]
            return v
        }
    ''')
    src = path.read_text(encoding='utf-8')
    content = src.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser('swift'), src))

    def get_text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    func = _first_function(root)
    effects = collect_effects(func, 1, 999, get_text, language='swift')
    env = [(e['line'], e['kind']) for e in effects if e.get('kind') == 'env']
    assert env == [(3, 'env')], effects
