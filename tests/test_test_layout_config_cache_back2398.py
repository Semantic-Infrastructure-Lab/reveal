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
