"""A relative target climbs to its project root like an absolute one (BACK-2572).

``resolve_project_root`` climbed the path as typed, and a relative spelling has no ancestors past
'.': ``Path('.').parent`` is ``Path('.')``. So from inside a package, ``calls://.?callees=`` (and
ast://'s ``resolved_calls``) read the import analysis of '.' alone, and a tsconfig ``paths`` alias or
a sibling package declared above it read as outside the tree, while ``imports://.`` (which resolves
its target first) climbed. The climb now runs from the absolute directory, and a relative target
gets its root back relative to the cwd.
"""

from pathlib import Path

from reveal.adapters.calls.adapter import CallsAdapter
from reveal.analyzers.imports import resolution
from reveal.utils import path_utils


def _tree(root: Path, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding='utf-8')
    return root


ALIASED = {
    'package.json': '{"name": "p"}\n',  # the root marker; tsconfig.json is not one
    'tsconfig.json': '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["app/*"]}}}\n',
    'app/main.ts': "import { helper } from '@app/b';\n\nexport function go() {\n  helper();\n}\n",
    'app/a.ts': 'export function helper() {}\n',
    'app/b.ts': 'export function helper() {}\n',
}


def test_a_relative_directory_climbs_to_the_marker_above_the_cwd(tmp_path, monkeypatch):
    _tree(tmp_path, {'pyproject.toml': '[project]\nname = "p"\n', 'pkg/__init__.py': ''})
    monkeypatch.chdir(tmp_path / 'pkg')
    path_utils._marker_root_cache.clear()
    assert path_utils.resolve_project_root(Path('.')) == Path('..')
    assert resolution.choose_scan_root(Path('.')).root == Path('..')
    monkeypatch.chdir(tmp_path)
    # Same tree, other spellings: the root comes back relative to the cwd.
    assert path_utils.resolve_project_root(Path('pkg')) == Path('.')
    assert path_utils.resolve_project_root(tmp_path / 'pkg') == tmp_path


def test_the_climb_cache_is_keyed_by_the_directory_not_its_spelling(tmp_path, monkeypatch):
    # Before: the key was Path('.') as typed, so the answer for one cwd was served in another.
    _tree(tmp_path, {'one/pyproject.toml': '[project]\nname = "one"\n', 'one/sub/x.py': '',
                     'two/sub/x.py': ''})
    path_utils._marker_root_cache.clear()
    monkeypatch.chdir(tmp_path / 'one' / 'sub')
    assert path_utils.resolve_project_root(Path('.')) == Path('..')
    monkeypatch.chdir(tmp_path / 'two' / 'sub')
    assert path_utils.resolve_project_root(Path('.'), use_vcs=False) is None


def test_a_callee_walk_spelled_dot_reads_the_alias_declared_above_it(tmp_path, monkeypatch):
    # Before: '@app/b' did not resolve from root '.', so helper() read as external.
    _tree(tmp_path, ALIASED)
    monkeypatch.chdir(tmp_path / 'app')
    path_utils._marker_root_cache.clear()
    result = CallsAdapter('.', 'callees=main.ts:go&depth=2').get_structure()
    edge = next(e for level in result['levels'] for e in level['callees'] if e['call_expr'] == 'helper')
    assert (edge['resolved'], edge.get('callee_file')) == (True, 'b.ts')


def test_the_same_walk_spelled_from_above_agrees(tmp_path, monkeypatch):
    # Control: the spelling BACK-2553's fix already handled.
    _tree(tmp_path, ALIASED)
    monkeypatch.chdir(tmp_path)
    result = CallsAdapter('app', 'callees=main.ts:go&depth=2').get_structure()
    edge = next(e for level in result['levels'] for e in level['callees'] if e['call_expr'] == 'helper')
    assert (edge['resolved'], edge.get('callee_file')) == (True, 'app/b.ts')
