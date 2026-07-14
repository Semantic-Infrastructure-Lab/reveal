"""Thin end-to-end smoke test driving the documented core CLI workflows.

The release gates (V007/V011/V012/V013, V027) validate metadata/doc
coherence — that a documented command exists and its schema is internally
consistent — but nothing drives the actual documented workflows through the
real CLI. BACK-508 (`--section` silently dumping the whole file) sailed
through every one of those gates because the unit tests called the analyzer
directly, in the correct argument order; only the CLI's own dispatch had the
swapped-argument bug (see test_section_cli_regression.py for that specific
regression).

This file is not meant to re-test any single adapter's behavior in depth —
each already has its own suite for that. It only asserts that the documented
shape of each command still holds when invoked exactly as a user/agent would:
`reveal <file>` outline, `--section NAME` extraction, an `ast://` element
query, and a `help://` load. If any of these regress to "silently does the
wrong thing," this is the file that catches it.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402


@pytest.fixture
def sample_py(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text(
        "def alpha():\n"
        "    pass\n"
        "\n"
        "\n"
        "def beta():\n"
        "    pass\n"
    )
    return p


@pytest.fixture
def sample_md(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(
        "# Title\n\n## Alpha\nalpha content\n\n## Beta\nbeta content\n"
    )
    return p


class TestOutlineWorkflow:
    """`reveal file.py` — the most basic entry point must list real functions."""

    def test_outline_lists_functions(self, sample_py):
        result = _run_reveal_direct(str(sample_py))
        assert result.returncode == 0, result.stderr
        assert "alpha" in result.stdout
        assert "beta" in result.stdout


class TestSectionExtractionWorkflow:
    """`reveal file.md --section NAME` must extract just that section."""

    def test_section_extracts_named_section_only(self, sample_md):
        result = _run_reveal_direct(str(sample_md), "--section", "Alpha")
        assert result.returncode == 0, result.stderr
        assert "alpha content" in result.stdout
        assert "beta content" not in result.stdout


class TestElementExtractionWorkflow:
    """`reveal file.py func_name` — extract a single named element."""

    def test_extract_single_function(self, sample_py):
        result = _run_reveal_direct(str(sample_py), "alpha")
        assert result.returncode == 0, result.stderr
        assert "def alpha" in result.stdout
        assert "def beta" not in result.stdout


class TestAstQueryWorkflow:
    """`reveal 'ast://dir?name=X'` — query code as an AST database."""

    def test_ast_query_finds_named_function(self, tmp_path, sample_py):
        result = _run_reveal_direct(f"ast://{tmp_path}?name=alpha")
        assert result.returncode == 0, result.stderr
        assert "alpha" in result.stdout
        assert "beta" not in result.stdout


class TestHelpLoadWorkflow:
    """`reveal help://quick` — the progressive-disclosure help entry point."""

    def test_help_quick_loads(self):
        result = _run_reveal_direct("help://quick")
        assert result.returncode == 0, result.stderr
        assert "reveal" in result.stdout.lower()
        assert len(result.stdout) > 0
