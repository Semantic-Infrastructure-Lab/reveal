"""Regression tests for BACK-1083: `reveal check` cannot distinguish "file is
clean" from "file could not be checked" -- no error/warning/skipped signal
in the check output contract.

Two independent swallow points, both now surfaced:

1. A file that parses via tree-sitter's error-recovery (BACK-1084's
   structure['_has_errors']) previously ran rules against fabricated/partial
   structure and reported "0 issues" identically to a genuinely clean file.
   check_and_collect_file() / run_pattern_detection() now classify this as
   status "warning" and add a `warning`/`detail` field to the contract.

2. A rule that raises inside RuleRegistry.check_file() was logged to stderr
   only (BACK-981 fixed the log *level*, but not visibility in the output
   contract). check_file()'s new optional `errors=` param and the two check
   entry points now surface it as a structured `rule_errors`/`errors` list.

A hard crash in analyzer construction / get_structure() (e.g. an unreadable
file) is classified as status "error", distinct from "skipped" (no analyzer
for this file type -- not an error at all, e.g. a binary asset).
"""

from pathlib import Path

import pytest

from reveal.cli.file_checker import check_and_collect_file

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


def _write_py(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(code, encoding="utf-8")
    return p


class TestCheckAndCollectFileStatus:
    """check_and_collect_file()'s 3rd return value distinguishes ok/warning/
    skipped/error -- used by the directory-scan `reveal check <dir>` path."""

    def test_clean_file_status_is_ok(self, tmp_path):
        f = _write_py(tmp_path, "clean.py", "def f():\n    return 1\n")
        _count, _detections, status = check_and_collect_file(f, tmp_path, None, None)
        assert status == {"status": "ok"}

    def test_syntax_error_file_status_is_warning_not_silently_ok(self, tmp_path):
        """The BACK-1083 headline repro: a syntax-error file with no imports
        previously returned (0, []) byte-for-byte identical to a clean file."""
        f = _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        count, detections, status = check_and_collect_file(f, tmp_path, None, None)

        assert count == 0
        assert detections == []
        assert status["status"] == "warning"
        assert "detail" in status

    def test_unsupported_file_type_is_skipped_not_error(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02")
        _count, _detections, status = check_and_collect_file(f, tmp_path, None, None)

        assert status["status"] == "skipped"

    def test_analyzer_exception_is_error_not_silent_zero(self, tmp_path, monkeypatch):
        f = _write_py(tmp_path, "ok.py", "x = 1\n")

        def boom(*_a, **_kw):
            raise RuntimeError("injected analyzer failure")

        import reveal.registry as registry
        monkeypatch.setattr(registry, "get_analyzer", lambda *a, **kw: boom)
        count, detections, status = check_and_collect_file(f, tmp_path, None, None)

        assert count == 0
        assert detections == []
        assert status["status"] == "error"
        assert "injected analyzer failure" in status["detail"]


class TestRuleCrashSurfacedInContract:
    """A rule that raises must be visible in the returned status, not just
    logged to stderr (BACK-981 only fixed the log level)."""

    def test_rule_crash_recorded_in_status(self, tmp_path, monkeypatch):
        from reveal.rules import RuleRegistry
        RuleRegistry.discover()

        f = _write_py(tmp_path, "target.py", "x = 1\n")
        rule_cls = next(rc for rc in RuleRegistry._rules if rc.code == "B001")
        monkeypatch.setattr(
            rule_cls, "check",
            lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("INJECTED FAULT")),
        )

        _count, _detections, status = check_and_collect_file(f, tmp_path, ["B001"], None)

        assert status["status"] == "ok"  # analyzer/parse pipeline itself succeeded
        rule_errors = status.get("rule_errors", [])
        assert any(e["rule"] == "B001" and "INJECTED FAULT" in e["error"] for e in rule_errors)

    def test_no_errors_param_preserves_prior_log_only_behavior(self, tmp_path, monkeypatch):
        """RuleRegistry.check_file() without errors= must behave exactly as
        before -- callers that don't opt in aren't affected."""
        from reveal.rules import RuleRegistry
        RuleRegistry.discover()

        rule_cls = next(rc for rc in RuleRegistry._rules if rc.code == "B001")
        monkeypatch.setattr(
            rule_cls, "check",
            lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("INJECTED FAULT")),
        )

        detections = RuleRegistry.check_file(
            str(tmp_path / "x.py"), {}, "x = 1\n", select=["B001"], ignore=None,
        )
        assert detections == []


class TestSingleFileCheckContractDisclosure:
    """checks.py::run_pattern_detection is the `reveal check <file>` path --
    the exact command from BACK-1083's own repro."""

    def test_json_output_carries_warning_for_degraded_parse(self, tmp_path, capsys):
        import argparse
        from reveal.analyzers.python import PythonAnalyzer
        from reveal.checks import run_pattern_detection

        f = _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        analyzer = PythonAnalyzer(str(f))
        args = argparse.Namespace(select=None, ignore=None, no_group=False, severity=None)

        run_pattern_detection(analyzer, str(f), "json", args)
        out = capsys.readouterr().out

        assert '"warning"' in out
        assert '"total": 0' in out

    def test_json_output_clean_file_has_no_warning_key(self, tmp_path, capsys):
        import argparse
        from reveal.analyzers.python import PythonAnalyzer
        from reveal.checks import run_pattern_detection

        f = _write_py(tmp_path, "clean.py", "def foo():\n    pass\n")
        analyzer = PythonAnalyzer(str(f))
        args = argparse.Namespace(select=None, ignore=None, no_group=False, severity=None)

        run_pattern_detection(analyzer, str(f), "json", args)
        out = capsys.readouterr().out

        assert '"warning"' not in out
