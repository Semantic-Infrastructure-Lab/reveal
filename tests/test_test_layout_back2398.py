"""Configured layout feature controls; declarations stay separate from merged lists."""
from dataclasses import replace

import pytest

from reveal.config import RevealConfig
from reveal.utils.path_utils import TestLayout as Layout
from reveal.analyzers.imports.types import ImportGraph


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    monkeypatch.setattr(RevealConfig, '_get_user_config_path', staticmethod(lambda: tmp_path / 'no-user.yaml'))
    RevealConfig.reset_request_cache()
    yield
    RevealConfig.reset_request_cache()


def project(tmp_path, yaml='test_layout:\n  additional_paths: [t/unit, src/helper.rs]\n'):
    root = tmp_path / 'repo'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="layout"\n', encoding='utf-8')
    (root / '.reveal.yaml').write_text(yaml, encoding='utf-8')
    return root.resolve()


def bind(root):
    return RevealConfig.get(root).apply_test_layout(Layout.for_path(root))


def test_literal_paths_select_files_and_component_bounded_subtrees(tmp_path):
    root = project(tmp_path, 'test_layout:\n  additional_paths: [./t/unit, "t\\\\unit", src/helper.rs, "literal*", "$HOME", "~"]\n')
    layout = bind(root)
    assert layout.additional_paths == tuple(sorted(('t/unit', 'src/helper.rs', 'literal*', '$HOME', '~')))
    for name in ('t/unit/worker.py', 'src/helper.rs', 'literal*/a.py', '$HOME/a.py', '~/a.py', 'tests/helper.py'):
        assert layout.is_test(root / name), name
    for name in ('t/unitized/a.py', 'src/t/unit/a.py', 'src/helper.rsx', 'literalZZ/a.py', 'src/lib.rs'):
        assert not layout.is_test(root / name), name


@pytest.mark.parametrize('value', ['null', '{}', 'wrong', '[null]', '[1]', '[""]', '["../outside"]', '["t/../unit"]', '["/abs"]', '["C:relative"]', '["C:/abs"]', '["\\\\\\\\server/share"]', '["bad\\0path"]'])
def test_selected_invalid_policy_is_rejected_at_adoption(tmp_path, value):
    root = project(tmp_path, f'test_layout:\n  additional_paths: {value}\n')
    config = RevealConfig.get(root)
    with pytest.raises(ValueError, match='test_layout'):
        config.apply_test_layout(Layout.for_path(root))


def test_empty_yaml_replaces_lower_toml_without_changing_global_merge(tmp_path):
    root = project(tmp_path, 'test_layout:\n  additional_paths: []\n')
    (root / 'pyproject.toml').write_text('[tool.reveal.test_layout]\nadditional_paths=["t/unit"]\n', encoding='utf-8')
    config = RevealConfig.get(root)
    assert config._config['test_layout']['additional_paths'] == ['t/unit']
    assert config.apply_test_layout(Layout.for_path(root)).additional_paths == ()


def test_ignored_ancestor_and_descendant_declarations_cannot_change_anchor_policy(tmp_path):
    root = project(tmp_path)
    (tmp_path / '.reveal.yaml').write_text('test_layout: malformed\n', encoding='utf-8')
    child = root / 'child'
    child.mkdir()
    (child / '.reveal.yaml').write_text('test_layout:\n  additional_paths: [child]\n', encoding='utf-8')
    a = RevealConfig.get(root).apply_test_layout(Layout.for_path(root))
    b = RevealConfig.get(child).apply_test_layout(Layout.for_path(child))
    assert a.identity == b.identity
    assert b.additional_paths == ('src/helper.rs', 't/unit')


