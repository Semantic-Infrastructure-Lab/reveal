"""Independent build roots must expose imports a scan-root oracle cannot see."""
from pathlib import Path

import pytest

from test_recall_gate import _repo, gate, oracles


def _metadata(name, package):
    return ('[build-system]\nrequires=["hatchling>=1.19"]\nbuild-backend="hatchling.build"\n'
            f'[project]\nname="{name}"\nversion="1.0"\n'
            f'[tool.hatch.build.targets.wheel]\npackages=["{package}"]\n')


@pytest.fixture
def workspace(tmp_path):
    return _repo(tmp_path, {
        'apps/client/pyproject.toml': _metadata('client-dist', 'src/client'),
        'apps/client/src/client/__init__.py': 'from provider import leaf\n',
        'libs/vendor/pyproject.toml': _metadata('provider-dist', 'code/provider'),
        'libs/vendor/code/provider/__init__.py': '',
        'libs/vendor/code/provider/leaf.py': 'VALUE = 1\n',
    }, {'oracle': 'python-hatch', 'importer_dirs': ['apps/client/src/client', 'libs/vendor/code/provider'],
        'build_projects': ['apps/client', 'libs/vendor']})


def _truth(workspace):
    root, entry = workspace
    scope = oracles.Scope(root, root, oracles.tracked_files(root, entry['recall']['importer_dirs'],
                                                         frozenset({'.py'})), entry['recall'])
    return oracles.ORACLES['python-hatch'].build(scope)


def test_build_roots_find_cross_package_edges_without_importing_application(workspace):
    root, _ = workspace
    # Import execution would fail: the oracle must ask PathFinder, not import this package.
    (root / 'libs/vendor/code/provider/__init__.py').write_text('raise RuntimeError("do not execute")\n', encoding='utf-8')
    edges, coverage = _truth(workspace)
    importer = 'apps/client/src/client/__init__.py'
    assert edges == {'libs/vendor/code/provider/__init__.py': [importer],
                     'libs/vendor/code/provider/leaf.py': [importer]}
    assert coverage['cross_package_edges'] == 2
    assert coverage['build_roots'] == ['apps/client/src', 'libs/vendor/code']


def test_scan_root_decoy_is_not_ground_truth(workspace):
    root, _ = workspace
    (root / 'provider').mkdir()
    (root / 'provider/__init__.py').write_text('', encoding='utf-8')
    (root / 'provider/leaf.py').write_text('DECOY = 1\n', encoding='utf-8')
    edges, _ = _truth(workspace)
    assert all(path.startswith('libs/vendor/code/provider/') for path in edges)


def test_changed_build_selection_changes_truth_not_a_directory_guess(workspace):
    root, _ = workspace
    directory = root / 'libs/vendor/selected/provider'
    directory.mkdir(parents=True)
    (directory / '__init__.py').write_text('', encoding='utf-8')
    (directory / 'leaf.py').write_text('', encoding='utf-8')
    (root / 'libs/vendor/pyproject.toml').write_text(_metadata('provider-dist', 'selected/provider'), encoding='utf-8')
    edges, _ = _truth(workspace)
    assert all(path.startswith('libs/vendor/selected/provider/') for path in edges)


def test_build_backed_row_agrees_and_a_resolver_loss_fails(workspace, monkeypatch):
    root, entry = workspace
    before = gate.measure(entry, root)
    assert before['recall'] == before['precision'] == 1
    from reveal.analyzers.imports.resolution import ProjectResolver
    real = ProjectResolver._resolve_statement_edges
    def lossy(self, stmt, file_path, *args, **kwargs):
        return None if stmt.module_name == 'provider' else real(self, stmt, file_path, *args, **kwargs)
    monkeypatch.setattr(ProjectResolver, '_resolve_statement_edges', lossy)
    with pytest.raises(RuntimeError, match='zero oracle edges'):
        gate.measure(entry, root)


@pytest.mark.parametrize('projects', [[], ['../outside'], ['missing']])
def test_missing_or_escaping_build_inputs_fail(workspace, projects):
    _, entry = workspace
    entry['recall']['build_projects'] = projects
    with pytest.raises(RuntimeError, match='build|project'):
        _truth(workspace)


def test_backend_failure_is_unavailable_truth_not_clean_zero(workspace):
    root, _ = workspace
    (root / 'apps/client/pyproject.toml').write_text('invalid [ TOML', encoding='utf-8')
    with pytest.raises(RuntimeError, match='Hatch'):
        _truth(workspace)


def test_python_ast_oracle_prefers_a_package_over_a_same_named_module(tmp_path):
    root, entry = _repo(tmp_path, {'caller.py': 'import pkg\n', 'pkg.py': '', 'pkg/__init__.py': ''}, {})
    files = oracles.tracked_files(root, ['.'], frozenset({'.py'}))
    edges, _ = oracles.build_python_oracle(oracles.Scope(root, root, files, entry['recall']))
    assert edges == {'pkg/__init__.py': ['caller.py']}


def test_new_row_is_selected_for_python_changes():
    import yaml
    from test_recall_gate import _load, SCRIPTS
    trigger = _load('check_imports_gate')
    manifest = yaml.safe_load((SCRIPTS.parent / 'tests/corpus/manifest.yaml').read_text(encoding='utf-8'))
    for path in ['reveal/analyzers/python.py', 'reveal/analyzers/imports/python.py',
                 'reveal/analyzers/imports/resolver.py']:
        assert 'python-dagster' in trigger.select([path], manifest)[0]


def test_editable_build_does_not_mutate_pinned_sources(workspace):
    import subprocess
    root, _ = workspace
    before = subprocess.run(['git', '-C', str(root), 'status', '--porcelain'], check=True,
                            capture_output=True, text=True, encoding='utf-8').stdout
    _truth(workspace)
    after = subprocess.run(['git', '-C', str(root), 'status', '--porcelain'], check=True,
                           capture_output=True, text=True, encoding='utf-8').stdout
    assert before == after == ''


def test_dynamic_editable_hook_is_declined_instead_of_guessed(workspace):
    root, _ = workspace
    metadata = root / 'apps/client/pyproject.toml'
    metadata.write_text(metadata.read_text(encoding='utf-8') + '\n[tool.hatch.build]\ndev-mode-exact=true\n', encoding='utf-8')
    with pytest.raises(RuntimeError, match='Dynamic editable import hook'):
        _truth(workspace)
