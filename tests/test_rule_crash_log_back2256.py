"""A rule that raises on one file logs one line at error, not a traceback (BACK-2256).

The failure already reaches the user through coverage, the errors list and the
caveat line; the error record carried exc_info=True, so the default stderr
handler printed ~25 traceback lines before `reveal overview` output (M104 on a
deep Go file, BACK-2252). The traceback stays available at debug.
"""

import logging

from reveal.rules import RuleRegistry


def _inject_fault(monkeypatch):
    RuleRegistry.discover()
    rule_cls = next(rc for rc in RuleRegistry._rules if rc.code == "B001")
    monkeypatch.setattr(
        rule_cls, "check",
        lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("INJECTED FAULT")),
    )


def _run(tmp_path, errors=None, coverage=None):
    return RuleRegistry.check_file(
        str(tmp_path / "x.py"), {}, "x = 1\n", select=["B001"], ignore=None,
        errors=errors, coverage=coverage,
    )


def test_rule_crash_error_record_carries_no_traceback(tmp_path, monkeypatch, caplog):
    _inject_fault(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="reveal.rules"):
        _run(tmp_path)
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "B001" in message and "x.py" in message and "INJECTED FAULT" in message
    assert errors[0].exc_info is None


def test_rule_crash_traceback_is_kept_at_debug(tmp_path, monkeypatch, caplog):
    _inject_fault(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="reveal.rules"):
        _run(tmp_path)
    debug = [r for r in caplog.records if r.levelno == logging.DEBUG and r.exc_info]
    assert len(debug) == 1
    assert debug[0].exc_info[0] is RuntimeError


def test_rule_crash_still_recorded_in_errors_and_coverage(tmp_path, monkeypatch):
    _inject_fault(monkeypatch)
    errors, coverage = [], []
    assert _run(tmp_path, errors=errors, coverage=coverage) == []
    assert errors == [{"rule": "B001", "error": "RuntimeError: INJECTED FAULT"}]
    assert any(c.get("rule") == "B001" and c.get("status") == "failed" for c in coverage), coverage
