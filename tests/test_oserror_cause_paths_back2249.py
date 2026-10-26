"""An unreadable directory's cause carries no host path, in every command that records it (BACK-2249).

``chmod 000`` a subdirectory: the failure was recorded as ``PermissionError: [Errno 13] Permission denied:
'/abs/.../locked'``, so the absolute path reached ``causes`` and ``message`` of the warning beside the
relative ``directories`` entry. The path is named once, relative; the cause is the class and ``strerror``.
"""
import json
import os
import sys

import pytest

from conftest import _run_reveal_in

pytestmark = pytest.mark.skipif(
    sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
    reason='needs chmod 000 to deny a directory (not on Windows, not as root)')


@pytest.fixture
def locked(tmp_path):
    proj = tmp_path / 'proj'
    (proj / 'src' / 'locked').mkdir(parents=True)
    (proj / 'package.json').write_text('{"name": "p"}\n', encoding='utf-8')
    (proj / 'src' / 'a.ts').write_text("import { b } from './b';\n", encoding='utf-8')
    (proj / 'src' / 'b.ts').write_text('export const b = 1;\n', encoding='utf-8')
    (proj / 'src' / 'locked' / 'c.ts').write_text('export const c = 1;\n', encoding='utf-8')
    (proj / 'src' / 'locked').chmod(0)
    yield tmp_path
    (proj / 'src' / 'locked').chmod(0o755)


def _run(tmp_path, uri, *flags):
    result = _run_reveal_in(tmp_path, uri, *flags)
    assert str(tmp_path) not in result.stdout + result.stderr, (uri, result.stdout, result.stderr)
    assert tmp_path.as_posix() not in result.stdout + result.stderr, (uri, result.stdout, result.stderr)
    return result


def _warning(data):
    for entry in (data.get('meta') or {}).get('warnings', []) or data.get('warnings', []):
        if entry.get('type') == 'analysis_incomplete' and entry.get('unit') == 'directories':
            return entry
    raise AssertionError(f'no directory enumeration warning in {json.dumps(data)[:600]}')


def test_imports_json_cause_and_message_name_the_directory_relative(locked):
    data = json.loads(_run(locked, 'imports://proj/src', '--format', 'json').stdout)
    warning = _warning(data)
    assert warning['directories'] == ['locked']
    assert warning['causes'] == ['PermissionError: Permission denied']
    assert '(PermissionError: Permission denied)' in warning['message']


def test_imports_text_names_the_directory_relative(locked):
    out = _run(locked, 'imports://proj/src').stdout
    assert 'locked (PermissionError: Permission denied)' in out


def test_importers_name_error_does_not_name_the_root(locked):
    """The unlocated-name usage error carried both leaks: the scan root and the failed directory."""
    result = _run(locked, 'imports://proj?importers=nosuchname')
    assert result.returncode == 2
    assert 'matched no file under' in result.stdout + result.stderr


@pytest.mark.parametrize('command', [
    ('overview', 'proj/src'),
    ('check', 'proj/src', '--format', 'json'),
    ('hotspots', 'proj/src'),
])
def test_other_commands_do_not_print_the_host_path(locked, command):
    _run(locked, *command)
