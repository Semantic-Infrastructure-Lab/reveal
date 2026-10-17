"""Qualified method identities preserve bare lookup (BACK-1910, BACK-1931)."""

import pytest

from reveal.display.element import (
    _extract_by_syntax, _extract_element_at_line, _extract_ordinal_element,
    _parse_element_syntax,
)
from reveal.element_resolve import owner_path, qualified_name, resolve_bare_name, resolve_path
from reveal.registry import get_analyzer
from reveal.treesitter import FUNCTION_NODE_TYPES

pytestmark = pytest.mark.component


def _analyzer(tmp_path, extension, source):
    path = tmp_path / f'owners.{extension}'
    path.write_text(source, encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    assert not analyzer.has_parse_errors()
    return analyzer


@pytest.fixture
def lua(tmp_path):
    return _analyzer(tmp_path, 'lua', '''local Outer = { Inner = {} }
local Other = {}
function run() return "top" end
function Outer.Inner.run() return "dot" end
function Other:run() return "colon" end
local Another = { Inner = {} }
function Another.Inner.run() return "nested" end
Outer.Inner.save = function(value) return value end
Other.save = function(value) return value end
local Table = { load = function(value) return value end }
invoke(function(value) return value end)
''')


@pytest.mark.parametrize('address,line,owner', [
    ('Outer.Inner.run', 4, 'Outer.Inner'), ('Other.run', 5, 'Other'),
    ('Another.Inner.run', 7, 'Another.Inner'),
    ('Outer.Inner.save', 8, 'Outer.Inner'), ('Other.save', 9, 'Other'),
    ('Table.load', 10, 'Table'),
])
def test_lua_qualified_declarations_and_bound_values(lua, address, line, owner):
    for _ in range(2):
        resolution = resolve_path(lua, address)
        assert resolution is not None
        assert not resolution.ambiguous
        assert owner_path(lua, resolution.node) == owner
        assert qualified_name(lua, resolution.node, address.rsplit('.', 1)[-1]) == address
        result = _extract_by_syntax(lua, address, _parse_element_syntax(address))
        assert (result['name'], result['line_start'], result['line_end']) == (address, line, line)
        expected_source = ('function(value) return value end'
                           if address.endswith(('.save', '.load')) else lua.lines[line - 1])
        assert result['source'] == expected_source


def test_lua_duplicate_bare_names_keep_all_distinct_qualified_candidates(lua):
    resolution = resolve_bare_name(lua, 'run', (FUNCTION_NODE_TYPES,))
    assert lua.element_span(resolution.node)['line_start'] == 3
    assert [qualified_name(lua, node, 'run') for node in resolution.candidates] == [
        'run', 'Outer.Inner.run', 'Other.run', 'Another.Inner.run',
    ]
    nested = resolve_path(lua, 'Inner.run')
    assert nested is not None and nested.ambiguous
    assert [owner_path(lua, node) for node in nested.candidates] == ['Outer.Inner', 'Another.Inner']
    saved = resolve_bare_name(lua, 'save', (FUNCTION_NODE_TYPES,))
    assert len(saved.candidates) == 2
    assert [owner_path(lua, node) for node in saved.candidates] == ['Outer.Inner', 'Other']


def test_lua_bare_names_and_unbound_callbacks_are_unchanged(lua):
    assert lua._get_node_name(resolve_bare_name(lua, 'run', (FUNCTION_NODE_TYPES,)).node) == 'run'
    result = _extract_by_syntax(lua, 'run', _parse_element_syntax('run'))
    assert (result['line_start'], result['line_end']) == (3, 3)
    assert 'return "top"' in result['source']
    assert resolve_path(lua, 'Missing.run') is None
    assert resolve_path(lua, 'invoke.value') is None


@pytest.fixture
def zig(tmp_path):
    return _analyzer(tmp_path, 'zig', '''fn run() u32 { return 0; }
const Outer = struct {
    fn run() u32 { return 1; }
    const Inner = struct {
        fn run() u32 { return 2; }
    };
};
const Other = struct { fn run() u32 { return 3; } };
const Choice = enum { first, fn run() u32 { return 4; } };
const Either = union { number: u32, fn run() u32 { return 5; } };
const scalar: u32 = 6;
const Derived = make(struct { fn hidden() u32 { return 6; } });
fn factory() type { return struct { fn hidden() u32 { return 7; } }; }
''')


@pytest.mark.parametrize('address,line,owner', [
    ('Outer.run', 3, 'Outer'), ('Outer.Inner.run', 5, 'Outer.Inner'),
    ('Other.run', 8, 'Other'), ('Choice.run', 9, 'Choice'), ('Either.run', 10, 'Either'),
])
def test_zig_verified_container_method_owners(zig, address, line, owner):
    for _ in range(2):
        resolution = resolve_path(zig, address)
        assert resolution is not None
        assert not resolution.ambiguous
        assert owner_path(zig, resolution.node) == owner
        assert qualified_name(zig, resolution.node) == address
        named = _extract_by_syntax(zig, address, _parse_element_syntax(address))
        positional = _extract_element_at_line(zig, line)
        assert named['name'] == address
        assert named['source'] == zig.element_span(resolution.node)['source']
        assert (named['line_start'], named['line_end']) == (line, line)
        assert positional['source'] == named['source']


def test_zig_bare_duplicate_and_ordinal_owners(zig):
    resolution = resolve_bare_name(zig, 'run', (FUNCTION_NODE_TYPES,))
    assert zig.element_span(resolution.node)['line_start'] == 1
    assert [qualified_name(zig, node) for node in resolution.candidates] == [
        'run', 'Outer.run', 'Outer.Inner.run', 'Other.run', 'Choice.run', 'Either.run',
    ]
    ordinal = _extract_ordinal_element(zig, 3, 'function')
    method = _extract_by_syntax(zig, 'Outer.Inner.run', _parse_element_syntax('Outer.Inner.run'))
    assert (ordinal['line_start'], ordinal['line_end'], ordinal['source']) == (
        method['line_start'], method['line_end'], method['source'],
    )


def test_zig_noncontainers_and_anonymous_values_are_not_owners(zig):
    for address in ('scalar.run', 'Derived.hidden', 'factory.hidden', 'Missing.run'):
        assert resolve_path(zig, address) is None
    assert _extract_element_at_line(zig, 11) is None
