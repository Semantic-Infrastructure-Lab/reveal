"""Claude Code conversation analysis adapter.

Provides progressive disclosure for Claude Code conversations:
- Session overview (messages, tools, duration, thinking)
- Message filtering (user, assistant, thinking, tools)
- Tool usage analytics and filtering
- Error detection with context
- Token usage estimates and optimization insights
- File operation tracking

Analyzes JSONL conversation files from ~/.claude/projects/
"""

from .adapter import ClaudeAdapter

__all__ = ['ClaudeAdapter']
