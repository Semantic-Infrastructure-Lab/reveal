"""BACK-2565: a focused import build (service.project_scope below the project root) indexes the
whole root but extracts and resolves only the focus's files, plus the files of languages whose
declarations other files resolve through, and answers exactly like the whole-root build for
every focus file. Calls' callee resolution (BACK-2553) reads it, so a sub-directory walk in a
large project no longer pays the whole project's import graph.
"""

import os
import sys
import textwrap
from pathlib import Path
from typing import Dict

import pytest

from reveal.analyzers.imports import resolution, service
from reveal.analyzers.imports.file_index import under_directory
from reveal.analyzers.imports.resolution import path_is_under


def _tree(root: Path, files: Dict[str, str]) -> Path:
    (root / '.git').mkdir(parents=True)  # the project marker the scan-root climb stops at
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding='utf-8')
    return root


PYTHON = {
    'pkg/a.py': 'import json\nfrom pkg import b\n\ndef run():\n    return b.go(json.loads("1"))\n',
    'pkg/b.py': 'def go(x):\n    return x\n',
    'other/c.py': 'import os\nfrom pkg import a\n',
}

CSHARP = {
    # The file's path does not spell its namespace, so only the namespace index finds it.
    'Lib/Helpers.cs': 'namespace Lib.Util { public class Helper { } }\n',
    'App/Main.cs': 'using Lib.Util;\nnamespace App { class Main { void Run() { var h = new Helper(); } } }\n',
}


def _facts(analysis, path: Path):
    ext = analysis.extractions[path]
    return [(s.module_name, s.resolved_path, s.intra_verdict) for s in ext.imports]


