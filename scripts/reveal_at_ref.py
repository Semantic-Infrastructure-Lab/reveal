#!/usr/bin/env python3
"""Run any reveal command against a git ref's tree, or diff it against the working tree.

The old-tree recipe that went wrong in the Sprint 4 docs (BACK-1841): ``PYTHONPATH=<old> python -I ...``
loads the *installed* reveal, because -I ignores PYTHONPATH, so a "before/after" would compare
HEAD with HEAD. This puts the exported tree first on sys.path inside the child and exits
if reveal was imported from anywhere else. The tree is built with ``git archive`` (never a
stash or checkout) and cached by commit hash.

Hygiene for raw-output diffs is set here: REVEAL_DISK_CACHE=0, PYTHONHASHSEED=0, no
PYTHONPYCACHEPREFIX (stale bytecode from another tree).

Usage:
    python scripts/reveal_at_ref.py b1263bac -- check src/ --select B006 --format json
    python scripts/reveal_at_ref.py HEAD~3 --diff -- 'calls://src?callers=helper' --format json
    python scripts/reveal_at_ref.py WORKTREE -- --version      # the current checkout, same guard

--diff runs the ref and then the working tree with the same arguments and prints a unified
diff of stdout; exit 0 when stdout and exit codes match, 1 otherwise. Run from the directory
the command should see (paths in the arguments are relative to it). For corpus-scale
before/after numbers see corpus_sweep.py, which uses the same export and guard.
"""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKTREE = "WORKTREE"

# Runs in the child. -I is not used: it also drops the user site-packages that hold reveal's
# dependencies. Instead the cwd entry is removed (it could shadow stdlib/reveal) and the tree goes first.
_BOOTSTRAP = """
import os, sys
tree = sys.argv[1]
sys.path[:] = [p for p in sys.path if p not in ("", os.getcwd())]
sys.path.insert(0, tree)
import reveal
from pathlib import Path
if not Path(reveal.__file__).resolve().is_relative_to(Path(tree).resolve()):
    sys.exit(f"reveal imported from {reveal.__file__}, not {tree}")
print(f"[reveal_at_ref] loaded {reveal.__file__}", file=sys.stderr)
from reveal.main import main
sys.argv = ["reveal"] + sys.argv[2:]
main()
"""


def cache_dir() -> Path:
    return Path(os.environ.get("REVEAL_AT_REF_CACHE", Path.home() / ".cache" / "reveal-measure" / "trees"))


def export_tree(ref: str) -> Path:
    """The ``reveal/`` package of *ref*, extracted once per commit; the WORKTREE is the checkout."""
    if ref == WORKTREE:
        return REPO
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", f"{ref}^{{commit}}"],
                         check=True, capture_output=True, text=True, encoding='utf-8').stdout.strip()
    dest = cache_dir() / sha
    if not (dest / "reveal" / "__init__.py").exists():
        dest.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "-C", str(REPO), "archive", sha, "reveal"],
                                 check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
    return dest


def run_at(tree: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ, REVEAL_DISK_CACHE="0", PYTHONHASHSEED="0")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONPYCACHEPREFIX", None)
    return subprocess.run([sys.executable, "-c", _BOOTSTRAP, str(tree), *args],
                          env=env, capture_output=True, text=True, encoding="utf-8")


def _diff(ref: str, old: subprocess.CompletedProcess, new: subprocess.CompletedProcess) -> int:
    lines = list(difflib.unified_diff(old.stdout.splitlines(), new.stdout.splitlines(),
                                      fromfile=ref, tofile=WORKTREE, lineterm=""))
    print("\n".join(lines) if lines else f"stdout identical ({len(new.stdout)} bytes)")
    if old.returncode != new.returncode:
        print(f"exit code differs: {ref}={old.returncode} {WORKTREE}={new.returncode}")
    return 1 if lines or old.returncode != new.returncode else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ref", help=f"git ref to run, or {WORKTREE} for the current checkout")
    ap.add_argument("--diff", action="store_true", help=f"also run {WORKTREE} and diff stdout")
    argv = sys.argv[1:] if argv is None else argv
    ours, sep, reveal_args = (argv[:argv.index("--")], True, argv[argv.index("--") + 1:]) if "--" in argv \
        else (argv, False, [])
    args = ap.parse_args(ours)
    if not sep or not reveal_args:
        ap.error("give the reveal arguments after --")
    old = run_at(export_tree(args.ref), reveal_args)
    if args.diff:
        new = run_at(REPO, reveal_args)
        sys.stderr.write(old.stderr.replace("loaded", f"{args.ref} loaded", 1) + new.stderr)
        return _diff(args.ref, old, new)
    sys.stdout.write(old.stdout)
    sys.stderr.write(old.stderr)
    return old.returncode


if __name__ == "__main__":
    sys.exit(main())
