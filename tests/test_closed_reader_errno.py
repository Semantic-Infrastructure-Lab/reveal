"""A closed stdout reader is EPIPE on POSIX and EINVAL (WinError 232) on Windows."""
import errno
import types

import pytest

from reveal.cli.routing import declared

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('os_name,exc,expected', [
    ('posix', BrokenPipeError(), True),
    ('nt', BrokenPipeError(), True),
    ('nt', OSError(errno.EINVAL, 'Invalid argument'), True),
    ('nt', OSError(errno.EPIPE, 'Broken pipe'), True),
    ('posix', OSError(errno.EINVAL, 'Invalid argument'), False),
    ('nt', OSError(errno.EACCES, 'Permission denied'), False),
    ('nt', ValueError('bad'), False),
])
def test_is_closed_reader(monkeypatch, os_name, exc, expected):
    monkeypatch.setattr(declared, 'os', types.SimpleNamespace(name=os_name))
    assert declared.is_closed_reader(exc) is expected
