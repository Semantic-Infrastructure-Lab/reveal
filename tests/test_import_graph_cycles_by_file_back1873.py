"""ImportGraph.cycles_by_file: the cycle search runs once per graph, not once per file (BACK-1873)."""

from pathlib import Path

from reveal.analyzers.imports.types import ImportGraph


def _graph(edges):
    graph = ImportGraph()
    for src, dst in edges:
        graph.files.setdefault(Path(src), [])
        graph.files.setdefault(Path(dst), [])
        graph.add_dependency(Path(src), Path(dst))
    return graph


def test_matches_filtering_find_cycles():
    graph = _graph([("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("d", "e")])
    cycles = graph.find_cycles()
    assert cycles, "fixture must contain a real cycle"
    index = graph.cycles_by_file()
    for path in graph.files:
        assert index.get(path, []) == [c for c in cycles if path in c]
    assert Path("d") not in index and Path("e") not in index


def test_search_runs_once_for_all_lookups(monkeypatch):
    graph = _graph([("a", "b"), ("b", "a")])
    calls = []
    real = ImportGraph.find_cycles
    monkeypatch.setattr(ImportGraph, "find_cycles",
                        lambda self: calls.append(1) or real(self))
    for path in graph.files:
        graph.cycles_by_file().get(path)
    assert len(calls) == 1


def test_add_dependency_invalidates_the_index():
    graph = _graph([("a", "b")])
    assert graph.cycles_by_file() == {}
    graph.add_dependency(Path("b"), Path("a"))
    assert Path("a") in graph.cycles_by_file()
