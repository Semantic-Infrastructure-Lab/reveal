#!/usr/bin/env bash
# Run what .github/workflows/test.yml runs, in an environment that matches CI's.
#
# Why this exists: a dev machine drifts from CI. Ours pinned an old tree-sitter-language-pack
# (vendored builtins.Node, which has Node.to_sexp) while CI installs the latest (core
# tree_sitter.Node, which does not) -- so a change passed every local check and failed every CI
# job. The pieces that differ, and what this script does about each:
#   - dependency versions  -> a dedicated venv, `pip install -e ".[dev]"` with eager upgrades,
#                             exactly as CI installs (optionally forcing a language-pack version)
#   - Python version       -> --python picks 3.10 / 3.12 / 3.14 (CI's matrix)
#   - CI-only steps        -> also runs the Windows-compat lint, CLI smoke, V-series
#                             self-validation, and the B006 ratchet (none run in the plain pytest)
#   - local caches/env     -> REVEAL_DISK_CACHE=0 (stale ~/.reveal/cache, BACK-1294) and
#                             PYTHONPYCACHEPREFIX unset (stale bytecode)
#   - Windows text encoding -> re-runs pytest under an ASCII locale (PYTHONUTF8=0 LC_ALL=C, no
#                             PYTHONIOENCODING) and runs scripts/check_text_encoding.py
# What it cannot do: run Windows or macOS. scripts/check_windows_compat.py is the local guard
# for the Windows path class; anything else Windows-specific still needs CI.
#
# Usage:
#   scripts/ci-local.sh                     # Python 3.12, latest deps (CI's `test` job)
#   scripts/ci-local.sh --python 3.14
#   scripts/ci-local.sh --lp 1.12.5         # force tree-sitter-language-pack (CI's compat-matrix)
#   scripts/ci-local.sh --no-tests          # only the non-pytest CI steps
#   scripts/ci-local.sh --fresh             # rebuild the venv from scratch
set -euo pipefail

PY_VERSION="3.12"
LP_VERSION=""
RUN_TESTS=1
FRESH=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --python) PY_VERSION="$2"; shift 2 ;;
        --lp) LP_VERSION="$2"; shift 2 ;;
        --no-tests) RUN_TESTS=0; shift ;;
        --fresh) FRESH=1; shift ;;
        -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

PY_BIN="$(command -v "python${PY_VERSION}" || true)"
if [[ -z "$PY_BIN" ]]; then
    echo "python${PY_VERSION} not found on PATH (CI's matrix: 3.10, 3.12, 3.14)" >&2
    exit 2
fi

VENV="${REVEAL_CI_VENV_ROOT:-$HOME/.cache/reveal-ci}/py${PY_VERSION}${LP_VERSION:+-lp$LP_VERSION}"
LOG_DIR="${REVEAL_CI_LOG_DIR:-$(dirname "$VENV")/logs}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ci-local-py${PY_VERSION}${LP_VERSION:+-lp$LP_VERSION}-$(date +%Y%m%d-%H%M%S).log"

step() { printf '\n== %s ==\n' "$1" | tee -a "$LOG"; }
fail() { printf 'FAIL: %s (log: %s)\n' "$1" "$LOG" >&2; exit 1; }

[[ $FRESH -eq 1 ]] && rm -rf "$VENV"
if [[ ! -x "$VENV/bin/python" ]]; then
    step "Create venv $VENV ($($PY_BIN --version))"
    "$PY_BIN" -m venv "$VENV" >>"$LOG" 2>&1 || fail "venv creation"
fi
PY="$VENV/bin/python"

# Same install as CI, plus eager upgrades so we track "latest" the way a fresh CI runner does.
step "Install dependencies (CI: pip install -e .[dev]${LP_VERSION:+, then language-pack==$LP_VERSION})"
"$PY" -m pip install -q --upgrade pip >>"$LOG" 2>&1
"$PY" -m pip install -q --upgrade --upgrade-strategy eager -e ".[dev]" >>"$LOG" 2>&1 || fail "pip install"
"$PY" -m pip install -q --upgrade build pytest-xdist >>"$LOG" 2>&1 || fail "pip install build"
if [[ -n "$LP_VERSION" ]]; then
    "$PY" -m pip install -q "tree-sitter-language-pack==$LP_VERSION" >>"$LOG" 2>&1 || fail "language-pack pin"
fi
echo "tree-sitter: $("$PY" -m pip list 2>/dev/null | grep -iE '^tree-sitter( |-language-pack)' | tr -s ' ' | tr '\n' ';')" | tee -a "$LOG"

# Env hygiene: nothing from the developer's shell may leak into the run.
export REVEAL_DISK_CACHE=0
export PYTHONIOENCODING=utf-8
unset PYTHONPYCACHEPREFIX PYTHONPATH

if [[ $RUN_TESTS -eq 1 ]]; then
    step "Run tests (pytest tests/)"
    "$PY" -m pytest tests/ -q -p no:cacheprovider -n auto >>"$LOG" 2>&1 \
        || { grep -E '^FAILED |^ERROR ' "$LOG" | head -30; fail "pytest"; }
    tail -1 "$LOG"

    step "Run tests under an ASCII locale (Windows cp1252 stand-in)"
    env -u PYTHONIOENCODING PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 LC_ALL=C \
        "$PY" -m pytest tests/ -q -p no:cacheprovider -n auto >>"$LOG" 2>&1 \
        || { grep -E '^FAILED |^ERROR ' "$LOG" | tail -30; fail "pytest under ASCII locale"; }
    tail -1 "$LOG"
fi

step "Windows compatibility checks"
"$PY" scripts/check_windows_compat.py --warn >>"$LOG" 2>&1 || fail "windows compat"
"$PY" scripts/check_text_encoding.py >>"$LOG" 2>&1 || { tail -8 "$LOG"; fail "text encoding (bare read_text/open breaks on Windows)"; }

step "CLI basics"
"$VENV/bin/reveal" --version >>"$LOG" 2>&1 && "$VENV/bin/reveal" --list-supported >>"$LOG" 2>&1 || fail "CLI basics"

step "Reveal self-validation (V-series)"
"$PY" - >>"$LOG" 2>&1 <<'EOF' || fail "V-series self-validation"
from reveal.adapters.reveal import RevealAdapter
from reveal.rules import RuleRegistry

structure = RevealAdapter().get_structure()
detections = RuleRegistry.check_file(file_path='reveal://', structure=structure, content='', select=['V'])
if detections:
    for d in detections:
        print(f'  [{d.severity.value.upper()}] {d.rule_code}: {d.message}')
    raise SystemExit(1)
print('V-series self-validation passed')
EOF

step "B006 ratchet"
BASELINE=$(cat .github/b006_baseline.txt)
COUNT=$( ("$VENV/bin/reveal" check reveal --select=B006 --format=json 2>/dev/null || true) \
    | "$PY" -c "import json,sys; print(json.load(sys.stdin)['summary']['total_issues'])")
echo "B006 issues: $COUNT (baseline: $BASELINE)" | tee -a "$LOG"
[[ "$COUNT" -le "$BASELINE" ]] || fail "B006 count increased ($BASELINE -> $COUNT)"

printf '\nCI-parity run passed (python %s%s). Log: %s\n' "$PY_VERSION" "${LP_VERSION:+, language-pack $LP_VERSION}" "$LOG"
