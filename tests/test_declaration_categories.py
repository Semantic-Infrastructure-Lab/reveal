"""BACK-1409: declaration kinds beyond functions/classes/structs appear in the
outline (TreeSitterAnalyzer.DECLARATION_CATEGORIES) and are extractable by name.

Before, C# enums/properties/indexers/delegates, Dart mixins/extensions/enums/
typedefs, Scala traits/objects/enums/type aliases, Java enums and annotation
interfaces, PHP traits/enums, Rust enums/type aliases and Swift/Kotlin type
aliases were missing from text, JSON and --outline with no sign they were skipped.
"""

from pathlib import Path

import pytest

from reveal.display.element import _extract_by_syntax, _parse_element_syntax
from reveal.registry import get_analyzer

pytestmark = pytest.mark.component

CASES = {
    "b.cs": ("""namespace N {
  public enum Color { Red, Green }
  public class Box {
    public int Size { get; set; }
    public string this[int i] { get { return ""; } }
  }
  public delegate void Handler(int x);
}
""", {"enums": ["Color"], "properties": ["Size", "this"], "delegates": ["Handler"]}),
    "b.dart": ("""mixin Walker { int walk() => 1; }
extension Ext on String { int twice() => 2; }
enum Color { red, green }
typedef IntFn = int Function(int);
typedef int Legacy(int x);
""", {"mixins": ["Walker"], "extensions": ["Ext"], "enums": ["Color"], "types": ["IntFn", "Legacy"]}),
    "b.scala": ("""trait Shape { def area: Int }
object Registry { def all = 1 }
enum Color { case Red, Green }
type Alias = Int
""", {"interfaces": ["Shape"], "objects": ["Registry"], "enums": ["Color"], "types": ["Alias"]}),
    "B.java": ("""public class B {
  enum Meta { A; boolean isMeta() { return true; } }
  @interface Marker {}
}
""", {"enums": ["Meta"], "interfaces": ["Marker"]}),
    "b.php": ("""<?php
trait Walk { function walk() { return 1; } }
enum Color { case Red; }
""", {"traits": ["Walk"], "enums": ["Color"]}),
    "b.rs": ("""pub trait Shape { fn area(&self) -> u32; }
pub enum Color { Red }
pub type Alias = u32;
""", {"interfaces": ["Shape"], "enums": ["Color"], "types": ["Alias"]}),
    "b.swift": ("""protocol Shape { func area() -> Int }
typealias Alias = Int
""", {"interfaces": ["Shape"], "types": ["Alias"]}),
    "b.kt": ("""interface Shape { fun area(): Int }
typealias Alias = Int
""", {"interfaces": ["Shape"], "types": ["Alias"]}),
    "c.ts": ("""enum Color { Red }
type Alias = number;
interface I { x: number }
""", {"interfaces": ["I"], "types": ["Alias"], "enums": ["Color"]}),
    "fifo.go": ("""package cache
type Queue interface {
\tPop() (interface{}, error)
}
""", {"interfaces": ["Queue"]}),
}


def _analyzer(tmp_path: Path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return get_analyzer(str(path))(str(path))


@pytest.mark.parametrize("name", sorted(CASES))
def test_declarations_are_listed(tmp_path, name):
    body, expected = CASES[name]
    structure = _analyzer(tmp_path, name, body).get_structure()
    assert {c: [i["name"] for i in structure.get(c, [])] for c in expected} == expected


@pytest.mark.parametrize("name", sorted(CASES))
def test_listed_declarations_are_extractable_by_name(tmp_path, name):
    body, expected = CASES[name]
    analyzer = _analyzer(tmp_path, name, body)
    structure = analyzer.get_structure()
    for category in expected:
        for item in structure[category]:
            result = _extract_by_syntax(analyzer, item["name"], _parse_element_syntax(item["name"]))
            assert result is not None, (category, item["name"])
            spans = [result] + result.get("candidates", [])
            assert any(s["line_start"] <= item["line_end"] and item["line"] <= s["line_end"] for s in spans), \
                (category, item["name"], result["line_start"])


def test_declaration_categories_honor_semantic_slicing(tmp_path):
    analyzer = _analyzer(tmp_path, "b.rs", "pub enum A { X }\npub enum B { Y }\npub enum C { Z }\n")
    assert [e["name"] for e in analyzer.get_structure(head=2)["enums"]] == ["A", "B"]
    assert [e["name"] for e in analyzer.get_structure(tail=1)["enums"]] == ["C"]


def test_typed_output_names_the_property_category(tmp_path):
    from reveal.structure import TypedStructure
    analyzer = _analyzer(tmp_path, "b.cs", CASES["b.cs"][0])
    typed = TypedStructure.from_analyzer_output(analyzer.get_structure(), str(tmp_path / "b.cs"))
    assert {e.name: e.category for e in typed.elements if e.name in ("Size", "this")} == \
        {"Size": "property", "this": "property"}
