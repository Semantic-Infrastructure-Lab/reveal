"""BACK-2559 (Python slice): an absolute import resolves from its package's import root.

Python resolution searched the scan root (and, without an ``__init__.py``, the importing directory)
only. A package whose import root is elsewhere, a monorepo's ``python_modules/<pkg>/<pkg>`` or a
``src/`` layout, got no edge for any absolute import of itself or of a sibling package: on the
dagster corpus 7,021 of 7,022 ``dagster*`` imports were unresolved (BACK-2571 audit), and calls'
callee resolution, which reads the same bindings, lost their targets (BACK-2573). The package model
now records each top-level package of the scan (the top of a contiguous ``__init__.py`` chain) and
the root Python imports it from (that directory's parent).

Each test asserts the edge's target or the recorded verdict, not that an edge exists.
"""
from pathlib import Path

from reveal.analyzers.imports import service


def _tree(root: Path, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding='utf-8')
    return root


def _statements(root: Path, scan: str = '.'):
    """(importer relative to root, module) -> (resolved file relative to root or None, verdict)."""
    analysis = service.analyze(service.path_scope(root / scan)).analysis
    out = {}
    for path, extraction in analysis.extractions.items():
        for stmt in extraction.imports:
            target = stmt.resolved_path
            out[(Path(path).resolve().relative_to(root).as_posix(), stmt.module_name)] = (
                Path(target).resolve().relative_to(root).as_posix() if target else None, stmt.intra_verdict)
    return out


MONOREPO = {
    'pyproject.toml': '[project]\nname = "mono"\n',
    'python_modules/core/core/__init__.py': '',
    'python_modules/core/core/engine/__init__.py': '',
    'python_modules/core/core/engine/run.py': 'def run_job():\n    pass\n',
    'python_modules/core/core/api.py': 'from core.engine.run import run_job\nimport core.engine\n',
    'python_modules/graphql/graphql_ext/__init__.py': '',
    'python_modules/graphql/graphql_ext/schema.py': 'from core.engine.run import run_job\nimport requests\n',
}


def test_a_package_resolves_its_own_absolute_imports_from_its_import_root(tmp_path):
    # Before: (None, None) for both -- the scan root holds no `core/`.
    got = _statements(_tree(tmp_path, MONOREPO))
    assert got[('python_modules/core/core/api.py', 'core.engine.run')] == (
        'python_modules/core/core/engine/run.py', None)
    assert got[('python_modules/core/core/api.py', 'core.engine')][0] == 'python_modules/core/core/engine/__init__.py'


def test_a_sibling_package_of_the_monorepo_resolves_from_its_root(tmp_path):
    got = _statements(_tree(tmp_path, MONOREPO))
    assert got[('python_modules/graphql/graphql_ext/schema.py', 'core.engine.run')][0] == (
        'python_modules/core/core/engine/run.py')


def test_a_third_party_import_stays_unresolved(tmp_path):
    # Control: `requests` is no package of the scan.
    got = _statements(_tree(tmp_path, MONOREPO))
    assert got[('python_modules/graphql/graphql_ext/schema.py', 'requests')][0] is None


def test_a_src_layout_package_resolves_from_src(tmp_path):
    got = _statements(_tree(tmp_path, {
        'pyproject.toml': '[project]\nname = "mylib"\n',
        'src/mylib/__init__.py': '', 'src/mylib/a.py': 'def f():\n    pass\n',
        'tests/test_a.py': 'from mylib.a import f\n'}))
    assert got[('tests/test_a.py', 'mylib.a')][0] == 'src/mylib/a.py'


def test_two_copies_of_a_package_resolve_only_for_an_importer_inside_one(tmp_path):
    # Which copy the program imports is not in the source: an importer outside both gets no edge,
    # one inside a copy gets its own.
    got = _statements(_tree(tmp_path, {
        'a/pkg/__init__.py': '', 'a/pkg/m.py': 'from pkg.n import x\n', 'a/pkg/n.py': 'x = 1\n',
        'b/pkg/__init__.py': '', 'b/pkg/n.py': 'x = 2\n',
        'tool.py': 'from pkg.n import x\n'}))
    assert got[('a/pkg/m.py', 'pkg.n')][0] == 'a/pkg/n.py'
    assert got[('tool.py', 'pkg.n')][0] is None


def test_a_package_at_the_scan_root_resolves_as_before(tmp_path):
    # Control: the root package was always found through the scan root.
    got = _statements(_tree(tmp_path, {'app/__init__.py': '', 'app/x.py': 'from app.y import z\n',
                                       'app/y.py': 'z = 1\n'}))
    assert got[('app/x.py', 'app.y')][0] == 'app/y.py'


