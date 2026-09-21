"""BACK-1351: the CLI must not crash when stdout cannot encode non-ASCII output.

Children run WITHOUT PYTHONIOENCODING (CI sets it to utf-8, which hid this) and with
an ASCII locale / cp1252 pipe.  Before the fix `reveal --help` died with
UnicodeEncodeError on U+2192.
"""
import os
import subprocess
import sys

import pytest


def _reveal(args, io_encoding=None, ascii_locale=True):
    env = {k: v for k, v in os.environ.items()
           if k not in ('PYTHONIOENCODING', 'PYTHONPYCACHEPREFIX', 'PYTHONUTF8', 'LC_ALL', 'LANG')}
    if ascii_locale:
        env.update(PYTHONUTF8='0', PYTHONCOERCECLOCALE='0', LC_ALL='C')
    if io_encoding:
        env['PYTHONIOENCODING'] = io_encoding
    return subprocess.run([sys.executable, '-m', 'reveal', *args], capture_output=True,
                          env=env, timeout=120)


@pytest.fixture
def non_ascii_py(tmp_path):
    f = tmp_path / 'a.py'
    f.write_text('def f():\n    return "❤ →"\n', encoding='utf-8')
    return f


@pytest.mark.parametrize('args', [['--help'], ['check', '--help'], ['trace', '--help']])
def test_help_survives_ascii_locale(args):
    r = _reveal(args)
    assert r.returncode == 0, r.stderr.decode('utf-8', 'replace')
    assert b'UnicodeEncodeError' not in r.stderr


def test_help_survives_cp1252_pipe():
    # U+2192 is not representable in cp1252
    r = _reveal(['--help'], io_encoding='cp1252', ascii_locale=False)
    assert r.returncode == 0, r.stderr.decode('utf-8', 'replace')


def test_output_of_non_ascii_source_survives_ascii_locale(non_ascii_py):
    for args in (['check', str(non_ascii_py)], [str(non_ascii_py), 'f']):
        r = _reveal(args)
        assert b'UnicodeEncodeError' not in r.stderr, r.stderr.decode('utf-8', 'replace')
        assert r.returncode in (0, 1)


def test_utf8_streams_are_left_alone(non_ascii_py):
    r = _reveal([str(non_ascii_py), 'f'], io_encoding='utf-8', ascii_locale=False)
    assert r.returncode == 0
    assert '❤'.encode('utf-8') in r.stdout