def test_policy_graph_identity_retains_production_edges_to_helper_targets(tmp_path):
    root = project(tmp_path)
    configured = bind(root)
    conventional = Layout.for_path(root)
    graph = ImportGraph()
    helper, target, prod = root / 't/unit/worker.py', root / 'src/helper.rs', root / 'src/lib.rs'
    graph.add_dependency(helper, target)
    graph.add_dependency(prod, target)
    assert graph.without_test_importers(configured).dependencies == {prod: {target}}
    assert graph.without_test_importers(conventional).dependencies == {helper: {target}, prod: {target}}
    assert graph.dependencies == {helper: {target}, prod: {target}}
    assert replace(configured, source='explicit_root').identity == configured.identity


def test_whole_scope_and_snapshot_relocation_are_explicit(tmp_path):
    root = project(tmp_path, 'test_layout:\n  additional_paths: [.]\n')
    layout = bind(root)
    assert layout.as_dict(root)['whole_scope'] is True
    relocated = layout.relocate(observed_root=tmp_path / 'neutral', logical_root=root / 'src')
    assert relocated.is_test(tmp_path / 'neutral/lib.rs')
    assert relocated.additional_paths == ('.',)


def test_custom_selection_uses_project_anchor_and_old_layout_stays_immutable(tmp_path, monkeypatch):
    root = project(tmp_path)
    custom = tmp_path / 'custom.yaml'
    custom.write_text('test_layout:\n  additional_paths: [src/lib.rs]\n', encoding='utf-8')
    monkeypatch.setenv('REVEAL_CONFIG', str(custom))
    old = bind(root)
    assert old.additional_paths == ('src/lib.rs',)
    custom.write_text('test_layout:\n  additional_paths: [t/unit]\n', encoding='utf-8')
    RevealConfig.reset_request_cache()
    new = bind(root)
    assert new.identity != old.identity
    assert old.is_test(root / 'src/lib.rs')
    assert not new.is_test(root / 'src/lib.rs')


def test_configured_importer_exclusion_entrypoint_and_external_agree(tmp_path):
    from reveal.adapters.imports import ImportsAdapter

    root = project(tmp_path)
    files = {
        'pkg/__init__.py': '', 'pkg/core.py': 'VALUE=1\n',
        'pkg/app.py': 'from src.helper import VALUE\nimport requests\n',
        'src/__init__.py': '', 'src/helper.py': 'VALUE=1\n',
        't/unit/helper.py': 'from pkg.core import VALUE\nimport pytest\n',
        't/unitized/app.py': 'from pkg.core import VALUE\nimport requests\n',
    }
    for name, content in files.items():
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding='utf-8')
    adapter = ImportsAdapter(str(root), 'importers&tests=include')
    include = adapter.get_structure()
    graph = adapter.analysis.graph
    scanned = adapter.analysis.scanned_files.copy()
    exclude = adapter.get_view('importers&tests=exclude')
    assert adapter.analysis.graph is graph
    assert adapter.analysis.scanned_files == scanned
    assert include['metadata'] == exclude['metadata']
    core = next(row for row in exclude['entries'] if row['file'] == 'pkg/core.py')
    assert core['importers'] == ['t/unitized/app.py']
    assert next(row for row in exclude['entries'] if row['file'] == 'src/helper.py')['importers'] == ['pkg/app.py']
    external = adapter.get_view('external&tests=exclude')
    assert {row['package'] for row in external['external_packages']} == {'requests'}
    entries = adapter.get_view('entrypoints')['entries']
    assert next(row for row in entries if row['file'] == 't/unit/helper.py')['is_test'] is True
    assert next(row for row in entries if row['file'] == 't/unitized/app.py')['is_test'] is False


def test_identical_tree_diff_validates_policy_before_proving_equality(tmp_path):
    pygit2 = pytest.importorskip('pygit2')
    from reveal.diff.architecture_diff import run_architecture_diff

    root = project(tmp_path, 'test_layout:\n  additional_paths: [../escape]\n')
    repo = pygit2.init_repository(str(root))
    repo.index.add_all()
    repo.index.write()
    author = pygit2.Signature('fixture', 'fixture@example.invalid')
    revision = str(repo.create_commit('HEAD', author, author, 'fixture', repo.index.write_tree(), []))
    with pytest.raises(ValueError, match='test_layout'):
        run_architecture_diff(root, revision)


