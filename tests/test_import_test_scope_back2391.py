"""Project scope, rather than checkout ancestors, determines test importers."""
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.imports import ImportsAdapter
from reveal.utils.entry_points import active_entry_points
from reveal.utils.path_utils import TestLayout as LexicalLayout, is_test_path
from reveal.analyzers.imports.types import ImportGraph


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
    # The package table counts import-bearing sources (app/probe), not every scanned file.
    assert result['total_files'] == 2


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


@pytest.mark.parametrize('aliased', [False, True])
def test_neutral_test_subtree_materialization_keeps_entrypoint_classification(tmp_path, monkeypatch, aliased):
    pygit2 = pytest.importorskip('pygit2')
    from reveal.diff.architecture_diff import run_architecture_diff
    from reveal.diff import architecture_diff as diff

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
    if aliased:
        original = diff.materialize_ref

        @contextmanager
        def observed_alias(*args, **kwargs):
            with original(*args, **kwargs) as materialized:
                alias = tmp_path / 'snapshot-alias'
                try:
                    alias.symlink_to(materialized, target_is_directory=True)
                except OSError as exc:
                    pytest.skip(f'directory symlinks unavailable: {exc.__class__.__name__}')
                try:
                    yield alias
                finally:
                    alias.unlink()

        monkeypatch.setattr(diff, 'materialize_ref', observed_alias)
    result = run_architecture_diff(root / 'tests', revision)
    assert result['deltas']['entry_points'] == {'added': [], 'removed': []}


def test_one_context_keeps_project_scope_across_narrower_scans(tmp_path):
    root = _write(tmp_path / 'tests')
    whole = LexicalLayout.for_path(root)
    narrow = LexicalLayout.for_path(root / 'pkg', fallback_root=root / 'pkg')
    assert whole.identity == narrow.identity
    assert narrow.is_test(root / 'pkg' / 'app.py') is False
    assert narrow.is_test(root / 'tests' / 'runner.py') is True


def test_explicit_boundary_overrides_nested_project_markers(tmp_path):
    outer = _write(tmp_path / 'repo', {'pyproject.toml': FILES['pyproject.toml']})
    inner = _write(outer / 'tests', {
        'pyproject.toml': FILES['pyproject.toml'], 'pkg/app.py': 'import core\n',
        'pkg/core.py': 'VALUE=1\n',
    })
    discovered = LexicalLayout.for_path(inner / 'pkg')
    selected = LexicalLayout.for_path(inner / 'pkg', root_override=outer)
    assert discovered.anchor == inner
    assert discovered.is_test(inner / 'pkg' / 'app.py') is False
    assert selected.anchor == outer and selected.source == 'explicit_root'
    assert selected.is_test(inner / 'pkg' / 'app.py') is True
    assert _cli(inner / 'pkg', f'importers&tests=exclude&root={outer}')['entries'] == []
    ignored = _cli(inner / 'pkg', f'importers&tests=exclude&scope=path&root={outer}')
    assert ignored['entries'] == [{'file': 'core.py', 'fan_in': 1, 'importers': ['app.py']}]


def test_explicit_test_named_boundary_does_not_classify_all_sources_as_tests(tmp_path):
    root = _write(tmp_path / 'tests')
    assert _cli(root, f'importers&tests=exclude&root={root}')['entries'] == [
        {'file': 'pkg/helper.py', 'fan_in': 1, 'importers': ['pkg/app.py']},
        {'file': 'tests/helper.py', 'fan_in': 1, 'importers': ['pkg/probe.py']},
    ]


def test_fallback_discloses_unknown_project_scope_and_retains_suite_name(tmp_path):
    root = _write(tmp_path / 'tests', {'helpers.py': 'VALUE=1\n'})
    layout = LexicalLayout.for_path(root)
    assert layout.anchor == root and layout.source == 'scan_root_fallback'
    assert layout.include_anchor_name is True
    assert layout.is_test(root / 'helpers.py') is True
    assert 'unknown' in layout.as_dict(root)['basis']


@pytest.mark.parametrize('view', ['importers', 'external'])
def test_fallback_basis_is_visible_in_both_text_and_json(tmp_path, view):
    root = _write(tmp_path / 'tests', {'runner.py': 'import core\n', 'core.py': 'VALUE=1\n'})
    result = _cli(root, view + '&tests=exclude')
    scope = (result['metadata'] if view == 'external' else result['edge_rule'])['test_scope']
    assert scope['anchor'] == '.' and scope['include_anchor_name'] is True
    assert scope['source'] == 'scan_root_fallback'
    rendered = _run_reveal_direct(f'imports://{root}?{view}&tests=exclude')
    assert rendered.returncode == 0, rendered.stderr
    assert 'project boundary unknown' in rendered.stdout
    assert str(tmp_path) not in scope['anchor']


