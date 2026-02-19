"""Claude adapter renderer for text output."""

import sys
from ...rendering import TypeDispatchRenderer


class ClaudeRenderer(TypeDispatchRenderer):
    """Renderer for Claude adapter results.

    Uses TypeDispatchRenderer for automatic routing to _render_{type}() methods.
    """

    @staticmethod
    def _render_claude_session_list(result: dict) -> None:
        """Render recent sessions list."""
        total = result.get('session_count', 0)
        recent = result.get('recent_sessions', [])
        print(f"Claude Sessions: {total} total | {len(recent)} most recent\n")
        print(f"  {'SESSION':<36} {'MODIFIED':<17} {'SIZE':>7}")
        print(f"  {'-'*36} {'-'*17} {'-'*7}")
        for s in recent:
            name = s.get('session', '?')
            if len(name) > 36:
                name = name[-36:]
            mod = s.get('modified', '')[:16].replace('T', ' ')
            kb = s.get('size_kb', 0)
            print(f"  {name:<36} {mod:<17} {kb:>5}kb")
        print()
        usage = result.get('usage', {})
        if usage:
            print("Usage:")
            for key, cmd in list(usage.items())[:3]:
                print(f"  {cmd}")
            print("  ...")

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
        """Render error summary with context."""
        session = result.get('session', 'unknown')
        count = result.get('error_count', 0)

        print(f"Errors: {session}")
        print(f"Total: {count}")
        print()

        errors = result.get('errors', [])
        for i, err in enumerate(errors[:20], 1):
            context = err.get('context', {})
            tool = context.get('tool_name', 'unknown')
            error_type = err.get('error_type', '?')
            msg_idx = err.get('message_index', '?')

            print(f"[{i:3}] Message {msg_idx} | {tool} | {error_type}")

            # Show tool input if available
            tool_input = context.get('tool_input_preview')
            if tool_input:
                # Truncate and show on separate line for readability
                if len(tool_input) > 70:
                    tool_input = tool_input[:67] + '...'
                print(f"      Input: {tool_input}")

            # Show error preview
            preview = err.get('content_preview', '')
            # Find first line with actual error content
            lines = preview.split('\n')
            for line in lines[:3]:
                if line.strip():
                    if len(line) > 70:
                        line = line[:67] + '...'
                    print(f"      Error: {line}")
                    break
            print()

        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors")

    @staticmethod
    def _render_claude_files(result: dict) -> None:
        """Render files touched summary."""
        session = result.get('session', 'unknown')
        total = result.get('total_operations', 0)
        unique = result.get('unique_files', 0)

        print(f"Files Touched: {session}")
        print(f"Total Operations: {total}")
        print(f"Unique Files: {unique}")
        print()

        by_operation = result.get('by_operation', {})
        for op in ['Read', 'Write', 'Edit']:
            files = by_operation.get(op, {})
            if files:
                print(f"{op}:")
                for file_path, count in sorted(files.items(), key=lambda x: -x[1])[:15]:
                    # Shorten long paths for display
                    display_path = file_path
                    if len(file_path) > 70:
                        display_path = '...' + file_path[-67:]
                    print(f"  {count:2}x {display_path}")
                if len(files) > 15:
                    print(f"  ... and {len(files) - 15} more files")
                print()

    @staticmethod
    def _render_claude_workflow(result: dict) -> None:
        """Render workflow sequence."""
        session = result.get('session', 'unknown')
        total = result.get('total_steps', 0)

        print(f"Workflow: {session}")
        print(f"Total Steps: {total}")
        print()

        workflow = result.get('workflow', [])
        for step in workflow[:50]:
            step_num = step.get('step', 0)
            tool = step.get('tool', 'unknown')
            detail = step.get('detail', '')

            # Truncate long details
            if detail and len(detail) > 60:
                detail = detail[:57] + '...'

            print(f"[{step_num:3}] {tool:12} {detail}")

        if len(workflow) > 50:
            print(f"  ... and {len(workflow) - 50} more steps")

    @staticmethod
    def _render_claude_context(result: dict) -> None:
        """Render context changes (directory and branch)."""
        session = result.get('session', 'unknown')
        total = result.get('total_changes', 0)

        print(f"Context Changes: {session}")
        print(f"Total Changes: {total}")
        print()

        final_cwd = result.get('final_cwd')
        final_branch = result.get('final_branch')
        if final_cwd:
            print(f"Final Directory: {final_cwd}")
        if final_branch:
            print(f"Final Branch: {final_branch}")
        if final_cwd or final_branch:
            print()

        changes = result.get('changes', [])
        for change in changes:
            msg_idx = change.get('message_index', '?')
            change_type = change.get('type', 'unknown')
            value = change.get('value', '')

            # Truncate long paths
            if len(value) > 70:
                value = '...' + value[-67:]

            if change_type == 'cwd':
                print(f"[{msg_idx:3}] Changed directory → {value}")
            elif change_type == 'branch':
                print(f"[{msg_idx:3}] Switched branch → {value}")

    @staticmethod
    def _render_claude_filtered_results(result: dict) -> None:
        """Render filtered results (composite queries)."""
        session = result.get('session', 'unknown')
        query = result.get('query', '')
        filters = result.get('filters_applied', [])
        count = result.get('result_count', 0)

        print(f"Filtered Results: {session}")
        print(f"Query: {query}")
        print(f"Filters: {', '.join(filters)}")
        print(f"Matches: {count}")
        print()

        results = result.get('results', [])
        for i, item in enumerate(results[:25], 1):
            msg_idx = item.get('message_index', '?')
            tool = item.get('tool_name', 'unknown')
            is_error = item.get('is_error', False)
            content = item.get('content', '')

            # Show error indicator
            status = '❌' if is_error else '✓'

            # Show first line of content
            first_line = content.split('\n')[0][:60]
            print(f"[{i:3}] {status} Message {msg_idx} | {tool}")
            if first_line:
                print(f"      {first_line}")
            print()

        if len(results) > 25:
            print(f"  ... and {len(results) - 25} more results")

    @staticmethod
    def _render_claude_thinking(result: dict) -> None:
        """Render thinking blocks with actual content text."""
        session = result.get('session', 'unknown')
        count = result.get('thinking_block_count', 0)
        total_tokens = result.get('total_tokens_estimate', 0)

        print(f"Thinking: {session}")
        print(f"Blocks: {count} | ~{total_tokens} tokens")
        print()

        for i, block in enumerate(result.get('blocks', []), 1):
            msg_idx = block.get('message_index', '?')
            char_count = block.get('char_count', 0)
            ts = (block.get('timestamp') or '')[:16].replace('T', ' ')
            content = block.get('content', '')

            print(f"[{i}] Message {msg_idx}  {ts}  ({char_count} chars)")
            print('─' * 60)
            if len(content) > 800:
                print(content[:800])
                print(f"  ... ({char_count - 800} more chars, use --format=json for full text)")
            else:
                print(content)
            print()

    @staticmethod
    def _render_claude_user_messages(result: dict) -> None:
        """Render user messages: first message as full text (the prompt), rest compact."""
        session = result.get('session', 'unknown')
        count = result.get('message_count', 0)

        print(f"User Messages: {session} ({count} total)")
        print()

        for i, msg in enumerate(result.get('messages', [])):
            msg_idx = msg.get('message_index', '?')
            ts = (msg.get('timestamp') or '')[:16].replace('T', ' ')
            blocks = msg.get('content', [])

            # Separate text blocks from tool results
            text_parts = []
            tool_result_count = 0
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                btype = block.get('type', '')
                if btype == 'text':
                    text_parts.append(block.get('text', ''))
                elif btype == 'tool_result':
                    tool_result_count += 1

            text = '\n'.join(text_parts).strip()

            print(f"[msg {msg_idx}] {ts}")

            if text:
                # First user message gets more space (it's the prompt)
                limit = 1200 if i == 0 else 300
                if len(text) > limit:
                    print(text[:limit])
                    print(f"  ... ({len(text) - limit} more chars)")
                else:
                    print(text)

            if tool_result_count:
                print(f"  [{tool_result_count} tool result(s)]")

            if not text and not tool_result_count:
                print("  [no text content]")

            print()

    @staticmethod
    def _parse_assistant_blocks(blocks: list):
        """Parse content blocks into (text, tool_use_names, has_thinking)."""
        text_parts = []
        tool_use_names = []
        has_thinking = False
        for block in blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get('type', '')
            if btype == 'text':
                text_parts.append(block.get('text', ''))
            elif btype == 'tool_use':
                tool_use_names.append(block.get('name', '?'))
            elif btype == 'thinking':
                has_thinking = True
        return '\n'.join(text_parts).strip(), tool_use_names, has_thinking

    @staticmethod
    def _render_claude_assistant_messages(result: dict) -> None:
        """Render assistant messages: text blocks only (skip thinking/tool_use)."""
        session = result.get('session', 'unknown')
        count = result.get('message_count', 0)

        print(f"Assistant Messages: {session} ({count} total)")
        print()

        for msg in result.get('messages', []):
            msg_idx = msg.get('message_index', '?')
            ts = (msg.get('timestamp') or '')[:16].replace('T', ' ')
            text, tool_use_names, has_thinking = ClaudeRenderer._parse_assistant_blocks(
                msg.get('content', [])
            )

            if not text and not tool_use_names and not has_thinking:
                continue

            meta_parts = []
            if has_thinking:
                meta_parts.append('thinking')
            if tool_use_names:
                meta_parts.append(f"tools: {', '.join(tool_use_names)}")
            meta = f"  [{', '.join(meta_parts)}]" if meta_parts else ''

            print(f"[msg {msg_idx}] {ts}{meta}")

            if text:
                if len(text) > 600:
                    print(text[:600])
                    print(f"  ... ({len(text) - 600} more chars, use /message/{msg_idx} for full text)")
                else:
                    print(text)
            elif tool_use_names:
                print(f"  (tool calls only, no text)")

            print()

    @staticmethod
    def _render_claude_message(result: dict) -> None:
        """Render a single message by index."""
        session = result.get('session', 'unknown')
        msg_idx = result.get('message_index', '?')
        role = result.get('message_type', '?')
        ts = (result.get('timestamp') or '')[:16].replace('T', ' ')

        if 'error' in result:
            print(f"Error: {result['error']}")
            return

        print(f"Message {msg_idx}: {session}")
        print(f"Role: {role}  |  {ts}")
        print()

        text = result.get('text', '')
        if text:
            print(text)
        else:
            # Fall back to raw message structure summary
            msg = result.get('message', {})
            content = msg.get('content', [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get('type', '?')
                        if btype == 'text':
                            print(block.get('text', ''))
                        elif btype == 'tool_use':
                            print(f"[tool_use: {block.get('name', '?')}]")
                        elif btype == 'thinking':
                            preview = block.get('thinking', '')[:200]
                            print(f"[thinking: {preview}...]")
                        else:
                            print(f"[{btype}]")
            elif isinstance(content, str):
                print(content)

    @staticmethod
    def _render_claude_search_results(result: dict) -> None:
        """Render search results with excerpts."""
        session = result.get('session', 'unknown')
        term = result.get('term', '')
        count = result.get('match_count', 0)

        print(f"Search: \"{term}\" in {session}")
        print(f"Matches: {count}")
        print()

        matches = result.get('matches', [])
        for i, match in enumerate(matches[:30], 1):
            msg_idx = match.get('message_index', '?')
            role = match.get('role', '?')
            btype = match.get('block_type', '?')
            ts = match.get('timestamp', '')
            excerpt = match.get('excerpt', '')

            # Truncate long excerpts
            if len(excerpt) > 200:
                excerpt = excerpt[:200] + '...'

            # Clean up newlines for compact display
            excerpt = excerpt.replace('\n', ' ').strip()

            print(f"[{i:3}] msg {msg_idx} | {role} | {btype}  {ts}")
            if excerpt:
                print(f"      {excerpt}")
            print()

        if count > 30:
            print(f"  ... and {count - 30} more matches")

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
