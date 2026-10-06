"""BACK-1408: --boundary INPUTS must not list names that are not reads of a free variable.

Each case pairs a class of non-input (struct-literal key, func-literal parameter,
`instanceof T name` binding, C# attribute/type name, Scala `s"..."` interpolator)
with a REAL undefined read in the same function that must stay listed.
"""

import textwrap

import pytest
import tree_sitter_language_pack as ts

from reveal.adapters.ast.nav_boundary import collect_boundary
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root

_FUNCTION_KINDS = {
    'go': ('function_declaration',),
    'java': ('method_declaration',),
    'c_sharp': ('method_declaration',),
    'scala': ('function_definition',),
}


def _inputs(language: str, code: str) -> set:
    src = textwrap.dedent(code).lstrip('\n')
    data = src.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser(language), src))

    def get_text(node):
        return data[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    stack = [root]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') in _FUNCTION_KINDS[language] and \
                get_text(node.child_by_field_name('name')) == 'target':
            end = _zero_arg(node, 'end_position').row + 1
            result = collect_boundary(node, 1, end, get_text, language=language)
            return {d['var'] for d in result['inputs']}
        stack.extend(node.children)
    raise AssertionError('no function named target')


GO_STRUCT = """\
package p

type Opts struct {
    ResourceVersion string
    Timeout         int
}

type Names map[string]int

func target(rv string) {
    o := Opts{ResourceVersion: rv, Timeout: undefinedRead}
    m := map[string]int{freeKey: 1}
    n := Names{aliasKey: 2}
    _, _, _ = o, m, n
}
"""


class TestGoStructLiteralKeys:
    def test_struct_field_keys_are_not_inputs(self):
        got = _inputs('go', GO_STRUCT)
        assert 'ResourceVersion' not in got and 'Timeout' not in got

    def test_real_reads_beside_struct_keys_stay(self):
        got = _inputs('go', GO_STRUCT)
        assert {'rv', 'undefinedRead'} <= got

    def test_map_literal_keys_are_still_reads(self):
        # negative control: a map key is a value expression, not a field name
        assert 'freeKey' in _inputs('go', GO_STRUCT)

    def test_key_of_a_same_file_map_type_is_still_a_read(self):
        assert 'aliasKey' in _inputs('go', GO_STRUCT)


GO_CLOSURE = """\
package p

func target(a int) {
    h := func(x string, y int) error {
        return use(x, y, a, freeInClosure)
    }
    _ = h
}
"""


class TestGoFuncLiteralParams:
    def test_closure_params_are_not_inputs(self):
        got = _inputs('go', GO_CLOSURE)
        assert 'x' not in got and 'y' not in got

    def test_outer_param_and_free_names_in_closure_stay(self):
        got = _inputs('go', GO_CLOSURE)
        assert {'a', 'use', 'freeInClosure'} <= got


JAVA = """\
class A {
    String target(Object o, int k) {
        if (o instanceof String s && s.length() > k) {
            return s + missing;
        }
        if (!(o instanceof Integer n)) { return null; }
        return n.toString();
    }
}
"""


class TestJavaInstanceofBinding:
    def test_pattern_bindings_are_not_inputs(self):
        got = _inputs('java', JAVA)
        assert 's' not in got and 'n' not in got

    def test_params_and_free_reads_stay(self):
        assert {'o', 'k', 'missing'} <= _inputs('java', JAVA)


CSHARP = """\
class B {
    [Obsolete("x")]
    public System.Collections.Generic.List<Widget> target(Widget w, int a) {
        Widget local = new Widget();
        var x = (Gadget)w;
        var t = typeof(Thing);
        Foo<Bar>(a);
        return Other.Make<Item>(a) ?? missing;
    }
}
"""


class TestCSharpAttributeAndTypeNames:
    def test_attribute_type_and_qualified_names_are_not_inputs(self):
        got = _inputs('c_sharp', CSHARP)
        for name in ('Obsolete', 'Widget', 'Gadget', 'Thing', 'Bar', 'Item',
                     'Collections', 'Generic', 'List'):
            assert name not in got, name

    def test_real_reads_stay(self):
        # negative control: params, a generic CALL's callee name, an expression-position
        # base object and a plain undefined read are all genuine
        assert {'a', 'w', 'Foo', 'Other', 'missing'} <= _inputs('c_sharp', CSHARP)


SCALA = """\
object A {
  def target(a: Int, name: String): String =
    s"hello $name ${a + missing} " + sql"select $a"
}
"""


class TestScalaInterpolator:
    def test_standard_interpolator_is_not_an_input(self):
        assert 's' not in _inputs('scala', SCALA)

    def test_interpolated_reads_and_custom_interpolator_stay(self):
        # negative control: custom interpolators resolve through implicits in scope
        assert {'a', 'name', 'missing', 'sql'} <= _inputs('scala', SCALA)
