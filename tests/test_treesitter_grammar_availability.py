"""BACK-979: tree-sitter grammar download failures must be visible, not silent.

Covers reveal/treesitter.py's _parse_tree(): a proactive warning when a
grammar hasn't been downloaded yet (before the network fetch it triggers),
and a reactive warning (upgraded from debug) when get_parser()/ts_parse()
raises. Both warnings are process-deduped per language so a directory scan
doesn't spam one line per file.
"""

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

import reveal.treesitter as ts
from reveal.analyzers.python import PythonAnalyzer

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


class TestGrammarAvailabilityWarnings(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.py_file = Path(self.temp_dir) / "test.py"
        self.py_file.write_text("def hello():\n    pass\n")
        # A second, distinct file/content so the dedup tests exercise the
        # per-language warning set, not treesitter.py's separate
        # (path, mtime_ns) parse cache short-circuiting the second parse.
        self.py_file2 = Path(self.temp_dir) / "test2.py"
        self.py_file2.write_text("def goodbye():\n    pass\n")
        ts._warned_uncached_languages.clear()
        ts._warned_failed_languages.clear()
        ts._get_parse_cache().clear()

    def test_uncached_language_warns_before_fetch(self):
        with patch.object(ts, "downloaded_languages", return_value=[]):
            with self.assertLogs("reveal.treesitter", level="WARNING") as cm:
                analyzer = PythonAnalyzer(str(self.py_file))
                self.assertIsNotNone(analyzer.tree)  # grammar is actually cached, parse still succeeds

        self.assertTrue(any("not yet downloaded" in msg for msg in cm.output))

    def test_uncached_language_warning_dedups_per_language(self):
        with patch.object(ts, "downloaded_languages", return_value=[]):
            with self.assertLogs("reveal.treesitter", level="WARNING") as cm:
                _ = PythonAnalyzer(str(self.py_file)).tree  # .tree triggers the lazy parse
                _ = PythonAnalyzer(str(self.py_file2)).tree

        warn_count = sum(1 for msg in cm.output if "not yet downloaded" in msg)
        self.assertEqual(warn_count, 1)

    def test_cached_language_does_not_warn(self):
        with patch.object(ts, "downloaded_languages", return_value=["python"]):
            with self.assertNoLogs("reveal.treesitter", level="WARNING"):
                analyzer = PythonAnalyzer(str(self.py_file))
                self.assertIsNotNone(analyzer.tree)

    def test_parse_failure_surfaces_as_warning_and_sets_parse_error(self):
        with patch.object(ts, "get_parser", side_effect=RuntimeError("Download error: no network")):
            with self.assertLogs("reveal.treesitter", level="WARNING") as cm:
                analyzer = PythonAnalyzer(str(self.py_file))
                self.assertIsNone(analyzer.tree)
                self.assertEqual(analyzer.parse_error, "Download error: no network")

        self.assertTrue(any("parse failed" in msg for msg in cm.output))

    def test_parse_failure_warning_dedups_per_language(self):
        with patch.object(ts, "get_parser", side_effect=RuntimeError("Download error: no network")):
            with self.assertLogs("reveal.treesitter", level="WARNING") as cm:
                _ = PythonAnalyzer(str(self.py_file)).tree
                _ = PythonAnalyzer(str(self.py_file2)).tree

        warn_count = sum(1 for msg in cm.output if "parse failed" in msg)
        self.assertEqual(warn_count, 1)


if __name__ == "__main__":
    unittest.main()
