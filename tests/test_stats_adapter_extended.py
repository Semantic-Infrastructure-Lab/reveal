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
from reveal.adapters.stats.adapter import StatsAdapter, _i002_preload, _i002_init_worker


class TestStatsAdapterExceptionHandling:
    """Test exception handling in StatsAdapter."""

    def test_query_filter_parsing_exception_fallback(self):
        """parse_query_filters exception should fall back to empty filters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal test directory
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("print('hello')\n")

            # Mock parse_query_filters to raise exception
            with patch('reveal.adapters.stats.adapter.parse_query_filters') as mock_parse:
                mock_parse.side_effect = ValueError("Invalid filter syntax")

                # Should not raise exception - should fall back to empty filters
                adapter = StatsAdapter(tmpdir, query_string="lines>5")
                assert adapter.query_filters == []

    def test_sorting_type_error_fallback(self):
        """Sorting TypeError should fall back to unsorted list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file1 = Path(tmpdir) / "test1.py"
            test_file1.write_text("def foo():\n    pass\n")

            test_file2 = Path(tmpdir) / "test2.py"
            test_file2.write_text("def bar():\n    pass\n")

            # Request sorting by a field that doesn't exist or causes TypeError
            adapter = StatsAdapter(tmpdir, query_string="sort=nonexistent_field")

            # Should not raise exception
            result = adapter.get_structure()
            assert 'files' in result

    def test_sorting_key_error_fallback(self):
        """Sorting KeyError should fall back to unsorted list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo():\n    pass\n")

            # Mock field_value to raise KeyError
            with patch('reveal.adapters.stats.adapter.field_value') as mock_field:
                mock_field.side_effect = KeyError("Field not found")

                adapter = StatsAdapter(tmpdir, query_string="sort=lines")

                # Should not raise exception
                result = adapter.get_structure()
                assert 'files' in result


class TestI002GraphCachePreload:
    """BACK-531: I002's per-worker cold cache made `overview`/`stats://` log the
    BACK-338 root-mis-detection warning once per ProcessPoolExecutor worker (up
    to 8x for one command). _i002_preload/_i002_init_worker mirror
    cli/file_checker.py's pattern: build the graph once in the main process and
    seed it into every worker via the pool initializer.
    """

    def test_init_worker_populates_cache(self, tmp_path):
        """_i002_init_worker seeds the I002 module-level cache."""
        from reveal.rules.imports.I002 import _graph_cache
        fake_root = tmp_path
        fake_graph = object()
        try:
            _i002_init_worker({fake_root: fake_graph})
            assert _graph_cache.get(fake_root) is fake_graph
        finally:
            _graph_cache.pop(fake_root, None)

    def test_init_worker_noop_on_empty_cache(self):
        """_i002_init_worker does nothing when called with empty dict."""
        # Should not raise
        _i002_init_worker({})

    def test_init_worker_survives_import_error(self):
        """_i002_init_worker silently ignores import errors."""
        with patch("reveal.adapters.stats.adapter._i002_init_worker", wraps=_i002_init_worker):
            with patch.dict("sys.modules", {"reveal.rules.imports.I002": None}):
                _i002_init_worker({"x": "y"})  # must not raise

    def test_preload_survives_missing_module(self, tmp_path):
        """_i002_preload returns {} instead of raising if I002 can't be imported."""
        with patch.dict("sys.modules", {"reveal.rules.imports.I002": None}):
            result = _i002_preload(tmp_path)
            assert result == {}

    def test_root_mis_detection_warning_logged_once_across_workers(self, tmp_path, monkeypatch, caplog):
        """End-to-end BACK-531 regression: a project with no I002 project markers
        and enough files to trigger the multi-worker path must log the BACK-338
        ceiling warning exactly once, not once per worker.

        Pre-fix, reveal.adapters.stats.adapter's ProcessPoolExecutor had no I002
        cache preload/initializer, so each cold forked worker independently
        rebuilt the graph and re-logged the ceiling warning (up to 8x for one
        `overview`/`stats://` invocation). Runs the real ProcessPoolExecutor
        (workers=2, forked) via StatsAdapter rather than mocking it, so this
        would have caught the pre-fix duplication: on Linux's fork start
        method, a forked child copies the parent's logging config, so a
        per-worker warning is visible to caplog exactly like a main-process one.
        """
        from reveal.rules.imports import I002 as i002_module

        # Force the ceiling to trip well below our 25-file fixture (0/negative
        # values are rejected by _max_graph_files and fall back to the 20000
        # default, so use the smallest valid positive override instead).
        monkeypatch.setenv("REVEAL_I002_MAX_FILES", "1")
        # Force every file's "project root" to resolve to the same tmp_path so
        # all workers share one cache key (matches the real mis-detection case,
        # where an un-marked language walks up to one shared, wrong root).
        monkeypatch.setattr(i002_module, "_find_project_root", lambda path: tmp_path)
        i002_module._graph_cache.clear()

        # >20 files so _collect_filtered_stats picks workers > 1 (workers = len//10).
        for i in range(25):
            (tmp_path / f"mod_{i}.py").write_text(f"def f_{i}():\n    return {i}\n")

        caplog.set_level(logging.WARNING, logger="reveal.rules.imports.I002")
        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()
        assert 'files' in result

        occurrences = sum(1 for r in caplog.records if "import-graph scan" in r.message)
        assert occurrences == 1, (
            f"expected exactly 1 ceiling warning, got {occurrences}"
        )
