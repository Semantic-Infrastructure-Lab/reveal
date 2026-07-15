"""BACK-447: guard the output-contract construction surface.

The Output Contract (the ``contract_version`` / ``type`` / ``source`` /
``meta`` dict every adapter returns) is reveal's agent-facing API.
``ResultBuilder`` (``reveal/utils/results.py``) is meant to be the *sole*
constructor of that contract so a future contract-version bump touches one
place, not every adapter.

Two guards:

1. ``ResourceAdapter.create_meta`` must not re-implement the meta contract —
   it must delegate to ``ResultBuilder`` so there is exactly one meta builder.
2. A ratchet on hand-built ``'contract_version': ...`` dict literals. At
   filing time 154 such literals existed across the adapters (the migration
   away from them is incremental — see BACK-447). This test freezes that
   number as a ceiling: new adapters must go through ``ResultBuilder``
   (which adds zero literals), and migrating an old one only lowers the
   count. If this assertion fails because the number went *up*, a new adapter
   is hand-building the contract instead of using ``ResultBuilder``. If it
   fails because the number went *down*, lower ``BASELINE`` to match — the
   ratchet only ever tightens.
"""

import re
from pathlib import Path

from reveal.adapters.base import ResourceAdapter
from reveal.utils.results import ResultBuilder

# Files that legitimately define the contract rather than consume it.
_CANONICAL = {
    Path("reveal/utils/results.py"),          # the sole constructor lives here
    Path("reveal/templates/adapter_template.py"),  # documents the pattern
}

# Frozen baseline — occurrences of a hand-built ``'contract_version':`` dict
# key outside the canonical files. Ratchet: may shrink, must never grow.
BASELINE = 145

_LITERAL = re.compile(r"""['"]contract_version['"]\s*:""")


def _reveal_root() -> Path:
    # tests/ sits directly under the external-git checkout root.
    return Path(__file__).resolve().parent.parent / "reveal"


def _count_hand_built_literals() -> int:
    root = _reveal_root()
    total = 0
    for py in root.rglob("*.py"):
        rel = py.relative_to(root.parent)
        if rel in _CANONICAL:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        total += len(_LITERAL.findall(text))
    return total


def test_resource_adapter_create_meta_delegates_to_result_builder():
    """ResourceAdapter.create_meta must not re-implement the meta contract."""
    inputs = dict(
        parse_mode="tree_sitter_full",
        confidence=1.5,  # exercises the [0,1] clamp
        warnings=[{"code": "W001", "message": "x"}],
        errors=[{"code": "E001", "message": "y"}],
    )
    assert ResourceAdapter.create_meta(**inputs) == ResultBuilder.create_meta(**inputs)


def test_result_builder_create_meta_public_and_alias_agree():
    """The public name and the back-compat _create_meta alias are identical."""
    assert ResultBuilder.create_meta(confidence=0.9) == ResultBuilder._create_meta(
        confidence=0.9
    )


def test_hand_built_contract_literals_do_not_grow():
    """Ratchet: hand-built contract_version literals may shrink, never grow."""
    count = _count_hand_built_literals()
    assert count <= BASELINE, (
        f"Hand-built 'contract_version' literals rose to {count} (baseline "
        f"{BASELINE}). New adapters must construct the Output Contract via "
        f"ResultBuilder, not a raw dict — see BACK-447."
    )
