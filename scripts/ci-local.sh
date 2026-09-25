#!/usr/bin/env bash
# Run what .github/workflows/test.yml runs, in an environment that matches CI's.
#
# Why this exists: a dev machine drifts from CI. Ours pinned an old tree-sitter-language-pack
# (vendored builtins.Node, which has Node.to_sexp) while CI installs the latest (core
# tree_sitter.Node, which does not) -- so a change passed every local check and failed every CI
# job. The pieces that differ, and what this script does about each:
#   - dependency versions  -> a dedicated venv, `pip install -e ".[dev]"` with eager upgrades,
#                             exactly as CI installs (optionally forcing a language-pack version)
#   - Python version       -> --python picks one of CI's matrix (3.10 / 3.12 / 3.14);
#                             --matrix runs all three, plus CI's language-pack floor leg (below)
#   - CI-only steps        -> the primary leg (3.12, no --lp) also runs the Windows-compat lint,
#                             V-series self-validation and B006 ratchet, which CI runs only on
#                             ubuntu/3.12; other legs run pytest + CLI basics, as CI does
#   - local caches/env     -> REVEAL_DISK_CACHE=0 (stale ~/.reveal/cache, BACK-1294) and
#                             PYTHONPYCACHEPREFIX unset (stale bytecode)
#   - Windows text encoding -> PYTHONWARNDEFAULTENCODING=1, so reveal/ text I/O without encoding=
#                             fails its test (pyproject filterwarnings), and scripts/check_text_encoding.py.
#                             Console output under a non-UTF-8 stream: tests/test_console_encoding.py.
#                             This replaced a full second pytest run under LC_ALL=C (~5 min, never
#                             caught anything the other checks missed)
# What it cannot do: run Windows or macOS. scripts/check_windows_compat.py is the local guard
# for the Windows path class; anything else Windows-specific still needs CI.
#
# Usage:
#   scripts/ci-local.sh                     # Python 3.12, latest deps (CI's ubuntu/3.12 `test` leg)
#   scripts/ci-local.sh --python 3.14
#   scripts/ci-local.sh --matrix            # 3.10, 3.12, 3.14, then 3.12 @ language-pack 1.8.1 (~8 min: legs measured 92-113 s of pytest each; run it in tmux)
#   scripts/ci-local.sh --matrix -- tests/test_foo.py   # fast: only these pytest targets per leg
#   scripts/ci-local.sh --lp 1.12.5         # force tree-sitter-language-pack (CI's compat-matrix)
#   scripts/ci-local.sh --matrix --changed  # per-commit check (~1 min): only the test files you added/edited
#                                           # vs upstream, on every leg incl. the language-pack floor
#   scripts/ci-local.sh --no-tests          # only the non-pytest CI steps
#   scripts/ci-local.sh --fresh             # rebuild the venv from scratch
#
# What only --matrix catches (both reached GitHub CI from a green 3.12 run, BACK-1438):
#   - 3.10: PEP 701 f-strings (same quote nested inside, backslashes in {...}) are 3.12+ syntax
#   - 3.14: tokenize/ast read PEP 750 t-strings and PEP 758 bare except natively, so code or
#           test expectations written around their absence differ
# What only the language-pack floor leg (3.12 @ 1.8.1, CI's compat-matrix `include`) catches:
#   - 1.8.1 is the only leg on the vendored builtins.Node, where start_byte/end_byte/start_point are
#     bound METHODS; 1.12.5+ make them properties. Bare `node.start_byte` in reveal/ or tests/ passes
#     everywhere but here and raises "slice indices must be integers" -- go through _zero_arg
#     (BACK-1406's test helper did, and reached CI red after a green 3-version --matrix).
# What only GitHub's Windows legs catch -- check by hand before pushing tests that do this:
#   - a Windows path as a re.sub replacement string (backslashes are escapes): pass a lambda
#   - '/tmp' or other POSIX paths: not a directory on Windows; use tmp_path/tempfile.gettempdir()
#   - shell=True / POSIX quoting in subprocess: pass an argument list
#   - str(path) compared or split on '/': use Path parts or as_posix() (check_windows_compat.py)
#   - open()/read_text() without encoding=: cp1252 default (check_text_encoding.py)
# Bare node.start_byte etc. (floor leg above) is also linted in seconds: check_treesitter_accessors.py.
set -euo pipefail

