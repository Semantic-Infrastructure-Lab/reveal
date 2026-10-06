"""Complete diagnostic artifacts survive cold, memory and disk reads (BACK-1491)."""
import pytest

from reveal.analyzers.imports.base import ImportsDiskCache
from reveal.analyzers.imports.types import ImportStatement
from reveal.analyzers.imports.python import PythonExtractor
import importlib

pytestmark = pytest.mark.component


@pytest.fixture(autouse=True)
def _disk_cache_on(monkeypatch):
    """These tests read back from the disk cache. scripts/ci-local.sh exports
    REVEAL_DISK_CACHE=0 for the whole run, so they enable it themselves."""
    monkeypatch.delenv("REVEAL_DISK_CACHE", raising=False)


def test_nested_diagnostics_and_caller_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    path = tmp_path / 'a.py'
    path.write_text('import os\n', encoding='utf-8')
    cache = ImportsDiskCache('artifact_negative_control')
    owner = PythonExtractor()

    def compute():
        owner.analysis.diagnostics = {'future': {'warnings': ['partial']}}
        owner.parse_failed = True
        return [ImportStatement(path, 1, 'os', ['os'], False, 'import')]

    cache.get_or_compute(path, compute, owner=owner)
    expected = {'future': {'warnings': ['partial']}}
    owner.analysis.diagnostics['future']['warnings'].clear()
    for disk in (False, True):
        if disk:
            cache.clear()
        cache.get_or_compute(path, lambda: pytest.fail('warm read recomputed'), owner=owner)
        assert owner.analysis.diagnostics == expected
        assert owner.parse_failed
        owner.analysis.diagnostics['future']['warnings'].append('caller mutation')


def test_i002_disclosures_survive_graph_cache(tmp_path, monkeypatch):
    mod = importlib.import_module('reveal.rules.imports.I002')
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    mod._graph_cache.clear()
    (tmp_path / 'broken.py').write_text('def f(\n x = (((\n', encoding='utf-8')
    rule = mod.I002()
    cold = rule._build_import_graph(tmp_path)
    assert cold.failed_files
    expected = mod.get_scan_disclosures()
    assert expected and 'incomplete' in expected[0]
    assert rule._build_import_graph(tmp_path) == cold
    assert mod.get_scan_disclosures() == expected
    mod._graph_cache.clear()
    monkeypatch.setattr(rule, '_collect_raw_imports', lambda path: pytest.fail('disk hit recomputed'))
    assert rule._build_import_graph(tmp_path) == cold
    assert mod.get_scan_disclosures() == expected
    mod._graph_cache.clear()


def test_markdown_link_graph_warm_equals_cold(tmp_path, monkeypatch):
    from reveal.adapters.markdown import operations
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    (tmp_path / 'a.md').write_text('[B](b.md)\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('# B\n', encoding='utf-8')
    cold = operations.build_link_graph(tmp_path)
    assert cold['total_edges'] == 1
    monkeypatch.setattr(operations.files, 'extract_internal_links',
                        lambda *args: pytest.fail('warm graph re-extracted'))
    assert operations.build_link_graph(tmp_path) == cold
