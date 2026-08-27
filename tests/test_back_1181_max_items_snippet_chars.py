"""Regression tests for BACK-1181: `reveal check` rejected --max-items and
--max-snippet-chars despite help://adapter-consistency / help://output-
diagnostics documenting them as "universal adapter options" -- in practice
they only worked for URI adapters, not the check subcommand.

Both flags cap what's RENDERED, never the true finding count: total_issues
(and thus the exit code) must still reflect reality even when --max-items
truncates the displayed detections, matching BACK-1186's "findings aren't
masked, only the exit code convention changes" principle.
"""

from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.rules.base import Detection, Severity

# BACK-1149: component/CLI-layer tests, in-process (no real subprocess)
pytestmark = pytest.mark.component

_B006_CODE = (
    "def foo():\n"
    "    try:\n"
    "        risky_operation()\n"
    "    except Exception as e:\n"
    "        pass\n"
)


def _write_py(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(code, encoding="utf-8")
    return p


class TestDetectionMaxSnippetChars:
    """Unit coverage of Detection.render()/to_dict()'s max_snippet_chars param."""

    def _detection(self):
        return Detection(
            file_path="a.py", line=4, rule_code="B006", message="msg",
            column=5, suggestion="fix it", context="except Exception as e:\n    pass",
            severity=Severity.MEDIUM,
        )

    def test_render_truncates_long_context(self):
        rendered = self._detection().render(max_snippet_chars=6)
        assert "except…" in rendered
        assert "except Exception as e:" not in rendered

    def test_render_leaves_short_context_untouched(self):
        rendered = self._detection().render(max_snippet_chars=1000)
        assert "except Exception as e:\n    pass" in rendered

    def test_to_dict_truncates_context(self):
        data = self._detection().to_dict(max_snippet_chars=6)
        assert data["context"] == "except…"

    def test_no_snippets_takes_priority_over_max_snippet_chars(self):
        data = self._detection().to_dict(no_snippets=True, max_snippet_chars=6)
        assert "context" not in data


class TestCheckMaxSnippetChars:
    def test_truncates_in_text_mode(self, tmp_path):
        f = _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(f), "--max-snippet-chars", "6")
        assert "except…" in result.stdout
        assert "except Exception as e:" not in result.stdout

    def test_truncates_in_json_mode(self, tmp_path):
        f = _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(f), "--format", "json", "--max-snippet-chars", "6")
        assert '"except\\u2026"' in result.stdout or "except…" in result.stdout

    def test_directory_mode_truncates(self, tmp_path):
        _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(tmp_path), "--max-snippet-chars", "6")
        assert "except…" in result.stdout
        assert "except Exception as e:" not in result.stdout


class TestCheckMaxItems:
    def test_single_file_caps_rendered_detections(self, tmp_path):
        f = _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(f), "--format", "json", "--max-items", "0")
        assert '"detections": []' in result.stdout
        assert '"total_available": 1' in result.stdout

    def test_directory_caps_rendered_but_not_total_issues(self, tmp_path):
        _write_py(tmp_path, "a.py", _B006_CODE)
        _write_py(tmp_path, "b.py", _B006_CODE)
        _write_py(tmp_path, "c.py", _B006_CODE)
        result = _run_reveal_direct(
            "check", str(tmp_path), "--format", "json", "--max-items", "2"
        )
        import json
        data = json.loads(result.stdout)
        rendered = sum(len(f["detections"]) for f in data["files"])
        assert data["summary"]["total_issues"] == 3
        assert rendered == 2
        assert data["summary"]["items_truncated"] is True

    def test_max_items_does_not_change_exit_code(self, tmp_path):
        """Findings must not be masked from the exit-code contract just
        because --max-items limited what's rendered."""
        _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct(
            "check", str(tmp_path), "--format", "json", "--max-items", "0"
        )
        assert result.returncode == 1

    def test_without_flag_is_unaffected(self, tmp_path):
        """Sanity check that --max-items is opt-in, not a behavior change."""
        _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(tmp_path), "--format", "json")
        import json
        data = json.loads(result.stdout)
        assert data["summary"].get("items_truncated") is False
