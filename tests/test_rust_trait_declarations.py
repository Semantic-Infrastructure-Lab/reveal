"""BACK-1088: Rust `trait` declarations appear in the structure as interfaces."""

import pytest

from reveal.analyzers.rust import RustAnalyzer

CODE = '''pub trait Shape {
    fn area(&self) -> f64;
}

trait Named: Shape + std::fmt::Debug {}

trait Generic<T>: Shape where T: Clone {}

struct Square(f64);

impl Shape for Square {
    fn area(&self) -> f64 { self.0 }
}
'''


@pytest.fixture
def structure(tmp_path):
    path = tmp_path / 'shapes.rs'
    path.write_text(CODE, encoding='utf-8')
    return RustAnalyzer(str(path)).get_structure()


def test_traits_listed_as_interfaces(structure):
    by_name = {i['name']: i for i in structure['interfaces']}
    assert set(by_name) == {'Shape', 'Named', 'Generic'}
    assert by_name['Shape']['line'] == 1
    assert by_name['Shape']['line_end'] == 3


def test_supertraits_are_bases(structure):
    by_name = {i['name']: i for i in structure['interfaces']}
    assert by_name['Shape']['bases'] == []
    assert by_name['Named']['bases'] == ['Shape', 'std::fmt::Debug']
    assert by_name['Generic']['bases'] == ['Shape']


def test_structs_and_functions_unchanged(structure):
    assert [s['name'] for s in structure['structs']] == ['Square']
    assert [f['name'] for f in structure['functions']] == ['area']


def test_head_slice_applies_to_interfaces(tmp_path):
    path = tmp_path / 'shapes.rs'
    path.write_text(CODE, encoding='utf-8')
    sliced = RustAnalyzer(str(path)).get_structure(head=1)
    assert [i['name'] for i in sliced['interfaces']] == ['Shape']


def test_struct_bases_are_implemented_traits(tmp_path):
    path = tmp_path / 'impls.rs'
    path.write_text(
        'struct Foo<T>(T);\nstruct Bar;\nstruct Plain;\n'
        'impl Display for Foo<i32> {}\nimpl<T> Clone for Foo<T> {}\n'
        'impl Display for Foo<i32> {}\nimpl std::fmt::Debug for Bar {}\nimpl Foo<u8> {}\n',
        encoding='utf-8')
    by_name = {s['name']: s for s in RustAnalyzer(str(path)).get_structure()['structs']}
    assert by_name['Foo']['bases'] == ['Display', 'Clone']
    assert by_name['Bar']['bases'] == ['std::fmt::Debug']
    assert by_name['Plain']['bases'] == []


@pytest.mark.parametrize('value', ['interface', 'interfaces', 'trait'])
def test_ast_type_filter_accepts_singular_and_trait(tmp_path, value):
    """`type=interface` / `type=trait` used to return 0 silently: only the plural
    category name matched, unlike function/class/struct."""
    from reveal.adapters.ast.adapter import AstAdapter
    (tmp_path / 'shapes.rs').write_text(CODE, encoding='utf-8')
    result = AstAdapter(str(tmp_path), f'type={value}').get_structure()
    assert {r['name'] for r in result['results']} == {'Shape', 'Named', 'Generic'}
