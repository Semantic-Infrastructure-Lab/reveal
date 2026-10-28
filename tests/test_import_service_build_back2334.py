"""The public import analysis operation builds without a resource adapter."""

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path

import pytest

from reveal.adapters.imports import ImportsAdapter
from reveal.analyzers.imports import service
from reveal.analyzers.imports.base import get_all_extensions
from reveal.registry import get_code_extensions
from reveal.utils.request_cache import host_request

pytestmark = pytest.mark.component


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    for name, content in {'a.py': 'import bb\n', 'bb.py': 'VALUE = 1\n',
                          'main.js': "import { value } from './leaf.js';\n",
                          'leaf.js': 'export const value = 1;\n'}.items():
        (root / name).write_text(content, encoding='utf-8')
    return root


def _scope(root):
    return service.ScanScope(root, frozenset(get_all_extensions()), get_code_extensions(), cap=5000)


def _edges(analysis):
    return {p.name: sorted(t.name for t in targets)
            for p, targets in analysis.graph.dependencies.items()}


def test_existing_adapter_sibling_keeps_edges_and_failed_file_counts(tree):
    sibling = ImportsAdapter(str(tree), 'scope=path').analyze()
    assert _edges(sibling) == {'a.py': ['bb.py'], 'main.js': ['leaf.js']}
    assert sibling.files_failed == []


def test_public_service_retains_real_multilanguage_edges_and_diagnostics(tree):
    built = service.analyze(_scope(tree))
    sibling = ImportsAdapter(str(tree), 'scope=path').analyze()
    assert _edges(built.analysis) == _edges(sibling) == {'a.py': ['bb.py'], 'main.js': ['leaf.js']}
    assert built.analysis.files_failed == sibling.files_failed == []
    assert built.analysis.extractions.keys() == sibling.extractions.keys()
    assert set(built.files.candidates) == built.analysis.scanned_files
    assert built.structures == []


def test_service_host_warm_and_after_edit_match_uncached_answer(tree):
    with host_request():
        cold = service.analyze(_scope(tree))
        warm = service.analyze(_scope(tree))
        assert warm.analysis is cold.analysis
        assert warm.files is not cold.files  # discovery disclosures are request-local
    (tree / 'a.py').write_text('VALUE = 12\n', encoding='utf-8')
    with host_request():
        edited = service.analyze(_scope(tree))
    direct = service.analyze(_scope(tree))
    assert _edges(edited.analysis) == _edges(direct.analysis) == {'main.js': ['leaf.js']}


def test_structures_and_notifications_never_enter_shared_graph_memo(tree):
    from reveal.adapters.ast.analysis import analyze_file_outcome
    seen = []
    with host_request():
        ordinary = service.analyze(_scope(tree))
        combined = service.analyze(_scope(tree), structure_reader=analyze_file_outcome,
                                   on_file_processed=seen.append)
        warm = service.analyze(_scope(tree))
    assert seen == list(combined.files.candidates)
    assert len(combined.structures) == 4
    assert warm.analysis is ordinary.analysis
    assert ordinary.structures == warm.structures == []
    assert not hasattr(combined.analysis, 'structures')
    assert _edges(combined.analysis) == _edges(ordinary.analysis)


@pytest.mark.parametrize('start_method', ['spawn', 'forkserver'])
def test_real_worker_can_pickle_optional_existing_structure_reader(tree, start_method):
    if start_method not in multiprocessing.get_all_start_methods():
        pytest.skip(f'{start_method} is unavailable')
    from reveal.adapters.ast.analysis import analyze_file_outcome
    from reveal.analyzers.imports.extraction import extract_chunk
    paths = [str(tree / 'a.py'), str(tree / 'bb.py')]
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context(start_method)) as pool:
        rows = pool.submit(extract_chunk, (paths, analyze_file_outcome, None)).result(timeout=60)
    assert [row[0] for row in rows] == paths
    assert [row[3]['file'] for row in rows] == paths
    assert all(row[5] is None for row in rows)


def test_service_scoped_family_and_cap_preserve_build_inputs(tree):
    scoped = service.analyze(service.ScanScope(tree, frozenset({'.py'}), cap=1))
    assert len(scoped.analysis.scanned_files) == 1
    assert scoped.analysis.resolution.capped
    assert scoped.analysis.resolution.scan_accounting.limit == 1
    assert {p.suffix for p in scoped.files.candidates} == {'.py'}
