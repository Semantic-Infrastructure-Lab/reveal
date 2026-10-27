"""BACK-2137: plain `reveal check` discloses rule outcomes (skipped / unavailable / not applicable).

Only `reveal reveal:// --check` and `RuleRegistry.check_file(coverage=)` disclosed them, so a rule
that was unavailable (a prerequisite missing) or not applicable to every file reached read exactly
like a clean pass. `check <file>` and `check <dir>` now hand the same ledger to the same builder
(`rules.coverage_report`) and the same renderer. A directory aggregates per rule across files
("ran on N, not applicable to M"). Text rule: a rule that was unavailable on any file always prints;
skipped / not-applicable rules print only when --select named the rules (the default view would
otherwise gain ~50 "target does not match" lines for rules aimed at other targets, AGENT_DEVELOPER_
GUIDELINES item 8) and always appear in JSON.
"""

import json

import pytest

from conftest import _run_reveal_direct, needs_forked_workers

pytestmark = pytest.mark.component

_CLEAN_PY = "def f():\n    return 1\n"
_BAD_M501 = "rules:\n  M501:\n    ignore_patterns: not-a-list\n"


def _mixed_tree(tmp_path, py=1):
    for i in range(py):
        (tmp_path / f"m{i}.py").write_text(_CLEAN_PY, encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Notes\n\nplain text, no links\n", encoding="utf-8")
    return tmp_path


def _rule(payload, code):
    return next((r for r in payload["coverage"]["rules"] if r["rule"] == code), None)


def _json(tmp_path, *flags):
    result = _run_reveal_direct("check", str(tmp_path), "--format", "json", *flags)
    return result, json.loads(result.stdout)


class TestDirectoryCoverage:
    def test_json_aggregates_a_rule_across_files(self, tmp_path):
        """L001 reads markdown: it ran on the .md and is not applicable to the .py."""
        result, payload = _json(_mixed_tree(tmp_path), "--select", "L001")
        assert result.returncode == 0
        l001 = _rule(payload, "L001")
        assert l001 is not None, "check's JSON carries a coverage ledger"
        assert l001["files"] == {"run": 1, "skipped": 1, "unavailable": 0, "failed": 0}
        assert "target does not match" in l001["reason"]
        assert payload["coverage"]["run"] == 1

    def test_text_names_the_selected_rule_it_did_not_run(self, tmp_path):
        result = _run_reveal_direct("check", str(_mixed_tree(tmp_path)), "--select", "L001")
        assert result.returncode == 0
        (line,) = [ln for ln in result.stdout.splitlines() if "L001" in ln]
        assert "ran on 1 file" in line and "not applicable to 1" in line

    def test_default_text_does_not_list_rules_aimed_at_other_targets(self, tmp_path):
        """No --select: ~50 'target does not match' rules are expected, so text stays quiet."""
        result = _run_reveal_direct("check", str(_mixed_tree(tmp_path)))
        assert "target does not match" not in result.stdout
        assert "not applicable" not in result.stdout
        _, payload = _json(tmp_path)
        assert _rule(payload, "L001")["files"]["skipped"] == 1, "JSON keeps every rule"

    def test_unavailable_rule_prints_in_the_default_text(self, tmp_path):
        """M501 cannot apply its setting, so its 'no findings' is not a pass."""
        _mixed_tree(tmp_path)
        (tmp_path / ".reveal.yaml").write_text(_BAD_M501, encoding="utf-8")
        result = _run_reveal_direct("check", str(tmp_path))
        assert result.returncode == 0, "exit codes do not change"
        assert "M501 unavailable" in result.stdout
        _, payload = _json(tmp_path)
        m501 = _rule(payload, "M501")
        assert m501["status"] == "unavailable" and m501["files"]["unavailable"] == 1
        assert payload["coverage"]["unavailable"] >= 1
        assert payload["summary"]["exit_code"] == 0

    def test_a_clean_tree_with_nothing_unavailable_prints_no_block(self, tmp_path):
        result = _run_reveal_direct("check", str(_mixed_tree(tmp_path)))
        assert "Checks:" not in result.stdout


class TestSingleFileCoverage:
    def test_json_discloses_the_rule_not_applicable_to_the_file(self, tmp_path):
        target = _mixed_tree(tmp_path) / "m0.py"
        result = _run_reveal_direct("check", str(target), "--select", "L001", "--format", "json")
        payload = json.loads(result.stdout)
        l001 = _rule(payload, "L001")
        assert l001["status"] == "skipped" and l001["files"]["skipped"] == 1
        assert payload["coverage"]["skipped"] == 1 and payload["coverage"]["run"] == 0

    def test_text_names_the_selected_rule_it_did_not_run(self, tmp_path):
        target = _mixed_tree(tmp_path) / "m0.py"
        result = _run_reveal_direct("check", str(target), "--select", "L001")
        assert any("L001" in ln and "not applicable" in ln for ln in result.stdout.splitlines())


class TestPooledCoverage:
    def test_pool_and_serial_runs_report_the_same_outcomes(self, tmp_path, monkeypatch):
        """Outcomes cross the process pool: 6 files hand work to 2 workers."""
        _mixed_tree(tmp_path, py=5)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "1")
        _, serial = _json(tmp_path, "--select", "L001")
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "2")
        _, pooled = _json(tmp_path, "--select", "L001")
        assert _rule(serial, "L001")["files"] == {"run": 1, "skipped": 5, "unavailable": 0, "failed": 0}
        assert pooled["coverage"] == serial["coverage"]

    def test_pooled_unavailable_survives_the_pool(self, tmp_path, monkeypatch):
        _mixed_tree(tmp_path, py=5)
        (tmp_path / ".reveal.yaml").write_text(_BAD_M501, encoding="utf-8")
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "2")
        _, payload = _json(tmp_path)
        assert _rule(payload, "M501")["files"]["unavailable"] >= 5

    @needs_forked_workers
    def test_a_lost_worker_file_is_not_counted_as_run(self, tmp_path, monkeypatch):
        import os
        from pathlib import Path
        from reveal.cli import file_checker

        _mixed_tree(tmp_path, py=5)
        real = file_checker.check_and_collect_file

        def killer(file_path, *args, **kwargs):
            if Path(file_path).name == "notes.md":
                os._exit(1)
            return real(file_path, *args, **kwargs)

        monkeypatch.setattr(file_checker, "check_and_collect_file", killer)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "2")
        result, payload = _json(tmp_path, "--select", "L001")
        assert result.returncode == 3
        assert payload["summary"]["files_errored"] >= 1
        l001 = _rule(payload, "L001")
        assert l001 is None or l001["files"]["run"] == 0, "the lost .md did not run L001 clean"


class TestSiblingSurfaceUnchanged:
    def test_reveal_uri_check_keeps_its_flat_ledger(self):
        result = _run_reveal_direct("reveal://", "--check", "--select", "V001", "--format", "json")
        payload = json.loads(result.stdout)
        assert set(payload["coverage"]) == {"scope", "rules", "run", "skipped", "failed", "unavailable"}
        assert all("files" not in entry for entry in payload["coverage"]["rules"])