@pytest.mark.parametrize('block', ['{additional_paths: !!set {foo: null}}', '{additional_paths: [2026-10-30]}', '{1: wrong}', '&loop {additional_paths: [*loop]}'])
def test_unserializable_yaml_is_invalid_only_when_selected(tmp_path, block):
    root = project(tmp_path, 'test_layout: ' + block + '\n')
    with pytest.raises(ValueError, match='test_layout'):
        bind(root)
    (root / '.reveal.yaml').write_text('test_layout: {}\n', encoding='utf-8')
    (tmp_path / '.reveal.yaml').write_text('test_layout: ' + block + '\n', encoding='utf-8')
    RevealConfig.reset_request_cache()
    assert bind(root).additional_paths == ()


def test_config_inspection_discloses_actual_cwd_policy_and_ignored_sources(tmp_path, monkeypatch):
    from reveal.adapters.reveal.config import get_config
    root = project(tmp_path)
    (tmp_path / '.reveal.yaml').write_text('test_layout:\n  additional_paths: [ignored]\n', encoding='utf-8')
    monkeypatch.chdir(root)
    result = get_config()
    assert result['metadata']['test_layout_anchor'] == root.as_posix()
    assert result['test_layout']['effective']['additional_paths'] == ['src/helper.rs', 't/unit']
    assert result['test_layout']['declarations'][0]['status'] == 'ignored'
    assert result['test_layout']['declarations'][-1]['status'] == 'selected'
    assert result['test_layout']['inspection_scope'] == 'current_directory'


def test_equivalent_selectors_reuse_graph_view_but_current_provenance_is_fresh(tmp_path):
    from reveal.analyzers.imports.views import ImportView
    from reveal.analyzers.imports.types import ImportAnalysis
    root = project(tmp_path, 'test_layout:\n  additional_paths: [t/unit, ./src/helper.rs, t/unit]\n')
    old = bind(root)
    graph = ImportGraph()
    graph.add_dependency(root / 't/unit/worker.py', root / 'src/lib.rs')
    graph.add_dependency(root / 'src/app.py', root / 'src/lib.rs')
    analysis = ImportAnalysis(graph=graph, scanned_files={root / 't/unit/worker.py', root / 'src/app.py'})
    old_view = ImportView(analysis, root, None, 100, tests='exclude', test_layout=old)
    old_metadata = old_view.test_scope()
    (root / '.reveal.yaml').write_text('test_layout:\n  additional_paths: [src/helper.rs, t/unit]\n', encoding='utf-8')
    RevealConfig.reset_request_cache()
    current = bind(root)
    assert old.identity == current.identity
    assert old.declaration != current.declaration
    assert graph.without_test_importers(old) is graph.without_test_importers(current)
    new_view = ImportView(analysis, root, None, 100, tests='exclude', test_layout=current)
    assert new_view.test_scope()['effective_policy'] == old_metadata['effective_policy']
    assert new_view.test_scope()['declaration'] != old_metadata['declaration']
    assert old_view.test_scope() == old_metadata
    (root / '.reveal.yaml').write_text('test_layout:\n  additional_paths: []\n', encoding='utf-8')
    RevealConfig.reset_request_cache()
    changed = bind(root)
    assert graph.without_test_importers(changed) is not graph.without_test_importers(old)
    assert old_view._edges('include').dependencies == {root / 'src/app.py': {root / 'src/lib.rs'}}


def test_direct_context_normalizes_immutable_tuple_and_rejects_mutable_list(tmp_path):
    layout = Layout(tmp_path.resolve(), 'project', additional_paths=('t/unit', './src/helper.rs', 't\\unit'))
    assert layout.additional_paths == ('src/helper.rs', 't/unit')
    with pytest.raises(ValueError, match='immutable tuple'):
        Layout(tmp_path.resolve(), 'project', additional_paths=['t/unit'])
