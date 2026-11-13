"""A reloaded registry class must use the parity fixture, never the real HOME."""
import json
from pathlib import Path

import pytest

from test_declared_parity_back2053 import project, run  # noqa: F401


@pytest.fixture(autouse=True)
def reloaded_claude_with_empty_home(tmp_path, monkeypatch):
    from claude_session_fixture import isolated_claude_reload
    home = tmp_path / 'empty-home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.delenv('REVEAL_CLAUDE_HOME', raising=False)
    monkeypatch.delenv('REVEAL_CLAUDE_BASE_PATH', raising=False)
    with isolated_claude_reload() as reload:
        reload()
        try:
            yield
        finally:
            monkeypatch.undo()


@pytest.mark.parametrize('spelling', ['cli', 'uri'])
def test_reloaded_adapter_uses_exact_synthetic_session_catalog(project, spelling):
    result = run('claude', spelling, '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert sorted(Path(row['path']).stem for row in answer['recent_sessions']) == [
        '2627362f-6f72-45e1-b7bb-d5a61519a388', 'infernal-earth-0118', 'my-session']
    assert answer['meta']['errors'] == []
