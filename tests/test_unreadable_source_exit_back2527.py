"""BACK-2527: a bare-path read of a file that exists but cannot be read exits 3 (D6).

D6 reserves exit 1 for a findings gate. ``reveal FILE``, ``reveal FILE NAME``, the nav
flags and a single-file ``--grep`` on an unreadable file exited 1, while ``reveal check``
on the same file already exited 3 and named it, as do directory ``--grep`` (BACK-2520),
``sqlite://`` (BACK-2521) and ``xlsx://``. A ``--stdin`` batch skipped an unreadable file
with a warning and exit 0: its answer was built without that file. A missing path in a
``--stdin`` batch keeps exit 0 (``git diff --name-only`` lists deleted files, BACK-1426),
and a file that vanishes between the existence check and the read is an invalid
resource (2), the cause the nav facts already recorded.
"""
import errno
import json
import os
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.skipif(
    os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
    reason='chmod 000 does not deny reads on Windows or for root')

SOURCE = 'def f():\n    return 1\n'


@pytest.fixture
def tree(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text(SOURCE, encoding='utf-8')
    locked = tmp_path / 'locked.py'
    locked.write_text(SOURCE, encoding='utf-8')
    locked.chmod(0)
    yield tmp_path
    locked.chmod(0o644)


@pytest.mark.parametrize('extra', [
    [],
    ['f'],
    ['--outline'],
    ['f', '--effects'],
    ['f', '--exits', '--format', 'json'],
], ids=['structure', 'element', 'outline', 'effects', 'exits-json'])
def test_unreadable_file_exits_3_and_names_it(tree, extra):
    run = _run_reveal_direct(str(tree / 'locked.py'), *extra)
    assert run.returncode == 3, (run.returncode, run.stderr)
    assert 'cannot read' in run.stderr and 'locked.py' in run.stderr
    assert 'Traceback' not in run.stderr
    assert run.stdout == ''


def test_single_file_grep_on_unreadable_file_exits_3_with_warning(tree):
    run = _run_reveal_direct(str(tree / 'locked.py'), '--grep', 'return', '--format', 'json')
    assert run.returncode == 3, (run.returncode, run.stderr)
    data = json.loads(run.stdout)
    warnings = data['meta']['warnings']
    assert [w['type'] for w in warnings] == ['analysis_failed']
    assert warnings[0]['count'] == 1 and any('locked.py' in f for f in warnings[0]['files'])


def test_stdin_batch_with_an_unreadable_file_exits_3_and_still_answers_the_rest(tree):
    listing = f"{tree / 'ok.py'}\n{tree / 'locked.py'}\n"
    with patch('sys.stdin', StringIO(listing)):
        run = _run_reveal_direct('--stdin')
    assert run.returncode == 3, (run.returncode, run.stderr)
    assert 'ok.py' in run.stdout  # the readable file was still answered
    assert 'locked.py' in run.stderr and 'not readable' in run.stderr


# --- controls: these must not move -------------------------------------------------

def test_control_readable_file_exits_0(tree):
    assert _run_reveal_direct(str(tree / 'ok.py')).returncode == 0
    assert _run_reveal_direct(str(tree / 'ok.py'), 'f').returncode == 0
    assert _run_reveal_direct(str(tree / 'ok.py'), '--grep', 'return').returncode == 0


def test_control_missing_file_and_missing_element_exit_2(tree):
    assert _run_reveal_direct(str(tree / 'missing.py')).returncode == 2
    assert _run_reveal_direct(str(tree / 'ok.py'), 'nope').returncode == 2


def test_control_invalid_grep_pattern_keeps_exit_1(tree):
    # A usage error, out of this task's scope (EXIT_CODE_CONTRACT "Not migrated").
    assert _run_reveal_direct(str(tree / 'ok.py'), '--grep', '(').returncode == 1


def test_control_stdin_missing_file_keeps_exit_0(tree):
    listing = f"{tree / 'ok.py'}\n{tree / 'missing.py'}\n"
    with patch('sys.stdin', StringIO(listing)):
        run = _run_reveal_direct('--stdin')
    assert run.returncode == 0, (run.returncode, run.stderr)
    assert 'missing.py not found, skipping' in run.stderr


def test_control_check_keeps_its_codes(tree):
    assert _run_reveal_direct('check', str(tree / 'locked.py')).returncode == 3
    assert _run_reveal_direct('check', str(tree / 'locked.py'), '--exit-zero').returncode == 0
    listing = f"{tree / 'ok.py'}\n{tree / 'locked.py'}\n"
    with patch('sys.stdin', StringIO(listing)):
        assert _run_reveal_direct('--stdin', '--check').returncode == 3


# --- the exit follows the recorded cause ----------------------------------------------

@pytest.mark.parametrize('nav_source', [False, True], ids=['plain', 'nav'])
@pytest.mark.parametrize('error,code', [(PermissionError, 3), (FileNotFoundError, 2)],
                         ids=['denied', 'vanished'])
def test_default_exit_follows_the_read_failure_cause(tmp_path, monkeypatch, nav_source, error, code):
    from reveal.file_handler import _get_analyzer_or_exit
    import reveal.registry as registry

    path = tmp_path / 'requested.py'

    def construct(request):
        number = errno.ENOENT if error is FileNotFoundError else errno.EACCES
        raise error(number, 'controlled source read', str(path))

    monkeypatch.setattr(registry, 'get_analyzer', lambda *args, **kwargs: construct)
    with pytest.raises(SystemExit) as caught:
        _get_analyzer_or_exit(str(path), True, nav_source=nav_source)
    assert caught.value.code == code
