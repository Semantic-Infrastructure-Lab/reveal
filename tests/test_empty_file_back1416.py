"""BACK-1416: an empty file printed a numbered line 1 under its "0 lines" header, in
the default and the --outline view. It says "(empty file)" now; a file holding one
blank line still shows that line.
"""

import os
import subprocess
import sys

import pytest


def _reveal(cwd, *argv):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', REVEAL_NO_UPDATE_CHECK='1')
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


@pytest.mark.parametrize('name', ['empty.py', 'empty.json'])
@pytest.mark.parametrize('flags', [(), ('--outline',)], ids=['default', 'outline'])
def test_empty_file_says_so(tmp_path, name, flags):
    (tmp_path / name).write_bytes(b'')
    run = _reveal(tmp_path, name, *flags)
    assert run.returncode == 0, run.stderr
    assert '(empty file)' in run.stdout
    assert '     1  ' not in run.stdout


def test_one_blank_line_is_still_shown(tmp_path):
    (tmp_path / 'nl.py').write_bytes(b'\n')
    run = _reveal(tmp_path, 'nl.py')
    assert '(empty file)' not in run.stdout
    assert '     1  ' in run.stdout
