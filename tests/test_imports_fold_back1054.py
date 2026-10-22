"""depends:// reuses the per-file import cache when PHP's constant index cannot change a result
(BACK-1054 slice S1).

The cascade (analyzers/imports/resolution.py) passes the project's PHP ``define()`` index to every
generic extractor's ``extract_imports``, and that call skipped the per-file cache whenever the index
was not ``None``: an empty index (every tree with no PHP define) and a language that never reads the
index (all but PHP) re-parsed every file on every request. The counts here are the per-file cache
lookups and the uncached extractions of the generic extractor, in one process, with the disk layer
switched off so only the in-process layer answers (deterministic whatever the ambient
REVEAL_DISK_CACHE says). Controls: a PHP file whose result depends on a constant defined in another
file still re-extracts and follows an edit of that file; an edited file re-extracts while the others
hit; a changed build fingerprint misses the disk layer.
"""
import os
from collections import Counter
from pathlib import Path

import pytest

from reveal.adapters.depends import DependsAdapter
from reveal.analyzers.imports import generic
from reveal.analyzers.imports.base import ImportsDiskCache
from reveal.core import disk_cache

pytestmark = pytest.mark.component


@pytest.fixture
def counted(monkeypatch, tmp_path):
    """Per-file lookups of the generic extractor's cache and the extractions it had to run."""
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    generic._IMPORTS_CACHE.clear()
    counts = {"lookups": Counter(), "computed": Counter()}
    real_lookup = ImportsDiskCache.get_or_compute
    real_compute = generic._GenericTreeSitterImportExtractor._extract_imports_uncached

    def lookup(self, file_path, compute, *, owner):
        if self is generic._IMPORTS_CACHE:
            counts["lookups"][Path(file_path).name] += 1
        return real_lookup(self, file_path, compute, owner=owner)

    def compute(self, file_path, constant_index):
        counts["computed"][Path(file_path).name] += 1
        return real_compute(self, file_path, constant_index)

    monkeypatch.setattr(ImportsDiskCache, "get_or_compute", lookup)
    monkeypatch.setattr(generic._GenericTreeSitterImportExtractor, "_extract_imports_uncached", compute)
    yield counts
    generic._IMPORTS_CACHE.clear()


def _request(counts, target):
    """One depends:// answer, with the counts it caused (the counters restart at each request)."""
    for counter in counts.values():
        counter.clear()
    result = DependsAdapter(str(target)).get_structure()
    return result, {name: dict(counter) for name, counter in counts.items()}


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _rewrite(path: Path, text: str) -> None:
    """New content with a distinct mtime_ns, whatever the filesystem's timestamp resolution."""
    before = os.stat(path).st_mtime_ns
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(before + 1_000_000, before + 1_000_000))


def _kotlin(root: Path) -> Path:
    (root / ".git").mkdir(parents=True)
    target = _write(root / "src/app/util/Helper.kt", "package app.util\n\nclass Helper\n")
    _write(root / "src/app/Main.kt", "package app\n\nimport app.util.Helper\n\nfun main() { Helper() }\n")
    _write(root / "src/app/Other.kt", "package app\n\nimport app.util.Helper\n\nval h = Helper()\n")
    return target


def _dependents(result):
    return sorted(Path(d["file"]).name for d in result["dependents"])


def test_a_second_request_on_a_tree_without_php_reads_every_file_from_the_cache(counted, tmp_path):
    target = _kotlin(tmp_path / "proj")
    first, cold = _request(counted, target)
    second, warm = _request(counted, target)
    assert _dependents(first) == ["Main.kt", "Other.kt"]
    assert second == first
    assert cold["computed"] == {"Helper.kt": 1, "Main.kt": 1, "Other.kt": 1}
    # The bug: the empty constant index sent every file past the cache, so the warm request
    # looked nothing up and extracted all three again.
    assert warm["lookups"] == {"Helper.kt": 1, "Main.kt": 1, "Other.kt": 1}
    assert warm["computed"] == {}


