"""scripts/profile_multiplicity.py (BACK-1877): flags per-unit duplicates from a cProfile dump.

The cases are the ones it was written for: a per-file artifact built twice (BACK-1868's
get_structure at 2.00/file) is listed and flagged x2 with its callers; the same code after
the fix (one build) is not listed at all.
"""

import cProfile
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "profile_multiplicity.py"
_spec = importlib.util.spec_from_file_location("profile_multiplicity", SCRIPT)
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)

UNITS = 30


def _build_structure(unit):
    return [unit] * 3


def _collector_a(unit):
    return _build_structure(unit)


def _collector_b(unit):
    return _build_structure(unit)


def _per_item_work(unit):
    return sum(range(5))


def _run_duplicating():
    for unit in range(UNITS):
        _collector_a(unit)
        _collector_b(unit)      # the second, redundant collector
        for _ in range(4):
            _per_item_work(unit)


def _run_fixed():
    for unit in range(UNITS):
        structures = _collector_a(unit)
        assert structures
        for _ in range(4):
            _per_item_work(unit)


def _profile(tmp_path, fn, name):
    path = tmp_path / name
    profiler = cProfile.Profile()
    profiler.runcall(fn)
    profiler.dump_stats(str(path))
    return path


def _rows(profile_path, **kwargs):
    import pstats
    stats = pstats.Stats(str(profile_path))
    kwargs.setdefault('min_calls', 5)
    kwargs.setdefault('only', [Path(__file__).name])
    return pm.analyze(stats.stats, UNITS, stats.total_tt, **kwargs)


def test_duplicate_per_unit_is_flagged_with_both_callers(tmp_path):
    rows = {r['function'].split(' ')[-1]: r for r in _rows(_profile(tmp_path, _run_duplicating, 'dup.prof'))}
    build = rows['_build_structure']
    assert (build['per_unit'], build['duplicate_of'], build['ncalls']) == (2.0, 2, 2 * UNITS)
    assert {c['caller'].split(' ')[-1] for c in build['callers']} == {'_collector_a', '_collector_b'}
    assert all(c['per_unit'] == 1.0 for c in build['callers'])


def test_single_pass_is_not_listed_negative_control(tmp_path):
    names = {r['function'].split(' ')[-1] for r in _rows(_profile(tmp_path, _run_fixed, 'fixed.prof'))}
    assert '_build_structure' not in names and '_collector_a' not in names
    assert '_per_item_work' in names                      # 4/unit is listed ...
    row = next(r for r in _rows(_profile(tmp_path, _run_fixed, 'fixed2.prof'))
               if r['function'].endswith('_per_item_work'))
    assert row['duplicate_of'] == 4                       # ... and is a clean multiple, so flagged x4


def test_large_whole_number_ratio_is_not_flagged():
    assert pm._integer_like(2.0) == 2
    assert pm._integer_like(2.04) == 2
    assert pm._integer_like(2.3) is None
    assert pm._integer_like(94.0) is None                 # coincidence above INTEGER_MAX
    assert pm._integer_like(1.0) is None


def test_units_must_be_positive():
    with pytest.raises(ValueError):
        pm.analyze({}, 0, 1.0)


def _cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding='utf-8', timeout=60)


def test_cli_text_json_and_units_from(tmp_path):
    prof = _profile(tmp_path, _run_duplicating, 'cli.prof')
    text = _cli(str(prof), '--units', str(UNITS), '--only', Path(__file__).name, '--min-calls', '5')
    assert text.returncode == 0 and 'x2' in text.stdout and '_build_structure' in text.stdout
    data = json.loads(_cli(str(prof), '--units-from', '_collector_a', '--only', Path(__file__).name,
                           '--min-calls', '5', '--json').stdout)
    assert data['units'] == UNITS
    assert any(r['function'].endswith('_build_structure') and r['duplicate_of'] == 2 for r in data['rows'])


def test_cli_rejects_a_missing_profile_and_zero_units(tmp_path):
    missing = _cli(str(tmp_path / 'nope.prof'), '--units', '10')
    assert missing.returncode == 2 and 'cannot read' in missing.stderr
    prof = _profile(tmp_path, _run_duplicating, 'z.prof')
    nothing = _cli(str(prof), '--units-from', 'no_such_function_anywhere')
    assert nothing.returncode == 2 and 'no units' in nothing.stderr
