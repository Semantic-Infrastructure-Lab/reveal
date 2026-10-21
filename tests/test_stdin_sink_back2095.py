"""BACK-2095: with --stdin one invocation is one result and each file sink is written once.

``printf 'a.py\\nb.py\\n' | reveal --stdin --check --also-json out.json`` rewrote out.json per file, so it held only the
last file's report. A URI list did the same, ``--batch`` and a plain path list dropped the sink without a word.
"""
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import pytest

from reveal.main import main


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('import os\n', encoding='utf-8')
    return tmp_path


def _run(stdin, *argv):
    out, err, code = io.StringIO(), io.StringIO(), 0
    with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', io.StringIO(stdin)):
        try:
            main(['reveal', *argv])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 0
    return code, out.getvalue(), err.getvalue()


def _paths(project):
    return f"{project / 'a.py'}\n{project / 'b.py'}\n"


@pytest.mark.parametrize('spelling', ['--output', '--also-json'])
def test_a_stdin_check_artifact_holds_every_file(project, tmp_path, spelling):
    out = tmp_path / 'o.json'
    value = f'json={out}' if spelling == '--output' else str(out)
    code, _stdout, stderr = _run(_paths(project), '--stdin', '--check', spelling, value)
    assert code == 1, stderr
    doc = json.loads(out.read_text(encoding='utf-8'))
    assert [entry['file'] for entry in doc['files']] == [(project / 'a.py').as_posix(), (project / 'b.py').as_posix()]
    assert doc['summary']['files_checked'] == 2
    assert doc['summary']['total_issues'] == 1


def test_a_stdin_check_writes_each_sink_once(project, tmp_path):
    first, second = tmp_path / 'a.json', tmp_path / 'b.json'
    writes = []
    real_open = open

    def counting_open(path, mode='r', *args, **kwargs):
        if 'w' in mode and str(path) in (str(first), str(second)):
            writes.append(str(path))
        return real_open(path, mode, *args, **kwargs)

    with patch('builtins.open', counting_open):
        code, _stdout, stderr = _run(_paths(project), '--stdin', '--check',
                                     '--output', f'json={first}', '--output', f'json={second}')
    assert code == 1, stderr
    assert sorted(writes) == sorted([str(first), str(second)]), writes
    assert first.read_text(encoding='utf-8') == second.read_text(encoding='utf-8')


def test_the_stdin_check_answer_does_not_change_with_a_sink(project, tmp_path):
    """Negative control: stdout and the exit code are those of the run without a sink."""
    bare = _run(_paths(project), '--stdin', '--check')
    sunk = _run(_paths(project), '--stdin', '--check', '--output', f'json={tmp_path / "o.json"}')
    assert sunk[:2] == bare[:2]


def test_an_unwritable_stdin_check_sink_exits_3_after_every_file_was_checked(project, tmp_path):
    code, stdout, stderr = _run(_paths(project), '--stdin', '--check',
                                '--output', f'json={tmp_path / "no-such-dir" / "o.json"}')
    assert code == 3, stderr
    assert 'b.py' in stdout


@pytest.mark.parametrize('extra', [[], ['--batch']], ids=['uri-list', 'batch'])
def test_a_stdin_run_that_cannot_hold_one_result_per_sink_refuses_the_sink(project, tmp_path, extra):
    """A URI list answers once per line; one file cannot hold N answers, so the sink is refused (exit 2)
    before stdin is read, instead of keeping the last answer or dropping the sink."""
    out = tmp_path / 'o.json'
    code, stdout, stderr = _run(f'ast://{project / "a.py"}\n', '--stdin', *extra, '--output', f'json={out}')
    assert code == 2, stderr
    assert '--stdin' in stderr and '--check' in stderr, stderr
    assert stdout == ''
    assert not out.exists()
