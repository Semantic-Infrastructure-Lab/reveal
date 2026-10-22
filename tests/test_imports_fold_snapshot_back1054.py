"""scripts/imports_fold_snapshot.py (BACK-1054 slice S0): the pre-merge snapshot that every fold slice
is compared against must report a changed answer, and must stay quiet on an unchanged one.

The compare logic is checked on hand-built rows (one changed dependent is reported as that module's
row, not as a list shift; an exit code, a row present on one side and a timeout all surface), and the
whole tool once end to end on a small fixture through real ``python -m reveal`` requests: the same
tree twice compares empty, and an edited tree differs on the rows the edit moved.
"""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "imports_fold_snapshot.py"
_spec = importlib.util.spec_from_file_location("imports_fold_snapshot", SCRIPT)
snap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snap)


def _dir_row(modules, exit_code=0, sha="aa"):
    data = {"type": "dependency_summary", "modules": modules, "total_modules": len(modules),
            "metadata": {"scan_capped": False}}
    row = {"status": "ok", "exit_code": exit_code, "stdout_sha256": sha, "stderr": "", "json": data}
    snap.summarize_row("depends_dir", row)
    return row


def _snapshot(rows, status="ok", targets=None):
    return {"corpora": {"c": {"status": status, "scan": "c", "targets": targets or [], "rows": rows}}}


MODULES = [{"module": "a.py", "dependent_count": 2, "dependents": ["b.py", "c.py"]},
           {"module": "d.py", "dependent_count": 1, "dependents": ["b.py"]}]


def test_identical_rows_compare_empty():
    a = _snapshot({"depends_dir": _dir_row(MODULES)})
    b = _snapshot({"depends_dir": _dir_row(MODULES)})
    assert snap.compare(a, b) == ([], [])


def test_one_changed_dependent_is_reported_on_its_module_row():
    moved = [dict(MODULES[0], dependent_count=1, dependents=["b.py"]), MODULES[1]]
    changed, incomparable = snap.compare(_snapshot({"depends_dir": _dir_row(MODULES)}),
                                         _snapshot({"depends_dir": _dir_row(moved, sha="bb")}))
    assert incomparable == []
    [(label, changes)] = changed
    assert label == "c depends_dir"
    assert "count: 3 -> 2" in changes
    assert "json modules[a.py].dependent_count: 2 -> 1" in changes
    assert "json modules[a.py].dependents[c.py]: only in A" in changes
    # d.py did not move, so nothing names it.
    assert not [line for line in changes if "d.py" in line]


def test_exit_code_row_and_timeout_changes_all_surface():
    a = _snapshot({"depends_dir": _dir_row(MODULES), "deps": {"status": "timeout", "exit_code": None}})
    b = _snapshot({"depends_dir": _dir_row(MODULES, exit_code=3), "check": _dir_row([]),
                   "deps": {"status": "ok", "exit_code": 3}})
    changed, incomparable = snap.compare(a, b)
    by_label = dict(changed)
    assert by_label["c depends_dir"] == ["exit_code: 0 -> 3"]
    assert by_label["c check"] == ["row only in B"]
    assert incomparable == ["c deps: timed out (timeout / ok)"]


def test_a_missing_corpus_is_not_reported_as_identical():
    changed, incomparable = snap.compare(_snapshot({}, status="missing"), _snapshot({}, status="missing"))
    assert changed == [] and incomparable == ["c: status missing / missing"]


def test_targets_are_every_kth_sorted_module_and_a_package_dir_stands_for_its_first_file(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "pkg" / "b.go").write_text("package pkg\n", encoding="utf-8")
    (tmp_path / "pkg" / "a.go").write_text("package pkg\n", encoding="utf-8")
    answer = {"modules": [{"module": name} for name in ("f4.py", "f1.py", "pkg", "f3.py", "f2.py", "f5.py")]}
    # sorted: f1 f2 f3 f4 f5 pkg; 6 // 3 = every 2nd
    assert snap.pick_targets(answer, tmp_path, 3, seed=0) == ["f1.py", "f3.py", "f5.py"]
    assert snap.pick_targets(answer, tmp_path, 3, seed=1) == ["f2.py", "f4.py", "pkg/a.go"]
    assert snap.pick_targets(answer, tmp_path, 3, seed=1) == snap.pick_targets(answer, tmp_path, 3, seed=1)
    assert snap.pick_targets(answer, tmp_path, 0, seed=0) == []


def test_zero_rows_are_listed_for_a_positive_control():
    snapshot = _snapshot({"depends_dir": _dir_row(MODULES), "calls_modules": {"status": "ok", "count": 0},
                          "deps": {"status": "no_json", "count": None}})
    assert snap.zero_rows(snapshot) == ["c calls_modules: status=ok count=0", "c deps: status=no_json count=None"]


def test_refuses_when_reveal_would_load_from_another_checkout(tmp_path):
    (tmp_path / "corp" / "c").mkdir(parents=True)
    out = tmp_path / "s.json"
    assert snap.main(["--output", str(out), "--src", str(tmp_path), "--corpus-root", str(tmp_path / "corp"),
                      "--corpus", "c"]) == 2
    assert not out.exists()


def _fixture(root: Path) -> None:
    pkg = root / "c" / "pkg"
    pkg.mkdir(parents=True)
    (root / "c" / "pyproject.toml").write_text("[project]\nname = 'c'\n", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (pkg / "a.py").write_text("from pkg import core\n", encoding="utf-8")
    (pkg / "b.py").write_text("from pkg.core import VALUE\n", encoding="utf-8")


def _take(root: Path, out: Path) -> dict:
    code = snap.main(["--output", str(out), "--corpus-root", str(root), "--corpus", "c", "--targets", "2",
                      "--only", "depends_dir", "--only", "depends_file", "--timeout", "300"])
    assert code == 0
    return snap.load_snapshot(out)


@pytest.mark.integration
def test_end_to_end_unchanged_tree_compares_empty_and_an_edit_differs(tmp_path, capsys):
    root = tmp_path / "corp"
    _fixture(root)
    first = _take(root, tmp_path / "a.json")
    rows = first["corpora"]["c"]["rows"]
    # Positive control: the answers are real, not empty successes.
    # `from pkg import core` loads pkg/__init__.py too: 3 edges.
    assert rows["depends_dir"]["exit_code"] == 0 and rows["depends_dir"]["count"] == 3
    assert first["corpora"]["c"]["targets"] == ["pkg/__init__.py", "pkg/core.py"]
    assert rows["depends_file:pkg/core.py"]["json"]["count"] == 2
    assert first["zero_rows"] == []

    second = _take(root, tmp_path / "b.json")
    assert snap.compare(first, second) == ([], [])

    (root / "c" / "pkg" / "d.py").write_text("import pkg.core\n", encoding="utf-8")
    third = _take(root, tmp_path / "c.json")
    changed, incomparable = snap.compare(first, third)
    assert incomparable == []
    by_label = dict(changed)
    assert {"c depends_dir", "c depends_file:pkg/core.py"} <= set(by_label)
    assert "json modules[pkg/core.py].dependents[pkg/d.py]: only in B" in by_label["c depends_dir"]
    assert "json dependents[pkg/d.py|1].file: only in B" in by_label["c depends_file:pkg/core.py"]
    assert snap.run_compare(tmp_path / "a.json", tmp_path / "c.json", shown=0) == 1
    assert snap.run_compare(tmp_path / "a.json", tmp_path / "b.json", shown=0) == 0
    printed = capsys.readouterr().out
    assert "0 changed, 0 not comparable" in printed
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["env"]["REVEAL_DISK_CACHE"] == "0"