@pytest.fixture
def no_disk_cache(monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


def test_a_focused_build_extracts_only_the_focus_and_answers_like_the_whole_root(tmp_path, no_disk_cache):
    root = _tree(tmp_path / 'proj', PYTHON)
    scope = service.project_scope(root / 'pkg')
    assert (scope.root, scope.focus, scope.focus_only) == (root, root / 'pkg', True)
    focused = service.analyze(scope).analysis
    full = service.analyze(service.path_scope(root)).analysis
    assert set(focused.extractions) == {root / 'pkg/a.py', root / 'pkg/b.py'}
    assert focused.resolved_at == root / 'pkg' and full.resolved_at is None
    assert root / 'other/c.py' in full.extractions
    for path in (root / 'pkg/a.py', root / 'pkg/b.py'):
        assert _facts(focused, path) == _facts(full, path)
    assert _facts(focused, root / 'pkg/a.py') == [('json', None, False), ('pkg', root / 'pkg', None)]


def test_a_project_root_target_is_not_focused(tmp_path, no_disk_cache):
    root = _tree(tmp_path / 'proj', PYTHON)
    scope = service.project_scope(root)
    assert scope.focus is None and not scope.focus_only
    assert root / 'other/c.py' in service.analyze(scope).analysis.extractions


def test_a_relative_focus_is_spelled_like_its_candidates(tmp_path, no_disk_cache, monkeypatch):
    root = _tree(tmp_path / 'proj', PYTHON)
    monkeypatch.chdir(tmp_path)
    focused = service.analyze(service.project_scope(Path('proj/pkg'))).analysis
    assert set(focused.extractions) == {Path('proj/pkg/a.py'), Path('proj/pkg/b.py')}
    full = service.analyze(service.path_scope(root)).analysis
    relative = [(m, p.relative_to(tmp_path) if p else None, v) for m, p, v in _facts(full, root / 'pkg/a.py')]
    assert _facts(focused, Path('proj/pkg/a.py')) == relative


def test_a_namespace_declared_outside_the_focus_still_resolves(tmp_path, no_disk_cache):
    root = _tree(tmp_path / 'sln', CSHARP)
    focused = service.analyze(service.project_scope(root / 'App')).analysis
    full = service.analyze(service.path_scope(root)).analysis
    main = root / 'App/Main.cs'
    assert _facts(full, main) == [('Lib.Util', root / 'Lib/Helpers.cs', None)]
    assert _facts(focused, main) == _facts(full, main)
    assert root / 'Lib/Helpers.cs' in focused.extractions   # C# declarations are indexed project-wide
    assert root / 'Lib/Helpers.cs' not in focused.graph.dependencies   # but not resolved


def test_red_control_without_project_declarations_the_namespace_import_is_lost(tmp_path, no_disk_cache,
                                                                               monkeypatch):
    root = _tree(tmp_path / 'sln', CSHARP)
    monkeypatch.setattr(resolution, 'indexes_project_declarations', lambda extractor: False)
    focused = service.analyze(service.project_scope(root / 'App')).analysis
    assert _facts(focused, root / 'App/Main.cs')[0][1] is None


@pytest.fixture
def disk_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')


@pytest.mark.disk_cache
def test_a_cached_whole_root_build_answers_a_focused_request(tmp_path, disk_cache, monkeypatch):
    root = _tree(tmp_path / 'proj', PYTHON)
    full = service.analyze(service.path_scope(root)).analysis
    assert full.resolved_at is None

    def no_build(*args, **kwargs):
        raise AssertionError('the cached whole-root build should have answered')
    monkeypatch.setattr(service, '_extract_and_resolve', no_build)
    served = service.analyze(service.project_scope(root / 'pkg')).analysis
    assert served.resolved_at is None and root / 'other/c.py' in served.extractions


@pytest.mark.disk_cache
def test_a_cached_focused_build_is_never_served_to_a_whole_root_request(tmp_path, disk_cache):
    root = _tree(tmp_path / 'proj', PYTHON)
    assert service.analyze(service.project_scope(root / 'pkg')).analysis.resolved_at == root / 'pkg'
    whole = service.analyze(service.path_scope(root)).analysis
    assert whole.resolved_at is None and root / 'other/c.py' in whole.extractions
    # The whole-root build just cached now answers every focus.
    other = service.analyze(service.project_scope(root / 'other')).analysis
    assert other.resolved_at is None and root / 'pkg/a.py' in other.extractions


@pytest.mark.disk_cache
def test_an_edit_at_the_focus_rebuilds_the_focused_build(tmp_path, disk_cache):
    root = _tree(tmp_path / 'proj', PYTHON)
    first = service.analyze(service.project_scope(root / 'pkg')).analysis
    warm = service.analyze(service.project_scope(root / 'pkg')).analysis
    assert [m for m, _, _ in _facts(first, root / 'pkg/b.py')] == [] == [m for m, _, _ in _facts(warm, root / 'pkg/b.py')]
    b = root / 'pkg/b.py'
    b.write_text('import re\n' + b.read_text(encoding='utf-8'), encoding='utf-8')
    os.utime(b, ns=(b.stat().st_atime_ns, b.stat().st_mtime_ns + 10_000_000))
    edited = service.analyze(service.project_scope(root / 'pkg')).analysis
    assert [m for m, _, _ in _facts(edited, b)] == ['re']


@pytest.mark.parametrize('path, directory', [
    ('a/b', 'a'), ('a', 'a'), ('ab', 'a'), ('a/b/c', 'a/b'), ('a/b', 'a/b/c'), ('a', '.'), ('.', '.'),
    ('../p/a.py', '../p'), ('../q', '../p'),
])
def test_under_directory_agrees_with_path_is_under(path, directory):
    assert under_directory(Path(directory))(Path(path)) == path_is_under(Path(path), Path(directory))


def test_under_directory_agrees_on_absolute_paths(tmp_path):
    inside, sibling = tmp_path / 'x' / 'y', tmp_path / 'xy'
    for path in (inside, sibling, tmp_path / 'x', tmp_path):
        assert under_directory(tmp_path / 'x')(path) == path_is_under(path, tmp_path / 'x')
    anchor = Path(tmp_path.anchor)
    assert under_directory(anchor)(inside) and path_is_under(inside, anchor)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows paths compare case-insensitively')
def test_under_directory_is_case_insensitive_where_paths_are(tmp_path):
    upper = Path(str(tmp_path).upper())
    assert under_directory(upper)(tmp_path / 'a.py') == path_is_under(tmp_path / 'a.py', upper) is True
