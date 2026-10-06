"""BACK-1437 / BACK-1429: M102's project-wide import scan is built once, in the parent.

M102 (orphaned module) reads every .py file under the project root on first use and
caches the result in ``M102._import_cache``. I002/D005/T006 are preloaded in the parent
and seeded into each pool worker (rules/scan_caches.py); M102 was not, so every worker
rebuilt the whole-project scan on its own first .py file -- on home-assistant's mqtt
component ~6.7s of M102 per worker process (BACK-1429 note #2).

The build counter below wraps ``M102._collect_all_imports`` and appends one line per
cache miss to a file, so builds in forked workers are counted too.
"""

import os

import pytest

from reveal.cli import file_checker
from reveal.rules.maintainability import M102 as m102_module


def _project(tmp_path):
    """A Python project: one importer, one imported module, orphans."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "p"\n', encoding="utf-8")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "used.py").write_text("def used():\n    return 1\n", encoding="utf-8")
    (pkg / "importer.py").write_text(
        "from pkg.used import used\n\n\ndef go():\n    return used()\n", encoding="utf-8")
    for i in range(6):
        (pkg / f"orphan{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
    return sorted(pkg.glob("*.py"))


@pytest.fixture
def count_m102_builds(tmp_path, monkeypatch):
    """Patch M102 so every real (uncached) project scan appends its pid to a file."""
    log = tmp_path / "m102_builds.log"
    real = m102_module.M102._collect_all_imports

    def counting(self, package_root):
        if package_root not in m102_module._import_cache:
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"{os.getpid()}\n")
        return real(self, package_root)

    monkeypatch.setattr(m102_module.M102, "_collect_all_imports", counting)

    def builds():
        return log.read_text(encoding="utf-8").split() if log.exists() else []
    return builds


def _m102_findings(result):
    _total, _files_with, file_results, _errored, _truncated = result
    return sorted(
        (entry["file"], d["message"])
        for entry in file_results for d in entry["detections"] if d["rule_code"] == "M102"
    )


class TestCheckPoolPreloadsM102:
    def test_pool_builds_the_import_scan_once(self, tmp_path, monkeypatch, count_m102_builds):
        files = _project(tmp_path)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "3")
        result = file_checker._check_files_json(files, tmp_path, None, None)

        assert _m102_findings(result), "fixture must produce M102 findings"
        builds = count_m102_builds()
        assert builds == [str(os.getpid())], (
            f"expected one M102 scan, in the parent; got {len(builds)} from pids {builds}")

    def test_pool_and_serial_findings_identical(self, tmp_path, monkeypatch):
        files = _project(tmp_path)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "1")
        serial = file_checker._check_files_json(files, tmp_path, None, None)
        m102_module._import_cache.clear()
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "3")
        parallel = file_checker._check_files_json(files, tmp_path, None, None)

        flagged = [message for _file, message in _m102_findings(serial)]
        # pkg.used is imported, so it is the one module not flagged.
        assert flagged == [
            f"Module 'pkg.{name}' is not imported anywhere in the package"
            for name in ["importer"] + [f"orphan{i}" for i in range(6)]
        ]
        assert serial == parallel

    def test_not_preloaded_when_m102_is_not_selected(self, tmp_path, monkeypatch, count_m102_builds):
        """Negative control: --select without M102 builds no M102 scan anywhere."""
        files = _project(tmp_path)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "3")
        file_checker._check_files_json(files, tmp_path, ["C901"], None)
        assert count_m102_builds() == []

    def test_serial_path_builds_once(self, tmp_path, monkeypatch, count_m102_builds):
        """Negative control: the serial path was already one build per process."""
        files = _project(tmp_path)
        monkeypatch.setenv("REVEAL_MAX_WORKERS", "1")
        file_checker._check_files_json(files, tmp_path, None, None)
        assert count_m102_builds() == [str(os.getpid())]


class TestM102PreloadUnit:
    def test_skipped_when_m102_not_in_rule_set(self, tmp_path, count_m102_builds):
        from reveal.rules.scan_caches import _m102_preload
        files = _project(tmp_path)
        assert _m102_preload(tmp_path, ["C901"], None, files) == {}
        assert count_m102_builds() == []

    def test_no_build_for_files_m102_never_scans_from(self, tmp_path, count_m102_builds):
        """Tests and entry points return before M102 resolves a root, so a
        preload sampled from one would build a scan no worker asked for."""
        from reveal.rules.scan_caches import _m102_preload
        _project(tmp_path)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        files = [tests_dir / "test_x.py", tmp_path / "pkg" / "__init__.py"]
        assert _m102_preload(tmp_path, None, None, files) == {}
        assert count_m102_builds() == []

    def test_preload_keys_the_root_workers_resolve(self, tmp_path):
        from reveal.rules.scan_caches import _m102_preload
        files = _project(tmp_path)
        cache = _m102_preload(tmp_path, None, None, files)
        assert list(cache) == [m102_module._project_root(files[-1].resolve())]
        assert "pkg.used" in next(iter(cache.values()))

    def test_init_worker_seeds_cache(self, tmp_path):
        from reveal.rules.scan_caches import _m102_init_worker
        _m102_init_worker({tmp_path: {"a.b"}})
        assert m102_module._import_cache[tmp_path] == {"a.b"}

    def test_init_worker_noop_on_empty(self):
        from reveal.rules.scan_caches import _m102_init_worker
        before = dict(m102_module._import_cache)
        _m102_init_worker({})
        assert m102_module._import_cache == before
