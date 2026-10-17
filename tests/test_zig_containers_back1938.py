"""Verified Zig container categories and field/source facts (BACK-1938)."""

import pytest

from reveal.display.element import _extract_by_syntax, _parse_element_syntax
from reveal.registry import get_analyzer

pytestmark = pytest.mark.component

BOX = '''pub const Box = struct {
    value: u32 = 0,
    present: bool = false,
    fn method(self: *Box) void {}
    const Inner = struct { nested: u8 };
};'''
CHOICE = '''const Choice = enum(u8) {
    first,
    second = 2,
};'''
EITHER = '''const Either = union(enum) {
    number: u32,
    text: []const u8,
};'''
SOURCE = '\n'.join([BOX, CHOICE, EITHER, '''const scalar: u32 = 3;
const Derived = make(struct { hidden: u32 });
const Selected = if (flag) struct { branch: u32 } else Box;
fn factory() type { return struct { anonymous: u32 }; }
const Tuple = struct { u32, bool };
const Open = enum(u8) { first, _ };
'''])


@pytest.fixture
def analyzer(tmp_path):
    path = tmp_path / 'containers.zig'
    path.write_text(SOURCE, encoding='utf-8')
    instance = get_analyzer(str(path))(str(path))
    assert not instance.has_parse_errors()
    return instance


@pytest.mark.parametrize('category,names', [
    ('structs', ['Box', 'Inner', 'Tuple']), ('enums', ['Choice', 'Open']), ('unions', ['Either']),
])
def test_structure_lists_exact_verified_container_names(analyzer, category, names):
    for _ in range(2):
        assert [item['name'] for item in analyzer.get_structure().get(category, [])] == names


@pytest.mark.parametrize('name,kind', [
    ('Box', 'struct'), ('Choice', 'enum'), ('Either', 'union'),
    ('Tuple', 'struct'), ('Open', 'enum'),
])
def test_container_type_fact_reads_declared_type_wrapper(analyzer, name, kind):
    declaration = next(node for node in analyzer._find_nodes_by_type('VarDecl')
                       if analyzer._extract_var_name_and_container(node)[0] == name)
    _, container = analyzer._extract_var_name_and_container(declaration)
    assert container is not None
    assert analyzer._is_correct_container_type(container, kind)
    for other in ('struct', 'enum', 'union'):
        if other != kind:
            assert not analyzer._is_correct_container_type(container, other)


@pytest.mark.parametrize('name,members', [
    ('Box', ['value', 'present']), ('Inner', ['nested']),
    ('Choice', ['first', 'second']), ('Either', ['number', 'text']),
    ('Tuple', []), ('Open', ['first']),  # Types and nonexhaustive markers are not named fields.
])
def test_members_are_direct_fields_not_nested_types_or_methods(analyzer, name, members):
    declaration = next(node for node in analyzer._find_nodes_by_type('VarDecl')
                       if analyzer._extract_var_name_and_container(node)[0] == name)
    _, container = analyzer._extract_var_name_and_container(declaration)
    assert analyzer._extract_container_members(container) == members


@pytest.mark.parametrize('name,start,end,source', [
    ('Box', 1, 6, BOX), ('Inner', 5, 5, '    const Inner = struct { nested: u8 };'),
    ('Choice', 7, 10, CHOICE), ('Either', 11, 14, EITHER),
    ('Tuple', 19, 19, 'const Tuple = struct { u32, bool };'),
    ('Open', 20, 20, 'const Open = enum(u8) { first, _ };'),
])
def test_named_container_extracts_exact_complete_source(analyzer, name, start, end, source):
    result = _extract_by_syntax(analyzer, name, _parse_element_syntax(name))
    assert result is not None
    assert (result['name'], result['line_start'], result['line_end']) == (name, start, end)
    assert result['source'] == source


def test_structure_omits_noncontainer_call_and_anonymous_values(analyzer):
    structure = analyzer.get_structure()
    for category in ('structs', 'enums', 'unions'):
        assert not {'scalar', 'Derived', 'Selected', 'factory'} & {
            item['name'] for item in structure.get(category, [])
        }
    for name in ('Derived', 'Selected'):
        declaration = next(node for node in analyzer._find_nodes_by_type('VarDecl')
                           if analyzer._extract_var_name_and_container(node)[0] == name)
        assert analyzer._extract_var_name_and_container(declaration)[1] is None


def test_function_structure_remains_separate_from_container_fields(analyzer):
    assert [item['name'] for item in analyzer.get_structure()['functions']] == ['method', 'factory']
