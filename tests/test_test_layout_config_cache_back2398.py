"""Policy binding must not make subsequent walker environment inputs stale."""
import pytest

from reveal.config import RevealConfig
from reveal.adapters.imports import ImportsAdapter


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    for name in ('REVEAL_CONFIG', 'REVEAL_NO_CONFIG', 'REVEAL_IGNORE'):
        monkeypatch.delenv(name, raising=False)
    RevealConfig.reset_request_cache()
    yield
    RevealConfig.reset_request_cache()


def test_single_file_policy_binding_does_not_freeze_later_directory_ignore(tmp_path, monkeypatch):
    (tmp_path / 'visible.py').write_text('import math\n', encoding='utf-8')
    (tmp_path / 'included_child').mkdir()
    (tmp_path / 'included_child' / 'hidden.py').write_text('import decimal\n', encoding='utf-8')
    ImportsAdapter(str(tmp_path / 'visible.py'), 'scope=path').get_structure()
    monkeypatch.setenv('REVEAL_IGNORE', 'included_child/')
    result = ImportsAdapter(str(tmp_path)).get_structure()
    assert set(result['files']) == {'visible.py'}
    assert result['metadata']['scanned_files'] == 1


def test_only_actual_loader_environment_inputs_change_config_identity(tmp_path, monkeypatch):
    first = RevealConfig.get(tmp_path)
    assert RevealConfig.get(tmp_path) is first
    monkeypatch.setenv('REVEAL_UNREAD_LAYOUT_CACHE_CONTROL', 'different')
    assert RevealConfig.get(tmp_path) is first
    monkeypatch.setenv('REVEAL_IGNORE', 'helpers/')
    second = RevealConfig.get(tmp_path)
    assert second is not first
    assert second.ignore_patterns() == ['helpers/']
    assert first.ignore_patterns() == []
    assert RevealConfig.get(tmp_path) is second


@pytest.mark.parametrize('selector', ['xdg', 'home'])
def test_user_config_selection_is_part_of_cache_identity(tmp_path, monkeypatch, selector):
    roots = [tmp_path / 'left', tmp_path / 'right']
    for root, ignored in zip(roots, ('left/', 'right/')):
        directory = root / ('reveal' if selector == 'xdg' else '.config/reveal')
        directory.mkdir(parents=True)
        (directory / 'config.yaml').write_text(f'ignore: [{ignored}]\n', encoding='utf-8')
    if selector == 'xdg':
        monkeypatch.setenv('XDG_CONFIG_HOME', str(roots[0]))
    else:
        monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
        monkeypatch.setattr('pathlib.Path.home', classmethod(lambda cls: roots[0]))
    first = RevealConfig.get(tmp_path)
    if selector == 'xdg':
        monkeypatch.setenv('XDG_CONFIG_HOME', str(roots[1]))
    else:
        monkeypatch.setattr('pathlib.Path.home', classmethod(lambda cls: roots[1]))
    second = RevealConfig.get(tmp_path)
    assert second is not first
    assert first.ignore_patterns() == ['left/']
    assert second.ignore_patterns() == ['right/']
    assert RevealConfig.get(tmp_path) is second


def test_relative_custom_selection_is_bound_to_its_loading_directory(tmp_path, monkeypatch):
    from reveal.utils.path_utils import TestLayout as Layout
    roots = [tmp_path / 'left', tmp_path / 'right']
    for root, ignored in zip(roots, ('left', 'right')):
        root.mkdir()
        (root / 'policy.yaml').write_text(f'test_layout:\n  additional_paths: [{ignored}]\n', encoding='utf-8')
    monkeypatch.setenv('REVEAL_CONFIG', 'policy.yaml')
    monkeypatch.chdir(roots[0])
    first = RevealConfig.get(tmp_path)
    monkeypatch.chdir(roots[1])
    second = RevealConfig.get(tmp_path)
    assert second is not first
    layout = Layout(tmp_path.resolve(), 'project')
    assert first.apply_test_layout(layout).additional_paths == ('left',)
    assert second.apply_test_layout(layout).additional_paths == ('right',)
    assert first.sources[0].path == roots[0] / 'policy.yaml'
    assert second.sources[0].path == roots[1] / 'policy.yaml'
    assert RevealConfig.get(tmp_path) is second
