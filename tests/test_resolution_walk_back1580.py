"""BACK-1580: imports:// and depends:// build their graph and index with one walk.

The two copies had drifted: depends:// never gained REVEAL_IGNORE, file-level --exclude or the
declaration-only skip imports:// had (BACK-1362, BACK-1495, BACK-1467), and both gemspec walks
tested the absolute path, so a project under ~/.cache/ lost every gemspec.
"""
import pytest

from reveal.adapters.depends import DependsAdapter
from reveal.adapters.imports import ImportsAdapter
from reveal.analyzers.imports.file_index import (
    basename_index, discover_import_files, load_path_manifests,
)
from reveal.registry import get_code_extensions
from reveal.utils.exclusions import exclusion_scope


@pytest.fixture
def project(tmp_path, monkeypatch):
    from reveal.config import RevealConfig
    for rel in ('src/a.py', 'src/a.pyi', 'src/b.py', 'src/app.ts', 'gen/out.py',
                'ign/skip.py', '.github/scripts/ci.py'):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text('import os\n', encoding='utf-8')
    (tmp_path / '.git').mkdir()
    (tmp_path / '.gitignore').write_text('gen/\n', encoding='utf-8')
    monkeypatch.setenv('REVEAL_IGNORE', 'ign/')
    monkeypatch.setattr(RevealConfig, '_cache', {})
    return tmp_path


def _rel(root, paths):
    return sorted(p.relative_to(root).as_posix() for p in paths)


def test_imports_and_depends_see_the_same_graph_files(project):
    exts = frozenset({'.py', '.pyi', '.ts'})
    with exclusion_scope(project, ['b.py']):
        imports, _ = ImportsAdapter._discover_candidate_files(project, exts, get_code_extensions())
        depends, _ = DependsAdapter()._discover_files(project, exts)
    expected = ['.github/scripts/ci.py', 'src/a.py', 'src/app.ts']
    assert _rel(project, imports) == expected
    assert _rel(project, depends) == expected


def test_gitignored_and_excluded_files_stay_resolution_targets(project):
    with exclusion_scope(project, ['b.py']):
        graph, index, capped = discover_import_files(project, lambda p: p.suffix == '.py')
    assert 'out.py' in index and 'b.py' in index      # targets, not graph nodes
    assert 'skip.py' not in index                      # REVEAL_IGNORE: not part of the project
    assert _rel(project, graph) == ['.github/scripts/ci.py', 'src/a.py']
    assert not capped


def test_cap_stops_the_walk(project):
    graph, _, capped = discover_import_files(project, lambda p: p.suffix == '.py', cap=1)
    assert len(graph) == 1 and capped


def test_basename_index_for_search_path_callers(project):
    assert _rel(project, basename_index([project / 'src'])['a.py']) == ['src/a.py']


def test_gemspecs_under_a_cache_directory_are_found(tmp_path):
    root = tmp_path / '.cache' / 'proj'
    for rel in ('engines/billing/billing.gemspec', 'node_modules/x/x.gemspec'):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text('', encoding='utf-8')
    assert _rel(root, load_path_manifests(root, '*.gemspec')) == [
        'engines/billing/billing.gemspec']
