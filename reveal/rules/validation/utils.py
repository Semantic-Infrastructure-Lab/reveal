"""Shared utilities for validation rules (V-series).

This module provides common functionality used across multiple V-series rules,
particularly for finding and working with reveal's installation directory.
"""

import ast
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from ...utils.path_utils import to_posix

if TYPE_CHECKING:
    from ..base import BaseRule

logger = logging.getLogger(__name__)


# Docs that carry *current* adapter/language count claims. Deliberately excludes
# AGENT_HELP.md and CHANGELOG.md, whose count mentions are all historical
# version-history entries (see BACK-388). Paths are relative to project_root.
CURRENT_CLAIM_DOCS = (
    'README.md',
    'ARCHITECTURE.md',
    'CONTRIBUTING.md',
    'INSTALL.md',
    'STABILITY.md',
    'reveal/docs/QUICK_START.md',
    'reveal/docs/WHY_REVEAL.md',
)
# ROADMAP.md deliberately excluded: its "What We've Shipped" table mixes
# historical per-version deltas (e.g. "+140 languages") with current-state
# claims in a format the version-history skip regex doesn't recognize
# (table rows / unlabeled "Value delivered" lines, not CHANGELOG's
# "**vX.Y.Z**" bold-heading convention) — would false-positive on real
# history. Its current-state sections were hand-corrected instead (BACK-388
# follow-up); revisit if ROADMAP's shipped-history format is ever
# standardized to match CHANGELOG's.

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
    except Exception as e:
        logger.warning("utils.py: skipped after %s: %s", type(e).__name__, e)
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


NOT_IN_CHECKOUT = (
    'Not in a reveal checkout: run from one (a directory holding pyproject.toml and '
    'reveal/) or set REVEAL_DEV_ROOT'
)


def find_reveal_checkout() -> Optional[Path]:
    """The dev checkout to write new files into: the directory holding
    pyproject.toml and the reveal/ package, from REVEAL_DEV_ROOT or the CWD.

    Never the installed package (BACK-1372): scaffolding a rule into
    site-packages is never what the user meant. Returns None outside a checkout.
    """
    root = find_reveal_root(dev_only=True)
    return root.parent if root is not None else None


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


def load_sources(rule: 'BaseRule', trees: Tuple[str, ...],
                 accept: Callable[[Path], bool]) -> List[Tuple[str, str]]:
    """(display path, source) for each ``*.py`` under *trees* (directories of the dev
    checkout's root) that *accept* takes (given the path relative to the root), sorted per
    tree; the shared reader behind the source-scanning rules.

    Records on *rule* why there is nothing to scan (no reveal root: unavailable; an
    installed package or no tests/: not applicable) and each module that cannot be read
    (unavailable, with the module as subject) rather than skipping it silently. A tree
    absent from the checkout is skipped; ``tests/`` is required, as the marker that
    this is a development checkout. Display paths are posix, relative to the root.
    """
    reveal_root = find_reveal_root()
    if not reveal_root:
        rule.unavailable("reveal source root unavailable")
        return []
    if not is_dev_checkout(reveal_root):
        rule.not_applicable("requires a development checkout")
        return []
    project_root = reveal_root.parent
    if not (project_root / 'tests').is_dir():
        rule.not_applicable("no tests/ directory")
        return []
    modules: List[Tuple[str, str]] = []
    for tree in trees:
        # boundary-ok: walker -- V-series: reveal's own source and test suite
        for path in sorted((project_root / tree).rglob('*.py')):
            display = to_posix(path.relative_to(project_root))
            if not accept(path.relative_to(project_root)):
                continue
            try:
                modules.append((display, path.read_text(encoding='utf-8')))
            except (OSError, UnicodeDecodeError) as e:
                rule.unavailable(f"{type(e).__name__}: {e}", display)
    return modules


def _is_test_module(path: Path) -> bool:
    return path.name.startswith('test_') or path.name == 'conftest.py'


def load_test_suite(rule: 'BaseRule') -> List[Tuple[str, str]]:
    """(display path, source) for each test module of the dev checkout's ``tests/``
    (``test_*.py`` and ``conftest.py``): what the test-suite rules scan. Rules
    pre-filter the source cheaply and parse only candidates (``parse_test_module``)."""
    return load_sources(rule, ('tests',), _is_test_module)


def parse_test_module(rule: 'BaseRule', display: str, source: str) -> Optional[ast.Module]:
    """The module's AST, or None after recording on *rule* that it does not parse."""
    try:
        return ast.parse(source, filename=display)
    except (SyntaxError, ValueError) as e:
        rule.unavailable(f"{type(e).__name__}: {e}", display)
        return None


def has_noqa(line: str, code: str) -> bool:
    """True if *line* carries ``# noqa: <code>`` (a justification may follow)."""
    return re.search(r'#\s*noqa:[^#]*\b' + re.escape(code) + r'\b', line) is not None
