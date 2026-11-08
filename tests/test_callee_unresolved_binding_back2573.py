"""A call bound by an import that resolved to no file reaches no project definition (BACK-2573).

BACK-2553 stopped a call through an import from outside the tree (``json.loads``) resolving to a
same-named project function, but only when the extractor's verdict said "outside the tree". For a
Python third-party package (``pytest``) the verdict is "cannot tell", and ``pytest.raises`` still
resolved to the project's one ``raises`` (python-celery: t/unit/tasks/test_trace.py:45, found by the
BACK-2569 call_targets invariant). Either verdict, the import names no project file, so no project
function is what the call reaches.

Each test asserts the edge's target, not that an edge exists.
"""

from pathlib import Path

from reveal.analyzers.imports import service
from reveal.analyzers.imports.bindings import file_bindings

from test_callee_import_binding_back2553 import _edges, _target, _tree


def test_third_party_qualifier_is_not_the_projects_function(tmp_path):
    # Before: pytest.raises -> helpers.py:raises (the one project 'raises').
    path = _tree(tmp_path, {'test_x.py': 'import pytest\n\ndef test_x():\n    pytest.raises(ValueError)\n',
                            'helpers.py': 'def raises(exc):\n    return exc\n'})
    assert _target(_edges(path, 'test_x')['pytest.raises']) == (None, 'external')


def test_third_party_named_import_is_not_the_projects_function(tmp_path):
    # Before: get -> client.py:get.
    path = _tree(tmp_path, {'app.py': 'from requests import get\n\ndef run(u):\n    return get(u)\n',
                            'client.py': 'def get(u):\n    return u\n'})
    assert _target(_edges(path, 'run')['get']) == (None, 'external')


def test_the_verdict_for_a_third_party_import_is_unknown_not_external(tmp_path):
    # Positive control for the cause: the case BACK-2553's external verdict did not cover.
    path = _tree(tmp_path, {'app.py': 'import json\nimport pytest\n'})
    extraction = next(iter(service.analyze(service.project_scope(Path(path))).analysis.extractions.values()))
    verdicts = {stmt.module_name: stmt.intra_verdict for stmt in extraction.imports}
    assert verdicts == {'json': False, 'pytest': None}
    bindings = file_bindings(extraction.imports)
    assert bindings['json'].unresolved and bindings['pytest'].unresolved


def test_a_name_bound_also_in_tree_is_not_unresolved(tmp_path):
    # try/except import fallbacks: one statement resolved in-tree, so the name may reach the tree.
    path = _tree(tmp_path, {'app.py': ('try:\n    from fastjson import dumps\nexcept ImportError:\n'
                                       '    from mylib import dumps\n\ndef run(x):\n    return dumps(x)\n'),
                            'mylib.py': 'def dumps(x):\n    return x\n'})
    assert _target(_edges(path, 'run')['dumps']) == ('mylib.py', None)


def test_a_local_definition_still_shadows_a_third_party_name(tmp_path):
    path = _tree(tmp_path, {'app.py': ('from requests import get\n\ndef get(u):\n    return u\n\n'
                                       'def run(u):\n    return get(u)\n'),
                            'client.py': 'def get(u):\n    return u\n'})
    assert _target(_edges(path, 'run')['get']) == ('app.py', None)


# --- an in-tree package the resolution pass cannot place still reaches its file -----------------
# A monorepo's packages live under roots reveal does not model (dagster's python_modules/<pkg>/),
# and a test directory imports its siblings through sys.path. Those imports resolve to no file with
# an unknown verdict; the call reaches a candidate only when its file sits at the module's path
# (dagster: 15,949 call sites in the census would otherwise have lost their target).

MONOREPO = {
    'pyproject.toml': '[project]\nname = "mono"\n',
    'python_modules/pkg/pkg/__init__.py': '',
    'python_modules/pkg/pkg/core.py': 'def run_job(x):\n    return x\n',
    'python_modules/pkg/pkg/api.py': 'from pkg.core import run_job\n\ndef go(x):\n    return run_job(x)\n',
    'python_modules/other/other/jobs.py': 'def run_job(x):\n    return x\n',
}


def test_an_unplaced_in_tree_import_reaches_the_file_at_its_module_path(tmp_path):
    path = _tree(tmp_path, MONOREPO)
    assert _target(_edges(path, 'go')['run_job']) == ('core.py', None)


def test_the_monorepo_import_is_unplaced_with_an_unknown_verdict(tmp_path):
    # Positive control: without the module-path rule this import would make run_job external.
    path = _tree(tmp_path, MONOREPO)
    analysis = service.analyze(service.project_scope(Path(path))).analysis
    stmt = next(s for e in analysis.extractions.values() for s in e.imports if s.module_name == 'pkg.core')
    assert (stmt.resolved_path, stmt.intra_verdict) == (None, None)


def test_a_sys_path_sibling_module_reaches_its_file(tmp_path):
    path = _tree(tmp_path, {'pyproject.toml': '[project]\nname = "p"\n',
                            'testing/lib/helpers_util.py': 'def make():\n    return 1\n',  # on sys.path at test time
                            'tests/test_a.py': 'import helpers_util\n\ndef test_a():\n    helpers_util.make()\n',
                            'src/factory.py': 'def make():\n    return 2\n'})
    assert _target(_edges(path, 'test_a')['helpers_util.make']) == ('helpers_util.py', None)


def test_a_third_party_name_does_not_reach_a_file_merely_named_like_its_member(tmp_path):
    # `pytest.raises` may reach only a file at pytest(.py|/__init__.py); helpers/raises.py is not one.
    path = _tree(tmp_path, {'test_x.py': 'import pytest\n\ndef test_x():\n    pytest.raises(ValueError)\n',
                            'helpers/raises.py': 'def raises(exc):\n    return exc\n'})
    assert _target(_edges(path, 'test_x')['pytest.raises']) == (None, 'external')
