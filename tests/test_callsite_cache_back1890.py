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


# --- safety guards (each is proved by mutation in the BACK-1890 report) --------------------------

def _analyzer(path):
    from reveal.registry import get_analyzer
    return get_analyzer(str(path))(str(path))


def _structure_only(root):
    """What the stats pool does: build and store the structure, collect no call sites."""
    for name in sorted(os.listdir(root)):
        _analyzer(root / name).get_structure()


def _entry(path):
    analyzer = _analyzer(path)
    return disk_cache.get(ts_mod._STRUCTURE_CACHE_NAMESPACE, analyzer._structure_fingerprint())


def test_layer_never_leaks_into_get_structure(project):
    _scan(project)
    assert ts_mod._CALL_SITE_LAYER_KEY in _entry(project / "a.py")  # it is in the stored entry...
    structure = _analyzer(project / "a.py").get_structure()
    assert ts_mod._CALL_SITE_LAYER_KEY not in structure  # ...and never in what consumers see


def test_layer_for_another_content_form_is_a_miss(project, spy):
    """BACK-1914 note 2: a layer built from one content form is not served for the other."""
    _scan(project)
    analyzer = _analyzer(project / "a.py")
    analyzer.get_structure()
    assert analyzer.load_call_site_layer(analyzer.call_site_form()) is not None
    assert analyzer.load_call_site_layer("canonical-content/eof-lf") is None
    flipped = _analyzer(project / "a.py")
    flipped._ends_with_newline = not flipped._ends_with_newline
    flipped.get_structure()
    assert flipped.load_call_site_layer(flipped.call_site_form()) is None


def test_js_layer_without_its_jsx_extras_is_a_miss(project, spy):
    """The JSX references and call sites live in the same entry or the layer is not used (item 5)."""
    _scan(project)
    path = project / "app.jsx"
    analyzer = _analyzer(path)
    key = analyzer._structure_fingerprint()
    entry = disk_cache.get(ts_mod._STRUCTURE_CACHE_NAMESPACE, key)
    layer = dict(entry[ts_mod._CALL_SITE_LAYER_KEY])
    assert "jsx_references" in layer and "jsx_call_sites" in layer
    del layer["jsx_call_sites"]
    disk_cache.put(ts_mod._STRUCTURE_CACHE_NAMESPACE, key, {**entry, ts_mod._CALL_SITE_LAYER_KEY: layer})
    spy.clear()
    after, _ = _scan(project)
    assert spy == ["app.jsx"]
    assert after["app.jsx"]["jsx_call_sites"] is not None


def test_outline_scan_stores_nothing_and_full_request_still_computes(project, spy):
    analysis.collect_structures(str(project), outline=True)
    assert spy == []  # an outline collects no call sites
    assert _entry(project / "a.py") is None  # and left no full entry for a layer to hang on
    analyzer = _analyzer(project / "a.py")
    analyzer.store_call_site_layer(analyzer.call_site_form(), {"module_call_sites": []})
    assert _entry(project / "a.py") is None  # nothing is invented to hold the layer
    full, _ = _scan(project)
    assert sorted(spy) == ["a.py", "app.jsx", "b.py", "broken.py"]
    assert full["a.py"]["module_call_sites"]


def test_parse_failure_during_collection_is_not_stored(project, spy, monkeypatch):
    """The BACK-2138 rule: a failure the content did not cause is reported every time, never filed."""
    _structure_only(project)

    def boom(*args, **kwargs):
        raise RuntimeError("transient parser failure")

    real_get_tree = ts_mod.get_tree
    monkeypatch.setattr(ts_mod, "get_tree", boom)
    _, skipped = _scan(project)
    failed = sorted(os.path.basename(path) for path, failure in skipped if "ParseError" in failure)
    assert "a.py" in failed
    assert ts_mod._CALL_SITE_LAYER_KEY not in _entry(project / "a.py")
    spy.clear()
    _, skipped_again = _scan(project)  # same injection: the hit must not have hidden it
    assert sorted(os.path.basename(path) for path, failure in skipped_again if "ParseError" in failure) == failed
    monkeypatch.setattr(ts_mod, "get_tree", real_get_tree)
    spy.clear()
    clean, skipped_clean = _scan(project)
    assert "a.py" in spy and not [f for _, f in skipped_clean if "ParseError" in f]
    assert clean["a.py"]["module_call_sites"]


