"""Execution provenance metadata for reveal's JSON output (BACK-881).

Answers "which reveal version, repo state, and config produced this result" --
useful for a DD/agent consumer deciding whether a JSON result is reproducible
or trustworthy for a given engagement. Purely additive: attached only when a
caller opts in (the global --provenance flag), never on by default.
"""

import hashlib
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from reveal.version import __version__


def _git_state(cwd: Path) -> Optional[Dict[str, Any]]:
    """Best-effort commit/dirty state of the git repo containing cwd.

    Shells out to git rather than depending on pygit2 here -- this runs on
    every --provenance invocation regardless of target, so it should stay a
    lightweight, best-effort lookup (same subprocess+timeout pattern already
    used by cli/commands/review.py and pack.py for git root detection).
    """
    try:
        commit = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if commit.returncode != 0:
            return None
        status = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        return {
            'commit': commit.stdout.strip()[:12],
            'dirty': bool(status.stdout.strip()) if status.returncode == 0 else None,
        }
    except Exception:
        return None


def _config_digest(cwd: Path) -> Optional[str]:
    """Short digest of the active merged .reveal.yaml config, if any."""
    try:
        from reveal.config import RevealConfig
        config = RevealConfig.get(cwd)
        return hashlib.sha256(config.dump().encode('utf-8')).hexdigest()[:12]
    except Exception:
        return None


def build_execution_provenance(cwd: Optional[Path] = None) -> Dict[str, Any]:
    """Build the 'execution' provenance block.

    Args:
        cwd: Directory to resolve repo/config state from. Defaults to the
            process's current working directory.

    Returns:
        Dict with reveal_version, command, platform, python_version, repo
        (commit/dirty or None outside a git repo), and config_digest.
    """
    cwd = cwd or Path.cwd()
    return {
        'reveal_version': __version__,
        'command': ' '.join(sys.argv),
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'repo': _git_state(cwd),
        'config_digest': _config_digest(cwd),
    }
