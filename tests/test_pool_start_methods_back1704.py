"""BACK-1704: check's and stats://'s process pools under every start method, on Linux.

Windows and macOS start pool workers with ``spawn`` and CPython 3.14 on Linux with
``forkserver``; the local gate runs 3.12 on Linux, which forks. A test that reaches a
worker by monkeypatching a module only works when the worker is forked from the patched
parent (BACK-1681's dying-worker tests went red on py3.14 Linux and macOS for exactly
that, 991424a3). These tests force each start method in a fresh interpreter instead
(``multiprocessing.set_start_method(..., force=True)`` in a driver, then the real CLI)
so spawn and forkserver behaviour is checked on the machine the gate runs on.

Nothing is patched. The worker death comes from a user rule on disk, the way reveal
loads any custom rule (``$XDG_DATA_HOME/reveal/rules/<category>/<CODE>.py``): every
worker discovers it, spawned and forkserver workers by importing it afresh. The rule
calls ``os._exit`` on one file, only inside a pool worker, and logs every call's start
method so each test can show its pool actually ran under the method it asked for.
"""

import json
import multiprocessing
import os
import subprocess
import sys
import textwrap

import pytest

pytestmark = [pytest.mark.cli, pytest.mark.integration]

METHODS = ['fork', 'spawn', 'forkserver']
DYING = 'm2.py'
N_FILES = 6
_BARE_EXCEPT = 'def f():\n    try:\n        return 1\n    except:\n        return 0\n'

_DRIVER = textwrap.dedent('''
    import multiprocessing, sys

    if __name__ == '__main__':
        multiprocessing.set_start_method(sys.argv[1], force=True)
        from reveal.main import main
        main(['reveal'] + sys.argv[2:])
''')

# Z901: logs "<start method> <in a worker?>" per call; ends the worker on $DIE_ON.
_RULE = textwrap.dedent('''
    import multiprocessing
    import os
    import uuid
    from pathlib import Path

    from reveal.rules.base import BaseRule, RulePrefix, Severity


    class Z901(BaseRule):
        code = "Z901"
        message = "test rule: records the pool's start method, dies on one file"
        category = RulePrefix.B
        severity = Severity.LOW
        file_patterns = ['*.py']
        version = "1.0.0"

        def check(self, file_path, structure, content):
            in_worker = multiprocessing.parent_process() is not None
            # One file per call: two workers appending to one shared file can lose a line on
            # Windows (BACK-1704, CI run 37536176203).
            record = Path(os.environ["WORKER_LOG"]) / uuid.uuid4().hex
            record.write_text(f"{multiprocessing.get_start_method()} {in_worker}", encoding="utf-8")
            if in_worker and Path(file_path).name == os.environ.get("DIE_ON"):
                os._exit(1)
            return []
''')


def _need(method):
    if method not in multiprocessing.get_all_start_methods():
        pytest.skip(f'{method} start method unavailable on {sys.platform}')


@pytest.fixture
def work(tmp_path):
    """tmp_path holding the driver and a 6-file tree whose every file has one B001
    finding (so a clean run exits 1, an errored one 3)."""
    (tmp_path / 'driver.py').write_text(_DRIVER, encoding='utf-8')
    tree = tmp_path / 'tree'
    tree.mkdir()
    for i in range(N_FILES):
        (tree / f'm{i}.py').write_text(_BARE_EXCEPT, encoding='utf-8')
    return tmp_path


def _run(work, method, workers, *argv, die=False, log='worker-calls'):
    """Run the CLI in a fresh interpreter under *method*; returns (proc, logged calls).

    Each run gets its own XDG data dir holding the user rule, so per-user state a run
    leaves there (show-once hints) cannot make two runs' output differ."""
    data = work / f'data-{log}'
    rules = data / 'reveal' / 'rules' / 'custom'
    rules.mkdir(parents=True)
    (rules / 'Z901.py').write_text(_RULE, encoding='utf-8')
    env = dict(os.environ, REVEAL_MAX_WORKERS=str(workers), REVEAL_DISK_CACHE='0',
               REVEAL_NO_UPDATE_CHECK='1', PYTHONIOENCODING='utf-8',
               XDG_DATA_HOME=str(data), WORKER_LOG=str(work / log))
    (work / log).mkdir()
    env.pop('DIE_ON', None)
    if die:
        env['DIE_ON'] = DYING
    proc = subprocess.run([sys.executable, str(work / 'driver.py'), method, *argv],
                          capture_output=True, text=True, encoding='utf-8', cwd=str(work),
                          env=env, timeout=300)
    calls = sorted(p.read_text(encoding='utf-8') for p in (work / log).iterdir())
    return proc, calls


def _ran_in_pool(calls, method):
    """Every rule call ran in a pool worker started by *method* (and some ran)."""
    assert calls, 'the user rule never ran'
    assert set(calls) == {f'{method} True'}, sorted(set(calls))


CHECK = ('check', 'tree', '--select', 'B001,Z901')


