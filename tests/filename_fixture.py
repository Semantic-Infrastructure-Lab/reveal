"""Qualify literal filename cases against the filesystem that runs the test."""
import errno

import pytest


def require_filename(path):
    """Probe only this literal case; portable siblings always run on every OS."""
    try:
        path.touch()
    except OSError as exc:
        forbidden = any(char in path.name for char in '<>:"|?*')
        invalid = exc.errno == errno.EINVAL or getattr(exc, 'winerror', None) == 123
        if forbidden and invalid:
            pytest.skip('filesystem rejects this literal filename; invalid-resource controls run separately')
        raise
    path.unlink()