def test_context_views_are_separate_and_identical_policy_reuses_a_view(tmp_path):
    root = tmp_path.resolve()
    source, target = root / 'tests' / 'helpers.py', root / 'tests' / 'core.py'
    graph = ImportGraph()
    graph.add_dependency(source, target)
    project = LexicalLayout(root, 'project')
    selected = LexicalLayout(root / 'tests', 'explicit_root')
    assert graph.without_test_importers(project).dependencies == {}
    retained = graph.without_test_importers(selected)
    assert retained.dependencies[source] == {target}
    same_policy = LexicalLayout(root / 'tests', 'project')
    assert graph.without_test_importers(same_policy) is retained
    assert graph.dependencies[source] == {target}


def test_relocated_context_retains_logical_prefix_and_memo_identity(tmp_path):
    root = tmp_path.resolve()
    source, target = root / 'snapshot' / 'helpers.py', root / 'snapshot' / 'core.py'
    layout = LexicalLayout(root, 'project')
    suite = layout.relocate(observed_root=root / 'snapshot', logical_root=root / 'tests')
    production = layout.relocate(observed_root=root / 'snapshot', logical_root=root / 'src')
    graph = ImportGraph()
    graph.add_dependency(source, target)
    assert suite.is_test(source) is True
    assert production.is_test(source) is False
    assert graph.without_test_importers(suite).dependencies == {}
    assert graph.without_test_importers(production).dependencies[source] == {target}
    assert suite.as_dict(root / 'snapshot')['anchor'] == '..'


def test_incompatible_source_context_is_rejected_instead_of_absolute_fallback(tmp_path):
    root = tmp_path.resolve()
    layout = LexicalLayout(root / 'project', 'project')
    with pytest.raises(ValueError, match='outside.*context'):
        layout.is_test(root / 'other' / 'tests' / 'app.py')
    with pytest.raises(ValueError):
        layout.relocate(observed_root=root / 'snapshot', logical_root=root / 'other')
    with pytest.raises(ValueError, match='absolute'):
        LexicalLayout(Path('project'), 'project')
    with pytest.raises(ValueError, match='observed and logical'):
        LexicalLayout(root, 'project', observed_root=root / 'snapshot')


@pytest.mark.parametrize('field', ['anchor', 'observed_root', 'logical_root'])
def test_context_rejects_parent_traversal_without_canonicalization(tmp_path, field):
    root = tmp_path.resolve()
    values = dict(anchor=root, source='project', observed_root=root / 'snapshot', logical_root=root / 'tests')
    values[field] = root / 'project' / '..' / 'elsewhere'
    with pytest.raises(ValueError, match='normalized absolute'):
        LexicalLayout(**values)


def test_source_cannot_escape_lexical_context_with_parent_components(tmp_path):
    root = tmp_path.resolve()
    layout = LexicalLayout(root / 'project', 'project')
    with pytest.raises(ValueError, match='normalized absolute'):
        layout.is_test(root / 'project' / '..' / 'tests' / 'app.py')


def test_observed_paths_are_lexical_without_alias_canonicalization(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    layout = LexicalLayout(root, 'project')

    def forbidden(*args, **kwargs):
        raise AssertionError('classification must not resolve observed paths')

    monkeypatch.setattr(Path, 'resolve', forbidden)
    assert layout.is_test(root / 'tests' / 'alias.py') is True
    assert layout.is_test(root / 'src' / 'alias.py') is False
    assert layout.is_test(str(root / 'tests' / 'alias.py').replace('/', '\\')) is True


@pytest.mark.parametrize('fan_out', [0, 1])
@pytest.mark.parametrize('invalid', [None, 'false', 0, 1])
def test_present_producer_label_is_validated_before_active_short_circuits(fan_out, invalid):
    with pytest.raises(ValueError, match='boolean'):
        active_entry_points([{'file': 'app.py', 'fan_out': fan_out, 'is_test': invalid}])


def test_no_label_legacy_rows_keep_lexical_classification():
    rows = [{'file': 'app.py', 'fan_out': 1}, {'file': 'tests/helpers.py', 'fan_out': 1}]
    assert active_entry_points(rows) == rows[:1]
    assert is_test_path(rows[1]['file']) is True
