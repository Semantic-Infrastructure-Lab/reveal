"""scripts/check_windows_compat.py blocks a new POSIX-path antipattern (BACK-1470).

CI and ci-local run it without ``--warn``; these tests pin that an un-exempted hit fails, that the
``# noqa: win-path`` pragma exempts a line, and that the repo's own tests are clean.
"""
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.component

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'check_windows_compat.py'

HIT = "def test_x():\n    assert result['file'] == '/fake/x.py'\n"  # noqa: win-path (sample source)
EXEMPT = "def test_x():\n    assert result['file'] == '/fake/x.py'  # noqa: win-path (plain string)\n"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding='utf-8', timeout=120)


def _scan(tmp_path, source, *args):
    # The script reports paths relative to the repo root, so the scanned file lives under it --
    # in a per-call dir outside tests/, which the repo-wide scan (and xdist peers) never walk.
    scratch = ROOT / f'.win_compat_scratch_{uuid.uuid4().hex}'
    scratch.mkdir()
    target = scratch / 'test_scratch_sample.py'
    try:
        target.write_text(source, encoding='utf-8')
        return _run(str(target), *args)
    finally:
        target.unlink(missing_ok=True)
        scratch.rmdir()


def test_unexempted_posix_path_assertion_fails(tmp_path):
    result = _scan(tmp_path, HIT)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'POSIX path literal in assertion' in result.stdout


def test_noqa_pragma_exempts_the_line(tmp_path):
    result = _scan(tmp_path, EXEMPT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_warn_flag_still_reports_but_does_not_block(tmp_path):
    result = _scan(tmp_path, HIT, '--warn')
    assert result.returncode == 0
    assert 'WARNING' in result.stdout


def test_repo_tests_have_no_unexempted_hits():
    """The gate CI runs: a new hit anywhere in tests/ fails here and in the workflow."""
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr


def test_ci_does_not_run_the_checker_in_warn_mode():
    for rel in ('.github/workflows/test.yml', 'scripts/ci-local.sh'):
        text = (ROOT / rel).read_text(encoding='utf-8')
        assert 'check_windows_compat.py --warn' not in text, rel