def test_a_namespace_package_declares_no_root(tmp_path):
    # No __init__.py: nothing says the directory is a package, so nothing is guessed.
    got = _statements(_tree(tmp_path, {'libs/ns/mod.py': 'x = 1\n', 'tool.py': 'from ns.mod import x\n'}))
    assert got[('tool.py', 'ns.mod')][0] is None


def test_a_scan_rooted_at_the_package_itself_stays_at_that_root(tmp_path):
    # `scope=path` on python_modules/core/core: the package is imported from python_modules/core,
    # above the root that was asked for, so its absolute self-imports stay unresolved there.
    root = _tree(tmp_path, MONOREPO)
    got = _statements(root, 'python_modules/core/core')
    assert got[('python_modules/core/core/api.py', 'core.engine.run')][0] is None
    # Its own directory as the scan root (the import root itself) resolves them.
    assert _statements(root, 'python_modules/core')[('python_modules/core/core/api.py', 'core.engine.run')][0] == (
        'python_modules/core/core/engine/run.py')


def test_namespace_container_before_a_regular_package_does_not_hide_it(tmp_path):
    from reveal.analyzers.imports.resolver import resolve_python_import, resolve_python_from_import_submodules
    from reveal.analyzers.imports.types import ImportStatement
    early, installed = tmp_path / 'scan', tmp_path / 'install'
    for path in [early / 'pkg/part.py', installed / 'pkg/__init__.py', installed / 'pkg/part.py']:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
    stmt = ImportStatement(file_path=tmp_path / 'caller.py', is_relative=False,
                           module_name='pkg', import_type='from_import', imported_names=['part'], line_number=1)
    assert resolve_python_import(stmt, tmp_path, [early, installed]) == installed / 'pkg/__init__.py'
    assert resolve_python_from_import_submodules(stmt, tmp_path, [early, installed]) == [installed / 'pkg/part.py']
    nested = ImportStatement(file_path=tmp_path / 'caller.py', is_relative=False, imported_names=[],
                             module_name='pkg.part', import_type='import', line_number=1)
    assert resolve_python_import(nested, tmp_path, [early, installed]) == installed / 'pkg/part.py'


def test_namespace_portions_still_supply_a_nested_module(tmp_path):
    from reveal.analyzers.imports.resolver import resolve_python_import
    from reveal.analyzers.imports.types import ImportStatement
    left, right = tmp_path / 'left', tmp_path / 'right'
    (left / 'pkg').mkdir(parents=True)
    (right / 'pkg').mkdir(parents=True)
    target = right / 'pkg/leaf.py'
    target.write_text('', encoding='utf-8')
    stmt = ImportStatement(tmp_path / 'caller.py', 1, 'pkg.leaf', [], False, 'import')
    assert resolve_python_import(stmt, tmp_path, [left, right]) == target


def test_regular_package_precedes_a_same_root_module_file(tmp_path):
    from reveal.analyzers.imports.resolver import resolve_python_import
    from reveal.analyzers.imports.types import ImportStatement
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg/__init__.py').write_text('', encoding='utf-8')
    (tmp_path / 'pkg.py').write_text('', encoding='utf-8')
    stmt = ImportStatement(tmp_path / 'caller.py', 1, 'pkg', [], False, 'import')
    assert resolve_python_import(stmt, tmp_path, [tmp_path]) == tmp_path / 'pkg/__init__.py'


def test_from_imported_package_precedes_a_same_named_module(tmp_path):
    from reveal.analyzers.imports.resolver import resolve_python_import, resolve_python_from_import_submodules
    from reveal.analyzers.imports.types import ImportStatement
    outer = tmp_path / 'outer'
    (outer / 'inner').mkdir(parents=True)
    for path in [outer / '__init__.py', outer / 'inner.py', outer / 'inner/__init__.py']:
        path.write_text('', encoding='utf-8')
    absolute = ImportStatement(tmp_path / 'caller.py', 1, 'outer', ['inner'], False, 'from_import')
    relative = ImportStatement(outer / 'caller.py', 1, '', ['inner'], True, 'from_import', level=1)
    assert resolve_python_from_import_submodules(absolute, tmp_path, [tmp_path]) == [outer / 'inner/__init__.py']
    assert resolve_python_import(relative, outer, [tmp_path]) == outer / 'inner/__init__.py'
    assert resolve_python_from_import_submodules(relative, outer, [tmp_path]) == [outer / 'inner/__init__.py']
