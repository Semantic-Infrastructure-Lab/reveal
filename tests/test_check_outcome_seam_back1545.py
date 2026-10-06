"""BACK-1545: `reveal check <dir>` leaves through the subcommand outcome seam.

Every other `reveal <name>` prints its result through
cli/routing/subcommand.emit_subcommand_result (BACK-1544), so a cut list is recorded once
with note_truncation and disclosed the same way in JSON (``meta.warnings``) and text
(``⚠ Truncated ...``). check kept its own spelling of the --max-items cut: a
``summary.items_truncated`` bool in JSON and its own text footer. It now records the cut
through note_truncation too. Kept for compatibility: ``summary.items_truncated``, the
0/1/2/3 exit contract (internal-docs EXIT_CODE_CONTRACT), --also-json being the document
--format json prints, and --limit as the text report's own density footer.
"""

import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

_BARE = "    try:\n        pass\n    except:\n        pass\n"


def _tree(tmp_path):
    """6 B001 findings: a.py 3, b.py 2, c.py 1; d.py clean."""
    for name, n in (("a", 3), ("b", 2), ("c", 1)):
        (tmp_path / f"{name}.py").write_text(f"def {name}():\n" + _BARE * n, encoding="utf-8")
    (tmp_path / "d.py").write_text("def d():\n    return 1\n", encoding="utf-8")
    return tmp_path


def _check(tmp_path, *flags):
    return _run_reveal_direct("check", str(tmp_path), "--select", "B001", *flags)


def _cuts(payload):
    return [w for w in payload.get("meta", {}).get("warnings", []) if w.get("type") == "truncated"]


class TestMaxItemsCutOnTheSeam:
    def test_json_records_the_cut_with_note_truncation(self, tmp_path):
        result = _check(_tree(tmp_path), "--format", "json", "--max-items", "2")
        payload = json.loads(result.stdout)
        assert result.returncode == 1
        assert payload["type"] == "check"
        assert payload["summary"]["total_issues"] == 6
        assert payload["summary"]["items_truncated"] is True, "kept for compatibility"
        assert sum(len(f["detections"]) for f in payload["files"]) == 2
        (cut,) = _cuts(payload)
        assert (cut["field"], cut["shown"], cut["total"], cut["cause"]) == ("detections", 2, 6, "max_items")
        assert cut["message"] == "detections: showing 2 of 6 — raise --max-items"

    def test_text_discloses_the_cut_once_through_the_seam(self, tmp_path):
        result = _check(_tree(tmp_path), "--max-items", "2")
        assert result.returncode == 1
        assert result.stdout.count("⚠ Truncated detections: showing 2 of 6 — raise --max-items") == 1
        assert "some issues hidden" not in result.stdout, "the cut is disclosed once, not twice"

    def test_text_cut_counts_only_the_files_it_prints(self, tmp_path):
        """--limit 1 prints a.py alone (3 findings); --max-items 2 cuts that to 2 of 3.
        The 3 findings in b.py/c.py are --limit's to disclose, not --max-items'."""
        result = _check(_tree(tmp_path), "--limit", "1", "--max-items", "2")
        assert "⚠ Truncated detections: showing 2 of 3 — raise --max-items" in result.stdout
        assert "+2 more files with 3 issues hidden (--limit 1)" in result.stdout

    def test_also_json_is_the_format_json_document(self, tmp_path):
        (tmp_path / "tree").mkdir()
        tree = _tree(tmp_path / "tree")
        artifact = tmp_path / "out.json"  # outside the tree, or the second run checks it
        text = _check(tree, "--max-items", "2", "--also-json", str(artifact))
        assert text.returncode == 1
        printed = json.loads(_check(tree, "--format", "json", "--max-items", "2").stdout)
        written = json.loads(artifact.read_text(encoding="utf-8"))
        assert written == printed
        assert _cuts(written), "the artifact carries the JSON budget's cut"


class TestUnchangedWithoutACut:
    """Negative controls: no cut, no new keys or lines; the exit contract holds."""

    def test_json_without_max_items_has_no_meta(self, tmp_path):
        payload = json.loads(_check(_tree(tmp_path), "--format", "json").stdout)
        assert "meta" not in payload
        assert payload["summary"]["items_truncated"] is False

    def test_max_items_above_the_total_records_nothing(self, tmp_path):
        payload = json.loads(_check(_tree(tmp_path), "--format", "json", "--max-items", "6").stdout)
        assert _cuts(payload) == []
        assert payload["summary"]["items_truncated"] is False

    def test_text_without_max_items_has_no_truncated_line(self, tmp_path):
        result = _check(_tree(tmp_path), "--limit", "1")
        assert "⚠ Truncated" not in result.stdout
        assert "(--limit 1)" in result.stdout

    @pytest.mark.parametrize("fmt", ["text", "json", "grep"])
    def test_exit_codes(self, tmp_path, fmt):
        clean = tmp_path / "clean"
        clean.mkdir()
        (clean / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
        assert _check(clean, "--format", fmt).returncode == 0

        found = tmp_path / "found"
        found.mkdir()
        assert _check(_tree(found), "--format", fmt, "--max-items", "0").returncode == 1

        broken = tmp_path / "broken"
        broken.mkdir()
        (broken / "bad.py").write_text("def bad(:\n", encoding="utf-8")
        assert _check(broken, "--format", fmt, "--max-items", "0").returncode == 3
        assert _check(broken, "--format", fmt, "--exit-zero").returncode == 0
