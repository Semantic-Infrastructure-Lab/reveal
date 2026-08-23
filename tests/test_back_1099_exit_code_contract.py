"""Regression tests for BACK-1099: `reveal check`'s exit code must
distinguish "clean" from "issues found" from "scan could not complete".

Confirmed live bug this closes: `reveal check <file-with-a-syntax-error>`
used to exit 0 -- byte-identical to a genuinely clean file -- because the
degraded/errored status BACK-1083 added to the *output contract* (JSON
`warning`/`status` fields, text summary lines) was never threaded through
to the actual process exit code. `check_exit_code()`
(reveal/cli/file_checker.py) is now the single place that decides:

  0 = clean (ran to completion, zero issues, nothing degraded/errored)
  1 = issues found (ran to completion, no degraded/errored files)
  2 = usage/invocation error (unchanged, not covered here)
  3 = incomplete scan (a file could not be parsed/checked at all, or was
      checked against a degraded/error-recovery parse, or a rule raised)
      -- takes priority over 1 even if issues were also reported, because
      the issue count itself may be wrong/incomplete.

See internal-docs/design/EXIT_CODE_CONTRACT.md for the full contract.
"""

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct
from reveal.cli.file_checker import check_exit_code

# BACK-1149: component/CLI-layer tests, in-process (no real subprocess)
pytestmark = pytest.mark.component


def _write_py(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(code, encoding="utf-8")
    return p


class TestCheckExitCodeFunction:
    """Unit coverage of the exit-code decision itself."""

    def test_clean_is_zero(self):
        assert check_exit_code(total_issues=0, files_errored=0, files_degraded=0) == 0

    def test_issues_found_is_one(self):
        assert check_exit_code(total_issues=3, files_errored=0, files_degraded=0) == 1

    def test_errored_file_is_three_even_with_zero_issues(self):
        assert check_exit_code(total_issues=0, files_errored=1, files_degraded=0) == 3

    def test_degraded_file_is_three_even_with_zero_issues(self):
        assert check_exit_code(total_issues=0, files_errored=0, files_degraded=1) == 3

    def test_degraded_takes_priority_over_issues_found(self):
        """A degraded scan reporting issues is still exit 3, not 1 -- the
        issue count can't be trusted when the scan didn't fully complete."""
        assert check_exit_code(total_issues=2, files_errored=0, files_degraded=1) == 3
        assert check_exit_code(total_issues=2, files_errored=1, files_degraded=0) == 3


class TestSingleFileCheckExitCode:
    """`reveal check <file>` -- the exact command from BACK-1099's repro."""

    def test_syntax_error_file_exits_3_not_0(self, tmp_path):
        f = _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        result = _run_reveal_direct("check", str(f), "--format", "json")
        assert result.returncode == 3, (
            f"Expected exit 3 (scan incomplete), got {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_clean_file_exits_0(self, tmp_path):
        f = _write_py(tmp_path, "clean.py", "def f():\n    return 1\n")
        result = _run_reveal_direct("check", str(f), "--format", "json")
        assert result.returncode == 0

    def test_syntax_error_and_clean_file_are_no_longer_indistinguishable(self, tmp_path):
        """The headline claim from the audit doc: previously both exited 0
        with byte-identical stdout shape. Exit codes must now differ."""
        broken = _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        clean = _write_py(tmp_path, "clean.py", "def f():\n    return 1\n")
        broken_result = _run_reveal_direct("check", str(broken), "--format", "json")
        clean_result = _run_reveal_direct("check", str(clean), "--format", "json")
        assert broken_result.returncode != clean_result.returncode


class TestDirectoryCheckExitCode:
    """`reveal check <dir>` -- directory/batch scan path, all three output formats."""

    def _make_mixed_dir(self, tmp_path):
        _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        _write_py(tmp_path, "clean.py", "def f():\n    return 1\n")
        return tmp_path

    def test_json_format_exits_3_with_one_degraded_file(self, tmp_path):
        d = self._make_mixed_dir(tmp_path)
        result = _run_reveal_direct("check", str(d), "--format", "json")
        assert result.returncode == 3
        assert '"exit_code": 3' in result.stdout

    def test_text_format_exits_3_with_one_degraded_file(self, tmp_path):
        d = self._make_mixed_dir(tmp_path)
        result = _run_reveal_direct("check", str(d))
        assert result.returncode == 3

    def test_grep_format_exits_3_with_one_degraded_file(self, tmp_path):
        d = self._make_mixed_dir(tmp_path)
        result = _run_reveal_direct("check", str(d), "--format", "grep")
        assert result.returncode == 3

    def test_all_clean_directory_exits_0(self, tmp_path):
        _write_py(tmp_path, "clean.py", "def f():\n    return 1\n")
        result = _run_reveal_direct("check", str(tmp_path), "--format", "json")
        assert result.returncode == 0
        assert '"exit_code": 0' in result.stdout


class TestStdinCheckExitCode:
    """`reveal --stdin --check` -- BACK-1099's originally-deferred follow-up
    (documented in EXIT_CODE_CONTRACT.md's "not yet fixed" section): the
    stdin file-list path dropped run_pattern_detection()'s `degraded` signal
    entirely, so a piped-in file with a syntax error exited identically to
    an all-clean run. Same fix pattern as TestDirectoryCheckExitCode above,
    applied to reveal/cli/handlers/batch.py's handle_stdin_mode()."""

    def _run_stdin_check(self, *paths):
        with patch("sys.stdin", StringIO("\n".join(str(p) for p in paths) + "\n")):
            return _run_reveal_direct("--stdin", "--check", "--format", "json")

    def test_clean_file_exits_0(self, tmp_path):
        f = _write_py(tmp_path, "clean.py", "def f():\n    return 1\n")
        result = self._run_stdin_check(f)
        assert result.returncode == 0

    def test_syntax_error_file_exits_3_not_0(self, tmp_path):
        f = _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        result = self._run_stdin_check(f)
        assert result.returncode == 3, (
            f"Expected exit 3 (scan incomplete), got {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_mixed_clean_and_broken_exits_3(self, tmp_path):
        broken = _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        clean = _write_py(tmp_path, "clean.py", "def f():\n    return 1\n")
        result = self._run_stdin_check(clean, broken)
        assert result.returncode == 3

    def test_syntax_error_and_clean_file_are_no_longer_indistinguishable(self, tmp_path):
        broken = _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        clean = _write_py(tmp_path, "clean.py", "def f():\n    return 1\n")
        broken_result = self._run_stdin_check(broken)
        clean_result = self._run_stdin_check(clean)
        assert broken_result.returncode != clean_result.returncode

    def test_plain_stdin_mode_unaffected(self, tmp_path):
        """Non---check --stdin (just routing files through, no quality
        check) must keep exiting 0 -- this fix only touches the --check
        aggregation path, not stdin mode in general."""
        f = _write_py(tmp_path, "clean.py", "def f():\n    return 1\n")
        with patch("sys.stdin", StringIO(f"{f}\n")):
            result = _run_reveal_direct("--stdin")
        assert result.returncode == 0
