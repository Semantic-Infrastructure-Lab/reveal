"""Nested configuration belongs to its discovery directory, not the first caller."""
from itertools import permutations
from pathlib import Path

import pytest

from reveal.config import RevealConfig
from reveal.utils.request_cache import host_request

pytestmark = pytest.mark.component


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    for name in ('REVEAL_CONFIG', 'REVEAL_NO_CONFIG', 'REVEAL_BREADCRUMBS',
                 'REVEAL_C901_THRESHOLD', 'REVEAL_RULES_DISABLE'):
        monkeypatch.delenv(name, raising=False)
    # The tests exercise project/custom discovery, independently of installed defaults.
    read_layer = RevealConfig._read_layer.__func__

    def local_layers(cls, layer, *args, **kwargs):
        if layer in ('system', 'user'):
            return None, None
        return read_layer(cls, layer, *args, **kwargs)

    monkeypatch.setattr(RevealConfig, '_read_layer', classmethod(local_layers))
    RevealConfig.reset_request_cache()
    yield
    RevealConfig.reset_request_cache()


def _write(directory: Path, threshold, *, root=False, kind='yaml'):
    if kind == 'toml':
        path = directory / 'pyproject.toml'
        text = (f'[tool.reveal]\nroot = {str(root).lower()}\n'
                f'[tool.reveal.rules.C901]\nthreshold = {threshold}\n')
    else:
        path = directory / '.reveal.yaml'
        text = f'root: {str(root).lower()}\nrules:\n  C901:\n    threshold: {threshold}\n'
    path.write_text(text, encoding='utf-8')
    return path


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    _write(root, 100, root=True)
    for name in ('left', 'right'):
        (root / name).mkdir()
    return root.resolve()


@pytest.mark.parametrize('kind', ['yaml', 'toml'])
@pytest.mark.parametrize('order', list(permutations(('root', 'left', 'right'))))
def test_nested_and_sibling_values_do_not_depend_on_query_order(project, kind, order):
    paths = {'root': project, 'left': project / 'left', 'right': project / 'right'}
    thresholds = {'root': 100, 'left': 20, 'right': 30}
    _write(paths['left'], 20, kind=kind)
    _write(paths['right'], 30, kind=kind)
    answers = {name: RevealConfig.get(paths[name]) for name in order}
    assert {name: cfg.get_rule_config('C901', 'threshold') for name, cfg in answers.items()} == {
        name: thresholds[name] for name in order
    }
    assert all(cfg.project_root == project.resolve() for cfg in answers.values())
    for name in order:
        assert RevealConfig.get(paths[name]) is answers[name]
        assert answers[name].sources[-1].path.parent == paths[name]


def test_file_and_parent_share_cached_context_without_reloading(project, monkeypatch):
    child = project / 'left'
    _write(child, 20)
    source = child / 'app.py'
    source.write_text('value = 1\n', encoding='utf-8')
    calls = []
    load = RevealConfig._load_and_merge.__func__

    def counted(cls, start_path, *args, **kwargs):
        calls.append(start_path)
        return load(cls, start_path, *args, **kwargs)

    monkeypatch.setattr(RevealConfig, '_load_and_merge', classmethod(counted))
    first = RevealConfig.get(source)
    for _ in range(5):
        assert RevealConfig.get(child) is first
        assert RevealConfig.get(source) is first
    assert calls == [child.resolve()]
    assert first.get_rule_config('C901', 'threshold') == 20


def test_each_discovery_directory_loads_once_and_repeats_do_no_reads(project, monkeypatch):
    children = [project / 'left', project / 'right']
    for directory, threshold in zip(children, (20, 30)):
        _write(directory, threshold)
    reads = []
    load = RevealConfig._load_file_outcome.__func__

    def counted(cls, path, *args, **kwargs):
        reads.append(path)
        return load(cls, path, *args, **kwargs)

    monkeypatch.setattr(RevealConfig, '_load_file_outcome', classmethod(counted))
    for directory in (project, *children):
        RevealConfig.get(directory)
    assert reads.count(project / '.reveal.yaml') == 3
    assert all(reads.count(child / '.reveal.yaml') == 1 for child in children)
    before = list(reads)
    for _ in range(5):
        for directory in (*children, project):
            RevealConfig.get(directory)
    assert reads == before


