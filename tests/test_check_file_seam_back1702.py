"""BACK-1702: `reveal check <file>` leaves through the subcommand outcome seam too.

BACK-1545 moved `check <dir>` onto emit_subcommand_result/note_truncation. The single-file
form kept its own spelling of the --max-items cut (``meta.total_available`` and a
``… +N more issue(s) hidden`` footer) and a hand-built envelope. It now records the cut with
note_truncation (``meta.warnings`` in JSON, one ``⚠ Truncated ...`` line in text). Kept for
compatibility: ``meta.truncated/total_available/returned``, top-level ``total``, the
0/1/2/3 exit contract (internal-docs EXIT_CODE_CONTRACT), and --also-json being the document
--format json prints.
"""

import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

_BARE = "    try:\n        pass\n    except:\n        pass\n"


def _file(tmp_path, n=3, name="a.py"):
    path = tmp_path / name
    path.write_text("def a():\n" + _BARE * n, encoding="utf-8")
    return path


def _check(path, *flags):
    return _run_reveal_direct("check", str(path), "--select", "B001", *flags)


def _cuts(payload):
    return [w for w in payload.get("meta", {}).get("warnings", []) if w.get("type") == "truncated"]


class TestMaxItemsCutOnTheSeam:
    def test_json_records_the_cut_with_note_truncation(self, tmp_path):
        result = _check(_file(tmp_path), "--format", "json", "--max-items", "2")
        payload = json.loads(result.stdout)
        assert result.returncode == 1
        assert (payload["type"], payload["source_type"]) == ("check", "file")
        assert payload["total"] == 2 and len(payload["detections"]) == 2
        (cut,) = _cuts(payload)
        assert (cut["field"], cut["shown"], cut["total"], cut["cause"]) == ("detections", 2, 3, "max_items")
        assert cut["message"] == "detections: showing 2 of 3 — raise --max-items"

    def test_json_keeps_the_compat_meta_fields(self, tmp_path):
        meta = json.loads(_check(_file(tmp_path), "--format", "json", "--max-items", "2").stdout)["meta"]
        assert (meta["truncated"], meta["total_available"], meta["returned"]) == (True, 3, 2)

    def test_text_discloses_the_cut_once_through_the_seam(self, tmp_path):
        result = _check(_file(tmp_path), "--max-items", "2")
        assert result.returncode == 1
        assert result.stdout.count("⚠ Truncated detections: showing 2 of 3 — raise --max-items") == 1
        assert "more issue(s) hidden" not in result.stdout, "the cut is disclosed once, not twice"

    def test_also_json_is_the_format_json_document(self, tmp_path):
        src = _file(tmp_path)
        artifact = tmp_path / "out.json"
        text = _check(src, "--max-items", "2", "--also-json", str(artifact))
        assert text.returncode == 1
        printed = json.loads(_check(src, "--format", "json", "--max-items", "2").stdout)
        assert json.loads(artifact.read_text(encoding="utf-8")) == printed
        assert _cuts(printed)


class TestUnchangedWithoutACut:
    """Negative controls: no cut, no new keys or lines; the exit contract holds."""

    def test_json_without_max_items_has_no_meta(self, tmp_path):
        payload = json.loads(_check(_file(tmp_path), "--format", "json").stdout)
        assert "meta" not in payload
        assert payload["total"] == 3

    def test_max_items_above_the_total_records_nothing(self, tmp_path):
        payload = json.loads(_check(_file(tmp_path), "--format", "json", "--max-items", "3").stdout)
        assert _cuts(payload) == [] and "meta" not in payload

    def test_text_without_max_items_has_no_truncated_line(self, tmp_path):
        out = _check(_file(tmp_path)).stdout
        assert "⚠ Truncated" not in out and "more issue(s) hidden" not in out

    def test_grep_prints_every_detection_and_no_cut_note(self, tmp_path):
        result = _check(_file(tmp_path), "--format", "grep", "--max-items", "2")
        assert len(result.stdout.strip().splitlines()) == 3
        assert "Truncated" not in result.stdout

    @pytest.mark.parametrize("fmt", ["text", "json", "grep"])
    def test_exit_codes(self, tmp_path, fmt):
        clean = tmp_path / "ok.py"
        clean.write_text("def ok():\n    return 1\n", encoding="utf-8")
        assert _check(clean, "--format", fmt).returncode == 0
        found = _file(tmp_path)
        assert _check(found, "--format", fmt, "--max-items", "0").returncode == 1
        broken = tmp_path / "bad.py"
        broken.write_text("def bad(:\n", encoding="utf-8")
        assert _check(broken, "--format", fmt, "--max-items", "0").returncode == 3
        assert _check(broken, "--format", fmt, "--exit-zero").returncode == 0
