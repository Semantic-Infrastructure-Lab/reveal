"""Projection delegation preserves the adapter's state before a scan exists."""
import pytest

from reveal.adapters.imports import ImportsAdapter
from reveal.analyzers.imports.types import ImportGraph, LAZY_INCLUDE

pytestmark = pytest.mark.component


def test_prebuild_helpers_do_not_invent_a_completed_scan(tmp_path):
    adapter = ImportsAdapter(str(tmp_path))
    assert adapter.get_metadata() == {'status': 'not_analyzed'}
    assert adapter.outside_root_edge_count() == 0
    assert adapter._in_scope(tmp_path.parent / 'sibling.py') is True


def test_graph_without_scan_keeps_existing_unrestricted_view(tmp_path):
    adapter = ImportsAdapter(str(tmp_path))
    graph = ImportGraph()
    graph.add_dependency(tmp_path / 'a.py', tmp_path.parent / 'sibling.py')
    adapter.analysis.graph = graph
    assert adapter._edges(LAZY_INCLUDE) is graph
    assert adapter._in_scope(tmp_path.parent / 'sibling.py') is True
