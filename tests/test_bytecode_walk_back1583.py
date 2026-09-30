"""BACK-1583: the stale-bytecode scan judges skip dirs below its root, and prunes them.

It tested every part of the absolute path, so a project under /opt/venv/ or ~/.cache/ had
every .pyc skipped and read as clean; and its rglob enumerated every .pyc (384,796 on one
tree) before filtering.
"""
from reveal.adapters.python.bytecode import check_bytecode


def _orphan(root):
    cache = root / 'pkg' / '__pycache__'
    cache.mkdir(parents=True)
    (cache / 'gone.cpython-312.pyc').write_bytes(b'\x00')


def test_a_project_under_a_skip_named_directory_is_scanned(tmp_path):
    root = tmp_path / 'venv' / 'app'
    _orphan(root)
    result = check_bytecode(str(root))
    assert result['status'] == 'issues_found'
    assert len(result['issues']) == 1


def test_skip_dirs_below_the_root_are_not_scanned(tmp_path):
    _orphan(tmp_path / '.venv' / 'lib')
    _orphan(tmp_path / 'build' / 'x.egg-info')
    assert check_bytecode(str(tmp_path))['status'] == 'clean'
