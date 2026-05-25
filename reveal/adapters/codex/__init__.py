"""OpenAI Codex CLI session analysis adapter.

Provides progressive disclosure for Codex sessions stored in ~/.codex/:
- Session list from SQLite (state_5.sqlite)
- Session overview (title, turns, model, tokens, duration, tool calls)
- Message extraction (user/agent turns)
- Tool call pairing (function_call + output)
- Shell execution pairing (exec_command_begin + end)
- Error/warning event extraction
- System resources (history, config, memories, rules)
"""

from .adapter import CodexAdapter
from .renderer import CodexRenderer

__all__ = ['CodexAdapter', 'CodexRenderer']
