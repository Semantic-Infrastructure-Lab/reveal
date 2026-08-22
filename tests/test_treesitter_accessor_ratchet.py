"""Regression ratchet: no *new* raw tree-sitter accessor call sites (BACK-573).

Context
-------
`tree-sitter-language-pack` <=1.12.2 returns a *vendored* parser exposing the old
py-tree-sitter API, where zero-argument ``Node``/``TreeCursor`` accessors are
methods (``node.kind()``). From core py-tree-sitter's newer API (surfaced when
language-pack >=1.12.5 hands back the *installed* parser) they are properties
(``node.kind``), and ``Parser.parse()`` requires ``bytes``. Reveal has ~700 call
sites still written against the old method-call form; the migration to route them
through ``reveal.core.treesitter_compat`` is BACK-573, deliberately deferred until
there's a driver (Python 3.14 support) — see
``internal-docs/design/BACK573_TREESITTER_1125_FORWARD_COMPAT_2026-07-13.md``.

What this guards
----------------
The 750-site problem exists *because* nothing stopped raw accessors from being
sprinkled tree-wide instead of going through one compat layer. This test is the
ratchet that stops it from regrowing: the counts below may only ever go **down**
(as sites are migrated onto the ``treesitter_compat`` helpers), never up. A new
raw ``.kind()`` / ``.start_byte()`` / etc. anywhere outside the compat module
fails this test and points the author at the helper to use instead.

``root_node()`` is baselined at 0 — it was fully migrated in ``floating-trajectory-0713``
(commit ``fb710d0``); this keeps it migrated.

Updating the baseline
---------------------
When you migrate call sites (lowering a count), re-run this test, read the
reported actual count from the failure message, and lower the matching
``BASELINE`` entry to it. Never *raise* a baseline to make the test pass — that
defeats the ratchet. Route the site through ``reveal.core.treesitter_compat``
instead (``tree_root``, ``ts_parse``, ``node_children``, or ``_zero_arg``).
"""

import re
from pathlib import Path

import reveal

# Zero-argument Node/TreeCursor accessors that flip method->property in the newer
# py-tree-sitter API, plus root_node (already fully migrated -> baseline 0).
# Counts are *occurrences* (multiple per line counted) found by the regex below,
# excluding the compat module itself. Ratchet direction: DOWN ONLY.
#
# All real BACK-620 call sites are migrated as of batch 8 (torrential-breeze-0821).
# The remaining kind=2/is_named=1 are permanent floors, not sites: this regex is a
# plain substring scan (see codemod_treesitter_accessors.py's own docstring), so it
# still flags 3 docstring/comment mentions the codemod itself correctly excludes --
# adapters/ast/nav_statewrites.py (`left.kind()`, BACK-439b/c history),
# analyzers/imports/rust.py (`` `.kind()` ``, grammar-quirk explanation), and
# core/node_taxonomy.py (`` `if not child.is_named(): continue` ``, code example).
#
# child_count/parent/start_position/end_position (BACK-1158, filed
# torrential-breeze-0821): a second, unscoped migration the codemod tool
# never covered until it was extended to find them. Baselines below are the
# as-filed raw-site counts, not yet migrated -- ratchet only guards against
# *growth* from here; batches lower these the same way BACK-620's did.
BASELINE = {
    "kind": 2,
    "start_byte": 0,
    "end_byte": 0,
    "is_named": 1,
    "root_node": 0,
    "child_count": 17,
    "parent": 35,
    "start_position": 127,
    "end_position": 38,
}

_SRC_ROOT = Path(reveal.__file__).parent
_COMPAT_MODULE = _SRC_ROOT / "core" / "treesitter_compat.py"


def _count_raw_accessors():
    """Return {accessor: (count, sorted_files)} across reveal's source (minus compat)."""
    patterns = {name: re.compile(r"\." + name + r"\(\s*\)") for name in BASELINE}
    counts = {name: 0 for name in BASELINE}
    files = {name: set() for name in BASELINE}
    for py in _SRC_ROOT.rglob("*.py"):
        if py == _COMPAT_MODULE:
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        for name, pat in patterns.items():
            hits = pat.findall(text)
            if hits:
                counts[name] += len(hits)
                files[name].add(py.relative_to(_SRC_ROOT))
    return {name: (counts[name], sorted(files[name])) for name in BASELINE}


def test_no_new_raw_treesitter_accessor_sites():
    """Raw tree-sitter accessor call sites must not increase (BACK-573 ratchet)."""
    actual = _count_raw_accessors()
    regressions = []
    for name, baseline in BASELINE.items():
        count, files = actual[name]
        if count > baseline:
            example = files[0] if files else "?"
            regressions.append(
                f"  .{name}(): {count} sites (baseline {baseline}, +{count - baseline}) "
                f"— e.g. {example}"
            )
    assert not regressions, (
        "New raw tree-sitter accessor call site(s) added (BACK-573). Route zero-arg\n"
        "accessors through reveal.core.treesitter_compat (tree_root / ts_parse /\n"
        "node_children / _zero_arg) instead of calling them directly:\n"
        + "\n".join(regressions)
    )


def test_ratchet_baseline_is_not_stale():
    """If every count has dropped below its baseline, the baseline should be lowered.

    A soft nudge (not a hard failure on any single drop): only fails when *all*
    tracked accessors sit strictly below baseline, meaning the whole ratchet has
    slack and should be re-tightened to lock in migration progress.
    """
    actual = _count_raw_accessors()
    all_below = all(
        actual[name][0] < baseline
        for name, baseline in BASELINE.items()
        if baseline > 0
    )
    if all_below:
        current = {name: actual[name][0] for name in BASELINE}
        raise AssertionError(
            "Every raw-accessor count is below its baseline — migration progressed.\n"
            f"Lower BASELINE in this file to the current counts to re-tighten:\n  {current}"
        )
