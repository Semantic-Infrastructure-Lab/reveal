"""Tests for the public Python SDK (reveal.api).

Covers: structure(), element(), query(), check()
"""
import textwrap
from pathlib import Path

import pytest

import reveal
from reveal.api import analyze, check, element, query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path: Path, name: str, src: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(src))
    return p


# ---------------------------------------------------------------------------
# analyze()
# ---------------------------------------------------------------------------

class TestAnalyze:
    def test_contains_function(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", """\
            def greet(name):
                return f"Hello, {name}"
        """)
        result = analyze(str(f))
        # Collect all names across all list-valued sections (keys vary by analyzer)
        all_names = [
            item.get("name", "")
            for items in result.values()
            if isinstance(items, list)
            for item in items
            if isinstance(item, dict)
        ]
        assert "greet" in all_names

    def test_contains_class(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", """\
            class Foo:
                pass
        """)
        result = analyze(str(f))
        all_names = [
            item.get("name", "")
            for items in result.values()
            if isinstance(items, list)
            for item in items
            if isinstance(item, dict)
        ]
        assert "Foo" in all_names

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            analyze("/no/such/file.py")

    def test_no_analyzer_raises(self, tmp_path):
        f = tmp_path / "data.unknownext12345"
        f.write_text("nothing")
        with pytest.raises(ValueError, match="No analyzer available"):
            analyze(str(f))


# ---------------------------------------------------------------------------
# element()
# ---------------------------------------------------------------------------

class TestElement:
    def test_returns_function_source(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", """\
            def add(a, b):
                return a + b
        """)
        result = element(str(f), "add")
        assert result is not None
        assert "add" in result.get("source", "")

    def test_returns_none_for_missing_element(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", "x = 1\n")
        result = element(str(f), "nonexistent_function_xyz")
        assert result is None

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            element("/no/such/file.py", "foo")

    def test_no_analyzer_raises(self, tmp_path):
        f = tmp_path / "data.unknownext12345"
        f.write_text("nothing")
        with pytest.raises(ValueError, match="No analyzer available"):
            element(str(f), "foo")


# ---------------------------------------------------------------------------
# query()
# ---------------------------------------------------------------------------

class TestQuery:
    def test_ast_uri_returns_dict(self, tmp_path):
        _write_py(tmp_path, "mod.py", """\
            def foo():
                pass
            class Bar:
                pass
        """)
        result = query(f"ast://{tmp_path}/")
        assert isinstance(result, dict)

    def test_invalid_uri_raises(self):
        with pytest.raises(ValueError, match="missing scheme"):
            query("not-a-uri")

    def test_unsupported_scheme_raises(self):
        with pytest.raises(ValueError, match="Unsupported URI scheme"):
            query("xyzscheme://something")

    def test_env_uri(self):
        """env:// adapter returns a dict containing real env vars."""
        result = query("env://")
        assert isinstance(result, dict)
        assert len(result) > 0  # must surface actual environment content


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------

class TestCheck:
    def test_returns_list(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", "x = 1\n")
        result = check(str(f))
        assert isinstance(result, list)

    def test_detects_long_line(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", "x = " + "a" * 120 + "\n")
        result = check(str(f), select=["E501"])
        codes = [d.rule_code for d in result]
        assert "E501" in codes

    def test_select_filters_rules(self, tmp_path):
        # A very long line should trigger E501 but not appear when selecting C
        f = _write_py(tmp_path, "mod.py", "x = " + "a" * 120 + "\n")
        result = check(str(f), select=["C"])
        codes = [d.rule_code for d in result]
        assert "E501" not in codes

    def test_ignore_suppresses_rule(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", "x = " + "a" * 120 + "\n")
        result = check(str(f), ignore=["E501"])
        codes = [d.rule_code for d in result]
        assert "E501" not in codes

    def test_detection_has_expected_attrs(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", "x = " + "a" * 120 + "\n")
        result = check(str(f), select=["E501"])
        assert result  # at least one detection
        d = result[0]
        assert hasattr(d, "rule_code")
        assert hasattr(d, "message")
        assert hasattr(d, "line")
        assert hasattr(d, "severity")

    def test_to_dict_serializable(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", "x = " + "a" * 120 + "\n")
        result = check(str(f), select=["E501"])
        for d in result:
            serialized = d.to_dict()
            assert isinstance(serialized, dict)
            assert "rule_code" in serialized

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            check("/no/such/file.py")



# ---------------------------------------------------------------------------
# Public package-root exports (reveal.analyze, .element, .query, .check)
# ---------------------------------------------------------------------------

class TestPublicApiExports:
    """Verify all four public functions are re-exported from the package root and work end-to-end."""

    def test_all_functions_exported(self, tmp_path):
        f = _write_py(tmp_path, "mod.py", "def greet(name): return name\n")
        path = str(f)

        all_names = [
            item.get("name")
            for items in reveal.analyze(path).values()
            if isinstance(items, list)
            for item in items
            if isinstance(item, dict)
        ]
        assert "greet" in all_names

        elem = reveal.element(path, "greet")
        assert elem is not None
        assert "greet" in elem.get("source", "")

        query_result = reveal.query(f"ast://{tmp_path}/")
        assert isinstance(query_result, dict)
        assert len(query_result) > 0

        check_result = reveal.check(path)
        assert isinstance(check_result, list)
