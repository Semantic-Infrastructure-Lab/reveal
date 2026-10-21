"""Git ranges for the rule pass: validate one, and list the files it changed.

Shared by ``reveal check --changed RANGE`` and ``reveal review`` (BACK-2068 slice 3b), so a range
is validated and expanded in one place.
"""
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def git_range_error(git_range: str) -> Optional[str]:
    """Why `git_range` can't be reviewed, or None. Without this an unknown
    ref or a cwd outside any repo produced an empty diff and a passing review."""
    def git(*cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(['git', *cmd], capture_output=True, text=True, timeout=10,
                              encoding='utf-8', errors='replace', check=False)
    try:
        if git('rev-parse', '--show-toplevel').returncode != 0:
            return f"not inside a git repository (cwd: {Path.cwd()})"
        sep = '...' if '...' in git_range else '..'
        for rev in git_range.split(sep, 1):
            # An empty side means HEAD, as in git itself (`main..`).
            rev = rev or 'HEAD'
            if git('rev-parse', '--verify', '--quiet', '--end-of-options',
                   f'{rev}^{{commit}}').returncode != 0:
                return f"unknown revision: {rev!r}"
    except (OSError, subprocess.SubprocessError) as e:
        return f"could not run git: {e}"
    return None


def changed_files(git_range: str) -> List[Path]:
    """Absolute paths of files changed in a git range that still exist on disk.

    Deleted files are omitted (nothing to quality-check). Names are resolved
    against the git top-level so `review` works from any subdirectory. Replaces
    the old whole-tree `_detect_source_root()` walk (BACK-538).
    """
    try:
        # --end-of-options: same git-argument-injection defense as _run_diff above.
        result = subprocess.run(
            ['git', 'diff', '--name-only', '--end-of-options', git_range],
            capture_output=True, text=True, timeout=10, encoding='utf-8', errors='replace',
        )
        if result.returncode != 0:
            return []
        toplevel = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, timeout=10, encoding='utf-8', errors='replace',
        )
        root = Path(toplevel.stdout.strip()) if toplevel.returncode == 0 else Path.cwd()
        files: List[Path] = []
        for name in result.stdout.splitlines():  # boundary-ok: splitlines -- git subprocess stdout
            name = name.strip()
            if not name:
                continue
            candidate = root / name
            if candidate.is_file():
                files.append(candidate.resolve())
        return files
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"Warning: could not determine changed files for {git_range!r}: {e}", file=sys.stderr)  # boundary-ok: print -- the git failure line, moved with the helper from review.py
        return []
