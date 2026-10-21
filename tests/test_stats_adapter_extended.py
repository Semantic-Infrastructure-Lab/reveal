"""Extended test coverage for reveal.adapters.stats.adapter module.

Targets remaining uncovered exception handlers:
- Line 247-249: parse_query_filters exception fallback
- Line 302-303: sorting TypeError/KeyError fallback
"""

import logging
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from conftest import needs_forked_workers
from reveal.adapters.stats.adapter import StatsAdapter

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


class TestStatsAdapterExceptionHandling:
    """Test exception handling in StatsAdapter."""

    def test_query_filter_parsing_failure_fails_the_query(self):
        """parse_query_filters exception fails the query (BACK-1059): empty filters would
        answer a filtered query with the unfiltered result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal test directory
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("print('hello')\n")

            # Mock parse_query_filters to raise exception
            with patch('reveal.adapters.stats.adapter.parse_query_filters') as mock_parse:
                mock_parse.side_effect = ValueError("Invalid filter syntax")

                with pytest.raises(ValueError, match="Invalid filter syntax"):
                    StatsAdapter(tmpdir, query="lines>5")

    def test_sorting_type_error_fallback(self):
        """Sorting TypeError should fall back to unsorted list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file1 = Path(tmpdir) / "test1.py"
            test_file1.write_text("def foo():\n    pass\n")

            test_file2 = Path(tmpdir) / "test2.py"
            test_file2.write_text("def bar():\n    pass\n")

            # Request sorting by a field that doesn't exist or causes TypeError
            adapter = StatsAdapter(tmpdir, query="sort=nonexistent_field")

            # Should not raise exception
            result = adapter.get_structure()
            assert 'files' in result

    def test_sorting_key_error_fallback(self):
        """Values that don't compare leave the list unsorted instead of raising."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ("a.py", "b.py"):
                (Path(tmpdir) / name).write_text("def foo():\n    pass\n")

            # field_value returns None for a missing field (BACK-1644 warns about that);
            # a str and an int under one field is what makes the sort itself fail.
            values = iter(["x", 1, "x", 1])
            with patch('reveal.adapters.stats.adapter.field_value',
                       side_effect=lambda stats, field: next(values, 1)):

                adapter = StatsAdapter(tmpdir, query="sort=lines")

                # Should not raise exception
                result = adapter.get_structure()
                assert 'files' in result


class TestI002GraphCachePreload:
    """BACK-531, reversed by BACK-1884: stats' pool no longer builds the I002 import graph.

    BACK-531 made `overview`/`stats://` log the BACK-338 root-mis-detection warning once, not
    once per ProcessPoolExecutor worker, by building the graph in the parent and seeding every
    worker (reveal/rules/scan_caches.py, BACK-1429). The issue count is file-local now and I002
    reads the whole project, so stats never asks for it: the graph is built nowhere (parent or
    worker) and the warning is logged zero times. The preload table still serves `check`
    (TestI002Preload and siblings in test_file_checker.py).
    """

    @needs_forked_workers  # the patched _find_project_root and caplog see forked workers only
    @pytest.mark.real_worker_pool
    def test_stats_pool_builds_no_import_graph_and_logs_no_ceiling_warning(self, tmp_path, monkeypatch, caplog):
        """Same fixture as BACK-531's regression (a project with no I002 markers, enough files for
        the multi-worker path, the ceiling forced to trip), now asserting the opposite: no worker
        and not the parent builds a graph, so there is no ceiling warning to repeat or to log once.
        """
        from reveal.rules.imports import I002 as i002_module

        monkeypatch.setenv("REVEAL_I002_MAX_FILES", "1")
        roots_asked = []

        def find_root(path):
            roots_asked.append(path)
            return tmp_path

        monkeypatch.setattr(i002_module, "_find_project_root", find_root)
        i002_module._graph_cache.clear()

        # >20 files so _collect_filtered_stats picks workers > 1 (workers = len//10).
        for i in range(25):
            (tmp_path / f"mod_{i}.py").write_text(f"def f_{i}():\n    return {i}\n")

        caplog.set_level(logging.WARNING, logger="reveal.rules.imports.I002")
        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()
        assert 'files' in result

        occurrences = sum(1 for r in caplog.records if "import-graph scan" in r.message)
        assert occurrences == 0, f"expected no ceiling warning, got {occurrences}"
        assert roots_asked == [] and i002_module._graph_cache == {}, "I002 was consulted by stats"
        assert 'analysis_incomplete' not in [w.get('type') for w in result.get('meta', {}).get('warnings', [])]


class TestStatsAdapterWorkerOverride:
    """BACK-1004: stats/adapter.py's worker pool was the only uncapped,
    unconfigurable parallelism reachable from `overview` — hardcoded
    `workers = min(8, files//10)` with no way to cap it, unlike
    adapters/imports.py's REVEAL_MAX_WORKERS. Running multiple full-repo
    scans concurrently on one machine could blow past timeouts even though
    each is fast in isolation."""

    def test_max_workers_env_forces_serial_path(self, tmp_path, monkeypatch):
        """REVEAL_MAX_WORKERS=1 must skip ProcessPoolExecutor entirely, even
        with enough files that the default heuristic would use a pool."""
        # >20 files so the default (unset) heuristic would pick workers > 1.
        for i in range(25):
            (tmp_path / f"mod_{i}.py").write_text(f"def f_{i}():\n    return {i}\n")

        monkeypatch.setenv("REVEAL_MAX_WORKERS", "1")

        with patch('concurrent.futures.ProcessPoolExecutor') as mock_pool:
            adapter = StatsAdapter(str(tmp_path))
            result = adapter.get_structure()

        mock_pool.assert_not_called()
        assert result['summary']['total_files'] == 25

    def test_max_workers_env_overrides_default_heuristic(self, tmp_path, monkeypatch):
        """A valid override wins even when it differs from the file-count heuristic."""
        for i in range(25):
            (tmp_path / f"mod_{i}.py").write_text(f"def f_{i}():\n    return {i}\n")

        monkeypatch.setenv("REVEAL_MAX_WORKERS", "3")

        real_executor = __import__('concurrent.futures', fromlist=['ProcessPoolExecutor']).ProcessPoolExecutor
        captured = {}

        def spy_executor(*args, **kwargs):
            captured['max_workers'] = kwargs.get('max_workers')
            return real_executor(*args, **kwargs)

        with patch('concurrent.futures.ProcessPoolExecutor', side_effect=spy_executor):
            adapter = StatsAdapter(str(tmp_path))
            adapter.get_structure()

        assert captured['max_workers'] == 3

    def test_invalid_max_workers_env_falls_back_to_heuristic(self, tmp_path, monkeypatch):
        """A non-numeric override must not crash — falls back to the default heuristic."""
        for i in range(25):
            (tmp_path / f"mod_{i}.py").write_text(f"def f_{i}():\n    return {i}\n")

        monkeypatch.setenv("REVEAL_MAX_WORKERS", "not-a-number")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()

        assert result['summary']['total_files'] == 25


class TestStatsAdapterSummaryOnly:
    """BACK-1008: an unscoped stats:// call over a large repo returns one
    entry per file, dwarfing the aggregate 'summary' block that's usually
    the actual signal wanted. summary_only=True (or ?summary_only=true)
    keeps the full-corpus walk (needed for the aggregate/hotspots) but
    drops the bulky per-file 'files' array from the output."""

    def test_summary_only_drops_files_key_for_directory(self, tmp_path):
        (tmp_path / "a.py").write_text("def f():\n    pass\n")
        (tmp_path / "b.py").write_text("def g():\n    pass\n")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(summary_only=True)

        assert 'files' not in result
        assert result['summary']['total_files'] == 2

    def test_summary_only_false_by_default(self, tmp_path):
        (tmp_path / "a.py").write_text("def f():\n    pass\n")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()

        assert 'files' in result

    def test_summary_only_via_query_param(self, tmp_path):
        (tmp_path / "a.py").write_text("def f():\n    pass\n")

        adapter = StatsAdapter(str(tmp_path), query="summary_only=true")
        result = adapter.get_structure()

        assert 'files' not in result
        assert result['summary']['total_files'] == 1

    def test_summary_only_keeps_hotspots(self, tmp_path):
        (tmp_path / "a.py").write_text("def f():\n    pass\n")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(summary_only=True, hotspots=True)

        assert 'files' not in result
        assert 'hotspots' in result

    def test_summary_only_drops_files_key_for_single_file(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("def f():\n    pass\n")

        adapter = StatsAdapter(str(f))
        result = adapter.get_structure(summary_only=True)

        assert 'files' not in result
        assert result['summary']['total_files'] == 1
