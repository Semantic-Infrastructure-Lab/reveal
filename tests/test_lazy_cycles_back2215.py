"""Lazy-import cycle ratchet for reveal's own package (BACK-2215, scripts/check_lazy_cycles.py).

The load-time graph of reveal has no cycles; cycles close only through function-level
imports, and nothing stopped a new one (one deferred import grew the largest group from
99 to 155 files). These tests hold the committed baseline and prove the measurement sees
a lazy cycle at all (positive control) and ignores a load-time-only package.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    'check_lazy_cycles', Path(__file__).resolve().parent.parent / 'scripts' / 'check_lazy_cycles.py')
lc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lc)


def _package(root: Path, files: dict) -> Path:
    pkg = root / 'pkg'
    pkg.mkdir()
    (pkg / '__init__.py').write_text('', encoding='utf-8')
    for name, body in files.items():
        (pkg / name).write_text(body, encoding='utf-8')
    return pkg


@pytest.mark.scans_checkout  # reveal's own graph resolves at the checkout root, as imports://reveal does
def test_reveal_adds_no_lazy_import_cycle():
    files, edges = lc.measure()
    base_files, base_edges = lc.load_baseline()
    assert lc.compare(files, edges, base_files, base_edges) == []


def test_a_deferred_back_import_is_a_lazy_cycle_edge(tmp_path):
    pkg = _package(tmp_path, {
        'low.py': 'def helper():\n    from .high import top  # deferred upward import\n    return top()\n',
        'high.py': 'from .low import helper\n\n\ndef top():\n    return helper\n',
    })
    files, edges = lc.measure(pkg, tmp_path)
    assert files == 2
    assert edges == {('pkg/low.py', 'pkg/high.py')}  # the load-time edge high -> low is not listed


def test_a_load_time_only_package_has_no_lazy_cycle(tmp_path):
    pkg = _package(tmp_path, {
        'low.py': 'def helper():\n    return 1\n',
        'high.py': 'from .low import helper\n\n\ndef top():\n    from .low import helper as h  # lazy, but downward\n    return h()\n',
    })
    assert lc.measure(pkg, tmp_path) == (0, set())


def test_compare_names_a_new_edge_a_rise_and_a_stale_list():
    base = {('a.py', 'b.py')}
    assert lc.compare(2, base, 2, base) == []
    rose = lc.compare(3, base | {('c.py', 'd.py')}, 2, base)
    assert any('rose: 2 -> 3' in p for p in rose)
    assert any('1 lazy import edge(s) now inside a cycle group' in p for p in rose)
    assert any(p.strip() == 'c.py -> d.py' for p in rose)
    stale = lc.compare(0, set(), 2, base)
    assert len(stale) == 1 and 'baseline is stale (1 listed edge(s)' in stale[0]
