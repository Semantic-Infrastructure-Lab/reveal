"""BACK-1424: a single huge file must not dump its whole structure to the terminal.

A 5 MB one-line bundle listed 81k functions (3.3 MB) and a 150k-function file 6 MB.
Text output is capped per category with a stated notice and an --all escape; a
minified/bundled file (by name or by content) gets a much lower cap. --max-items on a
bare file used to truncate silently ("Functions (3):" for a 150k-function file).
"""
import json
import subprocess
import sys

from reveal.defaults import DisplayDefaults
from reveal.utils.path_utils import is_minified_content

CAP = DisplayDefaults.FILE_MAX_ITEMS
MIN_CAP = DisplayDefaults.MINIFIED_FILE_MAX_ITEMS


def run_reveal(*args):
    return subprocess.run(
        [sys.executable, '-m', 'reveal.main'] + list(args),
        capture_output=True, text=True, encoding='utf-8',
    )


def write_many(path, n):
    path.write_text(
        "".join(f"def fn_{i}():\n    return {i}\n\n" for i in range(n)), encoding='utf-8')
    return str(path)


def write_one_line_bundle(path, n):
    path.write_text(
        "".join(f"function f{i}(a,b){{return a+b*{i}}};var v{i}=f{i}(1,2);" for i in range(n)),
        encoding='utf-8')
    return str(path)


class TestIsMinifiedContent:
    def test_one_giant_line_is_minified(self):
        assert is_minified_content("x" * 300_000)

    def test_normal_source_is_not(self):
        assert not is_minified_content("a = 1\n" * 5_000)

    def test_small_file_is_never_minified(self):
        assert not is_minified_content("x" * 500)


class TestDefaultCap:
    def test_text_view_is_capped_with_a_notice(self, tmp_path):
        f = write_many(tmp_path / "many.py", CAP + 100)
        r = run_reveal(f)
        assert r.returncode == 0, r.stderr
        assert f"Functions ({CAP} of {CAP + 100} shown):" in r.stdout
        assert (f"⚠ Truncated functions: showing {CAP} of {CAP + 100} — use --all for "
                "everything, or --max-items N") in r.stdout
        assert f"fn_{CAP - 1}(" in r.stdout
        assert f"fn_{CAP}(" not in r.stdout

    def test_capped_view_makes_no_partial_outline_claim(self, tmp_path):
        f = write_many(tmp_path / "many.py", CAP + 100)
        assert "Partial outline" not in run_reveal(f).stdout

    def test_all_lifts_the_cap(self, tmp_path):
        f = write_many(tmp_path / "many.py", CAP + 100)
        r = run_reveal(f, "--all")
        assert f"fn_{CAP + 99}(" in r.stdout
        assert "Truncated" not in r.stdout

    def test_file_under_the_cap_is_unchanged(self, tmp_path):
        f = write_many(tmp_path / "few.py", 20)
        r = run_reveal(f)
        assert "Functions (20):" in r.stdout
        assert "Truncated" not in r.stdout

    def test_json_is_never_capped_implicitly(self, tmp_path):
        f = write_many(tmp_path / "many.py", CAP + 100)
        r = run_reveal(f, "--format", "json")
        assert f"fn_{CAP + 99}" in r.stdout
        assert "Truncated" not in r.stdout


class TestExplicitMaxItems:
    def test_max_items_says_it_truncated(self, tmp_path):
        f = write_many(tmp_path / "many.py", 40)
        r = run_reveal(f, "--max-items", "3")
        assert "Functions (3 of 40 shown):" in r.stdout
        assert "⚠ Truncated functions: showing 3 of 40 — raise --max-items" in r.stdout
        assert "Partial outline" not in r.stdout


class TestMinified:
    def test_named_min_file_gets_the_low_cap(self, tmp_path):
        f = write_one_line_bundle(tmp_path / "lib.min.js", 200)
        r = run_reveal(f)
        assert f"Functions ({MIN_CAP} of 200 shown):" in r.stdout
        assert "looks minified" in r.stdout

    def test_unnamed_bundle_is_caught_by_content(self, tmp_path):
        f = write_one_line_bundle(tmp_path / "bundle.js", 400)
        r = run_reveal(f)
        assert f"Functions ({MIN_CAP} of 400 shown):" in r.stdout
        assert "looks minified" in r.stdout

    def test_all_still_lists_everything_for_a_minified_file(self, tmp_path):
        f = write_one_line_bundle(tmp_path / "bundle.js", 400)
        r = run_reveal(f, "--all")
        assert "Functions (400):" in r.stdout


class TestOneMarkerBack1564:
    """BACK-1564: these cuts were a private ``_budget`` key (JSON ``structure._budget``, text
    its own "Truncated:" line); now each is a ``note_truncation`` entry, like --head's."""

    def _json(self, *args):
        r = run_reveal(*args, "--format", "json")
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    def test_max_items_json_is_a_meta_warning_not_budget(self, tmp_path):
        f = write_many(tmp_path / "many.py", 40)
        d = self._json(f, "--max-items", "3")
        assert "_budget" not in d["structure"]
        [cut] = d["meta"]["warnings"]
        assert (cut["field"], cut["shown"], cut["total"], cut["cause"]) == ("functions", 3, 40, "max_items")

    def test_head_then_max_items_is_one_true_disclosure(self, tmp_path):
        """HEAD said 'showing 3 of 12' (--head's note) and _budget said '2 of 3' for a list of 2 of 12."""
        f = write_many(tmp_path / "many.py", 12)
        d = self._json(f, "--head", "3", "--max-items", "2")
        assert len(d["structure"]["functions"]) == 2
        [cut] = d["meta"]["warnings"]
        assert (cut["shown"], cut["total"]) == (2, 12)

    def test_a_cut_listing_makes_no_coverage_claim(self, tmp_path):
        """HEAD's JSON said the outline covered 0.6% of the file: of the 3 functions it kept."""
        f = write_many(tmp_path / "many.py", 540)
        assert "coverage" not in self._json(f, "--max-items", "3")["meta"]

    def test_a_category_header_reads_the_same_note_for_head(self, tmp_path):
        """The header's 'N of M shown' comes from the note, so --head says it too (HEAD: 'Functions (2):')."""
        f = write_many(tmp_path / "many.py", 12)
        assert "Functions (2 of 12 shown):" in run_reveal(f, "--head", "2").stdout

    def test_outline_view_discloses_the_default_cap(self, tmp_path):
        f = write_many(tmp_path / "many.py", CAP + 100)
        r = run_reveal(f, "--outline")
        assert f"⚠ Truncated functions: showing {CAP} of {CAP + 100}" in r.stdout

    def test_minified_hint_rides_on_the_note(self, tmp_path):
        f = write_one_line_bundle(tmp_path / "bundle.js", 400)
        r = run_reveal(f)
        assert (f"⚠ Truncated functions: showing {MIN_CAP} of 400 — this file looks "
                "minified/bundled") in r.stdout

    def test_no_source_spells_a_cut_budget_again(self):
        """The ratchet: no module under reveal/ names the old private keys."""
        import ast
        from pathlib import Path
        import reveal
        root = Path(reveal.__file__).parent
        offenders = [
            f"{path.relative_to(root)}:{node.lineno}"
            for path in root.rglob("*.py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and node.value in ("_budget", "_looks_minified")
        ]
        assert offenders == []
