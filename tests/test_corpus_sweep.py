"""scripts/corpus_sweep.py: pure logic + clean no-corpus behaviour (no real corpus needed)."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "corpus_sweep.py"
_spec = importlib.util.spec_from_file_location("corpus_sweep", SCRIPT)
corpus_sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(corpus_sweep)


def test_diff_complexity_counts_only_changed_functions():
    base = {"java": {"a.java": {"f@1": 3, "g@9": 2}, "b.java": {"h@1": 1}}}
    head = {"java": {"a.java": {"f@1": 1, "g@9": 2}, "b.java": {"h@1": 1}, "new.java": {"n@1": 5}}}
    rep = corpus_sweep.diff_complexity(base, head)["java"]
    assert (rep["files_changed"], rep["functions_changed"]) == (1, 1)
    assert rep["examples"] == ["a.java f@1: 3 -> 1"]


def test_sampling_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("REVEAL_CORPUS_DIR", str(tmp_path))
    for i in range(20):
        (tmp_path / "go").mkdir(exist_ok=True)
        (tmp_path / "go" / f"f{i}.go").write_text("package x\n" * 100)
    first = corpus_sweep.sample_files("go", 5, seed=7)
    assert first == corpus_sweep.sample_files("go", 5, seed=7)
    assert len(first) == 5


def test_absent_corpus_exits_zero(tmp_path):
    env = dict(os.environ, REVEAL_CORPUS_DIR=str(tmp_path / "missing"))
    r = subprocess.run([sys.executable, str(SCRIPT), "agree"], env=env, capture_output=True, text=True)
    assert r.returncode == 0 and "corpus not found" in r.stdout


def test_complexity_requires_base_ref(tmp_path):
    env = dict(os.environ, REVEAL_CORPUS_DIR=str(tmp_path))
    (tmp_path / "go").mkdir()
    r = subprocess.run([sys.executable, str(SCRIPT), "complexity"], env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "--base-ref" in r.stderr


def test_mypy_ratchet_parses_error_lines():
    spec = importlib.util.spec_from_file_location(
        "check_mypy_baseline", SCRIPT.with_name("check_mypy_baseline.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = mod._ERROR.match('reveal/x.py:12:5: error: Incompatible return value  [return-value]')
    assert (m["file"], m["code"]) == ("reveal/x.py", "return-value")
    assert mod._ERROR.match('reveal/x.py:12: note: see docs') is None
