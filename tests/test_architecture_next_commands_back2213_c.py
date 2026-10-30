"""Canonical navigation preserves the target once for retired architecture requests."""
import shlex
from urllib.parse import quote

from conftest import _run_reveal_direct as run
from reveal.adapters.architecture import ArchitectureAdapter


def test_relative_target_navigation_does_not_double_the_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'sub'
    root.mkdir()
    (root / 'a.py').write_text('import b\n', encoding='utf-8')
    (root / 'b.py').write_text('VALUE=1\n', encoding='utf-8')
    report = ArchitectureAdapter('sub').get_structure()
    assert report['map']['fan_in']['rows'] == [{'file': 'b.py', 'fan_in': 1, 'fan_out': 0}]
    assert report['map']['components']['rows'][0]['component'] == '.'
    for step in report['next_steps']:
        assert 'sub/sub' not in step['command']
        tokens = shlex.split(step['command'])
        assert run(*tokens[1:], '--format', 'json').returncode in (0, 1)


def test_absolute_target_navigation_remains_executable(tmp_path):
    (tmp_path / 'a.py').write_text('VALUE=1\n', encoding='utf-8')
    report = ArchitectureAdapter(str(tmp_path)).get_structure()
    assert report['path'] == tmp_path.as_posix()
    assert report['map']['components']['rows'][0]['component'] == '.'
    command = report['next_steps'][0]['command']
    assert 'imports://' + quote(tmp_path.as_posix(), safe='/.:') in shlex.split(command)[1]
    assert run(*shlex.split(command)[1:], '--format', 'json').returncode == 0
