#!/usr/bin/env python3
"""BACK-1048 prerequisite tool #1: dry-run codemod for BACK-620/BACK-573.

Rewrites raw zero-arg tree-sitter accessor calls --
``X.kind()`` / ``X.start_byte()`` / ``X.end_byte()`` / ``X.is_named()`` --
to route through ``reveal.core.treesitter_compat._zero_arg(X, 'name')``,
matching the pattern already used by the ~421 sites migrated so far (see
``reveal/analyzers/kotlin.py`` for a live example) and counted by
``tests/test_treesitter_accessor_ratchet.py``.

DRY-RUN ONLY. This script never writes to disk. Per the diligence protocol in
internal-docs/design/BACK573_TREESITTER_1125_FORWARD_COMPAT_2026-07-13.md
("Effort estimate + tooling recommendation"), real batches are applied one
file (or tightly related small batch) at a time, each followed by the
verification harness (verify_treesitter_migration.sh) -- never a blind
whole-tree pass. This tool's job is to make each batch's edit mechanical and
reviewable, not to apply it unsupervised.

Usage
-----
    # Summary across the whole source tree (or a subdir/file):
    python3 scripts/codemod_treesitter_accessors.py reveal/

    # Full unified diff for one file (the unit of a real migration batch):
    python3 scripts/codemod_treesitter_accessors.py reveal/treesitter.py --diff

    # Only one accessor, e.g. to batch by pattern instead of by file:
    python3 scripts/codemod_treesitter_accessors.py reveal/ --accessor kind

Receiver classification
------------------------
- "simple": the receiver expression is a bare identifier or an attribute
  chain (``node``, ``child``, ``self.tree``) -- the 95% case the design doc
  found safe for a scripted rewrite.
- "chained": the receiver itself contains a call or subscript
  (``node.child(1)``, ``_prev_sibling(node)``) -- rewritten too (the
  balanced-scan below handles it correctly) but flagged separately in the
  summary so a human skims the chained sites before trusting a batch.

What this does NOT do
----------------------
- Does not add the ``from ...core.treesitter_compat import _zero_arg``
  import -- report only; the design doc notes files already vary in import
  depth (``from ..core...`` vs ``from ...core...``), so the correct relative
  import is easiest for a human (or a follow-up pass) to get right per file.
- Does not touch ``.text`` (bare-attribute, ambiguous -- the design doc calls
  for a separate by-hand audit) or ``.child(i)`` (a real method in both API
  eras, needs no compat wrapper).
- Does not touch reveal/core/treesitter_compat.py itself (the canonical
  implementation of _zero_arg -- "don't touch it again").
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

ACCESSORS = ("kind", "start_byte", "end_byte", "is_named")
_SKIP_PATH_PARTS = {"core"}  # reveal/core/treesitter_compat.py is the impl, not a call site
_COMPAT_MODULE_NAME = "treesitter_compat.py"

# A receiver is "simple" if, read backward from the call site, it's nothing
# but identifier/attribute-chain characters -- no parens, no brackets, no
# quotes. Anything else (a trailing `)` or `]` immediately before the dot)
# means the balanced-paren scan had to step over a nested call/subscript.
_SIMPLE_RECEIVER_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_."
)


class CallSite:
    __slots__ = ("receiver_start", "call_end", "receiver", "accessor", "chained")

    def __init__(self, receiver_start: int, call_end: int, receiver: str, accessor: str):
        self.receiver_start = receiver_start
        self.call_end = call_end
        self.receiver = receiver
        self.accessor = accessor
        self.chained = not all(c in _SIMPLE_RECEIVER_CHARS for c in receiver)


def _find_receiver_start(text: str, dot_pos: int) -> int:
    """Scan backward from the '.' before an accessor call to find where the
    receiver expression begins, stepping over balanced ()/[] so a chained
    receiver like `node.child(1)` or `_prev_sibling(node)` is captured whole
    rather than truncated at its first inner paren.
    """
    i = dot_pos
    depth = 0
    while i > 0:
        c = text[i - 1]
        if c in ")]":
            depth += 1
            i -= 1
        elif c in "([":
            if depth == 0:
                break
            depth -= 1
            i -= 1
        elif depth > 0:
            i -= 1
        elif c.isalnum() or c in "_.'\"":
            i -= 1
        else:
            break
    return i


def find_call_sites(text: str, accessors=ACCESSORS) -> list[CallSite]:
    sites: list[CallSite] = []
    for accessor in accessors:
        needle = f".{accessor}("
        start = 0
        while True:
            dot_pos = text.find(needle, start)
            if dot_pos == -1:
                break
            # Confirm it's a genuine zero-arg call: only whitespace before ')'.
            close = text.find(")", dot_pos + len(needle))
            if close == -1:
                start = dot_pos + len(needle)
                continue
            between = text[dot_pos + len(needle):close]
            if between.strip() == "":
                receiver_start = _find_receiver_start(text, dot_pos)
                receiver = text[receiver_start:dot_pos]
                if receiver:  # a bare `.kind()` with no receiver isn't real Python
                    sites.append(CallSite(receiver_start, close + 1, receiver, accessor))
            start = dot_pos + len(needle)
    sites.sort(key=lambda s: s.receiver_start)
    return sites


def rewrite(text: str, sites: list[CallSite]) -> str:
    """Apply all call-site rewrites right-to-left so earlier offsets stay valid."""
    out = text
    for site in sorted(sites, key=lambda s: s.receiver_start, reverse=True):
        replacement = f"_zero_arg({site.receiver}, '{site.accessor}')"
        out = out[: site.receiver_start] + replacement + out[site.call_end :]
    return out


def _iter_target_files(root: Path):
    if root.is_file():
        yield root
        return
    for py in sorted(root.rglob("*.py")):
        if py.name == _COMPAT_MODULE_NAME:
            continue
        yield py


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="file or directory to scan (dry-run only)")
    parser.add_argument("--accessor", choices=ACCESSORS, help="limit to one accessor (default: all four)")
    parser.add_argument("--diff", action="store_true", help="print a unified diff per file instead of just a summary")
    args = parser.parse_args()

    accessors = (args.accessor,) if args.accessor else ACCESSORS

    total_simple = 0
    total_chained = 0
    files_touched = 0

    for py in _iter_target_files(args.path):
        text = py.read_text(encoding="utf-8", errors="replace")
        sites = find_call_sites(text, accessors)
        if not sites:
            continue
        files_touched += 1
        simple = [s for s in sites if not s.chained]
        chained = [s for s in sites if s.chained]
        total_simple += len(simple)
        total_chained += len(chained)
        print(f"{py}: {len(sites)} site(s) ({len(simple)} simple, {len(chained)} chained)")
        if chained:
            for s in chained:
                print(f"    chained: {s.receiver}.{s.accessor}()")
        if args.diff:
            new_text = rewrite(text, sites)
            diff = difflib.unified_diff(
                text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=str(py),
                tofile=f"{py} (proposed)",
            )
            sys.stdout.writelines(diff)
            print()

    print(
        f"\nTotal: {total_simple + total_chained} site(s) across {files_touched} file(s) "
        f"({total_simple} simple, {total_chained} chained) -- DRY RUN, nothing written."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
