"""diff:// discloses a git-directory file whose analyzer *returned* a failed result (BACK-2672).

BACK-1854 disclosed a blob the analyzer raised on. An analyzer that reports failure in its result instead (the
notebook analyzer on invalid JSON returns ``{'error': ...}``) produced an empty structure: the file was absent from
that side, with no warning and exit 0, while ast, calls and metrics name the same file and exit 3. The scan now
reads the shared outcome (``outcome_of``) as ast does.

The exit code is not asserted: git-directory diffs are not a qualified D6 invocation yet
(``DiffAdapter.uri_execution_facts`` leaves composed and directory views legacy), so a raised and a returned
failure both disclose with the same legacy exit.
"""
import json
import subprocess

from conftest import _run_reveal_direct

_ENV = {'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 'T',
        'GIT_COMMITTER_EMAIL': 't@example.com', 'PATH': '/usr/bin:/bin'}


def _git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, env={**_ENV, 'HOME': str(repo)})


def _repo(tmp_path, second_notebook):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    _git(tmp_path, 'init', '-q')
    (pkg / 'mod.py').write_text('def a():\n    return 1\n', encoding='utf-8')
    _git(tmp_path, 'add', '-A')
    _git(tmp_path, 'commit', '-q', '-m', 'one')
    (pkg / 'nb.ipynb').write_text(second_notebook, encoding='utf-8')
    (pkg / 'mod.py').write_text('def a():\n    return 1\n\ndef c():\n    return 2\n', encoding='utf-8')
    _git(tmp_path, 'add', '-A')
    _git(tmp_path, 'commit', '-q', '-m', 'two')
    return tmp_path


def _diff(repo, monkeypatch):
    monkeypatch.chdir(repo)
    run = _run_reveal_direct('diff://git://HEAD~1/pkg:git://HEAD/pkg', '--format', 'json')
    return run.returncode, json.loads(run.stdout)


def test_a_returned_analyzer_failure_is_disclosed_and_incomplete(tmp_path, monkeypatch):
    rc, doc = _diff(_repo(tmp_path, '{not json'), monkeypatch)
    failed = [w for w in doc['meta']['warnings'] if w.get('type') == 'analysis_failed']
    assert failed, doc['meta']
    (warning,) = failed
    assert warning['field'] == 'right' and warning['files'] == ['pkg/nb.ipynb']
    assert 'Expecting property name' in json.dumps(warning['failures'])
    assert doc['summary']['functions']['added'] == 1  # the healthy file's change still answers


def test_a_valid_notebook_is_no_failure(tmp_path, monkeypatch):
    rc, doc = _diff(_repo(tmp_path, '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}'),
                    monkeypatch)
    assert not [w for w in doc['meta']['warnings'] if w.get('type') == 'analysis_failed']
    assert rc == 0 and doc['summary']['functions']['added'] == 1
