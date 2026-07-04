"""BACK-437: make accepted-hard semantic gaps VISIBLE in test output.

BACK-421 (parts 2/3), BACK-428, and non-Python ``--narrow`` are real,
open-by-design gaps: each needs per-idiom *semantic* work (macro-name
heuristics, qualifier-preserving name extraction, per-language exit/annotation
semantics), not a mechanical node-kind addition. See
``internal-docs/design/MULTI_LANGUAGE_ARCHITECTURE_2026-07-03.md``.

Until this file existed, those gaps lived only in prose — BACKLOG notes and
``expected.yaml`` comments — so a fully-green conformance suite read as "no
known gaps." Each test below asserts the *desired* (gap-closed) behavior and
is marked ``xfail(strict=True)``:

  * Today it reports **XFAIL** — the gap is real and now shows up in the test
    report instead of being invisible.
  * When someone actually fixes the gap, the test **XPASSes**, and because
    ``strict=True`` an unexpected pass is a hard failure — forcing them to
    delete the marker and (ideally) fold the assertion into the real
    conformance matrix. The gap cannot be silently closed and forgotten.

If you are here because a strict-xfail flipped to failing: congratulations,
you fixed the gap. Remove the ``@pytest.mark.xfail`` decorator and move the
assertion into ``test_conformance_matrix.py`` / update the fixture's
``expected.yaml``.
"""

import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

_FIXTURES = Path(__file__).parent / "fixtures" / "conformance"


def _run(*args) -> str:
    res = _run_reveal_direct(*[str(a) for a in args])
    assert res.returncode == 0, f"reveal exited {res.returncode}\n{res.stderr}"
    return res.stdout


@pytest.mark.xfail(
    strict=True,
    reason="BACK-421 part 3: macro-hidden early return is invisible to --exits. "
    "CHECK_OR_RETURN(...) expands to `if (!(cond)) return (val)` but tree-sitter "
    "parses the raw source, seeing a plain call_expression, not a "
    "return_statement. Needs macro-name heuristics, not node-kind matching.",
)
def test_cpp_macro_hidden_return_is_an_exit():
    """process_order's line-20 CHECK_OR_RETURN is a real early exit."""
    out = _run(_FIXTURES / "cpp" / "sample.cpp", "process_order", "--exits",
               "--format", "json")
    exit_lines = {f["line"] for f in json.loads(out)["findings"]}
    assert 20 in exit_lines, (
        "macro-hidden early return at cpp/sample.cpp:20 should count as an exit"
    )


@pytest.mark.xfail(
    strict=True,
    reason="BACK-421 part 2: out-of-line `Widget::compute` definitions strip the "
    "`Widget::` qualifier during name extraction, so the method is reported as a "
    "free function `compute` with no class association. Needs qualifier-preserving "
    "name extraction in treesitter.py.",
)
def test_cpp_out_of_line_method_keeps_class_qualifier(tmp_path):
    """An out-of-line C++ method definition should keep its class association."""
    src = tmp_path / "widget.cpp"
    src.write_text(
        "class Widget {\n"
        "public:\n"
        "    int compute(int x);\n"
        "};\n"
        "\n"
        "int Widget::compute(int x) {\n"
        "    if (x < 0) {\n"
        "        return -1;\n"
        "    }\n"
        "    return x * 2;\n"
        "}\n"
    )
    out = _run(src, "--format", "json")
    data = json.loads(out)
    # Collect every function-ish name reveal reports for the file.
    names = json.dumps(data)
    assert "Widget::compute" in names or "Widget.compute" in names, (
        "out-of-line definition should preserve the Widget class qualifier, "
        f"not flatten to a bare `compute`:\n{out}"
    )


@pytest.mark.xfail(
    strict=True,
    reason="BACK-428: Rust's implicit exits are invisible to --exits — the `?` "
    "postfix operator (early Err return) and a bare tail expression (the "
    "function's return value) are not `return_statement`/`return_expression` "
    "nodes. Needs per-idiom 'what counts as exiting this function' semantics.",
)
def test_rust_implicit_exits_are_found():
    """process_order has 3 exits: `?` (L14), explicit return (L16), tail (L19)."""
    out = _run(_FIXTURES / "rust" / "sample.rs", "process_order", "--exits",
               "--format", "json")
    exit_lines = {f["line"] for f in json.loads(out)["findings"]}
    assert {14, 16, 19} <= exit_lines, (
        f"Rust `?` and tail-expression exits should be found, got {sorted(exit_lines)}"
    )


@pytest.mark.xfail(
    strict=True,
    reason="Non-Python --narrow: the type-narrowing walker only understands "
    "Python grammar (typed_parameter, Optional/Union, isinstance). A TypeScript "
    "union param narrowed by `typeof` reports 'No annotation' even though the "
    "annotation is right there. Needs per-language annotation/guard semantics.",
)
def test_typescript_union_param_narrows(tmp_path):
    """`x: string | number` narrowed by typeof should produce narrowing events."""
    src = tmp_path / "narrow.ts"
    src.write_text(
        "function handle(x: string | number): number {\n"
        '    if (typeof x === "string") {\n'
        "        return x.length;\n"
        "    }\n"
        "    return x;\n"
        "}\n"
    )
    out = _run(src, "handle", "--narrow", "x")
    assert "No annotation" not in out, (
        "TypeScript union param has an annotation; --narrow should not claim "
        f"it is missing:\n{out}"
    )
