"""Regression tests for BACK-1182: `reveal check` had no way to omit the
embedded source-code excerpt (the 📝 line / JSON `context` field) from
violation output.

For a compliance-sensitive DD engagement where the source is confidential,
there was previously no way to get "which files/lines have which rule
violations" without also getting a fragment of real source.

--no-snippets omits the excerpt while keeping rule/file/line/severity/
suggestion intact, across all four paths that render it: single-file text,
single-file JSON, directory/batch text, directory/batch JSON.
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


class TestDetectionRenderNoSnippets:
    """Unit coverage of Detection.render()/to_dict()'s no_snippets param."""

    def _detection(self):
        return Detection(
            file_path="a.py", line=4, rule_code="B006", message="msg",
            column=5, suggestion="fix it", context="except Exception as e:\n    pass",
            severity=Severity.MEDIUM,
        )

    def test_render_default_includes_context(self):
        assert "📝" in self._detection().render()

    def test_render_no_snippets_omits_context(self):
        rendered = self._detection().render(no_snippets=True)
        assert "📝" not in rendered
        assert "except Exception" not in rendered

    def test_render_no_snippets_keeps_suggestion(self):
        assert "💡" in self._detection().render(no_snippets=True)

    def test_to_dict_default_includes_context_key(self):
        assert "context" in self._detection().to_dict()

    def test_to_dict_no_snippets_omits_context_key(self):
        assert "context" not in self._detection().to_dict(no_snippets=True)

    def test_str_is_unaffected_backward_compat(self):
        """Implicit str()/print(d) callers elsewhere must keep seeing context."""
        assert "📝" in str(self._detection())


class TestSingleFileNoSnippets:
    def test_text_default_shows_snippet(self, tmp_path):
        f = _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(f))
        assert "📝" in result.stdout

    def test_text_no_snippets_hides_snippet(self, tmp_path):
        f = _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(f), "--no-snippets")
        assert "📝" not in result.stdout
        assert "B006" in result.stdout

    def test_json_default_includes_context_key(self, tmp_path):
        f = _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(f), "--format", "json")
        assert '"context"' in result.stdout

    def test_json_no_snippets_omits_context_key(self, tmp_path):
        f = _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(f), "--format", "json", "--no-snippets")
        assert '"context"' not in result.stdout
        assert '"B006"' in result.stdout


class TestDirectoryNoSnippets:
    def test_text_no_snippets_hides_snippet(self, tmp_path):
        _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(tmp_path), "--no-snippets")
        assert "📝" not in result.stdout
        assert "B006" in result.stdout

    def test_json_no_snippets_omits_context_key(self, tmp_path):
        _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(tmp_path), "--format", "json", "--no-snippets")
        assert '"context"' not in result.stdout
        assert '"B006"' in result.stdout

    def test_json_default_includes_context_key(self, tmp_path):
        """Sanity check that --no-snippets is opt-in, not a behavior change."""
        _write_py(tmp_path, "bad.py", _B006_CODE)
        result = _run_reveal_direct("check", str(tmp_path), "--format", "json")
        assert '"context"' in result.stdout
