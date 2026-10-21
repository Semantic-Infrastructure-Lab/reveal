"""Per-file call-site collection is persisted with the structure entry (BACK-1890, BACK-1889).

Before: a structure disk-cache hit parsed nothing, yet every full scan still re-parsed each Python,
JS, PHP and Ruby file in the parent just to collect module-level call sites (measured: 400 of 406
celery files per warm command). Acceptance is an INVOCATION count on ``module_call_sites`` (a hit
parses nothing, so a parse count cannot tell a hit from a skipped file): 0 on the second scan of an
unchanged tree, N on a changed/added file only.
"""
import os

import pytest

from reveal import treesitter as ts_mod
from reveal.adapters.ast import analysis
from reveal.core import disk_cache

pytestmark = [pytest.mark.component, pytest.mark.disk_cache]

PY_A = "import os\n\n\ndef helper():\n    return os.getcwd()\n\n\nprint(helper())\nos.makedirs('x')\n"
PY_B = "def other(n):\n    return n + 1\n\n\nvalue = other(2)\nprint(value)\n"
PY_BROKEN = "def (:\n    pass\n\nprint(1)\nsetup()\n"
JSX = ("function Btn() { return <b/>; }\n"
       "function App() { Btn(); return <div><Btn/></div>; }\n"
       "render(<App/>);\n")


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    ts_mod._get_parse_cache().clear()
    yield
    ts_mod._get_parse_cache().clear()


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text(PY_A, encoding="utf-8")
    (root / "b.py").write_text(PY_B, encoding="utf-8")
    (root / "broken.py").write_text(PY_BROKEN, encoding="utf-8")
    (root / "app.jsx").write_text(JSX, encoding="utf-8")
    return root


@pytest.fixture
def spy(monkeypatch):
    """Invocations of ``module_call_sites`` (file basenames), the acceptance counter."""
    calls = []
    real = analysis.module_call_sites

    def counted(file_path, analyzer):
        calls.append(os.path.basename(file_path))
        return real(file_path, analyzer)

    monkeypatch.setattr(analysis, "module_call_sites", counted)
    return calls


def _scan(root):
    """A fresh process-level state, then a full structure scan: what each CLI command does."""
    ts_mod._get_parse_cache().clear()
    structures = analysis.collect_structures(str(root))
    return {os.path.basename(s["file"]): s for s in structures}, list(structures.skipped)


def test_unchanged_tree_collects_call_sites_once(project, spy):
    first, _ = _scan(project)
    cold = sorted(spy)
    assert cold == ["a.py", "app.jsx", "b.py", "broken.py"]
    spy.clear()
    second, _ = _scan(project)
    assert spy == []  # the second scan of an unchanged tree invokes nothing
    assert second == first  # and answers exactly what the cold scan answered


def test_warm_answer_includes_jsx_extras_and_recovery_flag(project, spy):
    first, _ = _scan(project)
    second, _ = _scan(project)
    assert first["app.jsx"]["jsx_references"], "fixture must exercise the JSX extras"
    assert second["app.jsx"]["jsx_references"] == first["app.jsx"]["jsx_references"]
    assert second["app.jsx"]["jsx_call_sites"] == first["app.jsx"]["jsx_call_sites"]
    assert first["broken.py"].get("parse_recovered") is True
    assert second["broken.py"].get("parse_recovered") is True  # the diagnostic travels on a hit


def test_edit_recomputes_only_the_edited_file(project, spy):
    _scan(project)
    spy.clear()
    (project / "b.py").write_text(PY_B + "extra_call()\n", encoding="utf-8")
    after, _ = _scan(project)
    assert spy == ["b.py"]
    assert any(site["callee"] == "extra_call" for site in after["b.py"]["module_call_sites"])


def test_added_file_recomputes_only_itself(project, spy):
    _scan(project)
    spy.clear()
    (project / "c.py").write_text("def boot():\n    return 1\n\n\nboot()\n", encoding="utf-8")
    after, _ = _scan(project)
    assert spy == ["c.py"]
    assert "c.py" in after


def test_deleted_file_disappears_and_nothing_else_recomputes(project, spy):
    _scan(project)
    spy.clear()
    (project / "b.py").unlink()
    after, _ = _scan(project)
    assert spy == []
    assert "b.py" not in after


def test_language_pack_change_recomputes_everything(project, spy, monkeypatch):
    _scan(project)
    spy.clear()
    monkeypatch.setattr(disk_cache, "build_fingerprint", lambda: "other-language-pack")
    _scan(project)
    assert sorted(spy) == ["a.py", "app.jsx", "b.py", "broken.py"]


def test_cache_off_is_the_positive_control(project, spy, monkeypatch):
    first, _ = _scan(project)
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    spy.clear()
    off, _ = _scan(project)
    assert sorted(spy) == ["a.py", "app.jsx", "b.py", "broken.py"]  # off computes every time
    assert off == first
