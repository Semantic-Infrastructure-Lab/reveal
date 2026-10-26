"""BACK-2244: a .pyc is stale when it was compiled from different source, not when it is newer.

`_check_pyc_file` reported every .pyc whose mtime was later than its source's, which is the
normal state after any import (3,598 false hits on reveal's own tree). Python's own rule
(importlib) compares the source mtime and size recorded in the .pyc header to the source file.
"""
import os
import py_compile

from reveal.adapters.python.bytecode import check_bytecode


def _compile(src, mode=py_compile.PycInvalidationMode.TIMESTAMP):
    pyc = py_compile.compile(str(src), doraise=True, invalidation_mode=mode)
    return pyc


def _types(root):
    return [i['type'] for i in check_bytecode(str(root))['issues']]


def test_a_freshly_compiled_pyc_that_is_newer_than_its_source_is_clean(tmp_path):
    src = tmp_path / 'mod.py'
    src.write_text('x = 1\n')
    os.utime(src, (1_700_000_000, 1_700_000_000))  # source is old; the pyc is brand new
    _compile(src)
    assert check_bytecode(str(tmp_path))['status'] == 'clean'


def test_a_pyc_compiled_from_different_source_is_stale(tmp_path):
    src = tmp_path / 'mod.py'
    src.write_text('x = 1\n')
    _compile(src)
    src.write_text('x = 22222\n')  # the recorded size no longer matches
    issues = check_bytecode(str(tmp_path))['issues']
    assert [i['type'] for i in issues] == ['stale_bytecode']
    assert 'older version of the source' in issues[0]['problem']


def test_a_pyc_whose_source_mtime_changed_is_stale(tmp_path):
    src = tmp_path / 'mod.py'
    src.write_text('x = 1\n')
    _compile(src)
    st = src.stat()
    os.utime(src, (st.st_atime, st.st_mtime + 100))  # same size, newer mtime
    assert _types(tmp_path) == ['stale_bytecode']


def test_a_hash_based_pyc_is_not_judged_by_mtime(tmp_path):
    src = tmp_path / 'mod.py'
    src.write_text('x = 1\n')
    _compile(src, py_compile.PycInvalidationMode.CHECKED_HASH)
    st = src.stat()
    os.utime(src, (st.st_atime, st.st_mtime + 100))
    assert check_bytecode(str(tmp_path))['status'] == 'clean'
