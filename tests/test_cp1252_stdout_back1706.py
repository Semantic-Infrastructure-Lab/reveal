"""BACK-1706: non-ASCII output to a cp1252 stdout must not crash or traceback.

Coverage measured first: ``tests/test_console_encoding.py`` runs ``--help`` under
``PYTHONIOENCODING=cp1252`` and element/check output only under an ASCII *locale*;
no test sent element extraction, ``check`` or markdown output of non-ASCII source
through a cp1252 stream, which is what a Windows console pipe looks like.
The U+2764 / U+2192 below are not representable in cp1252; U+00E9 is.
"""
import os
import subprocess
import sys

import pytest

# BACK-1149: end-to-end CLI behavior on a non-UTF-8 stream
pytestmark = pytest.mark.integration

PY_SRC = 'def f():\n    return "café ❤ →"\n'
MD_SRC = '# Título ❤\n\nbody → café\n'


def _run(cwd, *args):
    env = {k: v for k, v in os.environ.items()
           if k not in ('PYTHONIOENCODING', 'PYTHONPYCACHEPREFIX', 'PYTHONUTF8', 'LC_ALL', 'LANG')}
    env['PYTHONIOENCODING'] = 'cp1252'
    env['REVEAL_DISK_CACHE'] = '0'
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=str(cwd),
                          env=env, capture_output=True, timeout=120)


@pytest.fixture
def sources(tmp_path):
    (tmp_path / 'a.py').write_bytes(PY_SRC.encode('utf-8'))
    (tmp_path / 'a.md').write_bytes(MD_SRC.encode('utf-8'))
    return tmp_path


@pytest.mark.parametrize('args', [
    ['a.py'],
    ['a.py', 'f'],
    ['a.py', 'f', '--format', 'json'],
    ['check', 'a.py'],
    ['a.md'],
    ['a.md', 'Título ❤'],
    ['check', 'a.md'],
], ids=lambda a: ' '.join(a))
def test_non_ascii_output_survives_cp1252_stdout(sources, args):
    r = _run(sources, *args)
    err = r.stderr.decode('utf-8', 'replace')
    assert b'Traceback' not in r.stderr, err
    assert b'UnicodeEncodeError' not in r.stderr, err
    assert r.returncode in (0, 1), err


@pytest.mark.skipif(sys.platform == 'win32',
                    reason='Windows forces UTF-8 on the console (main._setup_console)')
def test_unencodable_characters_are_replaced_encodable_ones_survive(sources):
    r = _run(sources, 'a.py', 'f')
    assert r.returncode == 0, r.stderr.decode('utf-8', 'replace')
    # cp1252 bytes: e-acute is 0xE9; the heart and arrow cannot be encoded and become '?'
    assert b'caf\xe9' in r.stdout
    assert b'caf\xe9 ? ?' in r.stdout
