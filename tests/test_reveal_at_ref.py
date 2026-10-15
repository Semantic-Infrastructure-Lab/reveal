"""scripts/reveal_at_ref.py runs reveal from the tree it was asked for (BACK-1841, BACK-1445).

The failure it exists to prevent: ``PYTHONPATH=<old> python -I`` silently loads the installed
reveal, so an old-versus-new comparison compares HEAD with HEAD.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "reveal_at_ref.py"
REPO = SCRIPT.parent.parent

pytestmark = [
    pytest.mark.component,
    pytest.mark.skipif(shutil.which("git") is None or not (REPO / ".git").exists(), reason="needs a git checkout"),
]


def _run(cache: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "REVEAL_AT_REF_CACHE": str(cache)}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, cwd=REPO)


def test_a_ref_loads_the_exported_tree_not_the_checkout(tmp_path):
    result = _run(tmp_path, "HEAD", "--", "--version")
    assert result.returncode == 0, result.stderr
    assert str(tmp_path) in result.stdout
    assert str(REPO / "reveal") not in result.stdout


def test_worktree_loads_the_checkout(tmp_path):
    result = _run(tmp_path, "WORKTREE", "--", "--version")
    assert result.returncode == 0, result.stderr
    assert str(REPO / "reveal") in result.stdout


def test_diff_of_the_same_tree_is_identical(tmp_path):
    result = _run(tmp_path, "WORKTREE", "--diff", "--", "--version")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "stdout identical" in result.stdout


def test_missing_reveal_args_is_a_usage_error(tmp_path):
    assert _run(tmp_path, "HEAD").returncode == 2
