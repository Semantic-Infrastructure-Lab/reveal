"""BACK-1400: by-name element resolution -- ambiguity is disclosed, never silent,
and every definition the outline lists has an address that reaches it.

Covers the three surfaces sharing reveal/element_resolve.py: element
extraction (`reveal file NAME`), nav flags (`reveal file NAME --boundary`),
and MCP `reveal_element`. Each case below was a live finding in the
earthly-sea-0922 manual test pass (GRJ9, C8, CC6).
"""

from pathlib import Path

import pytest

from reveal.display.element import _extract_by_syntax, _parse_element_syntax, extract_element
from reveal.registry import get_analyzer

pytestmark = pytest.mark.component


def _analyzer(tmp_path: Path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return get_analyzer(str(path))(str(path))


def _extract(analyzer, element: str):
    return _extract_by_syntax(analyzer, element, _parse_element_syntax(element))


def _span(result):
    return result["line_start"], result["line_end"]


PY_TWO_POPS = "class A:\n    def pop(self): return 1\nclass B:\n    def pop(self): return 2\n"

JAVA_OVERLOADS = """class Doc {
    public void removeField(String path) {
        removeField(path, false);
    }

    public void removeField(String path, boolean ignoreMissing) {
        if (ignoreMissing) { return; }
        throw new IllegalArgumentException(path);
    }
}
"""

RUST_TRAIT_IMPLS = """pub trait Upgrade { fn upgrade(&self) -> u32; }
pub struct First;
impl Upgrade for First {
    fn upgrade(&self) -> u32 { 1 }
}
pub struct Second;
impl super::Upgrade for Second {
    fn upgrade(&self) -> u32 { 2 }
}
"""


# ---------------------------------------------------------------------------
# Bare names: first match, but the others are disclosed with an address
# ---------------------------------------------------------------------------

class TestAmbiguousBareName:
    def test_python_same_named_methods_are_disclosed(self, tmp_path):
        result = _extract(_analyzer(tmp_path, "a.py", PY_TWO_POPS), "pop")
        assert _span(result) == (2, 2)  # unchanged pick: the first
        assert [(c["name"], c["address"], c["selected"]) for c in result["candidates"]] == [
            ("A.pop", "A.pop", True),
            ("B.pop", "B.pop", False),
        ]

    def test_unique_name_has_no_candidates(self, tmp_path):
        result = _extract(_analyzer(tmp_path, "a.py", "class A:\n    def only(self): pass\n"), "only")
        assert "candidates" not in result

    def test_java_overloads_share_a_qualified_name_so_the_address_is_the_span(self, tmp_path):
        analyzer = _analyzer(tmp_path, "Doc.java", JAVA_OVERLOADS)
        result = _extract(analyzer, "removeField")
        assert [(c["name"], c["address"]) for c in result["candidates"]] == [
            ("Doc.removeField", ":2-4"),
            ("Doc.removeField", ":6-9"),
        ]
        # The span address really selects the 66-line overload the finding
        # called unreachable (here: the second one).
        assert _span(_extract(analyzer, ":6-9")) == (6, 9)

    def test_go_receiver_methods_are_qualified_by_receiver(self, tmp_path):
        analyzer = _analyzer(tmp_path, "heap.go", (
            "package cache\n"
            "type heapData struct{}\n"
            "func (h *heapData) Pop() interface{} { return nil }\n"
            "type Heap struct{}\n"
            "func (h *Heap) Pop() (interface{}, error) { return nil, nil }\n"
        ))
        result = _extract(analyzer, "Pop")
        assert [c["address"] for c in result["candidates"]] == ["heapData.Pop", "Heap.Pop"]
        assert _span(_extract(analyzer, "Heap.Pop")) == (5, 5)

    def test_class_and_its_own_constructor_are_not_ambiguous(self, tmp_path):
        # The constructor is nested in the class you got; disclosing it on
        # every `reveal X.java Foo` would be noise, not information.
        analyzer = _analyzer(tmp_path, "Foo.java", "class Foo {\n    Foo() {\n    }\n}\n")
        result = _extract(analyzer, "Foo")
        assert _span(result) == (1, 4)
        assert "candidates" not in result

    def test_same_name_in_another_tier_is_disclosed(self, tmp_path):
        # Found by the corpus sweep (meilitool upgrade/v1_9.rs): the enum wins
        # the type tier, and the struct in a sibling module was unreachable.
        analyzer = _analyzer(tmp_path, "a.rs", (
            "pub enum Options { A }\n"
            "mod v2 {\n"
            "    pub struct Options { x: u32 }\n"
            "}\n"
        ))
        result = _extract(analyzer, "Options")
        assert _span(result) == (1, 1)
        assert [c["line_start"] for c in result["candidates"]] == [1, 3]

    def test_js_method_and_const_function_value_are_disclosed(self, tmp_path):
        # Found by the corpus sweep (VS Code themes.contribution.ts): a getter
        # won, and the same-named `const themes = ...` value was unreachable.
        analyzer = _analyzer(tmp_path, "a.ts", (
            "class Picker {\n"
            "    get themes() { return []; }\n"
            "}\n"
            "const themes = () => [];\n"
        ))
        result = _extract(analyzer, "themes")
        assert _span(result) == (2, 2)
        assert [c["line_start"] for c in result["candidates"]] == [2, 4]

    def test_repeated_test_label_is_disclosed(self, tmp_path):
        analyzer = _analyzer(tmp_path, "a.test.ts", (
            "describe('a', () => {\n"
            "    test('returns undefined', () => {});\n"
            "});\n"
            "describe('b', () => {\n"
            "    test('returns undefined', () => {});\n"
            "});\n"
        ))
        result = _extract(analyzer, "test(returns undefined)")
        assert [c["line_start"] for c in result["candidates"]] == [2, 5]
        assert [c["address"] for c in result["candidates"]] == [":2-2", ":5-5"]

    def test_every_address_selects_exactly_its_candidate(self, tmp_path):
        for name, body, element in (
            ("a.py", PY_TWO_POPS, "pop"),
            ("Doc.java", JAVA_OVERLOADS, "removeField"),
            ("a.rs", RUST_TRAIT_IMPLS, "upgrade"),
        ):
            analyzer = _analyzer(tmp_path, name, body)
            for candidate in _extract(analyzer, element)["candidates"]:
                picked = _extract(analyzer, candidate["address"])
                assert picked["line_start"] == candidate["line_start"], (name, candidate)
                assert "candidates" not in picked, (name, candidate)


# ---------------------------------------------------------------------------
# Parent.member
# ---------------------------------------------------------------------------

class TestMemberResolution:
    def test_rust_inherent_impl_behind_a_same_named_struct(self, tmp_path):
        # `struct Foo;` came first and has no members; the old first-parent-wins
        # walk stopped there and never reached `impl Foo`.
        analyzer = _analyzer(tmp_path, "i.rs", "pub struct Foo;\nimpl Foo {\n    pub fn bar(&self) -> u32 { 1 }\n}\n")
        assert _span(_extract(analyzer, "Foo.bar")) == (3, 3)

    def test_rust_trait_impl_is_addressed_by_its_self_type(self, tmp_path):
        analyzer = _analyzer(tmp_path, "a.rs", RUST_TRAIT_IMPLS)
        # `impl super::Upgrade for Second` used to be named by its Self type and
        # `impl Upgrade for First` by its trait -- whichever type_identifier came
        # first. Both answer to their Self type now.
        assert _span(_extract(analyzer, "First.upgrade")) == (4, 4)
        assert _span(_extract(analyzer, "Second.upgrade")) == (8, 8)

    def test_rust_trait_name_lists_every_impl(self, tmp_path):
        result = _extract(_analyzer(tmp_path, "a.rs", RUST_TRAIT_IMPLS), "Upgrade.upgrade")
        assert [c["address"] for c in result["candidates"]] == ["First.upgrade", "Second.upgrade"]

    def test_rust_generic_impl_self_type(self, tmp_path):
        analyzer = _analyzer(tmp_path, "a.rs", "trait Tr { fn d(&self); }\nimpl<T> Tr for Vec<T> { fn d(&self) {} }\n")
        assert _span(_extract(analyzer, "Vec.d")) == (2, 2)

    def test_cpp_out_of_line_definition(self, tmp_path):
        analyzer = _analyzer(tmp_path, "f.cpp", (
            "#include <vector>\n"
            "class FileAccess { public: static std::vector<int> get_bytes(int p); };\n"
            "std::vector<int> FileAccess::get_bytes(int p) {\n"
            "    return {p};\n"
            "}\n"
        ))
        for element in ("FileAccess.get_bytes", "get_bytes", "FileAccess::get_bytes"):
            assert _span(_extract(analyzer, element)) == (3, 5), element

    @pytest.mark.parametrize("element, span", [
        ("Vec.operator+", (3, 3)),       # inline in the struct
        ("Vec.operator==", (8, 10)),     # out-of-line Vec::operator==
        ("Vec.operator()", (5, 5)),
        ("Vec.~Vec", (6, 6)),
    ])
    def test_cpp_operator_and_destructor_members(self, tmp_path, element, span):
        # CC6: `Vec.operator+` failed the Parent.member syntax check and fell
        # through to a bare-name lookup of the literal string.
        analyzer = _analyzer(tmp_path, "v.cpp", (
            "struct Vec {\n"
            "  int x;\n"
            "  Vec operator+(const Vec &o) const { return Vec{x + o.x}; }\n"
            "  bool operator==(const Vec &o) const;\n"
            "  int operator()(int i) const { return i; }\n"
            "  ~Vec() {}\n"
            "};\n"
            "bool Vec::operator==(const Vec &o) const {\n"
            "  return x == o.x;\n"
            "}\n"
        ))
        assert _span(_extract(analyzer, element)) == span

    @pytest.mark.parametrize("element, kind", [
        ("Vec.operator<<=", "hierarchical"),
        ("Outer.Inner.m", "hierarchical"),
        ("v1.2.3", "name"),
        ("rr.php sentinel locking", "name"),
        ("a.operator new", "name"),
    ])
    def test_member_path_syntax(self, element, kind):
        assert _parse_element_syntax(element)["type"] == kind

    def test_direct_member_wins_over_nested_class_member(self, tmp_path):
        analyzer = _analyzer(tmp_path, "a.py", (
            "class Outer:\n"
            "    def m(self): return 1\n"
            "    class Inner:\n"
            "        def m(self): return 2\n"
        ))
        result = _extract(analyzer, "Outer.m")
        assert _span(result) == (2, 2)
        assert "candidates" not in result

    def test_nested_qualified_name_is_an_address(self, tmp_path):
        # Candidate lists print qualified names like Doc.Metadata.isMetadata;
        # each must work as an address, so deeper paths resolve too.
        analyzer = _analyzer(tmp_path, "Doc.java", JAVA_NESTED_ENUM)
        assert _span(_extract(analyzer, "Doc.Metadata.isMetadata")) == (6, 8)
        assert _extract(analyzer, "Other.Metadata.isMetadata") is None

    def test_dotted_name_that_is_not_a_member_path_falls_back_to_the_name(self, tmp_path):
        # `setup.py` parses as Parent.member; a markdown heading by that name
        # used to be "not found".
        analyzer = _analyzer(tmp_path, "doc.md", "# Files\n\n## setup.py\n\nBuild config.\n")
        result = _extract(analyzer, "setup.py")
        assert result is not None and result["line_start"] == 3

    def test_nested_member_still_found_when_no_direct_one(self, tmp_path):
        # Ruby `Module.method` where the method lives in a class inside the
        # module: the pre-BACK-1400 whole-subtree search, kept as a fallback.
        analyzer = _analyzer(tmp_path, "a.rb", "module Svc\n  class Job\n    def run\n      1\n    end\n  end\nend\n")
        assert _span(_extract(analyzer, "Svc.run")) == (3, 5)


# ---------------------------------------------------------------------------
# Type declarations beyond class/struct
# ---------------------------------------------------------------------------

JAVA_NESTED_ENUM = """class Doc {
    enum Metadata {
        INDEX("_index");
        Metadata(String fieldName) {
        }
        public static boolean isMetadata(String field) {
            return false;
        }
    }
}
"""


class TestTypeDeclarations:
    def test_java_enum_beats_its_constructor(self, tmp_path):
        # The enum wasn't in any type tier, so the bare name fell through to
        # the function tier and returned the enum's constructor.
        analyzer = _analyzer(tmp_path, "Doc.java", JAVA_NESTED_ENUM)
        assert _span(_extract(analyzer, "Metadata")) == (2, 9)

    def test_java_enum_is_a_member_container(self, tmp_path):
        analyzer = _analyzer(tmp_path, "Doc.java", JAVA_NESTED_ENUM)
        assert _span(_extract(analyzer, "Metadata.isMetadata")) == (6, 8)

    @pytest.mark.parametrize("name, body, element, line", [
        ("a.rs", "trait Tr { fn d(&self) -> u32 { 1 } }\n", "Tr.d", 1),
        ("a.cs", "namespace N {\n  struct P {\n    int M() { return 1; }\n  }\n}\n", "P.M", 3),
        ("a.scala", "object Obj {\n  def f = 1\n}\n", "Obj.f", 2),
        ("a.scala", "trait Tr {\n  def g = 2\n}\n", "Tr.g", 2),
        ("a.dart", "mixin M {\n  int f() => 1;\n}\n", "M.f", 2),
        ("a.dart", "extension Ext on String {\n  int g() => 2;\n}\n", "Ext.g", 2),
        ("a.php", "<?php\ntrait T {\n  function f() { return 1; }\n}\n", "T.f", 3),
        ("a.ts", "namespace NS {\n  export function f() { return 1 }\n}\n", "NS.f", 2),
    ])
    def test_member_of_type_declaration(self, tmp_path, name, body, element, line):
        result = _extract(_analyzer(tmp_path, name, body), element)
        assert result is not None, element
        assert result["line_start"] == line


# ---------------------------------------------------------------------------
# Listed in the outline => extractable
# ---------------------------------------------------------------------------

def test_go_interface_listed_in_outline_is_extractable(tmp_path):
    analyzer = _analyzer(tmp_path, "fifo.go", (
        "package cache\n"
        "type Queue interface {\n"
        "\tPop() (interface{}, error)\n"
        "}\n"
    ))
    assert [i["name"] for i in analyzer.get_structure()["interfaces"]] == ["Queue"]
    result = _extract(analyzer, "Queue")
    assert _span(result) == (2, 4)
    assert result["source"].startswith("type Queue interface {")


# ---------------------------------------------------------------------------
# Surfaces: CLI text, nav flags, MCP
# ---------------------------------------------------------------------------

class TestSurfaces:
    def test_cli_note_goes_to_stderr_and_stdout_is_unchanged(self, tmp_path, capsys):
        analyzer = _analyzer(tmp_path, "a.py", PY_TWO_POPS)
        extract_element(analyzer, "pop", "text")
        out, err = capsys.readouterr()
        assert "matches 2 definitions" in err
        assert f"reveal {analyzer.path} B.pop" in err
        assert "matches" not in out
        assert "def pop(self): return 1" in out

    def test_nav_flag_reports_ambiguity(self, tmp_path, capsys):
        from reveal.file_handler import _resolve_func_node
        analyzer = _analyzer(tmp_path, "a.py", PY_TWO_POPS)
        _, start, end = _resolve_func_node(analyzer, "pop")
        assert (start, end) == (2, 2)
        assert "matches 2 definitions" in capsys.readouterr().err

    def test_nav_flag_resolves_rust_inherent_impl(self, tmp_path):
        from reveal.file_handler import _resolve_func_node
        analyzer = _analyzer(tmp_path, "i.rs", "pub struct Foo;\nimpl Foo {\n    pub fn bar(&self) -> u32 { 1 }\n}\n")
        _, start, end = _resolve_func_node(analyzer, "Foo.bar")
        assert (start, end) == (3, 3)

    def test_mcp_reveal_element_carries_the_note(self, tmp_path):
        from reveal.mcp_server import reveal_element
        path = tmp_path / "a.py"
        path.write_text(PY_TWO_POPS, encoding="utf-8")
        text = reveal_element(str(path), "pop")
        assert "def pop(self): return 1" in text
        assert "matches 2 definitions" in text
        assert f"reveal {path} B.pop" in text