def test_php_without_any_define_also_hits_the_cache(counted, tmp_path):
    root = tmp_path / "proj"
    _write(root / "composer.json", "{}\n")
    target = _write(root / "lib/util.php", "<?php\nfunction util() {}\n")
    _write(root / "main.php", "<?php\nrequire __DIR__ . '/lib/util.php';\n")
    first, _ = _request(counted, target)
    second, warm = _request(counted, target)
    assert _dependents(first) == ["main.php"] and second == first
    assert first["metadata"]["php_constants_indexed"] == 0
    assert warm["lookups"] == {"main.php": 1, "util.php": 1}
    assert warm["computed"] == {}


def test_a_language_that_never_reads_the_constant_index_hits_while_php_still_re_extracts(counted, tmp_path):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    _write(root / "config.php", "<?php\ndefine('BASE', __DIR__ . '/lib/');\n")
    _write(root / "lib/util.php", "<?php\nfunction util() {}\n")
    _write(root / "main.php", "<?php\nrequire BASE . 'util.php';\n")
    _write(root / "lib/helper.rb", "module Helper\nend\n")
    _write(root / "app.rb", "require_relative 'lib/helper'\n")
    first, _ = _request(counted, root)
    second, warm = _request(counted, root)
    assert first["metadata"]["php_constants_indexed"] == 1 and second == first
    modules = {m["module"]: m["dependents"] for m in first["modules"]}
    assert modules["lib/helper.rb"] == ["app.rb"] and modules["lib/util.php"] == ["main.php"]
    # Ruby has no concatenation includes: the index cannot change its imports.
    assert {name: warm["lookups"].get(name) for name in ("app.rb", "helper.rb")} == {"app.rb": 1, "helper.rb": 1}
    assert "app.rb" not in warm["computed"] and "helper.rb" not in warm["computed"]
    # PHP reads the index, so every PHP file is still extracted, never looked up.
    assert warm["computed"] == {"config.php": 1, "main.php": 1, "util.php": 1}
    assert not {"config.php", "main.php", "util.php"} & set(warm["lookups"])


def test_a_php_include_through_a_constant_follows_an_edit_of_the_defining_file(counted, tmp_path):
    """Negative control: the result of main.php depends on config.php, so an unchanged main.php
    must not be served from a cache keyed on its own stat."""
    root = tmp_path / "proj"
    _write(root / "composer.json", "{}\n")
    config = _write(root / "config.php", "<?php\ndefine('BASE', __DIR__ . '/lib/');\n")
    old = _write(root / "lib/util.php", "<?php\nfunction util() {}\n")
    new = _write(root / "lib2/util.php", "<?php\nfunction util2() {}\n")
    _write(root / "main.php", "<?php\nrequire BASE . 'util.php';\n")
    assert _dependents(_request(counted, old)[0]) == ["main.php"]
    assert _dependents(_request(counted, new)[0]) == []
    _rewrite(config, "<?php\ndefine('BASE', __DIR__ . '/lib2/');\n")
    moved, counts = _request(counted, new)
    assert _dependents(moved) == ["main.php"]
    assert _dependents(_request(counted, old)[0]) == []
    assert counts["computed"].get("main.php") == 1


def test_an_edited_file_is_extracted_again_while_the_others_hit(counted, tmp_path):
    target = _kotlin(tmp_path / "proj")
    _request(counted, target)
    _rewrite(tmp_path / "proj/src/app/Other.kt", "package app\n\nval h = 1\n")
    result, warm = _request(counted, target)
    assert _dependents(result) == ["Main.kt"]
    assert warm["computed"] == {"Other.kt": 1}
    assert warm["lookups"] == {"Helper.kt": 1, "Main.kt": 1, "Other.kt": 1}


@pytest.mark.disk_cache
def test_a_changed_build_fingerprint_misses_the_disk_layer(counted, tmp_path, monkeypatch):
    monkeypatch.setenv("REVEAL_DISK_CACHE", "1")
    target = _kotlin(tmp_path / "proj")
    first, _ = _request(counted, target)
    generic._IMPORTS_CACHE.clear()  # a new process: only the disk layer is left
    from_disk, warm = _request(counted, target)
    assert from_disk == first and warm["computed"] == {}
    generic._IMPORTS_CACHE.clear()
    monkeypatch.setattr(disk_cache, "build_fingerprint", lambda: "another-pack")
    rebuilt, cold = _request(counted, target)
    assert rebuilt == first
    assert cold["computed"] == {"Helper.kt": 1, "Main.kt": 1, "Other.kt": 1}
