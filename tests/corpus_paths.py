"""Resolve real-corpus dogfood paths for tests, with clean skip when absent.

The real corpus (large open-source repos, see tests/corpus/manifest.yaml) is
NOT committed and NOT present in CI or a fresh clone. Tests that reference it
must therefore locate it flexibly and skip — never fail — when it is missing.

Resolution order for a language's corpus root:
  1. $REVEAL_CORPUS_DIR/<language>        (explicit override / CI cache)
  2. ~/.cache/reveal-corpus/<language>    (scripts/fetch_corpus.py default)
  3. <repo>/../samples/<language>         (legacy hand-cloned location)

Populate the cache reproducibly with:  python scripts/fetch_corpus.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# repo root is the parent of external-git/ ; samples/ is its sibling (legacy).
_LEGACY_SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _candidate_roots(language: str) -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("REVEAL_CORPUS_DIR")
    if env:
        roots.append(Path(env).expanduser() / language)
    roots.append(Path("~/.cache/reveal-corpus").expanduser() / language)
    roots.append(_LEGACY_SAMPLES / language)
    return roots


def corpus_root(language: str) -> Path | None:
    """First existing corpus root for a language, or None if not materialized."""
    for root in _candidate_roots(language):
        if root.is_dir():
            return root
    return None


def corpus_file(language: str, *relative: str) -> Path | None:
    """Resolve a specific file within a language's corpus, or None if absent.

    `relative` is the path under the repo root (e.g. corpus_file("go",
    "cluster", "get-kube.sh")). Returns None if the corpus isn't materialized
    OR the specific file isn't present at this commit — callers skip on None.
    """
    root = corpus_root(language)
    if root is None:
        return None
    path = root.joinpath(*relative)
    return path if path.exists() else None


def require_corpus_file(language: str, *relative: str) -> Path:
    """Like corpus_file, but pytest.skip() instead of returning None.

    Use in tests: `path = require_corpus_file("go", "cluster", "get-kube.sh")`.
    """
    path = corpus_file(language, *relative)
    if path is None:
        pytest.skip(
            f"{language} corpus file {'/'.join(relative)} not available "
            f"(run: python scripts/fetch_corpus.py {language})"
        )
    return path
