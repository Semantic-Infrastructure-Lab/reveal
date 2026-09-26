"""BACK-1501: pool workers must not outlive a killed reveal parent.

SIGKILL to the process that owns a ProcessPoolExecutor left its workers
running, reparented to init (a harness that timed out and killed only the pid
accumulated 272). worker_bootstrap now starts a thread that ends the worker
when the parent's sentinel fires.
"""

import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='POSIX signals and /proc-style liveness')

CHILD = textwrap.dedent('''
    import multiprocessing as mp, os, sys, time
    from concurrent.futures import ProcessPoolExecutor
    from reveal.logging_setup import worker_bootstrap

    def pid_then_sleep(_):
        time.sleep(0.3)
        return os.getpid()

    def forever(_):
        time.sleep(600)

    if __name__ == "__main__":
        ex = ProcessPoolExecutor(max_workers=2, mp_context=mp.get_context(sys.argv[1]),
                                 initializer=worker_bootstrap)
        pids = set(ex.map(pid_then_sleep, range(4)))
        for i in range(2):
            ex.submit(forever, i)
        print(" ".join(map(str, sorted(pids))), flush=True)
        time.sleep(600)
''')


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); it has exited all the same.
    try:
        with open(f'/proc/{pid}/stat', encoding='utf-8') as f:
            return f.read().split()[2] != 'Z'
    except OSError:
        return True


@pytest.mark.parametrize('method', ['fork', 'spawn'])
def test_workers_exit_when_parent_is_killed(tmp_path, method):
    if method not in __import__('multiprocessing').get_all_start_methods():
        pytest.skip(f'{method} unavailable')
    child = tmp_path / 'child.py'
    child.write_text(CHILD, encoding='utf-8')
    proc = subprocess.Popen([sys.executable, str(child), method], stdout=subprocess.PIPE,
                            text=True, encoding='utf-8', cwd=str(tmp_path))
    pids = [int(p) for p in proc.stdout.readline().split()]
    assert pids, 'child printed no worker pids'
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait()
    deadline = time.monotonic() + 10
    survivors = pids
    while survivors and time.monotonic() < deadline:
        time.sleep(0.2)
        survivors = [p for p in pids if _alive(p)]
    for p in survivors:  # never leave them behind, even on failure
        os.kill(p, signal.SIGKILL)
    assert not survivors, f'workers outlived their parent: {survivors}'
