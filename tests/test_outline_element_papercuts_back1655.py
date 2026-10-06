"""BACK-1655: C++ namespace-qualified element names and multi-line signatures.

`reveal tt.cpp "TT::probe"` said "Element not found" for a function inside
`namespace TT { }` (the Available list printed `probe`); a Rust `fn search(\\n ...)`
printed ") [879 lines]" in --outline with its name lost, because the parameter list
spanned lines.
"""

import pytest

from reveal.display.element import _extract_by_syntax, _parse_element_syntax
from reveal.display.outline import build_hierarchy
from reveal.registry import get_analyzer

pytestmark = pytest.mark.component

_CPP = """namespace TT {
  struct Entry { int x; };
  int probe(int k) { return k; }
  namespace Inner {
    int deep(int a) { return a; }
  }
}
int probe(int k, int j) { return k + j; }
class Thread {
 public:
  int qsearch(int a) { return a; }
};
int TT::other(int z) { return z; }
"""


def _analyzer(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    return get_analyzer(str(path))(str(path))


def _extract(analyzer, element):
    return _extract_by_syntax(analyzer, element, _parse_element_syntax(element))


@pytest.mark.parametrize('element, line', [
    ('TT::probe', 3),
    ('TT::Inner::deep', 5),
    ('Inner::deep', 5),
    ('Thread::qsearch', 11),
    ('TT.probe', 3),          # the dotted spelling keeps working
])
def test_namespace_qualified_name_extracts(tmp_path, element, line):
    result = _extract(_analyzer(tmp_path, 'tt.cpp', _CPP), element)
    assert result is not None, element
    assert result['line_start'] == line


@pytest.mark.parametrize('element', ['Nope::probe', 'TT::missing', 'Thread::probe'])
def test_unknown_qualifier_is_still_not_found(tmp_path, element):
    assert _extract(_analyzer(tmp_path, 'tt.cpp', _CPP), element) is None


def test_bare_and_out_of_line_names_unchanged(tmp_path):
    analyzer = _analyzer(tmp_path, 'tt.cpp', _CPP)
    assert _extract(analyzer, 'TT::other')['line_start'] == 13   # out-of-line definition, stored name
    assert _extract(analyzer, 'deep')['line_start'] == 5


_RUST = """fn search<NODE: NodeType>(
    td: &mut ThreadData,
    depth: i32,
) -> i32 {
    depth
}

pub fn simple(a: i32) -> i32 { a }
"""


@pytest.mark.parametrize('name, source, expected', [
    ('s.rs', _RUST, 'td: &mut ThreadData, depth: i32'),
    ('m.py', 'def f(\n    a,\n    b,\n) -> int:\n    return a\n', 'a, b'),
    ('m.go', 'package p\n\nfunc F(\n\ta int,\n\tb int,\n) int {\n\treturn a\n}\n', 'a int, b int'),
])
def test_multiline_signature_is_one_line_with_its_name(tmp_path, name, source, expected):
    items = _analyzer(tmp_path, name, source).get_structure()['functions']
    sig = items[0]['signature']
    assert '\n' not in sig
    assert expected in sig


def test_rust_outline_row_is_one_line_starting_with_the_name(tmp_path):
    from reveal.display.outline import _build_item_display
    analyzer = _analyzer(tmp_path, 's.rs', _RUST)
    structure = {k: v for k, v in analyzer.get_outline().items() if k != 'imports'}
    row = _build_item_display(build_hierarchy(structure)[0])
    assert '\n' not in row
    assert row.startswith('search(')


def test_single_line_signature_is_untouched(tmp_path):
    items = _analyzer(tmp_path, 's.rs', _RUST).get_structure()['functions']
    assert items[1]['signature'] == '(a: i32)'
