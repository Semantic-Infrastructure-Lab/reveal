"""BACK-2133: the doc-command fixture survives git's transient 'unable to create temporary file'.

CI run 39537054761 (ubuntu 3.12): `git commit` inside the module-scoped ``named_harness`` fixture
exited 128 with "error: unable to create temporary file: No such file or directory / fatal: failed
to write commit object" (git could not write into .git/objects: the directory vanished under it),
and pytest replayed the one cached fixture error as 231 test errors.  Cause not reproducible off CI;
these tests pin the hardening, which holds whatever removed the directory:

* that exact error rebuilds the tree from scratch, a bounded number of times, with a visible warning;
* any other git failure, and an exhausted retry budget, raise at once with git's own stderr;
* a tree that cannot be built becomes ONE failure (git's stderr) and skips for the rest.
"""

import shutil
import subprocess
import types
from pathlib import Path

import pytest

import doc_command_fixture as fx

pytestmark = [pytest.mark.component,
              pytest.mark.skipif(not shutil.which('git'), reason='the fixture builds history only when git is installed')]

_TRANSIENT = (b'error: unable to create temporary file: No such file or directory\n'
              b'fatal: failed to write commit object\n')
_MARK = 'feat: AuditLog logging'  # the 4th history commit: the one that failed in CI


def _flaky_git(monkeypatch, root, failures, stderr=_TRANSIENT):
    """Make the `_MARK` commit fail `failures` times, removing the object store like the CI failure."""
    real_run = subprocess.run
    calls = {'failed': 0, 'git': 0}

    def run(args, **kwargs):
        calls['git'] += 1
        if _MARK in args and calls['failed'] < failures:
            calls['failed'] += 1
            shutil.rmtree(Path(root) / '.git' / 'objects', ignore_errors=True)
            raise subprocess.CalledProcessError(128, args, output=b'', stderr=stderr)
        return real_run(args, **kwargs)

    monkeypatch.setattr(fx, 'subprocess', types.SimpleNamespace(
        run=run, CalledProcessError=subprocess.CalledProcessError))
    return calls


def _history_subjects(root):
    out = subprocess.run(['git', '-C', str(root), 'log', '--format=%s', 'main'], capture_output=True,
                         timeout=60, check=True)
    return out.stdout.decode('utf-8').split('\n')[:-1]


def test_the_transient_error_rebuilds_the_tree_and_says_so(tmp_path, monkeypatch):
    calls = _flaky_git(monkeypatch, tmp_path, failures=1)
    with pytest.warns(RuntimeWarning, match=r'attempt 1/3.*unable to create temporary file'):
        fx.build_doc_command_tree(tmp_path)
    assert calls['failed'] == 1
    subjects = _history_subjects(tmp_path)
    assert _MARK in subjects and subjects[-1] == 'Initial commit'
    assert len(subjects) == 1 + len(fx._HISTORY)  # rebuilt once, not appended to the broken repo


def test_a_rebuild_is_bounded_and_the_last_failure_carries_gits_stderr(tmp_path, monkeypatch):
    calls = _flaky_git(monkeypatch, tmp_path, failures=99)
    with pytest.warns(RuntimeWarning):
        with pytest.raises(RuntimeError, match=r'(?s)unable to create temporary file.*failed to write commit object'):
            fx.build_doc_command_tree(tmp_path)
    assert calls['failed'] == 3


def test_any_other_git_failure_is_not_retried(tmp_path, monkeypatch):
    calls = _flaky_git(monkeypatch, tmp_path, failures=99, stderr=b'fatal: bad object HEAD\n')
    with pytest.raises(RuntimeError, match='bad object HEAD'):
        fx.build_doc_command_tree(tmp_path)
    assert calls['failed'] == 1


def test_an_unbuildable_tree_fails_once_and_skips_the_rest():
    broken = fx.FailedBuild(RuntimeError('git commit exited 128: unable to create temporary file'))
    with pytest.raises(pytest.fail.Exception, match='unable to create temporary file'):
        broken.root
    for attribute in ('root', 'run_subcommand'):
        with pytest.raises(pytest.skip.Exception, match='already reported'):
            getattr(broken, attribute)
