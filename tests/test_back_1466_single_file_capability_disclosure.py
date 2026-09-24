"""Regression tests for BACK-1466: single-file `reveal check <file>` printed a
plain "✅ No issues found" for a language that I001/T006 do not check, while
recursive `reveal check <dir>` over the same file already disclosed the gap
(W-CAP-1 for T006, W-CAP-2 for I001). The MCP `reveal_check` tool had the same
bare "No issues found." for files and directories alike.

Same class, fixed alongside: `reveal deps --no-circular` rendered the skipped
check's empty result as "✅ no circular deps", and `--no-unused` still printed
the per-language "Unused imports not checked" note.
"""

import argparse
import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

JAVA = "import java.util.List;\nimport java.io.File;\npublic class A { }\n"


def _check(path: Path, fmt: str, capsys, select=None) -> str:
    from reveal.checks import run_pattern_detection
    from reveal.registry import get_analyzer
    analyzer = get_analyzer(str(path))(str(path))
    args = argparse.Namespace(select=select, ignore=None, no_group=False, severity=None)
    run_pattern_detection(analyzer, str(path), fmt, args)
    return capsys.readouterr().out


@pytest.fixture
def java_file(tmp_path):
    p = tmp_path / "A.java"
    p.write_text(JAVA, encoding="utf-8")
    return p


class TestSingleFileCheck:

    def test_text_discloses_i001_and_t006_before_the_verdict(self, java_file, capsys):
        out = _check(java_file, "text", capsys)
        lines = out.splitlines()
        verdict = next(i for i, line in enumerate(lines) if "No issues found" in line)
        w_cap_2 = next(i for i, line in enumerate(lines) if "W-CAP-2" in line)
        w_cap_1 = next(i for i, line in enumerate(lines) if "W-CAP-1" in line)
        assert w_cap_1 < verdict and w_cap_2 < verdict
        assert ".java (1)" in lines[w_cap_2]

    def test_json_carries_scan_disclosures(self, java_file, capsys):
        doc = json.loads(_check(java_file, "json", capsys))
        assert doc["total"] == 0
        assert any("W-CAP-2" in d for d in doc["scan_disclosures"])

    def test_python_file_has_empty_disclosures(self, tmp_path, capsys):
        p = tmp_path / "clean.py"
        p.write_text("def foo():\n    pass\n", encoding="utf-8")
        doc = json.loads(_check(p, "json", capsys))
        assert doc["scan_disclosures"] == []

    def test_rules_outside_the_selection_are_not_disclosed(self, java_file, capsys):
        out = _check(java_file, "text", capsys, select="C901")
        assert "W-CAP" not in out
        assert "No issues found" in out


class TestMcpRevealCheck:

    def test_file_result_carries_disclosures(self, java_file):
        from reveal.mcp_server import reveal_check
        out = reveal_check(str(java_file))
        assert "W-CAP-2" in out and out.rstrip().endswith("No issues found.")

    def test_directory_result_carries_disclosures(self, java_file):
        from reveal.mcp_server import reveal_check
        assert "W-CAP-2" in reveal_check(str(java_file.parent))

    def test_python_file_stays_a_plain_no_issues(self, tmp_path):
        from reveal.mcp_server import reveal_check
        p = tmp_path / "clean.py"
        p.write_text("def foo():\n    pass\n", encoding="utf-8")
        assert reveal_check(str(p)) == "No issues found."

    def test_unparseable_file_is_not_reported_clean(self, tmp_path):
        from reveal.mcp_server import reveal_check
        p = tmp_path / "broken.py"
        p.write_text("def f(:\n    pass\n", encoding="utf-8")
        assert "did not parse cleanly" in reveal_check(str(p))


class TestDepsSkippedChecks:

    @staticmethod
    def _render(report):
        from reveal.adapters.deps import _render_deps
        buf = StringIO()
        with patch("sys.stdout", buf):
            _render_deps(report, top=10)
        return buf.getvalue()

    @staticmethod
    def _report(**kw):
        report = {
            "path": ".",
            "base": {"files": {"a.py": [{"module": "b"}]},
                     "metadata": {"unused_not_checked_extensions": {".java": 1}}},
            "circular": {},
            "unused": [],
            "skipped": [],
        }
        report.update(kw)
        return report

    def test_no_circular_is_not_rendered_as_clean(self):
        out = self._render(self._report(skipped=["circular"]))
        assert "no circular deps" not in out.replace("circular deps not checked", "")
        assert "circular deps not checked" in out

    def test_no_unused_drops_the_per_language_note(self):
        out = self._render(self._report(skipped=["unused"]))
        assert "Unused imports not checked" not in out
        assert "unused imports not checked (--no-unused)" in out

    def test_default_run_keeps_the_per_language_note(self):
        assert "Unused imports not checked" in self._render(self._report())

    def test_adapter_records_skipped_checks(self, tmp_path):
        from reveal.adapters.deps import DepsAdapter
        (tmp_path / "a.py").write_text("import os\n", encoding="utf-8")
        result = DepsAdapter(str(tmp_path), "no_unused=false&no_circular=true").get_structure()
        assert result["skipped"] == ["circular"]
