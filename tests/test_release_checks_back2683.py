"""scripts/release_checks.sh: the release scripts' CI verdict (BACK-2683) and test interpreter (BACK-2684).

ci_verdict is fed run lines as `gh run list --json` renders them, never the network; release_test_python
is pointed at stub interpreters, never the real ~/.cache/reveal-ci venv.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHECKS = Path(__file__).resolve().parent.parent / "scripts" / "release_checks.sh"

pytestmark = pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                                reason="POSIX shell helpers of the POSIX-only release scripts")


def _bash(script: str, stdin: str = "", **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f'source "{CHECKS.as_posix()}"; {script}'],
        input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=30,
        env={**os.environ, **env},
    )


def _verdict(*runs: str) -> str:
    return _bash("ci_verdict", "\n".join(runs) + "\n").stdout.strip()


def test_a_queued_newest_run_does_not_hide_a_completed_success():
    # 0.135.0: the master fast-forward queued a second run on the sha ci/release-0135 had passed.
    assert _verdict("44295261725 master queued ",
                    "44291891639 ci/release-0135 completed success") == "green 44291891639 (ci/release-0135)"


def test_any_completed_failure_refuses_even_beside_a_success():
    assert _verdict("2 master completed failure", "1 ci/x completed success") == "failed 2 (master, failure)"
    assert _verdict("3 master completed timed_out") == "failed 3 (master, timed_out)"


def test_a_cancelled_superseded_run_is_neither_green_nor_red():
    assert _verdict("2 ci/x completed cancelled", "1 ci/x completed success") == "green 1 (ci/x)"
    assert _verdict("2 ci/x completed cancelled") == "none"


def test_only_running_runs_is_pending_and_no_runs_is_none():
    assert _verdict("2 master in_progress ") == "pending 2 (master, in_progress)"
    assert _bash("ci_verdict", "").stdout.strip() == "none"


def _stub_python(tmp_path: Path, name: str, has_extras: bool) -> Path:
    stub = tmp_path / name
    stub.write_text("#!/usr/bin/env bash\n" + ("exit 0\n" if has_extras else "exit 1\n"), encoding="utf-8")
    stub.chmod(0o755)
    return stub


def test_sourcing_unsets_an_exported_pythonpath():
    # An exported PYTHONPATH put another project's tests/conftest.py ahead of reveal's (BACK-2684).
    out = _bash('echo "[${PYTHONPATH-unset}]"', PYTHONPATH="/elsewhere").stdout.strip()
    assert out == "[unset]"


def test_the_named_interpreter_is_used_when_it_has_the_dev_extras(tmp_path):
    stub = _stub_python(tmp_path, "py", has_extras=True)
    result = _bash("release_test_python", REVEAL_TEST_PYTHON=str(stub))
    assert (result.returncode, result.stdout.strip()) == (0, str(stub))


def test_an_interpreter_without_the_dev_extras_fails_naming_the_fix(tmp_path):
    stub = _stub_python(tmp_path, "py", has_extras=False)
    result = _bash("release_test_python", REVEAL_TEST_PYTHON=str(stub))
    assert result.returncode == 1 and result.stdout == ""
    assert "dev extras" in result.stderr and "pip install -e '.[dev]'" in result.stderr


def test_the_ci_local_venv_is_the_default(tmp_path):
    venv_python = tmp_path / "py3.12" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    _stub_python(venv_python.parent, "python", has_extras=True)
    env = {k: v for k, v in os.environ.items() if k != "REVEAL_TEST_PYTHON"}
    result = subprocess.run(
        ["bash", "-c", f'source "{CHECKS.as_posix()}"; release_test_python'],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        env={**env, "REVEAL_CI_VENV_ROOT": str(tmp_path)},
    )
    assert (result.returncode, result.stdout.strip()) == (0, str(venv_python))
