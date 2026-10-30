"""Qualified execution edges for the optional existing exit-collector scope."""
import pytest
from tree_sitter_language_pack import get_parser

from reveal.adapters.ast.nav_exits import ExitOwnership, collect_exits, collect_gate_chains
from reveal.core.treesitter_compat import _zero_arg, node_children, tree_root, ts_parse

pytestmark = pytest.mark.component


def _scope(language, source, kind, needle=None):
    tree = ts_parse(get_parser(language), source)
    root = tree_root(tree)
    assert not _zero_arg(root, 'has_error'), source
    data = source.encode('utf-8')
    def text(node):
        return data[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')
    stack = [root]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') == kind and (needle is None or needle in text(node)):
            return tree, node, text
        stack.extend(reversed(node_children(node)))
    pytest.fail('scope not found: ' + kind)


def _owned(language, source, kind, needle=None):
    tree, node, text = _scope(language, source, kind, needle)
    ownership = ExitOwnership(language, node)
    exits = collect_exits(node, 1, 999, text, ownership=ownership)
    gates = collect_gate_chains(node, 1, 999, text, ownership=ExitOwnership(language, node))
    assert [{k: v for k, v in row.items() if k != 'gates'} for row in gates] == exits
    return exits, ownership


def test_default_library_inventory_is_unchanged_and_owned_mode_is_explicit():
    source = 'def outer():\n def inner():\n  return 1\n return 2\n'
    tree, node, text = _scope('python', source, 'function_definition')
    assert [r['line'] for r in collect_exits(node, 1, 999, text)] == [3, 4]
    owned, evidence = _owned('python', source, 'function_definition')
    assert [r['line'] for r in owned] == [4]
    assert evidence.mode == 'selected_callable'
    assert evidence.unresolved_sites == []


@pytest.mark.parametrize('language', ['javascript', 'typescript', 'tsx'])
def test_selected_computed_method_name_is_not_its_invocation_default(language):
    source = 'class C { [exit(1)](a=exit(2)){return 3;} }'
    rows, evidence = _owned(language, source, 'method_definition')
    assert [r['text'] for r in rows] == ['exit(2)', 'return 3;']
    assert evidence.unresolved_sites == []


def test_selected_cpp_lambda_excludes_capture_formation_and_retains_entry_default():
    source = 'int outer(){ auto f=[x=(exit(1),0)](int a=(exit(2),0)){return 3;}; return 4; }'
    rows, evidence = _owned('cpp', source, 'lambda_expression')
    assert [r['text'] for r in rows] == ['exit(2)', 'return 3;']
    assert evidence.unresolved_sites[0]['text'] == 'exit(2)'


def test_selected_cpp_constructor_retains_initializer_candidate_with_scope_evidence():
    source = 'struct C { int x; C():x((exit(1),0)){return;} };'
    rows, evidence = _owned('cpp', source, 'function_definition')
    assert [r['text'] for r in rows] == ['exit(1)', 'return;']
    assert evidence.unresolved_sites[0]['text'] == 'exit(1)'


@pytest.mark.parametrize('language,source,kind,expected', [
    ('ruby', 'def outer(a=exit(1))\n return 2\nend', 'method', ['exit(1)', 'return 2']),
    ('kotlin', 'fun outer(a:Int=throw Exception()):Int {return 2}', 'function_declaration', ['throw Exception()', 'return 2']),
    ('swift', 'func outer(a: Void = exit(1)) -> Int {return 2}', 'function_declaration', ['exit(1)', 'return 2']),
])
def test_selected_invocation_header_sites_are_not_silently_erased(language, source, kind, expected):
    rows, evidence = _owned(language, source, kind)
    assert [r['text'] for r in rows] == expected


def test_scope_inventory_of_aggregate_does_not_claim_one_callable():
    rows, evidence = _owned('javascript', 'class C {a(){return 1;} b(){return 2;}}', 'class_declaration')
    assert [r['text'] for r in rows] == ['return 1;', 'return 2;']
    assert evidence.mode == 'source_scope'


@pytest.mark.parametrize('language,source,kind,expected', [
    ('gdscript', 'func _init():\n var f=func():\n  return 1\n return\n', 'constructor_definition', ['return']),
    ('swift', 'class C {\n init() {let f = {return 1}; return}\n deinit {let f = {return 2}; return}\n}', 'deinit_declaration', ['return']),
])
def test_existing_lifecycle_callable_shapes_have_owned_bodies(language, source, kind, expected):
    rows, evidence = _owned(language, source, kind)
    assert evidence.mode == 'selected_callable'
    assert [r['text'] for r in rows] == expected


def test_same_line_uncertain_sites_retain_distinct_record_identity():
    source = 'def outer\n lambda { exit(1); exit(2) }\n return 3\nend'
    rows, evidence = _owned('ruby', source, 'method')
    assert [r['text'] for r in rows] == ['exit(1)', 'exit(2)', 'return 3']
    assert [s['line'] for s in evidence.unresolved_sites] == [2, 2]
    assert [s['text'] for s in evidence.unresolved_sites] == ['exit(1)', 'exit(2)']
    assert len({(s['start_byte'], s['end_byte']) for s in evidence.unresolved_sites}) == 2
    data = source.encode('utf-8')
    for site in evidence.unresolved_sites:
        assert data[site['start_byte']:site['end_byte']].decode('utf-8') == site['text']


def test_ambiguous_region_without_recorded_exits_does_not_claim_uncertain_sites():
    source = 'def outer\n lambda { x = 1 }\n return 3\nend'
    rows, evidence = _owned('ruby', source, 'method')
    assert [r['text'] for r in rows] == ['return 3']
    assert evidence.unresolved_sites == []
    assert evidence.warnings() == []


def test_excluded_range_and_next_call_do_not_leak_unresolved_sites():
    source = 'fun outer(): Int {\n run {return 1}\n return 2\n}'
    tree, node, text = _scope('kotlin', source, 'function_declaration')
    full = ExitOwnership('kotlin', node)
    collect_gate_chains(node, 1, 99, text, ownership=full)
    assert full.unresolved_sites[0]['line'] == 2
    selected = ExitOwnership('kotlin', node)
    rows = collect_gate_chains(node, 3, 3, text, ownership=selected)
    assert [r['text'] for r in rows] == ['return 2']
    assert selected.unresolved_sites == []


@pytest.mark.parametrize('language,source,kind,expected', [
    ('rust', 'fn outer() -> impl Fn() -> i32 {\n || {return 1;}\n}', 'function_item', '|| {return 1;}'),
    ('ruby', 'def outer\n -> {return 1}\nend', 'method', '-> {return 1}'),
])
def test_selected_implicit_tail_is_not_a_nested_callable_return(language, source, kind, expected):
    rows, evidence = _owned(language, source, kind)
    assert [(r['kind'], r['line'], r['text']) for r in rows] == [('RETURN', 2, expected)]


def test_unqualified_resolved_scope_retains_inventory_with_visible_reason():
    source = 'class C { public static C operator +(C a, C b) {return a;} }'
    rows, evidence = _owned('csharp', source, 'operator_declaration')
    assert evidence.mode == 'source_scope'
    assert evidence.reason == 'unqualified_resolved_scope'
    assert [r['text'] for r in rows] == ['return a;']
    assert evidence.warnings()[0]['type'] == 'ownership_scope_limited'
