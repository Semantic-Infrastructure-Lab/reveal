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

This test hardcodes the definitive set of node kinds that must be
special-cased in BOTH files (from a manual audit of the calls-recall
measurement program's commit history), so any future one-sided fix fails
CI instead of drifting silently. `ONE_SIDED_EXCEPTIONS` documents the one
case that's genuinely fine to leave asymmetric.
"""

import re
from pathlib import Path

import pytest

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
    "new_expression",           # C++ new ClassName() (BACK-730 C++ pre-flight)
    "method_invocation",        # Java obj.method() (BACK-734)
    "generic_function",         # Rust turbofish size_of::<u32>() (BACK-733)
    "parenthesized_expression",  # (f)(args) (BACK-733)
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
