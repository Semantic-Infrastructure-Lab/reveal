"""Regression tests for BACK-1082: a tree-sitter tree that exists but
contains ERROR node(s) (a partial/error-recovered parse, distinct from
`analyzer.tree is None` total failure already covered by BACK-982) must
still be treated as parse_failed -- otherwise I001 can report a used import
as unused, and worse, tell the caller to delete it.

Mirrors the mock pattern already used in test_go_imports_coverage.py /
test_js_imports_coverage.py for the `analyzer.tree is None` case; this
covers the newer `analyzer.has_parse_errors() is True` case those files
predate.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.analyzers.imports.python import PythonExtractor
from reveal.rules.imports.I001 import I001


def _write_py(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(code, encoding='utf-8')
    return p


class TestGetTreeAnalyzerErrorRecovery:
    """Direct coverage of the _get_tree_analyzer() branch added for BACK-1082."""

    def test_tree_with_error_nodes_marks_parse_failed(self, tmp_path):
        f = _write_py(tmp_path, 'x.py', 'import os\n')
        mock_analyzer = MagicMock()
        mock_analyzer.tree = MagicMock()  # truthy -- NOT the BACK-982 total-failure case
        mock_analyzer.has_parse_errors.return_value = True
        mock_cls = MagicMock(return_value=mock_analyzer)

        e = PythonExtractor()
        with patch('reveal.analyzers.imports.base.get_analyzer', return_value=mock_cls):
            result = e.extract_imports(f)

        assert result == []
        assert e.parse_failed is True

    def test_tree_without_error_nodes_parses_normally(self, tmp_path):
        """Sanity check the new branch doesn't fire on a clean tree."""
        f = _write_py(tmp_path, 'clean.py', 'import os\nprint(os.getcwd())\n')

        e = PythonExtractor()
        result = e.extract_imports(f)

        assert e.parse_failed is False
        assert [s.module_name for s in result] == ['os']


class TestI001SkipsPartialParse:
    """End-to-end: I001.check() must not flag an import as unused when the
    file's parse was only partially recovered (had ERROR nodes) -- the
    exact false-positive-with-harmful-remediation shape BACK-1082 reports."""

    def test_error_recovered_file_produces_no_false_positive(self, tmp_path):
        # Content is irrelevant here -- the mocked analyzer controls what
        # extract_imports/extract_symbols see, exercising the parse_failed
        # skip-and-warn guard in I001.check() (I001.py:221-227) directly,
        # the same way BACK-982's fix is covered for the total-failure case.
        f = _write_py(tmp_path, 'broken.py', 'import os\nimport sys\ndef f(\n')

        mock_analyzer = MagicMock()
        mock_analyzer.tree = MagicMock()
        mock_analyzer.has_parse_errors.return_value = True
        mock_cls = MagicMock(return_value=mock_analyzer)

        rule = I001()
        with patch('reveal.analyzers.imports.base.get_analyzer', return_value=mock_cls):
            detections = rule.check(str(f), None, f.read_text())

        assert detections == [], (
            "I001 must skip (not flag-as-unused) an import from a file whose "
            "parse only partially recovered -- the usage scan behind the "
            "'unused' verdict is unreliable, not confirmed empty (BACK-1082)"
        )
