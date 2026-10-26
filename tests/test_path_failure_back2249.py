"""``failure_of`` records a filesystem failure without its host path in the cause (BACK-2249).

``f'{type(e).__name__}: {e}'`` printed ``PermissionError: [Errno 13] Permission denied: '/abs/dir'`` next to
a path field the consumer spelled relative, so the absolute path reached JSON ``causes`` and ``message``.
"""
import os

from reveal.utils.path_utils import PathFailure, failure_of, traversal_failed_warning


def test_an_oserror_cause_has_the_class_and_strerror_only():
    failure = failure_of(PermissionError(13, 'Permission denied', '/abs/proj/locked'))
    assert failure == PathFailure('/abs/proj/locked', 'PermissionError: Permission denied')


def test_a_backslash_spelled_filename_is_a_posix_path_and_absent_from_the_cause():
    """Control for Windows, where ``filename`` is ``C:\\proj\\locked`` and ``str(e)`` quotes it with doubled backslashes."""
    failure = failure_of(PermissionError(13, 'Access is denied', 'C:\\proj\\locked'))
    assert failure.path == 'C:/proj/locked'
    assert 'proj' not in failure.cause and '\\' not in failure.cause


def test_filename2_is_not_in_the_cause():
    failure = failure_of(OSError(18, 'Invalid cross-device link', '/abs/a', None, '/abs/b'))
    assert failure.path == '/abs/a'
    assert 'abs' not in failure.cause and failure.cause == 'OSError: Invalid cross-device link'


def test_a_bytes_filename_is_decoded():
    failure = failure_of(FileNotFoundError(2, 'No such file or directory', os.fsencode('/abs/x')))
    assert failure.path == '/abs/x' and 'abs' not in failure.cause


def test_an_oserror_naming_no_path_has_no_path():
    assert failure_of(OSError(13, 'Permission denied')) == PathFailure(None, 'PermissionError: Permission denied')


def test_an_oserror_without_strerror_keeps_its_message():
    assert failure_of(OSError('no sem_open')) == PathFailure(None, 'OSError: no sem_open')


def test_a_file_descriptor_filename_is_not_a_path():
    assert failure_of(OSError(9, 'Bad file descriptor', 3)).path is None


def test_a_non_oserror_degrades_to_type_and_message():
    assert failure_of(ValueError('bad value')) == PathFailure(None, 'ValueError: bad value')


def test_the_warning_built_from_a_failure_names_the_path_once_and_relative(tmp_path):
    locked = tmp_path / 'proj' / 'locked'
    failure = failure_of(PermissionError(13, 'Permission denied', str(locked)))
    warning = traversal_failed_warning([failure], tmp_path / 'proj')
    assert warning['directories'] == ['locked']
    assert warning['causes'] == ['PermissionError: Permission denied']
    assert str(tmp_path) not in warning['message'] and tmp_path.as_posix() not in warning['message']
