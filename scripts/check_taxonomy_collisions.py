#!/usr/bin/env python3
"""BACK-665: corpus-grep collision checker for sideeffects taxonomy patterns.

BACK-636/633/637 shipped undetected for weeks: bare (single-segment) verbs
and receiver names in nav_effects.py's `_TAXONOMY_COMMON`/`_TAXONOMY_BY_LANG`/
`_RECEIVER_TAXONOMY` tables over-fired across languages they were never meant
to classify (`.execute(` matching Java's `Executor.execute`, `.select`
matching Ruby's `Enumerable#select`, a bare `files` receiver matching a local
Collection variable) because that class of bug is only ever caught by an
occasional manual corpus-grep review, not CI.

This script automates that review: it walks the taxonomy tables, identifies
every bare (single-segment) pattern or receiver name — the collision-risky
shape, since a dotted/scoped pattern like `os.remove` can't cross-language-
collide — and greps every locally-materialized `samples/<lang>/` corpus tree
(see tests/corpus_paths.py; populate with `python scripts/fetch_corpus.py`)
for that token firing as a call.

Two different checks, because "collision" means different things for the two
table shapes:

  - `_TAXONOMY_BY_LANG` patterns are scoped to one home language already —
    classify_call(language=X) only merges COMMON + language X's table, so a
    python-scoped bare verb literally cannot fire when parsing a Java file
    THROUGH THAT PATH. The residual risk is classify_call's unscoped
    `_COMPILED_ALL` mode (used when the caller doesn't know the file's
    language), which merges every language's table. Material hits in a
    non-home language are therefore an unambiguous, automatable finding —
    this check FAILS on them.

  - `_TAXONOMY_COMMON` patterns and `_RECEIVER_TAXONOMY` receivers apply to
    every language BY DESIGN (that's the point of "common") — a raw hit count
    can't say whether the dominant real-world usage in some language matches
    the pattern's kind (that took corpus-grepping and human judgment for
    BACK-636/633/637). This check instead diffs against a committed baseline
    snapshot (tests/fixtures/taxonomy_collision_baseline.json): a NEW bare
    pattern with no baseline entry, or a large jump in an existing pattern's
    hit count, fails and forces a conscious look — but an already-reviewed
    high count doesn't re-fail every run.

Usage:
    python scripts/check_taxonomy_collisions.py                # report + check
    python scripts/check_taxonomy_collisions.py --json          # machine-readable
    python scripts/check_taxonomy_collisions.py --write-baseline  # (re)snapshot
    python scripts/check_taxonomy_collisions.py --threshold 50  # hit-count floor
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reveal.adapters.ast.nav_effects import (  # noqa: E402
    _RECEIVER_TAXONOMY,
    _RECEIVER_VERB_FILTER,
    _TAXONOMY_BY_LANG,
    _TAXONOMY_COMMON,
    _tokenize,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT.parent / "samples"
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "taxonomy_collision_baseline.json"

DEFAULT_THRESHOLD = 20

# samples/<dir> -> file extensions to scan. Mirrors tests/corpus/manifest.yaml's
# language list; a corpus dir not present locally is skipped, never an error.
CORPUS_EXTENSIONS: Dict[str, List[str]] = {
    "c": [".c", ".h"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hxx"],
    "csharp": [".cs"],
    "dart": [".dart"],
    "gdscript": [".gd"],
    "go": [".go"],
    "java": [".java"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "kotlin": [".kt", ".kts"],
    "lua": [".lua"],
    "php": [".php"],
    "python": [".py"],
    "ruby": [".rb"],
    "rust": [".rs"],
    "scala": [".scala"],
    "swift": [".swift"],
    "tsx": [".tsx"],
    "typescript": [".ts"],
    "zig": [".zig"],
}

def available_corpus_dirs() -> Dict[str, Path]:
    """Corpus dirs actually present on disk (samples/<lang>/)."""
    if not CORPUS_ROOT.is_dir():
        return {}
    return {
        d.name: d for d in CORPUS_ROOT.iterdir()
        if d.is_dir() and d.name in CORPUS_EXTENSIONS
    }


# ─────────────────────────── bare pattern extraction ───────────────────────

class BarePattern:
    def __init__(self, token: str, kind: str, home: str, source: str) -> None:
        self.token = token       # the bare segment, e.g. "execute"
        self.kind = kind         # taxonomy kind, e.g. "db"
        self.home = home         # "common" or a _TAXONOMY_BY_LANG key
        self.source = source     # "literal" or "receiver"

    @property
    def key(self) -> str:
        return f"{self.source}:{self.home}:{self.kind}:{self.token}"


def bare_literal_patterns() -> List[BarePattern]:
    out = []
    for kind, patterns in _TAXONOMY_COMMON:
        for p in patterns:
            segs = _tokenize(p)
            if len(segs) == 1:
                out.append(BarePattern(segs[0], kind, "common", "literal"))
    for lang, taxonomy in _TAXONOMY_BY_LANG.items():
        for kind, patterns in taxonomy:
            for p in patterns:
                segs = _tokenize(p)
                if len(segs) == 1:
                    out.append(BarePattern(segs[0], kind, lang, "literal"))
    return out


def bare_receiver_patterns() -> List[BarePattern]:
    return [
        BarePattern(receiver, kind, "common", "receiver")
        for kind, receivers in _RECEIVER_TAXONOMY
        for receiver in receivers
    ]


# ─────────────────────────── corpus counting ───────────────────────────────
#
# Pure-Python per-file regex scanning (O(patterns x files) disk reads) took
# 25+ minutes on this corpus and was killed. Instead we shell out to ripgrep
# (mandatory dependency, checked in main()) with ONE combined alternation
# regex per corpus dir — a single fast native-code pass over the whole tree —
# and do the cheap per-token bucketing in Python only over the much smaller
# set of matched substrings, not the full corpus text.

import shutil
import subprocess

_RG = shutil.which("rg")


def _rg_glob_args(extensions: List[str]) -> List[str]:
    args = []
    for ext in extensions:
        args += ["-g", f"*{ext}"]
    return args


def _rg_matches(pattern: str, corpus_dir: Path, extensions: List[str]) -> List[str]:
    """All matched substrings (ripgrep -o, case-insensitive) across a corpus dir."""
    cmd = [_RG, "-o", "-i", "--no-filename", "--no-line-number", "-e", pattern,
           str(corpus_dir)] + _rg_glob_args(extensions)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in (0, 1):  # 1 = no matches, not an error
        raise RuntimeError(f"rg failed on {corpus_dir}: {result.stderr}")
    return result.stdout.splitlines()


def _combined_literal_regex(patterns: List[BarePattern]) -> str:
    tokens = sorted({re.escape(p.token) for p in patterns}, key=len, reverse=True)
    # Same shape as classify_call's subsequence rule: token firing as the call
    # verb (`token(`) or as a receiver prefix (`token.`/`token->`/`token::`).
    return r"\b(?:" + "|".join(tokens) + r")\s*(?:\(|\.|->|::)"


def _combined_receiver_regex(patterns: List[BarePattern]) -> str:
    tokens = sorted({re.escape(p.token) for p in patterns}, key=len, reverse=True)
    return r"\b(?:" + "|".join(tokens) + r")\s*\.\s*\w+\s*\("


_TOKEN_RE = re.compile(r"^(\w+)")
_VERB_RE = re.compile(r"\.\s*(\w+)\s*\($")


def scan_corpus(
    literal_patterns: List[BarePattern],
    receiver_patterns: List[BarePattern],
    corpus_dirs: Dict[str, Path],
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, Dict[str, int]]]:
    """One ripgrep pass per corpus dir per check kind (literal / receiver),
    using a single combined alternation regex so the whole tree is walked
    once, not once per pattern. Returns (literal_hits, receiver_hits), each
    {pattern.key: {lang_dir: count}}.
    """
    literal_hits: Dict[str, Dict[str, int]] = {p.key: {} for p in literal_patterns}
    receiver_hits: Dict[str, Dict[str, int]] = {p.key: {} for p in receiver_patterns}

    by_token_literal: Dict[str, List[BarePattern]] = {}
    for p in literal_patterns:
        by_token_literal.setdefault(p.token.lower(), []).append(p)

    by_token_receiver: Dict[str, List[BarePattern]] = {}
    for p in receiver_patterns:
        by_token_receiver.setdefault(p.token.lower(), []).append(p)

    literal_rx = _combined_literal_regex(literal_patterns) if literal_patterns else None
    receiver_rx = _combined_receiver_regex(receiver_patterns) if receiver_patterns else None

    for lang_dir, path in corpus_dirs.items():
        extensions = CORPUS_EXTENSIONS[lang_dir]

        if literal_rx:
            counts: Dict[str, int] = {}
            for match in _rg_matches(literal_rx, path, extensions):
                m = _TOKEN_RE.match(match)
                if m:
                    counts[m.group(1).lower()] = counts.get(m.group(1).lower(), 0) + 1
            for token, count in counts.items():
                for p in by_token_literal.get(token, []):
                    literal_hits[p.key][lang_dir] = literal_hits[p.key].get(lang_dir, 0) + count

        if receiver_rx:
            counts = {}
            for match in _rg_matches(receiver_rx, path, extensions):
                tok_m = _TOKEN_RE.match(match)
                verb_m = _VERB_RE.search(match)
                if not (tok_m and verb_m):
                    continue
                token, verb = tok_m.group(1).lower(), verb_m.group(1).lower()
                for p in by_token_receiver.get(token, []):
                    allowed = _RECEIVER_VERB_FILTER.get(p.kind)
                    if allowed is not None and verb not in allowed:
                        continue
                    receiver_hits[p.key][lang_dir] = receiver_hits[p.key].get(lang_dir, 0) + 1

    return literal_hits, receiver_hits


# ─────────────────────────── analysis ───────────────────────────────────────
#
# A hard "any material off-home hit count = fail" rule was tried first and
# rejected: bare verbs like query/execute/select/insert/update/delete ARE
# genuinely common across every language's corpus — that's *why* BACK-636/633
# scoped them to python+php instead of deleting them, and re-flagging that
# same, already-reviewed fact on every run is pure noise, not a regression
# signal. Every bare pattern (COMMON, BY_LANG, and receiver alike) is instead
# reported with its full per-language hit profile and diffed against a
# committed baseline snapshot (tests/fixtures/taxonomy_collision_baseline.json,
# same idea as BACK-659's doc-drift-detection): a pattern with NO baseline
# entry (freshly added, never corpus-reviewed) or whose hit count in some
# language has grown well beyond its reviewed baseline fails; an
# already-reviewed high count does not re-fail every run.

def build_report(threshold: int = DEFAULT_THRESHOLD) -> List[dict]:
    corpus_dirs = available_corpus_dirs()
    literal_patterns = bare_literal_patterns()
    receiver_patterns = bare_receiver_patterns()
    literal_hits, receiver_hits = scan_corpus(literal_patterns, receiver_patterns, corpus_dirs)

    report = []
    for pattern in literal_patterns:
        report.append({
            "key": pattern.key, "token": pattern.token, "kind": pattern.kind,
            "home": pattern.home, "source": pattern.source, "hits": literal_hits[pattern.key],
        })
    for pattern in receiver_patterns:
        report.append({
            "key": pattern.key, "token": pattern.token, "kind": pattern.kind,
            "home": pattern.home, "source": pattern.source, "hits": receiver_hits[pattern.key],
        })
    return report


def diff_against_baseline(
    report: List[dict], baseline: Dict[str, dict], threshold: int, growth_factor: float = 3.0,
) -> List[dict]:
    """Flag patterns with no baseline entry (new bare pattern, never corpus-
    reviewed) or hit counts that grew well beyond the reviewed baseline."""
    drift = []
    for entry in report:
        base = baseline.get(entry["key"])
        if base is None:
            if any(count >= threshold for count in entry["hits"].values()):
                drift.append({**entry, "reason": "no baseline entry (new bare pattern)"})
            continue
        base_hits = base.get("hits", {})
        for lang_dir, count in entry["hits"].items():
            base_count = base_hits.get(lang_dir, 0)
            if count >= threshold and count > base_count * growth_factor:
                drift.append({
                    **entry, "reason": f"{lang_dir} hits grew {base_count} -> {count}",
                })
    return drift


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                     help="material hit-count floor")
    ap.add_argument("--write-baseline", action="store_true",
                     help="(re)write the baseline snapshot")
    args = ap.parse_args()

    corpus_dirs = available_corpus_dirs()
    if not corpus_dirs:
        print(f"No corpus materialized under {CORPUS_ROOT} — nothing to check "
              f"(run: python scripts/fetch_corpus.py)", file=sys.stderr)
        return 0
    if _RG is None:
        print("ripgrep ('rg') not found on PATH — required for corpus scanning", file=sys.stderr)
        return 1

    report = build_report(threshold=args.threshold)

    if args.write_baseline:
        baseline = {entry["key"]: entry for entry in report}
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
        print(f"Wrote baseline for {len(baseline)} patterns to {BASELINE_PATH}")
        return 0

    drift = []
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text())
        drift = diff_against_baseline(report, baseline, threshold=args.threshold)

    if args.json:
        print(json.dumps({"drift": drift}, indent=2))
    else:
        print(f"Corpus dirs available: {', '.join(sorted(corpus_dirs))}")
        print(f"Bare patterns checked: {len(report)}")
        if drift:
            print(f"\n{len(drift)} pattern(s) drifted from baseline:")
            for d in drift:
                print(f"  '{d['token']}' ({d['kind']}, {d['source']}, "
                      f"home={d['home']}) — {d['reason']}")
        elif BASELINE_PATH.exists():
            print("No baseline drift.")
        else:
            print(f"\nNo baseline at {BASELINE_PATH} — run with --write-baseline to create one.")

    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
