"""Parity check between reveal's two independent callee-extraction paths.

Reveal has TWO separate implementations that special-case the same
tree-sitter node kinds for callee-name extraction:

  - reveal/adapters/ast/nav_calls.py::_extract_callee
    feeds ast:// nav's --calls/--sideeffects/--boundary
  - reveal/treesitter.py::_get_callee_name (+ its _callee_name_generic /
    _callee_name_from_node helper chain)
    feeds get_structure()'s 'calls' field, which build_callers_index /
    calls:// actually depends on

A language-specific fix landing in only one of the two lets the OTHER path
stay silently wrong while looking complete — this happened for real three
times: Scala's `instance_expression` (BACK-718/720) was fixed in
nav_calls.py but missing from treesitter.py until BACK-730 note #17 caught
it (fixed there too, BACK-739); PHP's `scoped_call_expression` (BACK-736)
and Rust's `generic_function`/`parenthesized_expression` (BACK-733) were
fixed in treesitter.py but were missing from nav_calls.py until BACK-740/
BACK-741 mirrored them. All three are now fixed in both files — this test
exists to catch the *next* occurrence, not these specific ones.

Two layers of protection, both required:

1. `test_callee_dispatch_kind_handled_in_both_files` — a fast textual grep
   over both source files, catching the case where a node kind is added to
   one dispatcher and simply forgotten in the other (no source-level trace
   of it at all).
2. `TestCalleeDispatchBehavioralParity` — actually parses a real code
   fixture per node kind and runs it through BOTH extraction paths (nav_calls
   ::_extract_callee via range_calls(), and the language analyzer's real
   get_structure()), then asserts they produce the *same* callee string. The
   textual grep alone is not sufficient: a stub dispatch case that's present
   but wrong (wrong field access, wrong node child) passes the grep while
   still being behaviorally broken — this is exactly the shape of bug the
   grep would miss. `ONE_SIDED_EXPECTATIONS` documents the one case that's
   genuinely fine to diverge, and pins down *what* the divergence must look
   like rather than blanket-skipping it.
"""

import re
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any, Callable

import pytest
import tree_sitter_language_pack as ts

REVEAL_DIR = Path(__file__).resolve().parent.parent / "reveal"
NAV_CALLS = REVEAL_DIR / "adapters" / "ast" / "nav_calls.py"
TREESITTER = REVEAL_DIR / "treesitter.py"

# Node kinds that MUST be specially dispatched in both files' callee-name
# extraction. Adding a fix for one of these to one file without the other
# is the exact bug class this test exists to catch.
REQUIRED_IN_BOTH = {
    "member_call_expression",   # PHP $obj->method()
    "object_creation_expression",  # PHP/C# new ClassName()
    "scoped_call_expression",   # PHP self::/parent::/static::/Class::method() (BACK-736)
    "instance_expression",      # Scala new ClassName() (BACK-718/720/730#17)
    "infix_expression",         # Scala a :: b / list map f (BACK-746)
    "new_expression",           # C++ new ClassName() (BACK-730 C++ pre-flight)
    "method_invocation",        # Java obj.method() (BACK-734)
    "generic_function",         # Rust turbofish size_of::<u32>() (BACK-733)
    "parenthesized_expression",  # (f)(args) (BACK-733)
    "init_declarator",          # C++ direct-init: ClassName obj(args); (BACK-744)
}

# node_kind -> reason it's allowed to be one-sided, and which file may omit it.
ONE_SIDED_EXCEPTIONS = {
    "constructor_expression": (
        "Swift generic call/constructor (BACK-730 note #17). Only "
        "nav_calls.py special-cases it; treesitter.py's generic fallback "
        "happens to keep the real name before '<' so it's rescued without "
        "a dedicated dispatch case. Documented as a known coincidence, not "
        "a guaranteed invariant — if this ever breaks, add a dedicated "
        "_callee_name_swift_constructor handler instead of relaxing this "
        "test."
    ),
}


def _kind_is_handled(text: str, kind: str) -> bool:
    """True if `kind` appears as a quoted string compared for equality
    (or membership in a literal collection) anywhere in `text`."""
    return bool(re.search(rf"""['"]{re.escape(kind)}['"]""", text))


