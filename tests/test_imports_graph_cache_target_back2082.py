"""BACK-2082: the whole-graph disk cache key must name the scan root it resolved against.

``imports://w`` and ``imports://w/sub`` can walk exactly the same files (``w`` holds only
``sub/``), but they resolve against different search paths: the scan root is an extra search
path for every file (``service.resolve_graph``), so ``from sub import x`` in ``w/sub/a.py``
resolves under ``w`` and not under ``w/sub``. A key over the file set alone made whichever
target ran first answer for the other, in both orders.
"""

import json

import pytest

from reveal.adapters.imports import ImportsAdapter
from conftest import _run_reveal_direct

pytestmark = [pytest.mark.integration, pytest.mark.disk_cache]


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """w/sub/{a.py, x.py}; the cache dir lives beside it, outside the scanned tree."""
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    sub = tmp_path / 'w' / 'sub'
    sub.mkdir(parents=True)
    (sub / 'a.py').write_text('from sub import x\n', encoding='utf-8')
    (sub / 'x.py').write_text('X = 1\n', encoding='utf-8')
    return tmp_path / 'w'


@pytest.fixture
def builds(monkeypatch):
    """How many times the graph was built from extraction, i.e. disk-cache misses."""
    calls = []
    original = ImportsAdapter._process_extracted_files

    def counting(self, *args, **kwargs):
        calls.append(self._target_path)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ImportsAdapter, '_process_extracted_files', counting)
    return calls


def _fan_in(target):
    result = _run_reveal_direct(f'imports://{target}?rank=fan-in', '--format', 'json')
    assert result.returncode == 0, result.stderr
    return {e['file']: e['fan_in'] for e in json.loads(result.stdout)['entries']}


def _uncached(target, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    try:
        return _fan_in(target)
    finally:
        monkeypatch.delenv('REVEAL_DISK_CACHE')


def test_fixture_targets_resolve_differently(tree, monkeypatch):
    """Precondition: without the cache the two targets give different answers."""
    assert _uncached(tree, monkeypatch)['sub/x.py'] == 1
    assert _uncached(tree / 'sub', monkeypatch)['x.py'] == 0


@pytest.mark.parametrize('first,second', [('.', 'sub'), ('sub', '.')], ids=['w-then-sub', 'sub-then-w'])
def test_each_target_gets_its_own_graph(tree, monkeypatch, builds, first, second):
    expected = {name: _uncached(tree / name, monkeypatch) for name in (first, second)}
    builds.clear()
    assert _fan_in(tree / first) == expected[first]
    assert _fan_in(tree / second) == expected[second]
    assert len(builds) == 2, 'the second target was served the first target\'s cached graph'


def test_same_target_twice_still_hits(tree, builds):
    """Negative control: the key change must not cost the cache its hits."""
    cold = _fan_in(tree)
    warm = _fan_in(tree)
    assert warm == cold
    assert len(builds) == 1, 'an unchanged target was rebuilt instead of read from the disk cache'
