"""Shared utilities for validation rules (V-series).

This module provides common functionality used across multiple V-series rules,
particularly for finding and working with reveal's installation directory.
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple


# Docs that carry *current* adapter/language count claims. Deliberately excludes
# AGENT_HELP.md and CHANGELOG.md, whose count mentions are all historical
# version-history entries (see BACK-388). Paths are relative to project_root.
CURRENT_CLAIM_DOCS = (
    'README.md',
    'ARCHITECTURE.md',
    'reveal/docs/QUICK_START.md',
    'reveal/docs/WHY_REVEAL.md',
)

# A line that documents a past release, e.g. "- **v0.72.1** - ... corrected to 22".
# Counts on these lines are correct-in-context and must not be flagged.
_VERSION_HISTORY_LINE = re.compile(r'\*\*v\d+\.\d+', re.IGNORECASE)


def is_version_history_line(line: str) -> bool:
    """True if a line is a changelog/version-history entry (skip count checks)."""
    return bool(_VERSION_HISTORY_LINE.search(line))


def iter_current_claim_docs(project_root: Path) -> List[Tuple[str, Path]]:
    """Yield (relative_path, absolute_path) for each existing current-claim doc."""
    docs: List[Tuple[str, Path]] = []
    for rel in CURRENT_CLAIM_DOCS:
        abs_path = project_root / rel
        if abs_path.exists():
            docs.append((rel, abs_path))
    return docs


def scan_doc_for_counts(doc_path: Path,
                        patterns: List[str]) -> List[Tuple[int, int]]:
    """Return (line_number, claimed_count) for every count matched by `patterns`.

    Version-history lines are skipped. Each pattern must capture the integer in
    group 1.
    """
    try:
        lines = doc_path.read_text(encoding='utf-8').split('\n')
    except Exception:
        return []
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    claims: List[Tuple[int, int]] = []
    for i, line in enumerate(lines, 1):
        if is_version_history_line(line):
            continue
        for rx in compiled:
            for match in rx.finditer(line):
                claims.append((i, int(match.group(1))))
    return claims


def find_reveal_root(dev_only: bool = False) -> Optional[Path]:
    """Find reveal's root directory.

    Priority:
    1. REVEAL_DEV_ROOT environment variable (explicit override)
    2. Git checkout in CWD or parent directories (prefer development)
    3. Installed package location (fallback, unless dev_only=True)

    Args:
        dev_only: If True, only return path for dev checkouts (not installed package).
                  Useful for rules that only make sense during development.

    Returns:
        Path to reveal's root directory, or None if not found.

    Example:
        >>> root = find_reveal_root()
        >>> if root:
        ...     analyzers_dir = root / 'analyzers'
        ...     rules_dir = root / 'rules'
    """
    # 1. Explicit override via environment
    env_root = os.getenv('REVEAL_DEV_ROOT')
    if env_root:
        dev_root = Path(env_root)
        if (dev_root / 'analyzers').exists() and (dev_root / 'rules').exists():
            return dev_root

    # 2. Search from CWD for git checkout (prefer development over installed)
    cwd = Path.cwd()
    for _ in range(10):  # Search up to 10 levels
        # Check for reveal git checkout patterns
        reveal_dir = cwd / 'reveal'
        if (reveal_dir / 'analyzers').exists() and (reveal_dir / 'rules').exists():
            # Verify it's a git checkout by checking for pyproject.toml in parent
            if (cwd / 'pyproject.toml').exists():
                return reveal_dir
        cwd = cwd.parent
        if cwd == cwd.parent:  # Reached root
            break

    # 3. Fallback to installed package location (unless dev_only)
    if not dev_only:
        installed = Path(__file__).parent.parent.parent
        if (installed / 'analyzers').exists() and (installed / 'rules').exists():
            return installed

    return None


def is_dev_checkout(reveal_root: Optional[Path]) -> bool:
    """Check if a reveal root path is a development checkout.

    A dev checkout has pyproject.toml in the parent directory.

    Args:
        reveal_root: Path returned by find_reveal_root()

    Returns:
        True if this is a dev checkout, False otherwise.
    """
    if not reveal_root:
        return False
    project_root = reveal_root.parent
    return (project_root / 'pyproject.toml').exists()
