"""A path that is neither a file nor a directory (a named pipe) is an invalid resource, exit 2 (D6), ruling B4 of
BACK-2325: ``reveal fifo`` exited 1, the findings code. Its message is unchanged."""
import os
import sys

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.skipif(sys.platform == 'win32' or not hasattr(os, 'mkfifo'), reason='no named pipes')


@pytest.fixture
def fifo(tmp_path, monkeypatch):
    os.mkfifo(tmp_path / 'fifo')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize('fmt', [[], ['--format', 'json']])
def test_a_named_pipe_is_an_invalid_resource_exit_2(fifo, fmt):
    run = _run_reveal_direct('fifo', *fmt)
    assert run.returncode == 2
    assert run.stderr == 'Error: fifo is neither file nor directory\n'


def test_sibling_a_missing_path_already_exits_2(fifo):
    assert _run_reveal_direct('missing.py').returncode == 2
