"""``disk_cache.put`` does not re-list its whole namespace on every write (BACK-2121).

``put`` ended with ``_prune``, which ``os.scandir``-ed the namespace to count its ``.pkl``
entries on every write: measured 1.15 ms per put at 1k entries, 8.3 ms at 10k, 21 ms at 40k, so
a cold run over a big tree (one structure entry per source file, cap 100,000) was quadratic.
The count is now kept per process and re-read from disk only when it says the cap is crossed or
every so often, so that writes by other processes are noticed. Counting scandir entries, not
timing, is what makes the test deterministic.
"""
import subprocess
import sys

import pytest

from reveal.core import disk_cache

pytestmark = [pytest.mark.component, pytest.mark.disk_cache]


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')


def _seed(namespace: str, count: int):
    """A namespace that already holds *count* entries, written by 'another process'."""
    ns_dir = disk_cache._namespace_dir(namespace)
    ns_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (ns_dir / f'seed{i:06d}.pkl').write_bytes(b'')
    return ns_dir


def _entries(ns_dir) -> int:
    return sum(1 for p in ns_dir.iterdir() if p.suffix == '.pkl')


class _ScandirSpy:
    """Counts the entries ``os.scandir`` yields for one directory."""

    def __init__(self, monkeypatch, directory):
        self.visited = 0
        self.calls = 0
        real = disk_cache.os.scandir
        spy = self

        class _Counting:
            def __init__(self, iterator):
                self._iterator = iterator

            def __enter__(self):
                self._iterator.__enter__()
                return self

            def __exit__(self, *exc):
                return self._iterator.__exit__(*exc)

            def __iter__(self):
                for entry in self._iterator:
                    spy.visited += 1
                    yield entry

        def scandir(path='.'):
            if str(path) != str(directory):
                return real(path)
            spy.calls += 1
            return _Counting(real(path))

        monkeypatch.setattr(disk_cache.os, 'scandir', scandir)


@pytest.mark.parametrize('size', [200, 3000])
def test_put_does_not_relist_the_namespace(size, monkeypatch):
    ns_dir = _seed('prune_scale', size)
    disk_cache.put('prune_scale', 'first', 0, max_entries=100_000)  # may count the namespace once
    spy = _ScandirSpy(monkeypatch, ns_dir)
    for i in range(10):
        disk_cache.put('prune_scale', f'k{i}', i, max_entries=100_000)
    assert (spy.calls, spy.visited) == (0, 0), (
        f"10 puts into a {size}-entry namespace listed it {spy.calls} times ({spy.visited} entries)")
    assert _entries(ns_dir) == size + 11


def test_bound_holds_after_every_put():
    ns_dir = disk_cache._namespace_dir('prune_bound')
    for i in range(300):
        disk_cache.put('prune_bound', f'k{i}', i, max_entries=20)
        assert _entries(ns_dir) <= 20, f"put {i} left {_entries(ns_dir)} entries (cap 20)"
    assert _entries(ns_dir) == 20


def test_namespace_over_cap_before_the_first_put_is_pruned_by_it():
    ns_dir = _seed('prune_preseeded', 50)
    disk_cache.put('prune_preseeded', 'new', 1, max_entries=20)
    assert _entries(ns_dir) == 20


def test_entries_written_by_another_process_are_noticed_within_the_resync_window():
    ns_dir = disk_cache._namespace_dir('prune_foreign')
    disk_cache.put('prune_foreign', 'first', 0, max_entries=200)
    _seed('prune_foreign', 300)  # a second process wrote 300 entries this one never counted
    for i in range(200):
        disk_cache.put('prune_foreign', f'k{i}', i, max_entries=200)
    assert _entries(ns_dir) <= 200


def test_get_put_round_trip_and_overwrite():
    disk_cache.put('prune_roundtrip', 'k', {'a': 1}, max_entries=20)
    assert disk_cache.get('prune_roundtrip', 'k') == {'a': 1}
    disk_cache.put('prune_roundtrip', 'k', {'a': 2}, max_entries=20)
    assert disk_cache.get('prune_roundtrip', 'k') == {'a': 2}
    assert disk_cache.get('prune_roundtrip', 'missing') is None


WRITER = (
    "import sys\n"
    "from reveal.core import disk_cache\n"
    "tag = sys.argv[1]\n"
    "for i in range(150):\n"
    "    disk_cache.put('prune_procs', tag + str(i), i, max_entries=40)\n"
)


def test_concurrent_writer_processes_leave_a_namespace_the_next_put_brings_under_the_cap():
    procs = [subprocess.Popen([sys.executable, '-c', WRITER, f'p{n}_']) for n in range(4)]
    for proc in procs:
        assert proc.wait(timeout=120) == 0
    ns_dir = disk_cache._namespace_dir('prune_procs')
    # Each process keeps its own count, so together they may overshoot between re-reads ...
    # (four processes, each at most one 16-put re-read window out of date).
    assert _entries(ns_dir) <= 40 + 4 * 16
    # ... and a fresh process's first put reads the directory and evicts back to the cap.
    disk_cache.put('prune_procs', 'last', 0, max_entries=40)
    assert _entries(ns_dir) == 40
