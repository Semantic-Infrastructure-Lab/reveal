"""BACK-665: regression test for nav_effects.py's bare-verb taxonomy tables.

Runs scripts/check_taxonomy_collisions.py against the real-corpus dogfood
tree (see tests/corpus_paths.py) so a newly added bare (single-segment)
pattern in _TAXONOMY_COMMON/_TAXONOMY_BY_LANG/_RECEIVER_TAXONOMY -- the shape
that let BACK-636/633/637 ship undetected for weeks, caught only by an
occasional manual sideeffects-recall-oracle sweep -- gets corpus-checked on
every nav_effects.py change instead. Skips cleanly when the corpus isn't
materialized (never present in CI or a fresh clone, see tests/corpus_paths.py)
or ripgrep isn't on PATH.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_taxonomy_collisions as checker  # noqa: E402


def test_no_new_taxonomy_bare_pattern_collisions():
    if not checker.available_corpus_dirs():
        pytest.skip(f"real corpus not materialized under {checker.CORPUS_ROOT} "
                     f"(run: python scripts/fetch_corpus.py)")
    if checker._RG is None:
        pytest.skip("ripgrep ('rg') not on PATH")
    if not checker.BASELINE_PATH.exists():
        pytest.skip(f"no baseline at {checker.BASELINE_PATH} "
                     f"(run: python scripts/check_taxonomy_collisions.py --write-baseline)")

    baseline = json.loads(checker.BASELINE_PATH.read_text())
    report = checker.build_report(threshold=checker.DEFAULT_THRESHOLD)
    drift = checker.diff_against_baseline(report, baseline, threshold=checker.DEFAULT_THRESHOLD)

    assert not drift, (
        "New or grown corpus collision risk in nav_effects.py's bare taxonomy "
        "patterns (see scripts/check_taxonomy_collisions.py, BACK-665). If this "
        "is a deliberate, reviewed change, regenerate the baseline with "
        "`python scripts/check_taxonomy_collisions.py --write-baseline`:\n" +
        "\n".join(
            f"  '{d['token']}' ({d['kind']}, {d['source']}, home={d['home']}) -- {d['reason']}"
            for d in drift
        )
    )
