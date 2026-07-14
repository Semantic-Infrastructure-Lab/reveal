"""BACK-437: make accepted-hard semantic gaps VISIBLE in test output.

Non-Python ``--narrow`` is a real, open-by-design gap: it needs per-language
annotation/guard semantics, not a mechanical node-kind addition. See
``internal-docs/design/MULTI_LANGUAGE_ARCHITECTURE_2026-07-03.md``.

(BACK-421 parts 2/3 and BACK-428 — qualifier-preserving name extraction,
macro-hidden early returns, and Rust's `?`/tail-expression implicit exits —
have all been resolved. Their tests below are now plain regression tests:
``test_cpp_out_of_line_method_keeps_class_qualifier`` stays here since it
targets a synthetic tmp_path fixture, not the shared conformance corpus;
``test_cpp_macro_hidden_return_is_an_exit`` and
``test_rust_implicit_exits_are_found`` are now redundant with
``test_conformance_matrix.py``'s data-driven `exits`/`returns` checks but
are kept as easy-to-find named pins for these idioms.)

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


def test_cpp_macro_hidden_return_is_an_exit():
    """process_order's line-20 CHECK_OR_RETURN is a real early exit.

    Superseded by the real conformance matrix (expected.yaml's cpp `exits`/
    `returns` entries now include line 20) — kept here as a standalone,
    easy-to-find regression pin for this specific idiom.
    """
    out = _run(_FIXTURES / "cpp" / "sample.cpp", "process_order", "--exits",
               "--format", "json")
    exit_lines = {f["line"] for f in json.loads(out)["findings"]}
    assert 20 in exit_lines, (
        "macro-hidden early return at cpp/sample.cpp:20 should count as an exit"
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


def test_rust_implicit_exits_are_found():
    """process_order has 3 exits: `?` (L14), explicit return (L16), tail (L19).

    Superseded by the real conformance matrix (expected.yaml's rust `exits`/
    `returns` entries now include lines 14 and 19) — kept here as a
    standalone, easy-to-find regression pin for these two idioms.
    """
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
