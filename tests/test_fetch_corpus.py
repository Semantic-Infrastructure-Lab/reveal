"""Tests for scripts/fetch_corpus.py's corpus-integrity checks (BACK-1002).

`--list` used to report `dest.exists()` as "present" — true the instant any
file sat in the cache directory, pinned repo or not. This let contamination
(BACK-1002: an unrelated repo's subtree dropped into the same per-language
cache dir) and even a completely unfetched corpus report as healthy. These
tests exercise the replacement: a real classification of what's actually on
disk, against small real (not mocked) git repos in a temp dir — no network.
"""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
import tempfile

import pytest

# BACK-1149: exercises internal functions/modules directly, not CLI/MCP/network surface
pytestmark = pytest.mark.component

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "fetch_corpus.py"
spec = importlib.util.spec_from_file_location("fetch_corpus", SCRIPT_PATH)
fetch_corpus = importlib.util.module_from_spec(spec)
sys.modules["fetch_corpus"] = fetch_corpus
spec.loader.exec_module(fetch_corpus)


def _init_repo(path: Path, files: dict) -> str:
    """Create a real git repo at `path` with the given {name: content} files,
    committed. Returns the resulting commit SHA."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    for name, content in files.items():
        (path / name).write_text(content)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


class TestHeadSha(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_repo_returns_sha(self):
        sha = _init_repo(self.tmp / "repo", {"a.txt": "x"})
        self.assertEqual(fetch_corpus._head_sha(self.tmp / "repo"), sha)

    def test_non_repo_returns_none(self):
        (self.tmp / "plain").mkdir()
        (self.tmp / "plain" / "f.txt").write_text("x")
        self.assertIsNone(fetch_corpus._head_sha(self.tmp / "plain"))

    def test_missing_dir_returns_none(self):
        self.assertIsNone(fetch_corpus._head_sha(self.tmp / "nope"))


class TestStrayEntries(unittest.TestCase):
    """The BACK-1002 regression: foreign content sitting alongside a
    correctly-checked-out repo, at the top level of the cache directory."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clean_repo_has_no_stray_entries(self):
        _init_repo(self.tmp / "repo", {"a.txt": "x", "b.txt": "y"})
        self.assertEqual(fetch_corpus._stray_entries(self.tmp / "repo"), [])

    def test_foreign_subtree_detected(self):
        dest = self.tmp / "repo"
        _init_repo(dest, {"a.txt": "x"})
        # Simulate BACK-1002: an unrelated repo's subtree dropped alongside.
        (dest / "overfit-guard-BACK815").mkdir()
        (dest / "overfit-guard-BACK815" / "unrelated.txt").write_text("z")
        self.assertEqual(fetch_corpus._stray_entries(dest), ["overfit-guard-BACK815"])

    def test_non_repo_reports_no_stray_entries(self):
        """Can't compare against a tracked-file list that doesn't exist —
        this case is reported separately as 'not a git repo', not as stray."""
        (self.tmp / "plain").mkdir()
        (self.tmp / "plain" / "f.txt").write_text("x")
        self.assertEqual(fetch_corpus._stray_entries(self.tmp / "plain"), [])


class TestStatusFor(unittest.TestCase):
    """`_status_for` is what `--list` actually prints — the fix's real
    surface. Covers every case BACK-1002 found live: missing, stray-only
    (no real git repo at all), wrong SHA, and a correct-but-contaminated
    checkout."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_directory(self):
        disk, status = fetch_corpus._status_for(self.tmp / "nope", "abc123")
        self.assertEqual((disk, status), ("—", "—"))

    def test_stray_only_reports_not_a_git_repo(self):
        """The exact BACK-1002 failure: a cache dir holding nothing but
        foreign content used to report as 'present' (healthy-looking)."""
        dest = self.tmp / "corpus"
        dest.mkdir()
        (dest / "overfit-guard-BACK815").mkdir()
        (dest / "overfit-guard-BACK815" / "f.txt").write_text("x")
        disk, status = fetch_corpus._status_for(dest, "abc123")
        self.assertEqual(disk, "present")
        self.assertIn("not a git repo", status)

    def test_empty_directory_reports_not_a_git_repo(self):
        """A fully-unfetched corpus (php/ruby/rust, BACK-1002) — an empty
        dir, not even stray content — must not read as healthy either."""
        dest = self.tmp / "corpus"
        dest.mkdir()
        disk, status = fetch_corpus._status_for(dest, "abc123")
        self.assertIn("not a git repo", status)

    def test_correct_sha_reports_ok(self):
        sha = _init_repo(self.tmp / "corpus", {"a.txt": "x"})
        disk, status = fetch_corpus._status_for(self.tmp / "corpus", sha)
        self.assertEqual(disk, sha[:12])
        self.assertEqual(status, "ok")

    def test_wrong_sha_reports_mismatch(self):
        _init_repo(self.tmp / "corpus", {"a.txt": "x"})
        disk, status = fetch_corpus._status_for(self.tmp / "corpus", "0" * 40)
        self.assertIn("SHA MISMATCH", status)

    def test_correct_sha_but_contaminated_flags_stray_count(self):
        """A repo at the exactly right commit can still be contaminated —
        the two checks are independent (this is the actual csharp/java/php
        state BACK-1002 first found: right repo, extra junk alongside it)."""
        dest = self.tmp / "corpus"
        sha = _init_repo(dest, {"a.txt": "x"})
        (dest / "overfit-guard-BACK815").mkdir()
        (dest / "overfit-guard-BACK815" / "f.txt").write_text("z")
        disk, status = fetch_corpus._status_for(dest, sha)
        self.assertEqual(disk, sha[:12])
        self.assertIn("ok", status)
        self.assertIn("stray", status)

    def test_unpinned_present_repo(self):
        sha = _init_repo(self.tmp / "corpus", {"a.txt": "x"})
        disk, status = fetch_corpus._status_for(self.tmp / "corpus", None)
        self.assertEqual(disk, sha[:12])
        self.assertEqual(status, "unpinned")


if __name__ == "__main__":
    unittest.main()
