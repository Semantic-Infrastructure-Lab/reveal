"""BACK-1747: REVEAL_TEST_SHARD balances shards by recorded Windows cost, not crc32 of the path.

CI run 37573474633: Windows half 1 took 251-384 s, half 2 729-1111 s, because crc32 of the file
path ignores that one file (test_example_recipes_run.py) costs ~27% of the suite. The shards
now come from tests/windows_test_durations.json (scripts/windows_test_durations.py).
"""
import json
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import conftest

pytestmark = pytest.mark.component

_DURATIONS = json.loads(
    (Path(__file__).parent / "windows_test_durations.json").read_text(encoding="utf-8"))["files"]


def _items(files, per_file=3):
    return [SimpleNamespace(nodeid=f"{name}::test_{i}") for name in files for i in range(per_file)]


def _shard(monkeypatch, items, index, total):
    """The nodeids that survive the real pytest_collection_modifyitems hook for shard index/total."""
    monkeypatch.setenv("REVEAL_TEST_SHARD", f"{index}/{total}")
    kept = list(items)
    dropped = []
    config = SimpleNamespace(hook=SimpleNamespace(pytest_deselected=lambda items: dropped.extend(items)))
    conftest.pytest_collection_modifyitems(config, kept)
    assert len(kept) + len(dropped) == len(items)
    return [i.nodeid for i in kept]


def _imbalance(shards):
    """max/min of the recorded cost carried by each shard (files only; every item is one file)."""
    costs = [sum(_DURATIONS.get(n.split("::")[0], 0.0) for n in {x.split("::")[0] for x in s})
             for s in shards]
    return max(costs) / min(costs)


class TestShardPartition:
    @pytest.mark.parametrize("total", [2, 3])
    def test_union_is_everything_and_shards_are_disjoint(self, monkeypatch, total):
        files = sorted(_DURATIONS) + [f"tests/test_brand_new_{i}.py" for i in range(7)]
        items = _items(files)
        shards = [_shard(monkeypatch, items, i, total) for i in range(1, total + 1)]
        flat = [n for s in shards for n in s]
        assert sorted(flat) == sorted(i.nodeid for i in items)
        assert len(flat) == len(set(flat))

    def test_a_file_stays_whole_in_one_shard(self, monkeypatch):
        items = _items(sorted(_DURATIONS))
        shards = [_shard(monkeypatch, items, i, 2) for i in (1, 2)]
        owners = {}
        for number, shard in enumerate(shards):
            for nodeid in shard:
                owners.setdefault(nodeid.split("::")[0], set()).add(number)
        assert all(len(o) == 1 for o in owners.values())

    def test_assignment_is_deterministic_and_independent_of_collection_order(self, monkeypatch):
        files = sorted(_DURATIONS) + ["tests/test_new_a.py", "tests/test_new_b.py"]
        items = _items(files)
        first = _shard(monkeypatch, items, 1, 2)
        assert _shard(monkeypatch, items, 1, 2) == first
        reordered = _shard(monkeypatch, list(reversed(items)), 1, 2)
        assert sorted(reordered) == sorted(first)

    def test_malformed_spec_is_still_a_usage_error(self, monkeypatch):
        monkeypatch.setenv("REVEAL_TEST_SHARD", "3/2")
        with pytest.raises(pytest.UsageError):
            conftest.pytest_collection_modifyitems(SimpleNamespace(), [])


class TestShardBalance:
    def test_recorded_cost_is_within_20_percent_across_two_shards(self, monkeypatch):
        items = _items(sorted(_DURATIONS))
        shards = [_shard(monkeypatch, items, i, 2) for i in (1, 2)]
        assert _imbalance(shards) <= 1.2

    def test_files_missing_from_the_record_are_spread_not_piled_on_one_shard(self, monkeypatch):
        new = [f"tests/test_unrecorded_{i}.py" for i in range(40)]
        items = _items(new, per_file=1)
        sizes = [len(_shard(monkeypatch, items, i, 2)) for i in (1, 2)]
        assert min(sizes) >= 12

    def test_the_balance_check_bites_on_a_skewed_split(self):
        # negative control: crc32 of the path, the old rule, on the recorded costs
        by_crc = [[], []]
        for name in _DURATIONS:
            by_crc[zlib.crc32(name.encode()) % 2].append(f"{name}::t")
        assert _imbalance(by_crc) > 1.2
