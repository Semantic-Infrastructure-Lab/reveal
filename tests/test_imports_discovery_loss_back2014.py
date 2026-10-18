"""Required resolution discovery loss survives the Imports producer and cache boundary."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from reveal.adapters.imports import ImportsAdapter, ImportsRenderer, _ADAPTER_IMPORT_GRAPH_NAMESPACE
from reveal.analyzers.imports import service
from reveal.core import disk_cache


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def make_tree(root, *, survivors=True, target_only=False):
    child = root / 'included_child'
    if target_only:
        write(root / 'visible.c', '#include "hidden.inc"\nint main(void) { return 0; }\n')
        write(child / 'deep' / 'hidden.inc', 'int helper(void);\n')
    else:
        write(child / 'hidden.py', 'import decimal\n')
        if survivors:
            write(root / 'visible.py', 'import math\n')
    return child


def deny_child(monkeypatch, child):
    real = os.scandir

    def scandir(directory):
        if Path(directory) == child:
            raise PermissionError(13, 'controlled Imports directory loss', str(child))
        return real(directory)

    monkeypatch.setattr(os, 'scandir', scandir)


def discovery_warning(result):
    warnings = [w for w in result.get('meta', {}).get('warnings', [])
                if w.get('type') == 'analysis_incomplete']
    assert len(warnings) == 1, 'known failed resolution discovery must reach the public answer'
    return warnings[0]


def assert_loss(result):
    warning = discovery_warning(result)
    assert warning['unit'] == 'directories'
    assert warning['count'] == 1
    assert warning['directories'] == ['included_child']
    assert 'PermissionError' in warning['message']
    assert 'missing file population is unknown' in warning['message']
    return warning


@pytest.mark.parametrize('survivors', [False, True])
def test_actual_source_discovery_loss_reaches_public_and_integrity_answers(tmp_path, monkeypatch, survivors):
    root, sibling = tmp_path / 'affected', tmp_path / 'sibling'
    child = make_tree(root, survivors=survivors)
    make_tree(sibling)
    clean_sibling = ImportsAdapter(str(sibling)).get_structure()
    with monkeypatch.context() as context:
        deny_child(context, child)
        adapter = ImportsAdapter(str(root))
        result = adapter.get_structure()
        assert result['metadata']['scanned_files'] == int(survivors)
        assert result['metadata']['total_imports'] == int(survivors)
        assert ImportsAdapter(str(sibling)).get_structure() == clean_sibling
        warning = assert_loss(result)
        assert warning in adapter.integrity_warnings(root)
    repaired = adapter.get_structure()
    assert repaired['metadata']['total_imports'] == 1 + int(survivors)
    assert not any(w.get('type') == 'analysis_incomplete' for w in repaired.get('meta', {}).get('warnings', []))


def test_actual_target_only_loss_keeps_source_counts_but_qualifies_missing_edge(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    child = make_tree(root, target_only=True)
    clean = ImportsAdapter(str(root))
    clean_result = clean.get_structure()
    assert sum(map(len, clean.analysis.graph.dependencies.values())) == 1
    deny_child(monkeypatch, child)
    adapter = ImportsAdapter(str(root))
    result = adapter.get_structure()
    assert result['metadata']['scanned_files'] == clean_result['metadata']['scanned_files'] == 1
    assert result['metadata']['total_imports'] == clean_result['metadata']['total_imports'] == 1
    assert not adapter.analysis.graph.dependencies
    assert_loss(result)


@pytest.mark.disk_cache
@pytest.mark.parametrize('target_only', [False, True])
def test_incomplete_actual_disk_backing_is_never_read_or_written(tmp_path, monkeypatch, target_only):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    root = tmp_path / 'affected'
    child = make_tree(root, target_only=target_only)
    with monkeypatch.context() as context:
        deny_child(context, child)
        with patch.object(disk_cache, 'get', wraps=disk_cache.get) as get, patch.object(disk_cache, 'put', wraps=disk_cache.put) as put:
            first = ImportsAdapter(str(root))
            first.get_structure()
            second = ImportsAdapter(str(root))
            with patch.object(second, '_process_extracted_files', wraps=second._process_extracted_files) as extract:
                second.get_structure()
            assert extract.call_count == 1, 'a retained partial graph must not replace required analysis'
            assert not [call for call in get.call_args_list if call.args[0] == _ADAPTER_IMPORT_GRAPH_NAMESPACE]
            assert not [call for call in put.call_args_list if call.args[0] == _ADAPTER_IMPORT_GRAPH_NAMESPACE]
        assert not disk_cache._namespace_dir(_ADAPTER_IMPORT_GRAPH_NAMESPACE).exists()
    recovered = ImportsAdapter(str(root))
    recovered.get_structure()
    assert recovered.analysis.graph.get_import_count() == (1 if target_only else 2)
    assert sum(map(len, recovered.analysis.graph.dependencies.values())) == int(target_only)
    assert disk_cache._namespace_dir(_ADAPTER_IMPORT_GRAPH_NAMESPACE).exists()


@pytest.mark.disk_cache
def test_clean_actual_graph_disk_cache_preserves_full_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    root = tmp_path / 'healthy'
    make_tree(root)
    first = ImportsAdapter(str(root))
    result = first.get_structure()
    second = ImportsAdapter(str(root))
    with patch.object(second, '_process_extracted_files', wraps=second._process_extracted_files) as extract:
        assert second.get_structure() == result
    assert extract.call_count == 0
    assert second.analysis == first.analysis


@pytest.mark.parametrize('query', ['', 'circular', 'unused', 'violations', 'rank=fan-in', 'entrypoints', 'components'])
def test_actual_loss_text_once_and_json_parseable(tmp_path, monkeypatch, capsys, query):
    root = tmp_path / 'affected'
    child = make_tree(root)
    deny_child(monkeypatch, child)
    result = ImportsAdapter(str(root), query).get_structure()
    ImportsRenderer.render_structure(result)
    output = capsys.readouterr()
    assert output.out.count('missing file population is unknown') == 1
    if query == 'circular':
        assert 'No circular dependencies found!' not in output.out
    ImportsRenderer.render_structure(result, 'json')
    output = capsys.readouterr()
    assert_loss(json.loads(output.out))
    assert not output.err


def test_exact_healthy_single_file_and_hard_excluded_controls(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    child = make_tree(root)
    source = root / 'visible.py'
    single = ImportsAdapter(str(source)).get_structure()
    # REVEAL_IGNORE removes inputs from both source and target populations. Soft
    # --exclude/gitignore paths remain resolution targets and are tested separately.
    monkeypatch.setenv('REVEAL_IGNORE', 'included_child/')
    excluded = ImportsAdapter(str(root)).get_structure()
    deny_child(monkeypatch, child)
    assert ImportsAdapter(str(source)).get_structure() == single
    assert ImportsAdapter(str(root)).get_structure() == excluded


@pytest.mark.parametrize('query,forbidden', [
    ('unused', '✅ No unused imports found'),
    ('circular', '✅ No circular dependencies found'),
    ('entrypoints', 'every file is imported by at least one other'),
    ('', 'only one file scanned'),
    ('violations', '✅ No violations'),
])
def test_directory_loss_does_not_render_definitive_clean_conclusions(tmp_path, monkeypatch, capsys, query, forbidden):
    root = tmp_path / 'affected'
    child = make_tree(root, survivors=False)
    if query != 'entrypoints':
        write(root / 'visible.py', 'VALUE = 1\n')
    if query == 'violations':
        write(root / '.reveal.yaml', 'architecture:\n  layers:\n    - name: app\n      paths: [app/]\n      allow_imports: []\n      deny_imports: [db/]\n')
    deny_child(monkeypatch, child)
    result = ImportsAdapter(str(root), query).get_structure()
    ImportsRenderer.render_structure(result)
    output = capsys.readouterr().out
    assert forbidden not in output
    assert 'analysis is incomplete' in output or 'discovery incomplete' in output
