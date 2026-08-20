#!/usr/bin/env bash
# BACK-1048 prerequisite tool #2: isolated-venv verification harness for
# BACK-620 (tree-sitter-language-pack>=1.12.5 forward-compat migration).
#
# Automates the per-batch verification protocol from
# internal-docs/design/BACK573_TREESITTER_1125_FORWARD_COMPAT_2026-07-13.md
# ("Recommended approach", step 5): after migrating a batch of call sites to
# reveal.core.treesitter_compat._zero_arg(...), re-run this in a fresh
# isolated venv with tree-sitter-language-pack forced past the pyproject.toml
# ceiling, so no batch is trusted without dogfooding it against the real new
# API surface -- the exact failure mode behind the v0.108.0 outage (BACK-574:
# a fix trusted without dogfooding every affected language).
#
# Run from the repo root (external-git/). Never modifies pyproject.toml or
# the dev environment -- everything happens inside a throwaway venv.
#
# Usage:
#   scripts/verify_treesitter_migration.sh [venv-dir] [language-pack-version]
#
# Defaults: venv-dir=/tmp/reveal-ts-verify-venv, language-pack-version=1.12.5
#
# Exit 0 = full suite passed AND every per-language CLI smoke fixture parsed
# clean under the forced version. Exit 1 = something in that chain broke --
# read the printed failures before touching pyproject.toml's ceiling.

set -euo pipefail

VENV_DIR="${1:-/tmp/reveal-ts-verify-venv}"
LP_VERSION="${2:-1.12.5}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "== BACK-1048 verification harness =="
echo "repo:    $REPO_ROOT"
echo "venv:    $VENV_DIR"
echo "forcing: tree-sitter-language-pack==$LP_VERSION"
echo

rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

pip install -q --upgrade pip
pip install -q -e ".[dev]"
pip install -q "tree-sitter-language-pack==$LP_VERSION"

echo "-- confirming the forced version is actually active --"
python3 -c "
from tree_sitter_language_pack import get_parser
p = get_parser('python')
print(f'get_parser(python) -> {type(p).__module__}.{type(p).__qualname__}')
import tree_sitter
if isinstance(p, tree_sitter.Parser):
    print('-> core tree_sitter.Parser (post-1.12.5 property API) -- as expected')
else:
    print('-> WARNING: not the core parser; version pin did not take effect as expected')
"
echo

echo "-- full test suite (PYTHONPATH=. so the venv install isn't shadowed) --"
FAIL=0
if ! PYTHONPATH=. python3 -m pytest -q; then
    echo "FULL SUITE FAILED"
    FAIL=1
fi
echo

echo "-- per-language CLI smoke pass --"
# tests/fixtures/conformance/<lang>/ + tests/fixtures/smoke/<lang>/ together
# cover every language with a curated fixture (BACK-422's conformance matrix
# plus the smoke set for languages conformance doesn't include).
for fixture_root in tests/fixtures/conformance tests/fixtures/smoke; do
    [ -d "$fixture_root" ] || continue
    for lang_dir in "$fixture_root"/*/; do
        [ -d "$lang_dir" ] || continue
        lang="$(basename "$lang_dir")"
        for f in "$lang_dir"*; do
            [ -f "$f" ] || continue
            if out="$(python3 -m reveal.main "$f" --outline 2>&1)"; then
                echo "  ok   [$lang] $f"
            else
                status=$?
                echo "  FAIL [$lang] $f (exit $status)"
                echo "$out" | sed 's/^/      /'
                FAIL=1
            fi
        done
    done
done

deactivate
echo

if [ "$FAIL" -ne 0 ]; then
    echo "VERIFICATION FAILED -- do not lower the ratchet baseline or lift the pyproject.toml ceiling."
    exit 1
fi
echo "VERIFICATION PASSED -- full suite green, every per-language fixture parsed clean under $LP_VERSION."
