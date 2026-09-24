"""Regression tests for BACK-1082: a tree-sitter tree that exists but
contains ERROR node(s) (a partial/error-recovered parse, distinct from
`analyzer.tree is None` total failure already covered by BACK-982) must
still be treated as parse_failed -- otherwise I001 can report a used import
as unused, and worse, tell the caller to delete it.

Mirrors the mock pattern already used in test_go_imports_coverage.py /
test_js_imports_coverage.py for the `analyzer.tree is None` case; this
covers the newer `analyzer.has_parse_errors() is True` case those files
predate.

BACK-1460: a partial parse must still flag ``parse_failed`` but must NOT
discard the imports tree-sitter did recover -- returning nothing dropped every
edge from any file with an ERROR node out of depends:// / imports:// / I002.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reveal.analyzers.imports.generic import CImportExtractor
from reveal.analyzers.imports.python import PythonExtractor
from reveal.rules.imports.I001 import I001

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


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
            e.extract_imports(f)

        assert e.parse_failed is True

    def test_partial_parse_keeps_imports_before_error_region(self, tmp_path):
        """BACK-1460: imports outside the ERROR region survive, flagged parse_failed."""
        f = _write_py(tmp_path, 'broken.py', 'import os\nimport sys\ndef f(\n')

        e = PythonExtractor()
        result = e.extract_imports(f)

        assert e.parse_failed is True
        assert [s.module_name for s in result] == ['os', 'sys']

    def test_partial_parse_keeps_c_includes_before_error_region(self, tmp_path):
        """BACK-1460: the macro-heavy C shape (Redis/curl) that lost every #include."""
        f = tmp_path / 'broken.c'
        f.write_text('#include "util.h"\n#include <stdio.h>\n'
                     'int x = FOO(( ;\nstatic int LIST_HEAD(a) { }} }\n', encoding='utf-8')

        e = CImportExtractor()
        result = e.extract_imports(f)

        assert e.parse_failed is True
        assert [s.module_name for s in result] == ['util.h', 'stdio.h']

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


class TestDependsKeepsEdgesFromPartialParse:
    """BACK-1460 end-to-end: depends:// must report an importer whose
    #include sits before an ERROR region (Redis samples/c/src/util.h: 4 -> 11)."""

    def test_include_before_error_region_yields_dependent(self, tmp_path):
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()
        (tmp_path / 'util.h').write_text('int u(void);\n', encoding='utf-8')
        (tmp_path / 'clean.c').write_text('#include "util.h"\nint ok(void) { return 1; }\n',
                                          encoding='utf-8')
        (tmp_path / 'broken.c').write_text(
            '#include "util.h"\nint x = FOO(( ;\nstatic int LIST_HEAD(a) { }} }\n',
            encoding='utf-8')

        r = DependsAdapter(str(tmp_path / 'util.h')).get_structure()

        assert {Path(d['file']).name for d in r['dependents']} == {'clean.c', 'broken.c'}
