"""Required source/target discovery loss reaches existing Imports consumers."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.imports import ImportsAdapter, _ADAPTER_IMPORT_GRAPH_NAMESPACE
from reveal.core import disk_cache
from reveal.utils.exclusions import exclusion_scope

pytestmark = pytest.mark.component

QUERIES = ['', 'unused', 'circular', 'violations', 'rank=fan-in', 'entrypoints', 'components']


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def python_tree(root, survivors=True):
    child = root / 'included_child'
    write(child / 'hidden.py', 'import json\nVALUE = json.dumps({})\n')
    if survivors:
        write(root / 'visible.py', 'import stable\nVALUE = stable.VALUE\n')
        write(root / 'stable.py', 'import math\nVALUE = math.pi\n')
    return child


def deny(monkeypatch, child, unknown=False):
    real = os.scandir
    attempts = []

    def scandir(path):
        if Path(path) == child:
            attempts.append(Path(path))
            if unknown:
                raise PermissionError('controlled Imports unknown enumeration location')
            raise PermissionError(13, 'controlled Imports discovery consumer loss', str(child))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    return attempts


def traversal_warning(result, *, unknown=False):
    entries = [w for w in (result.get('meta') or {}).get('warnings', [])
               if w.get('type') == 'analysis_incomplete']
    assert len(entries) == 1
    warning = entries[0]
    assert warning['unit'] == 'directories'
    assert warning['count'] == (0 if unknown else 1)
    if unknown:
        assert warning['unknown_directory_events'] == 1
    else:
        assert warning['directories'] == ['included_child']
    assert 'PermissionError' in warning['message']
    assert 'missing file population is unknown' in warning['message']
    return warning


@pytest.mark.parametrize('policy', ['included', 'file_excluded', 'gitignored'])
def test_resolution_only_target_loss_reaches_private_and_public_consumers(tmp_path, monkeypatch, policy):
    root = tmp_path / 'project'
    source = write(root / 'visible.c', '#include "hidden.inc"\nint main(void) { return 0; }\n')
    child = root / 'included_child'
    target = write(child / 'deep' / 'hidden.inc', 'int helper(void);\n')
    if policy == 'gitignored':
        subprocess.run(['git', 'init', '-q', str(root)], check=True, timeout=20)
        write(root / '.gitignore', 'included_child/\n')
    patterns = ['included_child/deep/hidden.inc'] if policy == 'file_excluded' else []
    with exclusion_scope(root, patterns):
        clean = ImportsAdapter(str(root)); clean.get_structure()
        assert clean.analysis.graph.dependencies[source] == {target}
        with monkeypatch.context() as context:
            deny(context, child)
            adapter = ImportsAdapter(str(root))
            result = adapter.get_structure()
            assert len(adapter.analysis.scanned_files) == 1
            assert adapter.analysis.graph.get_import_count() == 1
            assert not adapter.analysis.graph.dependencies.get(source)
            warnings = adapter.integrity_warnings(root)
            assert len([w for w in warnings if w.get('type') == 'analysis_incomplete']) == 1
            traversal_warning(result)


@pytest.mark.parametrize('query', QUERIES)
@pytest.mark.parametrize('survivors', [True, False])
def test_all_imports_text_modes_disclose_loss_without_clean_claim(tmp_path, monkeypatch, query, survivors):
    root = tmp_path / 'project'; child = python_tree(root, survivors)
    deny(monkeypatch, child)
    uri = f'imports://{root}' + (f'?{query}' if query else '')
    machine = run(uri, '--format', 'json')
    assert machine.returncode == 0, machine.stderr
    result = json.loads(machine.stdout)
    assert result['metadata']['scanned_files'] == (2 if survivors else 0)
    traversal_warning(result)
    human = run(uri)
    assert human.returncode == 0, human.stderr
    assert human.stdout.count('missing file population is unknown') == 1
    assert '✅ No' not in human.stdout
    assert '(every file is imported by at least one other)' not in human.stdout


def test_unknown_loss_survives_json_projection_and_text_sidecar(tmp_path, monkeypatch):
    root = tmp_path / 'project'; child = python_tree(root)
    deny(monkeypatch, child, unknown=True)
    result = run(f'imports://{root}', '--format', 'json', '--fields', 'metadata')
    assert result.returncode == 0, result.stderr
    traversal_warning(json.loads(result.stdout), unknown=True)
    artifact = tmp_path / 'imports.json'
    text = run(f'imports://{root}?rank=fan-in&top=1', '--also-json', str(artifact))
    assert text.returncode == 0, text.stderr
    assert text.stdout.count('missing file population is unknown') == 1
    traversal_warning(json.loads(artifact.read_text(encoding='utf-8')), unknown=True)


@pytest.mark.disk_cache
def test_incomplete_graph_bypasses_real_disk_get_and_put_but_clean_reuse_survives(tmp_path, monkeypatch):
    root = tmp_path / 'project'; child = python_tree(root)
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    clean = ImportsAdapter(str(root)).get_structure()
    warm_adapter = ImportsAdapter(str(root))
    with patch.object(warm_adapter, '_process_extracted_files', wraps=warm_adapter._process_extracted_files) as extract:
        assert warm_adapter.get_structure() == clean
        assert extract.call_count == 0
    with monkeypatch.context() as context:
        deny(context, child)
        with patch.object(disk_cache, 'get', wraps=disk_cache.get) as get, patch.object(disk_cache, 'put', wraps=disk_cache.put) as put:
            partial = ImportsAdapter(str(root)).get_structure()
        assert partial['metadata']['scanned_files'] == 2
        assert not [c for c in get.call_args_list if c.args[0] == _ADAPTER_IMPORT_GRAPH_NAMESPACE]
        assert not [c for c in put.call_args_list if c.args[0] == _ADAPTER_IMPORT_GRAPH_NAMESPACE]
    recovered = ImportsAdapter(str(root)).get_structure()
    assert recovered == clean


@pytest.mark.parametrize('policy', ['reveal_ignore', 'reserved_noise', 'directory_excluded'])
def test_hard_policy_and_single_file_remain_exactly_unchanged(tmp_path, monkeypatch, policy):
    root = tmp_path / 'project'
    child = root / ('node_modules' if policy == 'reserved_noise' else 'included_child')
    write(child / 'hidden.py', 'import json\n')
    source = write(root / 'visible.py', 'import math\nVALUE = math.pi\n')
    if policy == 'reveal_ignore':
        monkeypatch.setenv('REVEAL_IGNORE', 'included_child/')
        from reveal.config import RevealConfig
        RevealConfig._cache.clear()
    patterns = ['included_child/'] if policy == 'directory_excluded' else []
    with exclusion_scope(root, patterns):
        baseline = ImportsAdapter(str(root)).get_structure()
        single = ImportsAdapter(str(source)).get_structure()
        attempts = deny(monkeypatch, child)
        assert ImportsAdapter(str(root)).get_structure() == baseline
        assert ImportsAdapter(str(source)).get_structure() == single
        assert attempts == []


def test_defaulted_evidence_preserves_constructors_and_empty_private_sink(tmp_path, monkeypatch):
    import pickle
    from dataclasses import FrozenInstanceError
    from reveal.analyzers.imports import service
    from reveal.analyzers.imports.base import get_all_extensions
    from reveal.analyzers.imports.file_index import discover_import_files
    from reveal.analyzers.imports.types import ImportGraph
    from reveal.registry import get_code_extensions

    files = service.ImportFileSet((), {}, False)
    assert files.traversal_failures == ()
    with pytest.raises(FrozenInstanceError):
        files.capped = True
    graph = ImportGraph({}, {}, {}, {}, [], [], None, {})
    assert graph.traversal_failures == []
    graph.traversal_failures.append((None, 'PermissionError: unknown location'))
    assert pickle.loads(pickle.dumps(graph)).traversal_failures == graph.traversal_failures
    root = tmp_path / 'project'; child = python_tree(root)
    assert len(discover_import_files(root, lambda p: p.suffix == '.py', 1)) == 3
    deny(monkeypatch, child)
    sink = []
    pair = ImportsAdapter._discover_candidate_files(
        root, frozenset(get_all_extensions()), get_code_extensions(), traversal_failures=sink)
    assert len(pair) == 2 and len(pair[0]) == 2
    assert len(sink) == 1 and sink[0][0] == child.as_posix()
    artifact = service.discover(service.ScanScope(root, frozenset({'.py'})))
    assert artifact.traversal_failures == tuple(sink)
