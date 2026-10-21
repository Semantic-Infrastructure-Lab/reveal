"""``reveal check --changed RANGE``: the rule pass over the files a git range changed (BACK-2068 slice 3b).

The fold of ``review``'s rule pass into ``check`` (D3): same collector, same report, same exit
contract as ``check <dir>``, with the file set cut to what the range touched and the cut stated in
``scope.changed``. Controls run the same tree without the flag, so a pass cannot mean "nothing was
checked".
"""
import json
import os
import subprocess
import sys

import pytest

_BAD = "def f(x):\n    try:\n        return 1 / x\n    except:\n        pass\n"
_OK = "def f(x):\n    return x\n"
_GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', '-c', 'commit.gpgsign=false']


def _git(cwd, *args):
    subprocess.run([*_GIT, *args], cwd=cwd, check=True, capture_output=True, text=True, encoding='utf-8')


def _reveal(cwd, *args):
    env = {**os.environ, 'REVEAL_DISK_CACHE': '0'}
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd, capture_output=True,
                          text=True, env=env, timeout=120, check=False, encoding='utf-8')


def _write(root, name, body):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def _repo(tmp_path, base, change):
    """A repo with one commit of ``base`` files and a second commit applying ``change``
    (name -> body, or None to delete)."""
    root = tmp_path / 'repo'
    root.mkdir()
    _git(root, 'init', '-q')
    for name, body in base.items():
        _write(root, name, body)
    _git(root, 'add', '-A')
    _git(root, 'commit', '-q', '-m', 'base')
    for name, body in change.items():
        if body is None:
            (root / name).unlink()
        else:
            _write(root, name, body)
    _git(root, 'add', '-A')
    _git(root, 'commit', '-q', '-m', 'change')
    return root


def _check(root, *args):
    done = _reveal(root, 'check', *args, '--format', 'json')
    return done, (json.loads(done.stdout) if done.stdout.strip().startswith('{') else None)


def _flagged(result):
    return sorted(entry['file'] for entry in result['files'] if entry.get('issues') or entry.get('detections'))


def test_changed_scopes_the_rule_pass_to_the_range(tmp_path):
    root = _repo(tmp_path, {'old_bad.py': _BAD, 'ok.py': _OK}, {'new_bad.py': _BAD, 'ok.py': _OK + '\n'})
    done, result = _check(root, '.', '--changed', 'HEAD~1..HEAD')
    assert done.returncode == 1, done.stderr
    assert result['summary']['files_checked'] == 2
    assert _flagged(result) == ['new_bad.py']
    # control: the same tree without the flag sees the unchanged violation too
    done, whole = _check(root, '.')
    assert whole['summary']['files_checked'] == 3
    assert _flagged(whole) == ['new_bad.py', 'old_bad.py']


def test_findings_outside_the_range_do_not_fail_the_run(tmp_path):
    root = _repo(tmp_path, {'old_bad.py': _BAD, 'ok.py': _OK}, {'ok.py': _OK + '\n'})
    done, result = _check(root, '.', '--changed', 'HEAD~1..HEAD')
    assert done.returncode == 0, done.stderr
    assert result['summary']['files_checked'] == 1
    assert result['summary']['total_issues'] == 0
    assert _check(root, '.')[0].returncode == 1  # control: the whole tree still fails


def test_scope_states_the_range_and_its_file_count(tmp_path):
    root = _repo(tmp_path, {'ok.py': _OK}, {'new_bad.py': _BAD, 'notes.txt': 'not code\n'})
    done, result = _check(root, '.', '--changed', 'HEAD~1..HEAD')
    assert result['scope']['changed'] == {'range': 'HEAD~1..HEAD', 'files': 2}  # git's list, before the code filter
    text = _reveal(root, 'check', '.', '--changed', 'HEAD~1..HEAD')
    assert 'HEAD~1..HEAD' in text.stdout and 'changed' in text.stdout.lower()


def test_path_is_optional_and_restricts_when_given(tmp_path):
    root = _repo(tmp_path, {'pkg/a.py': _OK, 'other/b.py': _OK}, {'pkg/a.py': _BAD, 'other/b.py': _BAD})
    done, everywhere = _check(root, '--changed', 'HEAD~1..HEAD')
    assert _flagged(everywhere) == ['other/b.py', 'pkg/a.py']
    done, narrowed = _check(root, 'pkg', '--changed', 'HEAD~1..HEAD')
    assert narrowed['summary']['files_checked'] == 1
    assert [entry['file'] for entry in narrowed['files']] == ['pkg/a.py']  # relative to the cwd, as check always reports


def test_deleted_files_are_skipped_not_errors(tmp_path):
    root = _repo(tmp_path, {'gone.py': _BAD, 'ok.py': _OK}, {'gone.py': None, 'ok.py': _OK + '\n'})
    done, result = _check(root, '.', '--changed', 'HEAD~1..HEAD')
    assert done.returncode == 0, done.stderr
    assert result['summary']['files_checked'] == 1


def test_a_single_ref_means_uncommitted_changes(tmp_path):
    root = _repo(tmp_path, {'old_bad.py': _BAD, 'ok.py': _OK}, {'ok.py': _OK + '\n'})
    _write(root, 'ok.py', _BAD)  # modified after the last commit, not committed
    done, result = _check(root, '.', '--changed', 'HEAD')
    assert done.returncode == 1 and _flagged(result) == ['ok.py']
    assert result['summary']['files_checked'] == 1


@pytest.mark.parametrize('bad_range', ['nope..HEAD', 'HEAD~99..HEAD', 'nope'])
def test_an_unusable_range_is_a_usage_error(tmp_path, bad_range):
    root = _repo(tmp_path, {'ok.py': _OK}, {'ok.py': _OK + '\n'})
    done = _reveal(root, 'check', '.', '--changed', bad_range)
    assert done.returncode == 2
    assert 'Traceback' not in done.stderr and 'unknown revision' in done.stderr
    assert done.stdout == ''  # no report was produced


def test_outside_a_repository_is_a_usage_error(tmp_path):
    (tmp_path / 'x.py').write_text(_OK, encoding='utf-8')
    done = _reveal(tmp_path, 'check', '.', '--changed', 'a..b')
    assert done.returncode == 2 and 'not inside a git repository' in done.stderr