@pytest.mark.parametrize("kind", sorted(REQUIRED_IN_BOTH))
def test_callee_dispatch_kind_handled_in_both_files(kind):
    nav_text = NAV_CALLS.read_text()
    ts_text = TREESITTER.read_text()

    in_nav = _kind_is_handled(nav_text, kind)
    in_ts = _kind_is_handled(ts_text, kind)

    if kind in ONE_SIDED_EXCEPTIONS:
        pytest.skip(f"{kind}: documented one-sided exception — {ONE_SIDED_EXCEPTIONS[kind]}")

    assert in_nav, (
        f"Node kind '{kind}' is handled in treesitter.py's calls:// path "
        f"but missing from nav_calls.py's _extract_callee dispatch — "
        f"ast:// nav's --calls/--sideeffects/--boundary will silently "
        f"misname this call. Add a dispatch case mirroring treesitter.py."
    )
    assert in_ts, (
        f"Node kind '{kind}' is handled in nav_calls.py's ast:// nav path "
        f"but missing from treesitter.py's _get_callee_name dispatch — "
        f"calls:// will silently misname or drop this call (the exact "
        f"BACK-730 note #17 Scala bug). Add a dispatch case mirroring "
        f"nav_calls.py."
    )


# ---------------------------------------------------------------------------
# Behavioral parity: same fixture, both extraction paths, same answer.
#
# A textual grep can't tell a correct dispatch case from a present-but-wrong
# one (e.g. reading the wrong child index, or a field name that doesn't
# exist on this node shape). Each fixture below is real source for the node
# kind it targets; both paths are run against it and must agree.
# ---------------------------------------------------------------------------

def _nav_calls_callees(language: str, code: str) -> list:
    from reveal.adapters.ast.nav_calls import range_calls

    parser = ts.get_parser(language)
    src = textwrap.dedent(code).lstrip("\n")
    content_bytes = src.encode("utf-8")
    tree = parser.parse(src)
    root = tree.root_node()

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode("utf-8")

    calls = range_calls(root, 1, 999, get_text)
    return [c["callee"] for c in calls]


def _treesitter_callees(analyzer_cls, suffix: str, code: str) -> list:
    import os

    src = textwrap.dedent(code).lstrip("\n")
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(src)
        f.flush()
        temp_path = f.name

    try:
        analyzer = analyzer_cls(temp_path)
        structure = analyzer.get_structure()
        callees = []
        for fn in structure["functions"]:
            callees.extend(fn.get("calls") or [])
        return callees
    finally:
        os.unlink(temp_path)


