"""Project scope, rather than checkout ancestors, determines test importers."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.imports import ImportsAdapter
from reveal.utils.entry_points import active_entry_points


FILES = {
    'pyproject.toml': '[project]\nname="scope-fixture"\nversion="0.0.0"\n',
    'pkg/__init__.py': '',
    'pkg/helper.py': 'VALUE = 1\n',
    'pkg/app.py': 'from pkg.helper import VALUE\nimport requests\n',
    'pkg/probe.py': 'from tests.helper import FIXTURE\n',
    'tests/__init__.py': '',
    'tests/helper.py': 'FIXTURE = 1\n',
    'tests/test_app.py': 'from pkg.helper import VALUE\nimport pytest\n',
    'tests/runner.py': 'from pkg.helper import VALUE\n',
}


@pytest.fixture(autouse=True)
def uncached(monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


def _write(root, files=FILES):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return root.resolve()


def _cli(root, query):
    result = _run_reveal_direct(f'imports://{root}?{query}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('checkout', ['normal/repo', 'tests/repo', 'tests'])
def test_public_exclusion_uses_project_paths_and_retains_test_targets(tmp_path, checkout):
    root = _write(tmp_path / checkout)
    result = _cli(root, 'importers&tests=exclude')
    assert result['entries'] == [
        {'file': 'pkg/helper.py', 'fan_in': 1, 'importers': ['pkg/app.py']},
        {'file': 'tests/helper.py', 'fan_in': 1, 'importers': ['pkg/probe.py']},
    ]


@pytest.mark.parametrize('checkout', ['normal/repo', 'tests/repo', 'tests'])
def test_include_preserves_the_complete_importer_population(tmp_path, checkout):
    root = _write(tmp_path / checkout)
    result = _cli(root, 'importers&tests=include')
    assert result['entries'] == [
        {'file': 'pkg/helper.py', 'fan_in': 3,
         'importers': ['pkg/app.py', 'tests/runner.py', 'tests/test_app.py']},
        {'file': 'tests/helper.py', 'fan_in': 1, 'importers': ['pkg/probe.py']},
    ]


def test_external_packages_use_the_same_project_scope(tmp_path):
    root = _write(tmp_path / 'tests' / 'repo')
    result = _cli(root, 'external&tests=exclude')
    assert {row['package'] for row in result['external_packages']} == {'requests'}
    assert result['total_files'] == 4


def test_display_relative_test_labels_govern_the_active_filter(tmp_path):
    root = _write(tmp_path / 'repo')
    result = _cli(root / 'tests', 'entrypoints')
    runner = next(row for row in result['entries'] if row['file'] == 'runner.py')
    assert runner['is_test'] is True
    assert runner['fan_out'] == 1
    assert active_entry_points([runner]) == []


def test_entrypoint_labels_ignore_checkout_ancestors(tmp_path):
    root = _write(tmp_path / 'tests' / 'repo')
    result = _cli(root, 'entrypoints')
    app = next(row for row in result['entries'] if row['file'] == 'pkg/app.py')
    assert app['is_test'] is False
    assert app['fan_out'] == 1
    assert next(row for row in result['entries'] if row['file'] == 'tests/runner.py')['is_test'] is True


def test_narrow_scope_preserves_discovered_test_prefix(tmp_path):
    root = _write(tmp_path / 'repo', {
        'pyproject.toml': FILES['pyproject.toml'],
        'tests/runner.py': 'import core\n',
        'tests/core.py': 'VALUE=1\n',
    })
    result = _cli(root / 'tests', 'importers&tests=exclude&scope=path')
    assert result['entries'] == []


def test_project_name_is_not_test_evidence_under_narrow_scope(tmp_path):
    root = _write(tmp_path / 'tests', {
        'pyproject.toml': FILES['pyproject.toml'],
        'pkg/app.py': 'import core\n',
        'pkg/core.py': 'VALUE=1\n',
    })
    result = _cli(root / 'pkg', 'importers&tests=exclude&scope=path')
    assert result['entries'] == [{'file': 'core.py', 'fan_in': 1, 'importers': ['app.py']}]


def test_markerless_direct_suite_keeps_unnamed_helpers_as_tests(tmp_path):
    suite = _write(tmp_path / 'tests', {'runner.py': 'import core\n', 'core.py': 'VALUE=1\n'})
    assert _cli(suite, 'importers&tests=exclude')['entries'] == []


def test_scanned_population_and_diagnostics_do_not_depend_on_test_filter(tmp_path):
    root = _write(tmp_path / 'tests' / 'repo')
    adapter = ImportsAdapter(str(root), 'importers&tests=include')
    include = adapter.get_structure()
    graph = adapter.analysis.graph
    scanned = adapter.analysis.scanned_files.copy()
    exclude = adapter.get_view('importers&tests=exclude')
    assert adapter.analysis.graph is graph
    assert adapter.analysis.scanned_files == scanned
    assert exclude['metadata'] == include['metadata']


def test_neutral_test_subtree_materialization_keeps_entrypoint_classification(tmp_path):
    pygit2 = pytest.importorskip('pygit2')
    from reveal.diff.architecture_diff import run_architecture_diff

    root = _write(tmp_path / 'repo', {
        'tests/runner.py': 'import core\n', 'tests/core.py': 'VALUE=1\n',
    })
    repo = pygit2.init_repository(str(root))
    for name in ('tests/runner.py', 'tests/core.py'):
        repo.index.add(name)
    repo.index.write()
    author = pygit2.Signature('fixture', 'fixture@example.invalid')
    revision = str(repo.create_commit('HEAD', author, author, 'fixture', repo.index.write_tree(), []))
    (root / 'tests' / 'runner.py').write_text('import core\n# unchanged behavior\n', encoding='utf-8')
    result = run_architecture_diff(root / 'tests', revision)
    assert result['deltas']['entry_points'] == {'added': [], 'removed': []}
