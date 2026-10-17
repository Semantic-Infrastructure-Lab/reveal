"""Real grammar controls for GDScript/Zig variable flow (BACK-1924/25/27)."""

import pytest

from reveal.adapters.ast.nav_exits import collect_mutations
from reveal.adapters.ast.nav_varflow import all_var_flow, var_flow
from reveal.element_resolve import resolve_bare_name
from reveal.registry import get_analyzer
from reveal.treesitter import FUNCTION_NODE_TYPES

pytestmark = pytest.mark.component


def _scope(tmp_path, extension, source):
    path = tmp_path / f'flow.{extension}'
    path.write_text(source, encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    assert not analyzer.has_parse_errors()
    resolution = resolve_bare_name(analyzer, 'target', (FUNCTION_NODE_TYPES,))
    assert resolution is not None
    return resolution.node, analyzer._get_node_text


def _events(scope, get_text, name):
    return [(event['kind'], event['line']) for event in var_flow(scope, name, 1, 100, get_text)]


@pytest.fixture
def gdscript(tmp_path):
    return _scope(tmp_path, 'gd', '''extends RefCounted
func target(input):
    var result = input
    sink.store_string(str(result))
    store_string(result)
    var store_string = result
    var unread: int = 0
    sink.store_string(other)
    result = result + 1
    return result
''')


def test_gdscript_nested_argument_reads_and_local_reassignment(gdscript):
    scope, text = gdscript
    expected = [('WRITE', 3), ('READ', 4), ('READ', 5), ('READ', 6),
                ('WRITE', 9), ('READ', 9), ('READ', 10)]
    for _ in range(2):
        assert _events(scope, text, 'result') == expected


def test_gdscript_member_type_and_function_names_remain_excluded(gdscript):
    scope, text = gdscript
    assert _events(scope, text, 'store_string') == [('READ', 5), ('WRITE', 6)]
    assert _events(scope, text, 'sink') == [('READ', 4), ('READ', 8)]
    assert _events(scope, text, 'int') == []
    assert _events(scope, text, 'target') == []


def test_gdscript_argument_only_range_keeps_nested_candidate(gdscript):
    scope, text = gdscript
    events = all_var_flow(scope, 8, 8, text)
    assert set(events) == {'sink', 'other'}
    assert [(event['kind'], event['line']) for event in events['other']] == [('READ', 8)]


def test_gdscript_declaration_only_range_keeps_write_candidate(gdscript):
    scope, text = gdscript
    events = all_var_flow(scope, 3, 3, text)
    assert set(events) == {'result', 'input'}
    assert events['result'][0]['kind'] == 'WRITE'


def test_gdscript_mutations_follow_initialization_and_reassignment(gdscript):
    scope, text = gdscript
    assert collect_mutations(scope, 3, 3, text) == [
        {'var': 'result', 'last_write_line': 3, 'next_read_line': 4},
    ]
    assert collect_mutations(scope, 9, 9, text) == [
        {'var': 'result', 'last_write_line': 9, 'next_read_line': 10},
    ]
    assert collect_mutations(scope, 7, 7, text) == []  # Unread typed local.
    assert collect_mutations(scope, 8, 8, text) == []  # Read-only call.


@pytest.fixture
def zig(tmp_path):
    return _scope(tmp_path, 'zig', '''fn target(input: u32) u32 {
    var result = input;
    const other = result + 1;
    result = result + other;
    result += other;
    sink.consume(result);
    _ = result == other;
    return result;
}
''')


def test_zig_assignment_compound_and_binary_reads(zig):
    scope, text = zig
    expected = [('WRITE', 2), ('READ', 3), ('WRITE', 4), ('READ', 4),
                ('READ', 5), ('WRITE', 5), ('READ', 6), ('READ', 7), ('READ', 8)]
    for _ in range(2):
        assert _events(scope, text, 'result') == expected


def test_zig_rhs_binary_and_method_names_remain_reads_or_excluded(zig):
    scope, text = zig
    assert _events(scope, text, 'other') == [
        ('WRITE', 3), ('READ', 4), ('READ', 5), ('READ', 7),
    ]
    assert _events(scope, text, 'consume') == []
    assert _events(scope, text, 'target') == []


def test_zig_mutations_identify_reassignment_not_binary_expression(zig):
    scope, text = zig
    assert collect_mutations(scope, 4, 4, text) == [
        {'var': 'result', 'last_write_line': 4, 'next_read_line': 5},
    ]
    assert collect_mutations(scope, 7, 7, text) == []


def test_python_member_names_remain_excluded(tmp_path):
    scope, text = _scope(tmp_path, 'py', '''def target(source, sink):
    value = source
    sink.value(convert(value))
    return value
''')
    assert _events(scope, text, 'value') == [('WRITE', 2), ('READ', 3), ('READ', 4)]
    assert set(all_var_flow(scope, 3, 3, text)) == {'sink', 'convert', 'value'}
