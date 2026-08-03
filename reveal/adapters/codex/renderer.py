"""Codex adapter renderer — dispatches by result['type']."""

import sys

from ...rendering import TypeDispatchRenderer

from .render_sessions import (
    _render_codex_session_list,
    _render_codex_session_overview,
    _render_codex_content_search,
)
from .render_messages import (
    _render_codex_messages,
    _render_codex_digest,
    _render_codex_exchanges,
    _render_codex_message,
)
from .render_system import (
    _render_codex_info,
    _render_codex_history,
    _render_codex_config,
    _render_codex_memories,
    _render_codex_rules,
    _render_codex_skills,
    _render_codex_skill,
    _render_codex_plugins,
    _render_codex_plugin,
)
from .render_analytics import (
    _render_codex_tools,
    _render_codex_errors,
    _render_codex_shell,
    _render_codex_tokens,
    _render_codex_workflow,
    _render_codex_timeline,
    _render_codex_goal,
    _render_codex_memories_pipeline,
)


class CodexRenderer(TypeDispatchRenderer):
    """Renderer for Codex adapter results.

    TypeDispatchRenderer automatically routes result['type'] → _render_{type}().
    """

    # Session renderers
    _render_codex_session_list = staticmethod(_render_codex_session_list)
    _render_codex_session_overview = staticmethod(_render_codex_session_overview)

    # Message renderer (also used for ?last)
    _render_codex_messages = staticmethod(_render_codex_messages)
    _render_codex_digest = staticmethod(_render_codex_digest)
    _render_codex_exchanges = staticmethod(_render_codex_exchanges)
    _render_codex_message = staticmethod(_render_codex_message)

    # System renderers
    _render_codex_info = staticmethod(_render_codex_info)
    _render_codex_history = staticmethod(_render_codex_history)
    _render_codex_config = staticmethod(_render_codex_config)
    _render_codex_memories = staticmethod(_render_codex_memories)
    _render_codex_rules = staticmethod(_render_codex_rules)
    _render_codex_skills = staticmethod(_render_codex_skills)
    _render_codex_skill = staticmethod(_render_codex_skill)
    _render_codex_plugins = staticmethod(_render_codex_plugins)
    _render_codex_plugin = staticmethod(_render_codex_plugin)

    # Analytics renderers
    _render_codex_tools = staticmethod(_render_codex_tools)
    _render_codex_errors = staticmethod(_render_codex_errors)
    _render_codex_shell = staticmethod(_render_codex_shell)
    _render_codex_tokens = staticmethod(_render_codex_tokens)
    _render_codex_workflow = staticmethod(_render_codex_workflow)
    _render_codex_timeline = staticmethod(_render_codex_timeline)
    _render_codex_goal = staticmethod(_render_codex_goal)
    _render_codex_memories_pipeline = staticmethod(_render_codex_memories_pipeline)

    # Content search renderer
    _render_codex_content_search = staticmethod(_render_codex_content_search)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error: {error}", file=sys.stderr)
