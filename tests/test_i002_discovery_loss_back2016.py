"""I002's real source/target loss must qualify graphs and cache reuse.

Since BACK-2156 I002 builds through the analysis service: one discovery walk finds the graph
sources and the resolution targets together (``discover_import_files``), and the service's own
caches (``adapter_import_graph`` on disk) never store a build that lost a directory. I002's own
count walk, which only decides the scan limits, is not the graph's evidence.
"""

import importlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.analyzers.imports import service as import_service
from reveal.analyzers.imports.build_cache import _ADAPTER_IMPORT_GRAPH_NAMESPACE as GRAPH_NAMESPACE
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
    assert get.call_args_list, 'fixture: the disk layer is on'
    assert not [c for c in get.call_args_list if c.args[0] == GRAPH_NAMESPACE]
    assert not [c for c in put.call_args_list if c.args[0] == GRAPH_NAMESPACE]


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
        with patch.object(import_service, 'analyze', wraps=import_service.analyze) as extract:
            partial = rule._build_import_graph(root)
            assert rule._build_import_graph(root) is partial
            assert extract.call_count == 1
        actual = check(file)
        assert (actual.returncode, actual.stdout, actual.stderr) == (baseline.returncode, baseline.stdout, baseline.stderr)


@pytest.mark.disk_cache
@pytest.mark.parametrize('stage', ['count', 'build'])
def test_actual_phase_loss_keeps_cache_and_source_budget_ownership(tmp_path, monkeypatch, stage):
    """A loss in I002's count walk decides nothing the graph says; a loss in the build's own
    walk loses the target with the source walk (one walk), qualifies the budget and is never stored."""
    root = tmp_path / 'affected'
    source = write(root / 'visible.c', '#include "hidden.inc"\nint main(void) { return 0; }\n')
    child = root / 'included_child'
    target = write(child / 'deep' / 'hidden.inc', 'int helper(void);\n')
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    active = [None]
    real_discover = import_service.discover
    real_analyze = import_service.analyze
    real_scandir = os.scandir

    def discover(*args, **kwargs):
        previous = active[0]
        active[0] = previous or 'count'
        try:
            return real_discover(*args, **kwargs)
        finally:
            active[0] = previous

    def analyze(*args, **kwargs):
        active[0] = 'build'
        try:
            return real_analyze(*args, **kwargs)
        finally:
            active[0] = None

    def scandir(path):
        if Path(path) == child and active[0] == stage:
            raise PermissionError(13, f'controlled I002 {stage} loss', str(child))
        return real_scandir(path)

    monkeypatch.setattr(import_service, 'discover', discover)
    monkeypatch.setattr(import_service, 'analyze', analyze)
    monkeypatch.setattr(os, 'scandir', scandir)
    with patch.object(disk_cache, 'put', wraps=disk_cache.put) as put:
        graph = mod.I002()._build_import_graph(root)
    stored = [c for c in put.call_args_list if c.args[0] == GRAPH_NAMESPACE]
    assert len(stored) == (1 if stage == 'count' else 0)
    assert bool(graph.traversal_failures) is (stage == 'build')
    assert graph.scan_budget['analyzed_files'] == 1
    assert graph.scan_budget['exact'] is (stage == 'count')
    assert graph.dependencies.get(source, set()) == ({target} if stage == 'count' else set())


def test_unknown_location_only_memo_is_pruned_but_parse_and_cap_memos_stay(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; _, child = cycle(root)
    with monkeypatch.context() as context:
        deny(context, child, unknown=True)
        partial = mod.I002()._build_import_graph(root)
    assert partial.traversal_failures and all(path is None for path, _ in partial.traversal_failures)
    assert any('0 identified directory' in note and 'unknown directory' in note for note in mod.get_scan_disclosures())
    broken_root = tmp_path / 'broken'
    write(broken_root / 'broken.py', 'def broken(\n  value = (((\n')
    parsed = mod.I002()._build_import_graph(broken_root)
    assert parsed.failed_files and not parsed.traversal_failures
    cap_root = tmp_path / 'capped'
    write(cap_root / 'a.py', 'import math\n'); write(cap_root / 'b.py', 'import decimal\n')
    with monkeypatch.context() as context:
        context.setenv('REVEAL_I002_MAX_FILES', '1')
        capped = mod.I002()._build_import_graph(cap_root)
    assert capped.scan_skipped_reason and not capped.traversal_failures
    mod._evict_incomplete_graphs()
    assert root not in mod._graph_cache
    assert mod._graph_cache[broken_root] is parsed
    assert mod._graph_cache[cap_root] is capped


def test_repeated_actual_directory_loss_uses_unique_display_count_and_rule_filters(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    visible = write(root / 'visible.py', 'import math\n')
    write(root / 'pyproject.toml', '[project]\nname="bounded-disclosure"\n')
    children = {root / f'included_{n}' for n in range(7)}
    for child in children:
        write(child / 'hidden.py', 'import decimal\n')
    real = os.scandir

    def scandir(path):
        if Path(path) in children:
            raise PermissionError(13, 'controlled repeated I002 loss', str(path))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    graph = mod.I002()._build_import_graph(root)
    assert len(graph.traversal_failures) == 7  # one walk finds sources and resolution targets
    notes = mod.get_scan_disclosures([visible])
    assert len(notes) == 1 and '7 identified directory' in notes[0] and 'and 2 more' in notes[0]
    from reveal.rules.scan_caches import get_scan_disclosures
    assert get_scan_disclosures([visible], ['C901'], None) == []
    assert get_scan_disclosures([visible], ['I002'], None) == notes


def test_formatter_identity_and_rule_layer_do_not_require_adapters():
    import subprocess
    import sys
    from reveal.adapters.ast.analysis import traversal_failed_warning as compatibility
    from reveal.utils.path_utils import traversal_failed_warning

    assert compatibility is traversal_failed_warning
    subprocess.run([sys.executable, '-c',
                    'import sys; import reveal.rules.imports.I002; '
                    'assert not any(name.startswith("reveal.adapters") for name in sys.modules)'],
                   check=True, timeout=30)


def test_all_graph_sources_lost_are_incomplete_without_inventing_file_failures(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; child = root / 'included_child'
    write(root / 'pyproject.toml', '[project]\nname="all-loss"\n')
    source = write(child / 'a.py', 'from included_child.b import b\n\ndef a():\n    return b()\n')
    write(child / 'b.py', 'from included_child.a import a\n\ndef b():\n    return a()\n')
    assert check(source).returncode == 1
    mod._graph_cache.clear()
    deny(monkeypatch, child)
    result = check(source)
    assert result.returncode == 3
    graph = mod._graph_cache[root]
    assert graph.get_import_count() == 0
    assert graph.failed_files == graph.lost_files == []
    assert graph.scan_budget['analyzed_files'] == 0 and graph.scan_budget['exact'] is False
    assert any('missing file population is unknown' in reason for reason in json.loads(result.stdout)['scan_disclosures'])
