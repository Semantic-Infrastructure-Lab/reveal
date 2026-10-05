"""Negative controls for computed clean defaults retired by BACK-1638."""
from pathlib import Path
import importlib
import pytest


@pytest.mark.parametrize('module_name', ['reveal.adapters.codex.handlers.system',
                                        'reveal.adapters.claude.handlers.system'])
def test_unreadable_directory_is_unknown_not_empty(module_name, tmp_path, monkeypatch):
    module = importlib.import_module(module_name)
    def unreadable(self):
        raise PermissionError('recorded permission denied')
    monkeypatch.setattr(Path, 'iterdir', unreadable)
    result = module._path_info(tmp_path)
    assert result['count'] is None
    assert 'permission denied' in result['error']


def test_calls_configuration_failure_propagates(monkeypatch, tmp_path):
    from reveal.adapters.calls import index
    def broken(*args, **kwargs):
        raise RuntimeError('recorded config failure')
    monkeypatch.setattr('reveal.config.get_config', broken)
    with pytest.raises(RuntimeError, match='recorded config failure'):
        index._project_entry_point_decorators(tmp_path)