@pytest.mark.parametrize('method', METHODS)
def test_check_counts_every_file_when_a_worker_dies(work, method):
    """BACK-1681 under every start method: the file lost with its worker is an errored
    file in the report, every file is reported once, exit 3."""
    _need(method)
    proc, calls = _run(work, method, 2, *CHECK, die=True)
    _ran_in_pool(calls, method)
    out = proc.stdout
    assert proc.returncode == 3, (proc.returncode, out, proc.stderr)
    for i in range(N_FILES):
        assert out.count(f'tree/m{i}.py: ') == 1, (i, out)
    dead = next(ln for ln in out.splitlines() if ln.startswith(f'tree/{DYING}: '))
    assert 'could not be checked' in dead and 'BrokenProcessPool' in dead
    assert f'Checked {N_FILES} files' in out
    assert DYING not in proc.stderr


def _json_files(out):
    return {f['file']: f for f in json.loads(out)['files']}


@pytest.mark.parametrize('method', METHODS)
def test_check_json_counts_every_file_when_a_worker_dies(work, method):
    """BACK-1717: --format json treats the lost file like the text path (BACK-1681): an
    errored file in files[], files_errored counts it, exit 3, and no file is re-run in
    the parent (the user rule only dies in a worker, so a serial re-run would hide it)."""
    _need(method)
    proc, calls = _run(work, method, 2, *CHECK, '--format', 'json', die=True)
    assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)
    assert set(calls) <= {f'{method} True'}, sorted(set(calls))  # nothing ran in the parent
    result = json.loads(proc.stdout)
    files = _json_files(proc.stdout)
    assert sorted(files) == [f'tree/m{i}.py' for i in range(N_FILES)], sorted(files)
    assert 'BrokenProcessPool' in json.dumps(files[f'tree/{DYING}'])
    assert result['summary']['files_errored'] >= 1, result['summary']


@pytest.mark.parametrize('method', METHODS)
def test_check_also_json_matches_format_json_when_a_worker_dies(work, method):
    """BACK-1717: text's --also-json artifact lists the same files, errored one included,
    as --format json."""
    _need(method)
    out = work / 'also.json'
    text, _ = _run(work, method, 2, *CHECK, '--also-json', str(out), die=True, log='text-calls')
    as_json, _ = _run(work, method, 2, *CHECK, '--format', 'json', die=True)
    assert text.returncode == as_json.returncode == 3, (text.stderr, as_json.stderr)
    also = json.loads(out.read_text(encoding='utf-8'))
    assert sorted(f['file'] for f in also['files']) == sorted(_json_files(as_json.stdout))
    # How many collateral files the broken pool takes with it varies run to run; the dead
    # one is always an errored file in both.
    assert 'BrokenProcessPool' in json.dumps(
        next(f for f in also['files'] if f['file'] == f'tree/{DYING}'))
    assert also['summary']['files_errored'] >= 1


@pytest.mark.parametrize('method', METHODS)
def test_check_grep_does_not_hide_a_dead_worker(work, method):
    """BACK-1717: --format grep exits 3 on a lost file and never re-runs it in the parent."""
    _need(method)
    proc, calls = _run(work, method, 2, *CHECK, '--format', 'grep', die=True)
    assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)
    assert set(calls) <= {f'{method} True'}, sorted(set(calls))


@pytest.mark.parametrize('fmt', ['text', 'json', 'grep'])
@pytest.mark.parametrize('method', METHODS)
def test_check_pool_matches_the_serial_run(work, method, fmt):
    """Negative control (no death): the pooled run prints what the serial run prints,
    byte for byte, with the same exit code."""
    _need(method)
    serial, serial_calls = _run(work, method, 1, *CHECK, '--format', fmt, log='serial-calls')
    pooled, calls = _run(work, method, 2, *CHECK, '--format', fmt)
    assert serial_calls and all(c.endswith(' False') for c in serial_calls)  # no pool
    _ran_in_pool(calls, method)
    assert len(calls) == len(serial_calls) == N_FILES
    assert serial.returncode == pooled.returncode == 1, (serial.stderr, pooled.stderr)
    assert pooled.stdout == serial.stdout
    assert 'could not be checked' not in pooled.stdout


@pytest.mark.parametrize('method', METHODS)
def test_stats_pool_matches_the_serial_run(work, method):
    """stats://'s pool: every file analysed, JSON identical to the serial run, exit 0."""
    _need(method)
    argv = ('stats://tree', '--format', 'json')
    serial, _ = _run(work, method, 1, *argv, log='serial-calls')
    pooled, calls = _run(work, method, 2, *argv)
    _ran_in_pool(calls, method)
    assert serial.returncode == pooled.returncode == 0, (serial.stderr, pooled.stderr)
    assert pooled.stdout == serial.stdout
    assert f'"total_files": {N_FILES}' in pooled.stdout


@pytest.mark.parametrize('method', METHODS)
def test_stats_worker_death_reports_the_lost_file_and_continues(work, method):
    """BACK-1718: a dead worker no longer fails the whole run. The file lost with it goes
    through BACK-1614's failure channel (a named warning, not in the totals) and the files
    that did finish are still reported. Which collateral files the broken pool takes with
    it varies, so the count is a bound; every file is either counted or named once."""
    _need(method)
    proc, calls = _run(work, method, 2, 'stats://tree', '--format', 'json', die=True)
    _ran_in_pool(calls, method)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    result = json.loads(proc.stdout)
    warning, = [w for w in result['meta']['warnings'] if w['type'] == 'analysis_failed']
    assert DYING in warning['files'], warning
    assert 1 <= warning['count'] <= N_FILES
    assert result['summary']['total_files'] + warning['count'] == N_FILES, (result['summary'], warning)
    assert 'terminated abruptly' not in proc.stderr