class TestCalleeDispatchBehavioralParity(unittest.TestCase):
    """Each case parses a real fixture for one REQUIRED_IN_BOTH node kind
    through both extraction paths and asserts they agree on the callee
    string — not just that both files "mention" the node kind."""

    def test_php_member_call_expression(self):
        from reveal.analyzers.php import PhpAnalyzer

        code = """
        <?php
        class Foo {
            function bar($obj) {
                $obj->method();
            }
        }
        """
        nav = _nav_calls_callees("php", code)
        ts_calls = _treesitter_callees(PhpAnalyzer, ".php", code)
        self.assertIn("$obj->method", nav)
        self.assertIn("$obj->method", ts_calls)

    def test_php_object_creation_expression(self):
        from reveal.analyzers.php import PhpAnalyzer

        code = """
        <?php
        class Foo {
            function bar() {
                new Baz();
            }
        }
        """
        nav = _nav_calls_callees("php", code)
        ts_calls = _treesitter_callees(PhpAnalyzer, ".php", code)
        self.assertIn("new Baz", nav)
        self.assertIn("new Baz", ts_calls)

    def test_php_scoped_call_expression(self):
        from reveal.analyzers.php import PhpAnalyzer

        code = """
        <?php
        class Foo {
            function bar() {
                self::baz();
            }
        }
        """
        nav = _nav_calls_callees("php", code)
        ts_calls = _treesitter_callees(PhpAnalyzer, ".php", code)
        self.assertIn("self::baz", nav)
        self.assertIn("self::baz", ts_calls)
        # The specific bug BACK-740 fixed: dropping the method name entirely.
        self.assertNotIn("self", nav)

    def test_scala_instance_expression(self):
        from reveal.analyzers.scala import ScalaAnalyzer

        code = """
        object T {
          def foo(): Unit = {
            val f = new File("x")
          }
        }
        """
        nav = _nav_calls_callees("scala", code)
        ts_calls = _treesitter_callees(ScalaAnalyzer, ".scala", code)
        self.assertIn("new File", nav)
        self.assertIn("new File", ts_calls)

    def test_scala_instance_expression_qualified(self):
        # BACK-747: `new java.io.File(...)` (a stable_type_identifier), and
        # `new scala.Array[Byte](...)` (a stable_type_identifier inside a
        # generic_type) both resolve to the simple type name in both paths.
        from reveal.analyzers.scala import ScalaAnalyzer

        code = """
        object T {
          def foo(): Unit = {
            val f = new java.io.File("x")
            val a = new scala.Array[Byte](8)
          }
        }
        """
        nav = _nav_calls_callees("scala", code)
        ts_calls = _treesitter_callees(ScalaAnalyzer, ".scala", code)
        self.assertIn("new File", nav)
        self.assertIn("new File", ts_calls)
        self.assertIn("new Array", nav)
        self.assertIn("new Array", ts_calls)

    def test_scala_infix_expression(self):
        # BACK-746: infix method calls (`a :: b`, `list map f`) resolve to the
        # bare operator/method name in BOTH extraction paths.
        from reveal.analyzers.scala import ScalaAnalyzer

        code = """
        object T {
          def foo(): Unit = {
            val r = list map doubler
            val s = a :: rest
          }
        }
        """
        nav = _nav_calls_callees("scala", code)
        ts_calls = _treesitter_callees(ScalaAnalyzer, ".scala", code)
        self.assertIn("map", nav)
        self.assertIn("map", ts_calls)
        self.assertIn("::", nav)
        self.assertIn("::", ts_calls)

    def test_cpp_new_expression(self):
        from reveal.analyzers.cpp import CppAnalyzer

        code = """
        class Foo {
        public:
            Foo(int x) {}
        };

        void run() {
            Foo* f = new Foo(5);
        }
        """
        nav = _nav_calls_callees("cpp", code)
        ts_calls = _treesitter_callees(CppAnalyzer, ".cpp", code)
        self.assertIn("new Foo", nav)
        self.assertIn("new Foo", ts_calls)

    def test_cpp_direct_init(self):
        # BACK-744: C++'s OTHER constructor-call syntax, direct-initialization
        # (no `new` keyword, no call-expression wrapper at all) — parses to
        # `declaration > init_declarator` with a bare `argument_list` in its
        # 'value' field. Both paths must resolve the bare type name (no "new "
        # prefix), including through a qualified type (`std::vector`).
        from reveal.analyzers.cpp import CppAnalyzer

        code = """
        class Foo {
        public:
            Foo(int x, int y) {}
        };

        void run() {
            Foo obj(1, 2);
            std::vector<int> v(10);
        }
        """
        nav = _nav_calls_callees("cpp", code)
        ts_calls = _treesitter_callees(CppAnalyzer, ".cpp", code)
        self.assertIn("Foo", nav)
        self.assertIn("Foo", ts_calls)
        self.assertIn("vector<int>", nav)
        self.assertIn("vector<int>", ts_calls)

    def test_python_iife_chained_call_no_duplicate_raw_text(self):
        # BACK-732: `f(...)()` -- an outer call whose callee is itself a call
        # node (chained/IIFE-style). The inner call already gets its own
        # entry from the tree walk; both paths used to ALSO emit a second,
        # un-normalized entry holding the inner call's raw source text (found
        # via Home Assistant's helpers/temperature.py display_temp(), which
        # calls TemperatureConverter.converter_factory(unit, ha)(temperature)).
        # Only the normalized "Class.method" entry should survive.
        from reveal.analyzers.python import PythonAnalyzer

        code = """
        class TemperatureConverter:
            @staticmethod
            def converter_factory(unit, ha_unit):
                def convert(t):
                    return t
                return convert

        def display_temp(temperature_unit, ha_unit, temperature):
            return TemperatureConverter.converter_factory(temperature_unit, ha_unit)(temperature)
        """
        nav = _nav_calls_callees("python", code)
        ts_calls = _treesitter_callees(PythonAnalyzer, ".py", code)
        self.assertIn("TemperatureConverter.converter_factory", nav)
        self.assertIn("TemperatureConverter.converter_factory", ts_calls)
        for callee in nav + ts_calls:
            self.assertNotIn("(", callee, f"un-normalized raw call text leaked into callee list: {callee!r}")

    def test_cpp_direct_init_excludes_plain_and_copy_init(self):
        # BACK-744 regression guard: 'init_declarator' is shared with EVERY
        # other initialized declaration, not just direct-init. A plain
        # declaration (no initializer), a copy-init (`= Foo(...)`, already
        # captured as its own call_expression), and a primitive direct-init
        # (`int x(5);`, no user-defined constructor) must NOT produce a
        # bogus/duplicate entry in either path.
        from reveal.analyzers.cpp import CppAnalyzer

        code = """
        class Foo {
        public:
            Foo(int x, int y) {}
        };

        void run() {
            Foo uninitialized;
            Foo copy = Foo(3, 4);
            int x(5);
        }
        """
        nav = _nav_calls_callees("cpp", code)
        ts_calls = _treesitter_callees(CppAnalyzer, ".cpp", code)
        self.assertEqual(nav.count("Foo"), 1)  # only the copy-init call_expression
        self.assertEqual(ts_calls.count("Foo"), 1)
        self.assertNotIn(None, nav)
        self.assertNotIn("int", nav)
        self.assertNotIn("int", ts_calls)

    def test_java_method_invocation(self):
        from reveal.analyzers.java import JavaAnalyzer

        code = """
        class Foo {
            void bar() {
                Files.createDirectories(x);
            }
        }
        """
        nav = _nav_calls_callees("java", code)
        ts_calls = _treesitter_callees(JavaAnalyzer, ".java", code)
        self.assertIn("Files.createDirectories", nav)
        self.assertIn("Files.createDirectories", ts_calls)

    def test_rust_generic_function_turbofish(self):
        from reveal.analyzers.rust import RustAnalyzer

        code = """
        fn foo() {
            let n = size_of::<u32>();
        }
        """
        nav = _nav_calls_callees("rust", code)
        ts_calls = _treesitter_callees(RustAnalyzer, ".rs", code)
        self.assertIn("size_of", nav)
        self.assertIn("size_of", ts_calls)
        self.assertNotIn("size_of::<u32>", nav)
        self.assertNotIn("size_of::<u32>", ts_calls)

    def test_rust_parenthesized_callee(self):
        from reveal.analyzers.rust import RustAnalyzer

        code = """
        fn foo() {
            let f = get_handler();
            (f)(1, 2);
        }
        """
        nav = _nav_calls_callees("rust", code)
        ts_calls = _treesitter_callees(RustAnalyzer, ".rs", code)
        self.assertIn("f", nav)
        self.assertIn("f", ts_calls)

    def test_swift_constructor_expression_documented_one_sided_asymmetry(self):
        """The one node kind ONE_SIDED_EXCEPTIONS documents as intentionally
        divergent — pinned down precisely rather than skipped outright, so a
        change to *either* side's actual behavior fails this test instead of
        silently drifting further from the documented rationale."""
        from reveal.analyzers.swift import SwiftAnalyzer

        code = """
        func identity<T>(_ x: T) -> T { return x }
        func run() {
            let n = identity<Int>(5)
        }
        """
        nav = _nav_calls_callees("swift", code)
        ts_calls = _treesitter_callees(SwiftAnalyzer, ".swift", code)
        # nav_calls.py has a dedicated dispatch case: bare name.
        self.assertIn("identity", nav)
        # treesitter.py has NO dedicated case for constructor_expression —
        # get_structure() itself still carries the generic suffix. It's only
        # rescued at calls:// index-build time (_bare_callee_name), not here.
        self.assertIn("identity<Int>", ts_calls)
        self.assertNotIn("identity", [c for c in ts_calls if c != "identity<Int>"])


if __name__ == "__main__":
    unittest.main()
