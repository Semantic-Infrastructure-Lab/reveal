#!/usr/bin/env bash
# Sourced by scripts/ci-local.sh. Refuses to repoint the shared CI venv (BACK-1680).
#
# The venv is keyed on python version only, and ci-local.sh's install step runs
# `pip install -e .` from the current checkout. Run from a second checkout or git worktree,
# that silently makes every later run (other agents', the main checkout's) import THIS tree.
# The venv's editable target is recorded in reveal_cli-*.dist-info/direct_url.json (PEP 610).
#
#   ci_editable_guard <venv> <git-toplevel>
#     0  allow: venv absent, not editable, unreadable-as-editable, or already points at <git-toplevel>
#     1  refuse: it points somewhere else (message on stderr)
# Override, deliberately and visibly: REVEAL_CI_ALLOW_REPOINT=1 (e.g. the main checkout moved).

ci_editable_guard() {
    local venv="$1" top="$2" target
    target="$(python3 - "$venv" <<'PY'
import glob, json, os, sys
from urllib.parse import unquote, urlparse
for f in glob.glob(os.path.join(sys.argv[1], "lib*", "python*", "site-packages", "reveal_cli-*.dist-info", "direct_url.json")):
    with open(f, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("dir_info", {}).get("editable") and d.get("url", "").startswith("file:"):
        print(os.path.realpath(unquote(urlparse(d["url"]).path)))
        break
PY
)" || { echo "ci-local: could not read the editable target of $venv; refusing to guess" >&2; return 1; }
    [[ -z "$target" ]] && return 0
    [[ "$target" == "$(cd "$top" && pwd -P)" ]] && return 0
    if [[ "${REVEAL_CI_ALLOW_REPOINT:-0}" == "1" ]]; then
        echo "ci-local: REVEAL_CI_ALLOW_REPOINT=1 -- repointing $venv from $target to $top" >&2
        return 0
    fi
    cat >&2 <<MSG
ci-local: refusing to run from $top
  The shared venv $venv is installed editable from
    $target
  and this run would repoint it, silently switching every other run onto this checkout (BACK-1680).
  From a worktree or second checkout, test with ~/.cache/reveal-wt/wt-check.sh instead
  (PYTHONPATH=<worktree> over the shared venv), or give this checkout its own venv:
    REVEAL_CI_VENV_ROOT=<dir> scripts/ci-local.sh ...
  To repoint on purpose (main checkout moved): REVEAL_CI_ALLOW_REPOINT=1 scripts/ci-local.sh ...
MSG
    return 1
}
