"""Claude adapter renderer for text output."""

import sys
from ...rendering import TypeDispatchRenderer


class ClaudeRenderer(TypeDispatchRenderer):
    """Renderer for Claude adapter results.

    Uses TypeDispatchRenderer for automatic routing to _render_{type}() methods.
    """

    @staticmethod
    def _render_claude_session_overview(result: dict) -> None:
        """Render session overview."""
        print(f"Claude Session: {result.get('session', 'unknown')}")
        print(f"Messages: {result.get('message_count', 0)}")
        print(f"User: {result.get('user_messages', 0)} | Assistant: {result.get('assistant_messages', 0)}")
        if 'duration' in result:
            print(f"Duration: {result['duration']}")
        print()

        tools = result.get('tools_used', {})
        if tools:
            print("Tools Used:")
            for tool, count in sorted(tools.items(), key=lambda x: -x[1]):
                print(f"  {tool}: {count}")
            print()

        print(f"Conversation: {result.get('conversation_file', 'unknown')}")

    @staticmethod
    def _render_claude_tool_calls(result: dict) -> None:
        """Render tool calls with clear command display for Bash."""
        tool_name = result.get('tool_name', 'unknown')
        call_count = result.get('call_count', 0)
        session = result.get('session', 'unknown')

        print(f"Tool: {tool_name} ({call_count} calls)")
        print(f"Session: {session}")
        print()

        calls = result.get('calls', [])
        for i, call in enumerate(calls, 1):
            inp = call.get('input', {})

            if tool_name == 'Bash':
                cmd = inp.get('command', '?')
                desc = inp.get('description', '')
                # Show command with description
                if desc:
                    print(f"[{i:3}] {desc}")
                    print(f"      $ {cmd[:100]}")
                else:
                    print(f"[{i:3}] $ {cmd[:100]}")
                if len(cmd) > 100:
                    print(f"        ... ({len(cmd)} chars)")
            elif tool_name == 'Read':
                path = inp.get('file_path', '?')
                print(f"[{i:3}] {path}")
            elif tool_name == 'Edit':
                path = inp.get('file_path', '?')
                print(f"[{i:3}] {path}")
            elif tool_name == 'Write':
                path = inp.get('file_path', '?')
                print(f"[{i:3}] {path}")
            elif tool_name == 'Grep':
                pattern = inp.get('pattern', '?')
                path = inp.get('path', '.')
                print(f"[{i:3}] '{pattern}' in {path}")
            elif tool_name == 'Glob':
                pattern = inp.get('pattern', '?')
                print(f"[{i:3}] {pattern}")
            else:
                # Generic: show first few input keys
                preview = ', '.join(f"{k}={str(v)[:30]}" for k, v in list(inp.items())[:3])
                print(f"[{i:3}] {preview}")

    @staticmethod
    def _render_claude_tool_summary(result: dict) -> None:
        """Render tool usage summary."""
        session = result.get('session', 'unknown')
        total = result.get('total_calls', 0)

        print(f"Tool Summary: {session}")
        print(f"Total Calls: {total}")
        print()

        tools = result.get('tools', {})
        for tool, stats in sorted(tools.items(), key=lambda x: -x[1].get('count', 0)):
            count = stats.get('count', 0)
            success_rate = stats.get('success_rate', 'N/A')
            print(f"  {tool}: {count} calls ({success_rate} success)")

    @staticmethod
    def _render_claude_errors(result: dict) -> None:
        """Render error summary."""
        session = result.get('session', 'unknown')
        count = result.get('error_count', 0)

        print(f"Errors: {session}")
        print(f"Total: {count}")
        print()

        errors = result.get('errors', [])
        for i, err in enumerate(errors[:20], 1):
            context = err.get('context', {})
            tool = context.get('tool_name', err.get('tool_name', 'unknown'))
            preview = err.get('content_preview', '')[:60]
            print(f"[{i:3}] {tool}: {preview}")

        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors")

    @classmethod
    def _render_text(cls, result: dict) -> None:
        """Dispatch to type-specific renderer with custom fallback."""
        result_type = result.get('type', 'default')

        # Convert type to method name (e.g., 'claude_tool_calls' -> '_render_claude_tool_calls')
        method_name = f'_render_{result_type}'
        method = getattr(cls, method_name, None)

        if method and callable(method):
            method(result)
        else:
            # Custom fallback for Claude adapter (not JSON)
            cls._render_fallback(result)

    @staticmethod
    def _render_fallback(result: dict) -> None:
        """Default fallback for unknown types."""
        # Show type and session
        result_type = result.get('type', 'unknown')
        session = result.get('session', 'unknown')
        print(f"Type: {result_type}")
        print(f"Session: {session}")
        print()

        # Show other fields
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

        # Text format
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
