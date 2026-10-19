"""check rejects an invalid request with the D6 usage code 2, never the findings code 1 (BACK-2051).

A missing path, a URI given as a path, an unknown profile and no path at all were rejected
before any analysis but exited 1, which since ``--fail-on`` reads as "the findings gate
matched". Every other D6 command (deps, hotspots, review, pack, ...) already exits 2 for them.
"""
import os
import subprocess
import sys

import pytest


def _reveal(cwd, *args):
    env = {**os.environ, 'REVEAL_DISK_CACHE': '0'}
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd, capture_output=True,
                          text=True, env=env, timeout=120, check=False, encoding='utf-8')


@pytest.fixture(scope='module')
def clean(tmp_path_factory):
    root = tmp_path_factory.mktemp('check_usage')
    (root / 'ok.py').write_text('def f(x):\n    return x\n', encoding='utf-8')
    return root


@pytest.mark.parametrize('spelling', ['subcommand', 'flag'])
def test_missing_path_is_usage(clean, spelling):
    argv = ['check', 'nope.py'] if spelling == 'subcommand' else ['nope.py', '--check']
    result = _reveal(clean, *argv)
    assert result.returncode == 2, result.stderr
    assert 'no such file or directory' in result.stderr


def test_uri_as_path_is_usage(clean):
    result = _reveal(clean, 'check', 'ssl://example.com')
    assert result.returncode == 2
    assert 'looks like a URI' in result.stderr


def test_unknown_profile_is_usage(clean):
    result = _reveal(clean, 'check', 'ok.py', '--profile', 'no-such-profile')
    assert result.returncode == 2
    assert 'no-such-profile' in result.stderr


def test_no_path_is_usage(clean):
    result = _reveal(clean, 'check')
    assert result.returncode == 2
    assert 'path is required' in result.stderr


def test_control_a_clean_file_still_exits_zero(clean):
    """Positive control: the harness can see a successful check."""
    assert _reveal(clean, 'check', 'ok.py', '--select', 'B').returncode == 0
