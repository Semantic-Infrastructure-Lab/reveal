"""BACK-1556: a URI that fails under --stdin or @file fails the run.

Plain `--stdin` and `@file` caught each URI's SystemExit, printed
"Warning: <uri> failed, skipping" and exited 0, so a CI step piping URIs passed
while one of them errored. `@file` had its own copy of the loop; it now goes
through --stdin's. A missing *file* still skips with a warning: `git diff
--name-only` lists deleted files, and that degradation is deliberate.
"""

import subprocess
import sys


def _run(argv, stdin=''):
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], input=stdin,
                          capture_output=True, text=True, encoding='utf-8', timeout=120)


def test_a_failed_uri_on_stdin_exits_1(tmp_path):
    (tmp_path / 'ok.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    result = _run(['--stdin'], f'ast:///no/such/dir\nast://{tmp_path}\n')
    assert result.returncode == 1
    assert 'Path not found' in result.stderr
    assert 'f' in result.stdout  # the rest still ran


def test_a_failed_uri_in_an_at_file_exits_1(tmp_path):
    listing = tmp_path / 'targets.txt'
    listing.write_text('ast:///no/such/dir\n', encoding='utf-8')
    assert _run([f'@{listing}']).returncode == 1


def test_good_uris_and_a_missing_file_still_exit_0(tmp_path):
    (tmp_path / 'ok.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    result = _run(['--stdin'], f'ast://{tmp_path}\n{tmp_path / "deleted.py"}\n')
    assert result.returncode == 0, result.stderr
    assert 'not found, skipping' in result.stderr
