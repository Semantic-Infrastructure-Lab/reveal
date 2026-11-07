"""BACK-2550: an import's 'classification' comes from the resolution pass, not a second ask from the scan root.

Before, ``ImportsAdapter._format_import`` asked ``is_intra_project_import`` again at presentation time with the
scan root as the base path. Manifest languages find the nearest manifest from the path they are given, so
the verdict described the scan root's package instead of the importing file's: scanning a directory with no
manifest of its own (Kubernetes' ``staging/src/k8s.io``, a Python monorepo root) put each module's own
unresolved imports under the parent's go.mod or under no project at all, and they read 'unresolved'. The
resolution pass already asked the same question from the importing file's directory to count
``unresolved_intra``; it now records that verdict on the statement, and the classification reads it.
"""
import json
from pathlib import Path

from conftest import _run_reveal_in
from reveal.analyzers.imports.go import GoExtractor
from reveal.analyzers.imports.resolution import ProjectResolver
from reveal.analyzers.imports.types import ImportStatement

from test_go_package_model_back2557 import STAGING, WORKSPACE, write_workspace

GO_FILES = {
    **WORKSPACE,
    # a package of the file's own module that is not in the tree (generated, or cut by a scan cap)
    f'{STAGING}/api/core/v1/gen.go': 'package v1\n\nimport "example.com/api/generated/clientset"\n',
    # a package of a go.work sibling module that is not in the tree
    f'{STAGING}/client/rest/sample.go': 'package rest\n\nimport "example.com/sampler/missing"\n',
}

PY_FILES = {
    'projects/alpha/pyproject.toml': '[project]\nname = "alpha"\n',
    'projects/alpha/alpha/__init__.py': '',
    'projects/alpha/alpha/core.py': (
        'from typing import TYPE_CHECKING\n'
        'from alpha.missing import Thing\n'
        'if TYPE_CHECKING:\n'
        '    from alpha.also_missing import Other\n'
    ),
}


def _classifications(cwd: Path, target: str):
    result = _run_reveal_in(cwd, f'imports://{target}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    return {(s['file'], s['module']): s['classification']
            for stmts in json.loads(result.stdout)['files'].values() for s in stmts}


def test_a_module_scanned_from_a_directory_above_it_classifies_by_its_own_go_mod(tmp_path):
    """The scan root has no go.mod; the nearest one above it is the root module's (example.com/app)."""
    ws = write_workspace(tmp_path / 'ws', GO_FILES)
    got = _classifications(ws / STAGING, '.')
    assert got[('api/core/v1/gen.go', 'example.com/api/generated/clientset')] == 'intra_project'
    assert got[('client/rest/sample.go', 'example.com/sampler/missing')] == 'intra_project'
    # control: apimachinery is in the tree but no go.work or replace links it to api, so it is not upgraded
    assert got[('api/core/v1/conv.go', 'example.com/apimachinery/pkg')] == 'unresolved'


def test_a_go_work_sibling_counts_as_in_tree_only_through_the_model(tmp_path):
    """The verdict searches the units resolution searches: with the model a go.work sibling is in-tree."""
    ws = write_workspace(tmp_path / 'ws', GO_FILES)
    sample = ws / f'{STAGING}/client/rest/sample.go'
    stmt = ImportStatement(sample, 3, 'example.com/sampler/missing', [], False, 'import')
    model = ProjectResolver._build_package_model(sorted(ws.rglob('*.go')), on_error=lambda e: None)
    assert GoExtractor().is_intra_project_import(stmt, sample.parent, packages=model) is True
    assert GoExtractor().is_intra_project_import(stmt, sample.parent) is False   # nearest go.mod only
    outside = ImportStatement(sample, 3, 'example.com/apimachinery/pkg', [], False, 'import')
    assert GoExtractor().is_intra_project_import(outside, sample.parent, packages=model) is False  # not linked


def test_a_monorepo_root_classifies_each_project_by_its_own_manifest(tmp_path):
    """From the root (no pyproject) the project package is unknown; from the file it is in-tree. A
    TYPE_CHECKING import has no edge in any view but is classified by the same pass."""
    for rel, text in PY_FILES.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding='utf-8')
    got = _classifications(tmp_path, '.')
    assert got[('projects/alpha/alpha/core.py', 'alpha.missing')] == 'intra_project'
    assert got[('projects/alpha/alpha/core.py', 'alpha.also_missing')] == 'intra_project'
    assert got[('projects/alpha/alpha/core.py', 'typing')] == 'stdlib'