def test_cli_overrides_and_no_config_do_not_contaminate_nested_values(project):
    child = project / 'left'
    _write(child, 20)
    parent = RevealConfig.get(project)
    plain = RevealConfig.get(child)
    overrides = {'rules': {'C901': {'threshold': 7}}}
    overridden = RevealConfig.get(child, cli_overrides=overrides)
    assert overridden.get_rule_config('C901', 'threshold') == 7
    assert RevealConfig.get(child, cli_overrides=overrides) is overridden
    assert RevealConfig.get(child, no_config=True)._config == {}
    assert RevealConfig.get(child, no_config=True, cli_overrides=overrides)._config == overrides
    assert RevealConfig.get(project) is parent
    assert RevealConfig.get(child) is plain
    assert plain.get_rule_config('C901', 'threshold') == 20
    assert parent.get_rule_config('C901', 'threshold') == 100


def test_nested_root_marker_preserves_its_own_project_boundary(project):
    child = project / 'left'
    _write(child, 20, root=True)
    parent = RevealConfig.get(project)
    nested = RevealConfig.get(child)
    assert parent.project_root == project.resolve()
    assert nested.project_root == child.resolve()
    assert nested.get_rule_config('C901', 'threshold') == 20
    assert [source.path for source in nested.sources] == [child / '.reveal.yaml']


def test_nearest_yaml_toml_precedence_and_list_merge_are_unchanged(project):
    child = project / 'left'
    _write(child, 20)
    _write(child, 30, kind='toml')
    root_config = project / '.reveal.yaml'
    root_config.write_text(root_config.read_text(encoding='utf-8') + 'ignore: [vendor]\n', encoding='utf-8')
    child_config = child / '.reveal.yaml'
    child_config.write_text(child_config.read_text(encoding='utf-8') + 'ignore: [build]\n', encoding='utf-8')
    RevealConfig.get(project)
    nested = RevealConfig.get(child)
    assert nested.get_rule_config('C901', 'threshold') == 20
    assert nested.ignore_patterns == ['vendor', 'build']
    assert [source.path.name for source in nested.sources] == [
        '.reveal.yaml', 'pyproject.toml', '.reveal.yaml',
    ]


def test_next_host_request_refreshes_all_directory_contexts(project):
    child = project / 'left'
    _write(child, 20)
    with host_request():
        parent = RevealConfig.get(project)
        nested = RevealConfig.get(child)
        assert nested.get_rule_config('C901', 'threshold') == 20
        _write(child, 40)
        assert RevealConfig.get(child) is nested
        assert nested.get_rule_config('C901', 'threshold') == 20
    with host_request():
        refreshed = RevealConfig.get(child)
        assert refreshed.get_rule_config('C901', 'threshold') == 40
        assert refreshed is not nested
        assert RevealConfig.get(project).get_rule_config('C901', 'threshold') == 100
        assert RevealConfig.get(project) is not parent


def test_environment_is_snapshotted_per_context_and_refreshed_next_request(project, monkeypatch):
    with host_request():
        monkeypatch.setenv('REVEAL_C901_THRESHOLD', '7')
        first = RevealConfig.get(project)
        assert first.get_rule_config('C901', 'threshold') == 7
        monkeypatch.setenv('REVEAL_C901_THRESHOLD', '9')
        assert RevealConfig.get(project) is first
        assert first.get_rule_config('C901', 'threshold') == 7
    with host_request():
        assert RevealConfig.get(project).get_rule_config('C901', 'threshold') == 9
