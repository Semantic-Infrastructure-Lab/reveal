#!/usr/bin/env python3
"""Materialize the real-corpus dogfood repos from tests/corpus/manifest.yaml.

The corpus is the set of large open-source repos used for exploratory,
real-world validation of reveal's analyzers (NOT for deterministic CI tests —
those use tiny hand-written fixtures under tests/fixtures/). See the manifest's
header for the full rationale.

Design goals this script exists to satisfy:
  - Reproducible: each repo is checked out at an exact pinned commit, so a
    finding's line numbers stay valid.
  - Cheap: blobless (--filter=blob:none), single-commit (--depth 1), no full
    history — a fraction of a hand-clone's size, and no .git bloat to speak of.
  - Idempotent: an already-materialized corpus at the right commit is left
    alone; re-running is a fast no-op.
  - Shared: materializes into $REVEAL_CORPUS_DIR (or ~/.cache/reveal-corpus),
    so it is reused across git worktrees rather than re-cloned per checkout.

Usage:
    python scripts/fetch_corpus.py                 # fetch all
    python scripts/fetch_corpus.py go rust         # fetch only these languages
    python scripts/fetch_corpus.py --list          # show manifest + cache state
    python scripts/fetch_corpus.py --dry-run       # print what would run
    REVEAL_CORPUS_DIR=/data/corpus python scripts/fetch_corpus.py

Entries with `sha: null` (snapshots whose commit was lost) are fetched at the
default-branch HEAD; the resolved SHA is printed so it can be pinned back into
the manifest.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parent.parent / "tests" / "corpus" / "manifest.yaml"


def _load_manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text())


def cache_root(manifest: dict) -> Path:
    env = os.environ.get("REVEAL_CORPUS_DIR")
    base = env or manifest.get("cache_dir_default", "~/.cache/reveal-corpus")
    return Path(base).expanduser()


def _run(cmd: list[str], cwd: Path | None = None, dry: bool = False) -> None:
    printable = " ".join(cmd)
    print(f"    $ {printable}" + (f"   (cwd={cwd})" if cwd else ""))
    if dry:
        return
    subprocess.run(cmd, cwd=cwd, check=True)


def _head_sha(dest: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def fetch_one(entry: dict, root: Path, dry: bool = False) -> None:
    lang = entry["language"]
    repo = entry["repo"]
    sha = entry.get("sha")
    dest = root / lang

    current = _head_sha(dest) if dest.exists() else None
    if sha and current == sha:
        print(f"[{lang}] already at {sha[:12]} — skip")
        return
    if current and not sha:
        print(f"[{lang}] present (unpinned, at {current[:12]}) — skip; "
              f"delete {dest} to re-fetch")
        return

    print(f"[{lang}] fetching {repo}" + (f" @ {sha[:12]}" if sha else " @ HEAD (unpinned)"))
    if dest.exists() and not dry:
        # Wrong commit or partial checkout — start clean.
        _run(["rm", "-rf", str(dest)], dry=dry)

    root.mkdir(parents=True, exist_ok=True)

    if sha:
        # Blobless, single commit at the exact SHA — smallest reproducible tree.
        _run(["git", "clone", "--filter=blob:none", "--no-checkout",
              "--single-branch", repo, str(dest)], dry=dry)
        _run(["git", "-C", str(dest), "fetch", "--depth", "1",
              "--filter=blob:none", "origin", sha], dry=dry)
        _run(["git", "-C", str(dest), "checkout", "--detach", sha], dry=dry)
    else:
        # No pinned commit: shallow-clone default HEAD and report the SHA.
        _run(["git", "clone", "--depth", "1", "--filter=blob:none",
              "--single-branch", repo, str(dest)], dry=dry)
        if not dry:
            resolved = _head_sha(dest)
            print(f"    → resolved {lang} HEAD = {resolved}  "
                  f"(pin this into {MANIFEST.name})")


def cmd_list(manifest: dict, root: Path) -> None:
    print(f"cache root: {root}\n")
    print(f"{'language':<12} {'pinned sha':<14} {'on-disk':<14} repo")
    print("-" * 78)
    for e in manifest["corpora"]:
        lang = e["language"]
        sha = (e.get("sha") or "—")[:12]
        disk = _head_sha(root / lang)
        disk = disk[:12] if disk else ("present" if (root / lang).exists() else "—")
        print(f"{lang:<12} {sha:<14} {disk:<14} {e['repo']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("languages", nargs="*", help="only fetch these (default: all)")
    ap.add_argument("--list", action="store_true", help="show manifest + cache state, do nothing")
    ap.add_argument("--dry-run", action="store_true", help="print commands without running them")
    args = ap.parse_args(argv)

    manifest = _load_manifest()
    root = cache_root(manifest)

    if args.list:
        cmd_list(manifest, root)
        return 0

    entries = manifest["corpora"]
    if args.languages:
        wanted = set(args.languages)
        entries = [e for e in entries if e["language"] in wanted]
        missing = wanted - {e["language"] for e in entries}
        if missing:
            print(f"unknown language(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    for entry in entries:
        try:
            fetch_one(entry, root, dry=args.dry_run)
        except subprocess.CalledProcessError as exc:
            print(f"[{entry['language']}] FAILED: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
