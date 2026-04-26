"""Claude adapter renderer for text output."""

import sys
from ...rendering import TypeDispatchRenderer

from .render_sessions import (
    _render_claude_session_list,
    _render_claude_session_overview,
    _render_claude_files,
    _render_claude_file_sessions,
    _render_claude_history,
    _render_claude_chain,
    _render_claude_cross_session_search,
    _render_claude_search_results,
)
from .render_messages import (
    _tool_summary,
    _parse_assistant_blocks,
    _format_tool_params,
    _render_raw_block,
    _render_claude_tool_calls,
    _render_claude_tool_summary,
    _render_claude_thinking,
    _render_claude_user_messages,
    _render_claude_assistant_messages,
    _render_claude_message,
    _render_claude_message_range,
    _render_claude_filtered_results,
    _render_claude_messages,
)
from .render_system import (
    _render_claude_info,
    _render_claude_settings,
    _render_claude_plans,
    _render_claude_plan,
    _render_claude_config,
    _render_claude_memory,
    _render_claude_agents,
    _render_claude_agent,
    _render_claude_hooks,
)
from .render_analytics import (
    _render_claude_analytics,
    _render_claude_errors,
    _render_claude_workflow,
    _render_claude_token_breakdown,
    _render_claude_context,
)


class ClaudeRenderer(TypeDispatchRenderer):
    """Renderer for Claude adapter results.

    Uses TypeDispatchRenderer for automatic routing to _render_{type}() methods.
    Rendering logic lives in render_sessions, render_messages, render_system,
    and render_analytics submodules.
    """

    # Session renderers
    _render_claude_session_list = staticmethod(_render_claude_session_list)
    _render_claude_session_overview = staticmethod(_render_claude_session_overview)
    _render_claude_files = staticmethod(_render_claude_files)
    _render_claude_file_sessions = staticmethod(_render_claude_file_sessions)
    _render_claude_history = staticmethod(_render_claude_history)
    _render_claude_chain = staticmethod(_render_claude_chain)
    _render_claude_cross_session_search = staticmethod(_render_claude_cross_session_search)
    _render_claude_search_results = staticmethod(_render_claude_search_results)

    # Message renderers
    _tool_summary = staticmethod(_tool_summary)
    _parse_assistant_blocks = staticmethod(_parse_assistant_blocks)
    _format_tool_params = staticmethod(_format_tool_params)
    _render_raw_block = staticmethod(_render_raw_block)
    _render_claude_tool_calls = staticmethod(_render_claude_tool_calls)
    _render_claude_tool_summary = staticmethod(_render_claude_tool_summary)
    _render_claude_thinking = staticmethod(_render_claude_thinking)
    _render_claude_user_messages = staticmethod(_render_claude_user_messages)
    _render_claude_assistant_messages = staticmethod(_render_claude_assistant_messages)
    _render_claude_message = staticmethod(_render_claude_message)
    _render_claude_message_range = staticmethod(_render_claude_message_range)
    _render_claude_filtered_results = staticmethod(_render_claude_filtered_results)
    _render_claude_messages = staticmethod(_render_claude_messages)

    # System renderers
    _render_claude_info = staticmethod(_render_claude_info)
    _render_claude_settings = staticmethod(_render_claude_settings)
    _render_claude_plans = staticmethod(_render_claude_plans)
    _render_claude_plan = staticmethod(_render_claude_plan)
    _render_claude_config = staticmethod(_render_claude_config)
    _render_claude_memory = staticmethod(_render_claude_memory)
    _render_claude_agents = staticmethod(_render_claude_agents)
    _render_claude_agent = staticmethod(_render_claude_agent)
    _render_claude_hooks = staticmethod(_render_claude_hooks)

    # Analytics renderers
    _render_claude_analytics = staticmethod(_render_claude_analytics)
    _render_claude_errors = staticmethod(_render_claude_errors)
    _render_claude_workflow = staticmethod(_render_claude_workflow)
    _render_claude_token_breakdown = staticmethod(_render_claude_token_breakdown)
    _render_claude_context = staticmethod(_render_claude_context)

    @classmethod
    def _render_text(cls, result: dict) -> None:
        """Dispatch to type-specific renderer with custom fallback."""
        result_type = result.get('type', 'default')

        method_name = f'_render_{result_type}'
        method = getattr(cls, method_name, None)

        if method and callable(method):
            method(result)
        else:
            cls._render_fallback(result)

    @staticmethod
    def _render_fallback(result: dict) -> None:
        """Default fallback for unknown types."""
        result_type = result.get('type', 'unknown')
        session = result.get('session', 'unknown')
        print(f"Type: {result_type}")
        print(f"Session: {session}")
        print()

        skip = {'type', 'session', 'contract_version', 'source', 'source_type',
                'adapter', 'uri', 'timestamp'}
        for key, value in result.items():
            if key not in skip:
                if isinstance(value, (list, dict)) and len(str(value)) > 100:
                    print(f"{key}: [{type(value).__name__} with {len(value)} items]")
                else:
                    print(f"{key}: {value}")

    @classmethod
    def render_element(cls, result: dict, format: str = 'text') -> None:
        """Render specific Claude element (message, tool call, etc.)."""
        if cls.should_render_json(format):
            cls.render_json(result)
            return

        if 'content' in result:
            print(result['content'])
        else:
            for key, value in result.items():
                if key not in ('adapter', 'uri', 'timestamp'):
                    print(f"{key}: {value}")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error: {error}", file=sys.stderr)
