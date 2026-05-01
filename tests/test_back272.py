"""Tests for BACK-272: REVEAL_CLAUDE_BASE_PATH env var as persistent --base-path default.

When REVEAL_CLAUDE_BASE_PATH is set, claude:// URIs use it as the default base path
without requiring --base-path on every command. CLI --base-path still takes precedence.
"""

import json
import os
import pytest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch, MagicMock

from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.cli.routing.uri import generic_adapter_handler


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_projects(tmp_path: Path, session_name: str = 'my-sess') -> Path:
    """Return a projects dir with one session JSONL."""
    projects = tmp_path / 'projects'
    proj = projects / f'-home-user-tia-sessions-{session_name}'
    proj.mkdir(parents=True, exist_ok=True)
    f = proj / f'{session_name}.jsonl'
    f.write_text(json.dumps({
        'type': 'user',
        'timestamp': '2026-01-01T00:00:00',
        'message': {'role': 'user', 'content': 'hello world'},
    }) + '\n')
    return projects


def _make_args(**kwargs) -> Namespace:
    defaults = {
        'base_path': None,
        'verbose': False,
        'check': False,
        'format': 'text',
        'output': None,
        'max_tokens': None,
        'field': None,
        'budget': None,
        'max_cost': None,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


# ─── Unit: env var applied in generic_adapter_handler ─────────────────────────

class TestEnvVarAppliedInHandler:

    def test_env_var_calls_reconfigure_base_path(self, tmp_path):
        """REVEAL_CLAUDE_BASE_PATH env var triggers reconfigure_base_path."""
        projects = _make_projects(tmp_path)
        adapter = MagicMock()
        adapter_class = MagicMock(return_value=adapter)
        adapter_class.from_uri = MagicMock(return_value=adapter)
        adapter.reconfigure_base_path = MagicMock()
        renderer_class = MagicMock()
        renderer_class.render_error = MagicMock()

        with patch.dict(os.environ, {'REVEAL_CLAUDE_BASE_PATH': str(projects)}):
            with patch('reveal.cli.routing.uri._handle_rendering'):
                generic_adapter_handler(
                    adapter_class, renderer_class,
                    'claude', 'session/my-sess', None, _make_args()
                )

        adapter.reconfigure_base_path.assert_called_once_with(projects)

    def test_cli_arg_overrides_env_var(self, tmp_path):
        """--base-path CLI arg takes precedence over REVEAL_CLAUDE_BASE_PATH."""
        projects_env = _make_projects(tmp_path / 'from_env')
        projects_cli = _make_projects(tmp_path / 'from_cli')
        adapter = MagicMock()
        adapter_class = MagicMock(return_value=adapter)
        adapter_class.from_uri = MagicMock(return_value=adapter)
        adapter.reconfigure_base_path = MagicMock()
        renderer_class = MagicMock()

        with patch.dict(os.environ, {'REVEAL_CLAUDE_BASE_PATH': str(projects_env)}):
            with patch('reveal.cli.routing.uri._handle_rendering'):
                generic_adapter_handler(
                    adapter_class, renderer_class,
                    'claude', 'session/my-sess', None,
                    _make_args(base_path=str(projects_cli))
                )

        adapter.reconfigure_base_path.assert_called_once_with(projects_cli)

    def test_no_env_var_no_cli_skips_reconfigure(self, tmp_path):
        """Without --base-path or env var, reconfigure_base_path is not called."""
        adapter = MagicMock()
        adapter_class = MagicMock(return_value=adapter)
        adapter_class.from_uri = MagicMock(return_value=adapter)
        adapter.reconfigure_base_path = MagicMock()
        renderer_class = MagicMock()

        env = {k: v for k, v in os.environ.items() if k != 'REVEAL_CLAUDE_BASE_PATH'}
        with patch.dict(os.environ, env, clear=True):
            with patch('reveal.cli.routing.uri._handle_rendering'):
                generic_adapter_handler(
                    adapter_class, renderer_class,
                    'claude', 'session/my-sess', None, _make_args()
                )

        adapter.reconfigure_base_path.assert_not_called()

    def test_adapter_without_reconfigure_ignores_env_var(self, tmp_path):
        """Adapters without reconfigure_base_path are unaffected."""
        projects = _make_projects(tmp_path)
        adapter = MagicMock(spec=[])  # no reconfigure_base_path attribute
        adapter_class = MagicMock(return_value=adapter)
        adapter_class.from_uri = MagicMock(return_value=adapter)
        renderer_class = MagicMock()

        with patch.dict(os.environ, {'REVEAL_CLAUDE_BASE_PATH': str(projects)}):
            with patch('reveal.cli.routing.uri._handle_rendering'):
                generic_adapter_handler(
                    adapter_class, renderer_class,
                    'ast', 'src/', None, _make_args()
                )
        # No AttributeError raised — clean pass


# ─── Integration: env var wires through to session resolution ─────────────────

class TestEnvVarIntegration:

    def test_env_var_resolves_session(self, tmp_path):
        """With REVEAL_CLAUDE_BASE_PATH set, adapter finds the session JSONL."""
        projects = _make_projects(tmp_path, 'test-session-0101')
        adapter = ClaudeAdapter('session/test-session-0101')

        # Before reconfigure: uses default (won't find the session)
        assert adapter.conversation_path is None or \
            str(adapter.CONVERSATION_BASE) != str(projects)

        adapter.reconfigure_base_path(projects)
        assert adapter.conversation_path is not None
        assert adapter.conversation_path.exists()

    def test_session_dir_rejected_via_reconfigure(self, tmp_path):
        """reconfigure_base_path rejects a session dir (JSONL at root)."""
        session_dir = tmp_path / 'my-sess'
        session_dir.mkdir()
        (session_dir / 'my-sess.jsonl').write_text('')

        adapter = ClaudeAdapter('session/my-sess')
        with pytest.raises(ValueError, match="Try the parent directory instead"):
            adapter.reconfigure_base_path(session_dir)
