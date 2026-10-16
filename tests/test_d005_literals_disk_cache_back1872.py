"""D005's per-file literal extraction is served from the disk cache for an unchanged file (BACK-1872)."""
import os

import pytest

from reveal.rules.duplicates import D005 as d005_mod
from reveal.rules.duplicates.D005 import D005, _build_index, _clear_index

pytestmark = [pytest.mark.component, pytest.mark.disk_cache]

LITERAL = 'NAMES = ["a", "b", "c", "d", "e"]\n'


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    _clear_index()
    yield
    _clear_index()


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname="scan"\n', encoding="utf-8")
    for i in range(3):
        (root / f"f{i}.py").write_text(LITERAL, encoding="utf-8")
    return root


def _index_of(root):
    return {key: sorted(occ) for key, occ in _build_index(root, D005()).items()}


def _count_parses(monkeypatch):
    calls = []
    real = d005_mod.parse_python

    def counting(content, *a, **k):
        calls.append(1)
        return real(content, *a, **k)

    monkeypatch.setattr(d005_mod, "parse_python", counting)
    return calls


def test_an_unchanged_file_is_not_parsed_again_and_the_index_is_identical(project, monkeypatch):
    first = _index_of(project)
    calls = _count_parses(monkeypatch)
    second = _index_of(project)
    assert first and second == first
    assert calls == []


def test_a_changed_file_is_extracted_again(project, monkeypatch):
    _index_of(project)
    target = project / "f0.py"
    target.write_text('OTHER = ["p", "q", "r", "s", "t"]\n', encoding="utf-8")
    os.utime(target, ns=(1, 2))  # a different mtime even on a coarse-clock filesystem
    calls = _count_parses(monkeypatch)
    index = _index_of(project)
    assert calls == [1]
    names = {name for occ in index.values() for _, _, name in occ}
    assert names == {"NAMES", "OTHER"}


def test_a_file_that_fails_to_parse_is_never_cached(project, monkeypatch):
    (project / "bad.py").write_text("def broken(\n", encoding="utf-8")
    first = _build_index(project, D005())
    assert first.scan_budget["failed_files"] == 1
    calls = _count_parses(monkeypatch)
    second = _build_index(project, D005())
    assert second.scan_budget["failed_files"] == 1
    assert calls == [1]  # only bad.py, parsed (and failing) again
    assert any("bad.py" in d for d in second.disclosures)


def test_the_answer_does_not_depend_on_the_cache(project, monkeypatch):
    cached = _index_of(project)
    _index_of(project)  # now served from the cache
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    assert _index_of(project) == cached
