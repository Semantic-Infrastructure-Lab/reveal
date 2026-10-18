"""I002's real source/target loss must qualify graphs and cache reuse."""

import importlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.core import disk_cache

mod = importlib.import_module('reveal.rules.imports.I002')
pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def cycle(root):
    write(root / 'pyproject.toml', '[project]\nname="discovery-fixture"\n')
    visible = write(root / 'visible.py', 'from included_child.hidden import hidden\n\ndef visible():\n    return hidden()\n')
    child = root / 'included_child'
    write(child / 'hidden.py', 'from visible import visible\n\ndef hidden():\n    return visible()\n')
    return visible, child


def deny(monkeypatch, child, active=None, unknown=False):
    real = os.scandir
    attempts = []

    def scandir(path):
        if Path(path) == child and (active is None or active[0]):
            attempts.append(Path(path))
            if unknown:
                raise PermissionError('controlled unknown I002 enumeration location')
            raise PermissionError(13, 'controlled I002 discovery loss', str(child))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    return attempts


def check(path):
    return run(str(path), '--check', '--select', 'I002', '--format', 'json')


def test_real_source_loss_qualifies_check_and_keeps_surviving_graph(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; visible, child = cycle(root)
    assert check(visible).returncode == 1
    mod._graph_cache.clear()
    with monkeypatch.context() as context:
        deny(context, child)
        result = check(visible)
        graph = mod._graph_cache[root]
        assert graph.get_import_count() == 1
        assert sum(map(len, graph.dependencies.values())) == 1
        assert result.returncode == 3
        payload = json.loads(result.stdout)
        assert any('directory' in note and 'PermissionError' in note for note in payload['scan_disclosures'])
        assert graph.traversal_failures


def test_real_target_only_loss_reaches_graph_disclosure(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    source = write(root / 'visible.c', '#include "hidden.inc"\nint main(void) { return 0; }\n')
    child = root / 'included_child'
    target = write(child / 'deep' / 'hidden.inc', 'int helper(void);\n')
    clean = mod.I002()._build_import_graph(root)
    assert clean.dependencies[source] == {target}
    mod._graph_cache.clear()
    deny(monkeypatch, child)
    graph = mod.I002()._build_import_graph(root)
    assert graph.get_import_count() == 1 and not graph.dependencies
    assert graph.traversal_failures
    assert any('PermissionError' in note for note in mod.get_scan_disclosures())


@pytest.mark.disk_cache
def test_real_loss_disables_graph_disk_backing(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; _, child = cycle(root)
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    deny(monkeypatch, child)
    with patch.object(disk_cache, 'get', wraps=disk_cache.get) as get, patch.object(disk_cache, 'put', wraps=disk_cache.put) as put:
        graph = mod.I002()._build_import_graph(root)
    assert graph.get_import_count() == 1
    assert not [c for c in get.call_args_list if c.args[0] == mod._IMPORT_GRAPH_NAMESPACE]
    assert not [c for c in put.call_args_list if c.args[0] == mod._IMPORT_GRAPH_NAMESPACE]


def test_actual_source_loss_budget_is_lower_bound(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; _, child = cycle(root)
    deny(monkeypatch, child)
    graph = mod.I002()._build_import_graph(root)
    assert graph.scan_budget['analyzed_files'] == 1
    assert graph.scan_budget['exact'] is False


def test_transient_build_loss_recovered_before_seal_cannot_hide_next_mcp_cycle(tmp_path, monkeypatch):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    from reveal.utils import request_cache

    root = tmp_path / 'affected'; visible, child = cycle(root)
    original_build = mod.I002._build_import_graph
    active = [False]

    def build(self, directory):
        active[0] = True
        try:
            return original_build(self, directory)
        finally:
            active[0] = False

    with monkeypatch.context() as context:
        attempts = deny(context, child, active)
        context.setattr(mod.I002, '_build_import_graph', build)
        first = reveal_check(str(visible), select='I002')
        assert attempts
    # Recovered tree stamps alone cannot certify that the graph had complete input.
    assert request_cache._tree_stamp(root) is not None
    partial = mod._graph_cache[root]
    repaired = reveal_check(str(visible), select='I002')
    assert 'Circular dependency detected' in repaired
    assert mod._graph_cache[root] is not partial
    assert 'PermissionError' in first


def test_clean_graph_same_invocation_reuse_and_sibling_remain_exact(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; _, child = cycle(root)
    sibling = tmp_path / 'sibling'; file = write(sibling / 'clean.py', 'VALUE = 1\n')
    baseline = check(file)
    mod._graph_cache.clear()
    rule = mod.I002()
    with monkeypatch.context() as context:
        deny(context, child)
        with patch.object(rule, '_collect_raw_imports', wraps=rule._collect_raw_imports) as extract:
            partial = rule._build_import_graph(root)
            assert rule._build_import_graph(root) is partial
            assert extract.call_count == 1
        actual = check(file)
        assert (actual.returncode, actual.stdout, actual.stderr) == (baseline.returncode, baseline.stdout, baseline.stderr)