MATRIX_VERSIONS=(3.10 3.12 3.14)  # keep in step with .github/workflows/test.yml
FLOOR_LP=1.8.1                    # the compat matrix's `include` leg (3.12 @ pyproject's floor); same file

PY_VERSION="3.12"
PY_EXPLICIT=0
LP_VERSION=""
RUN_TESTS=1
FRESH=0
MATRIX=0
CHANGED=0
PYTEST_TARGETS=(tests/)
EXPLICIT_TARGETS=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --python) PY_VERSION="$2"; PY_EXPLICIT=1; shift 2 ;;
        --lp) LP_VERSION="$2"; shift 2 ;;
        --no-tests) RUN_TESTS=0; shift ;;
        --fresh) FRESH=1; shift ;;
        --matrix) MATRIX=1; shift ;;
        --changed) CHANGED=1; shift ;;
        --) shift; [[ $# -gt 0 ]] && { PYTEST_TARGETS=("$@"); EXPLICIT_TARGETS=1; }; break ;;
        -h|--help) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

# --changed: pytest targets = test files added/edited vs upstream (committed, staged, unstaged, new).
# It catches what a NEW test does on an old dependency (BACK-1406's helper, red only on the language-pack
# floor) in seconds; it cannot see a source change breaking an untouched test -- that is the full run's job.
if [[ $CHANGED -eq 1 ]]; then
    [[ $EXPLICIT_TARGETS -eq 1 ]] && { echo "--changed and explicit pytest targets are exclusive" >&2; exit 2; }
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    BASE="$(git -C "$REPO_ROOT" merge-base HEAD '@{upstream}' 2>/dev/null || git -C "$REPO_ROOT" merge-base HEAD origin/master)"
    PYTEST_TARGETS=()
    while IFS= read -r f; do
        [[ -f "$REPO_ROOT/$f" ]] && PYTEST_TARGETS+=("$f")
    done < <({ git -C "$REPO_ROOT" diff --name-only "$BASE"; git -C "$REPO_ROOT" ls-files --others --exclude-standard; } \
                 | grep -E '^tests/.*test_[^/]*\.py$' | sort -u)
    if [[ ${#PYTEST_TARGETS[@]} -eq 0 ]]; then
        echo "--changed: no test files changed vs ${BASE:0:8}; skipping pytest" >&2
        RUN_TESTS=0
        PYTEST_TARGETS=(tests/)
    else
        echo "--changed: ${#PYTEST_TARGETS[@]} test file(s) vs ${BASE:0:8}" >&2
    fi
fi

if [[ $MATRIX -eq 1 ]]; then
    [[ $PY_EXPLICIT -eq 1 ]] && { echo "--matrix and --python are exclusive" >&2; exit 2; }
    leg_args=()
    [[ $FRESH -eq 1 ]] && leg_args+=(--fresh)
    [[ $RUN_TESTS -eq 0 ]] && leg_args+=(--no-tests)
    # Legs are "python:language-pack". An explicit --lp pins every leg; otherwise the Python legs use
    # latest deps (as CI's `test` job does) and one extra leg pins the language-pack floor.
    legs=()
    for v in "${MATRIX_VERSIONS[@]}"; do legs+=("$v:$LP_VERSION"); done
    [[ -z "$LP_VERSION" ]] && legs+=("3.12:$FLOOR_LP")
    # Every leg runs even after a failure (CI's fail-fast: false), so one run shows all breakage.
    results=()
    status=0
    for leg in "${legs[@]}"; do
        v="${leg%%:*}"; lp="${leg#*:}"
        label="python $v${lp:+ @ language-pack $lp}"
        lp_args=()
        [[ -n "$lp" ]] && lp_args=(--lp "$lp")
        printf '\n######## %s ########\n' "$label"
        if "$0" --python "$v" ${lp_args[@]+"${lp_args[@]}"} ${leg_args[@]+"${leg_args[@]}"} -- "${PYTEST_TARGETS[@]}"; then
            results+=("  $label: pass")
        else
            results+=("  $label: FAIL (exit $?)")
            status=1
        fi
    done
    printf '\n######## Matrix summary ########\n'
    printf '%s\n' "${results[@]}"
    exit $status
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

PY_BIN="$(command -v "python${PY_VERSION}" || true)"
if [[ -z "$PY_BIN" ]]; then
    echo "python${PY_VERSION} not found on PATH (CI's matrix: ${MATRIX_VERSIONS[*]})" >&2
    exit 2
fi
# Build the venv from the real interpreter, not a symlink to it: a venv records the directory it
# was created from as `home`, and a uv-managed CPython reached through ~/.local/bin/pythonX.Y then
# cannot find its stdlib ("No module named 'encodings'" at ensurepip, BACK-1341).
PY_BIN="$("$PY_BIN" -c 'import os, sys; print(os.path.realpath(sys.executable))')"

PRIMARY=0  # CI runs its extra steps only on ubuntu-latest/3.12, never in the compat matrix
[[ "$PY_VERSION" == "3.12" && -z "$LP_VERSION" ]] && PRIMARY=1

VENV="${REVEAL_CI_VENV_ROOT:-$HOME/.cache/reveal-ci}/py${PY_VERSION}${LP_VERSION:+-lp$LP_VERSION}"
LOG_DIR="${REVEAL_CI_LOG_DIR:-$(dirname "$VENV")/logs}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ci-local-py${PY_VERSION}${LP_VERSION:+-lp$LP_VERSION}-$(date +%Y%m%d-%H%M%S).log"

step() { printf '\n== %s ==\n' "$1" | tee -a "$LOG"; }
fail() { printf 'FAIL: %s (log: %s)\n' "$1" "$LOG" >&2; exit 1; }

[[ $FRESH -eq 1 ]] && rm -rf "$VENV"
# A venv whose interpreter cannot import pip is broken (e.g. a half-created one); rebuild it.
if ! "$VENV/bin/python" -c 'import pip' >/dev/null 2>&1; then
    step "Create venv $VENV ($($PY_BIN --version))"
    rm -rf "$VENV"
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
export PYTHONWARNDEFAULTENCODING=1
unset PYTHONPYCACHEPREFIX PYTHONPATH

if [[ $RUN_TESTS -eq 1 ]]; then
    step "Run tests (pytest ${PYTEST_TARGETS[*]})"
    "$PY" -m pytest "${PYTEST_TARGETS[@]}" -q -p no:cacheprovider -n auto >>"$LOG" 2>&1 \
        || { grep -E '^FAILED |^ERROR ' "$LOG" | head -30; fail "pytest"; }
    tail -1 "$LOG"
fi

step "CLI basics"
"$VENV/bin/reveal" --version >>"$LOG" 2>&1 && "$VENV/bin/reveal" --list-supported >>"$LOG" 2>&1 || fail "CLI basics"

if [[ $PRIMARY -eq 1 ]]; then
    step "Windows compatibility checks"
    "$PY" scripts/check_windows_compat.py --warn >>"$LOG" 2>&1 || fail "windows compat"
    "$PY" scripts/check_text_encoding.py >>"$LOG" 2>&1 || { tail -8 "$LOG"; fail "text encoding (bare read_text/open breaks on Windows)"; }
    "$PY" scripts/check_treesitter_accessors.py >>"$LOG" 2>&1 || { tail -8 "$LOG"; fail "bare tree-sitter accessor (a method on language-pack 1.8.1; use _zero_arg)"; }

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
fi

printf '\nCI-parity run passed (python %s%s%s). Log: %s\n' "$PY_VERSION" \
    "${LP_VERSION:+, language-pack $LP_VERSION}" "$([[ $PRIMARY -eq 1 ]] || echo ', pytest + CLI only as in CI')" "$LOG"