def test_grammar_unavailable_is_reported_each_time_and_never_stored(project, monkeypatch):
    from reveal.core.treesitter_parse import GrammarUnavailable
    _structure_only(project)

    def unavailable(file_path, analyzer):
        raise GrammarUnavailable("python", RuntimeError("grammar missing"))

    monkeypatch.setattr(analysis, "module_call_sites", unavailable)
    for _ in range(2):
        _, skipped = _scan(project)
        assert any("GrammarUnavailable" in failure or "grammar" in failure.lower()
                   for path, failure in skipped if path.endswith("a.py"))
        assert ts_mod._CALL_SITE_LAYER_KEY not in _entry(project / "a.py")


def test_uncacheable_structure_build_stores_no_layer(project, monkeypatch):
    """A build whose imports failed for a reason the content did not cause (BACK-2138) files nothing."""
    original = ts_mod.TreeSitterAnalyzer._get_or_build_structure

    def uncacheable(self):
        self._imports_uncacheable = True
        return original(self)

    monkeypatch.setattr(ts_mod.TreeSitterAnalyzer, "_get_or_build_structure", uncacheable)
    _scan(project)
    assert _entry(project / "a.py") is None


def test_unreadable_file_fails_the_same_cold_and_warm(project, spy):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root reads a mode 000 file")
    target = project / "b.py"
    _scan(project)
    target.chmod(0)
    try:
        _, warm_skipped = _scan(project)
        os.environ["REVEAL_DISK_CACHE"] = "0"
        try:
            _, cold_skipped = _scan(project)
        finally:
            del os.environ["REVEAL_DISK_CACHE"]
    finally:
        target.chmod(0o644)
    assert warm_skipped == cold_skipped
    assert any(path.endswith("b.py") for path, _ in warm_skipped)


def test_same_stat_edit_is_exactly_as_stale_as_the_structure_entry(project):
    """Item 1: the key is (path, mtime_ns, size, language). An edit that keeps mtime and size is
    served from the old entry for the structure TODAY; the call-site layer inherits that and
    adds no staleness of its own: both answer the old file together, never a mix."""
    target = project / "b.py"
    before = target.stat()
    _scan(project)
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace("other", "OTHER"), encoding="utf-8")  # same length
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert target.stat().st_size == before.st_size
    after, _ = _scan(project)
    functions = {e["name"] for e in after["b.py"]["elements"] if e["category"] == "functions"}
    callees = {site["callee"] for site in after["b.py"]["module_call_sites"]}
    assert "other" in functions and "other" in callees
    assert "OTHER" not in functions and "OTHER" not in callees


def test_uncacheable_analyzer_does_not_extend_an_entry_another_process_stored(project):
    """The structure cache re-reads nothing after a miss, so a racing clean build can store the entry
    between this analyzer's uncacheable build and its call-site store: the layer must still be refused."""
    _structure_only(project)
    analyzer = _analyzer(project / "a.py")
    analyzer._imports_uncacheable = True
    analyzer.store_call_site_layer(analyzer.call_site_form(), {"module_call_sites": []})
    assert ts_mod._CALL_SITE_LAYER_KEY not in _entry(project / "a.py")


def test_same_size_edit_with_a_new_mtime_recomputes(project, spy):
    """Positive control for the stat key: size alone is not the key; mtime_ns changes it."""
    target = project / "b.py"
    _scan(project)
    before = target.stat()
    target.write_text(target.read_text(encoding="utf-8").replace("other", "OTHER"), encoding="utf-8")
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + 5_000_000_000))
    assert target.stat().st_size == before.st_size
    spy.clear()
    after, _ = _scan(project)
    assert spy == ["b.py"]
    assert any(site["callee"] == "OTHER" for site in after["b.py"]["module_call_sites"])


def test_longer_edit_with_the_old_mtime_recomputes(project, spy):
    """Positive control for the other half of the key: a restored mtime does not hide a size change."""
    target = project / "b.py"
    _scan(project)
    before = target.stat()
    target.write_text(target.read_text(encoding="utf-8") + "extra_call()\n", encoding="utf-8")
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
    spy.clear()
    after, _ = _scan(project)
    assert spy == ["b.py"]
    assert any(site["callee"] == "extra_call" for site in after["b.py"]["module_call_sites"])
