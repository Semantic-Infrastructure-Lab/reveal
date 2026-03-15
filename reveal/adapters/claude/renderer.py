"""Claude adapter renderer for text output."""

import sys
from ...rendering import TypeDispatchRenderer


class ClaudeRenderer(TypeDispatchRenderer):
    """Renderer for Claude adapter results.

    Uses TypeDispatchRenderer for automatic routing to _render_{type}() methods.
    """

    @staticmethod
    def _render_claude_session_list(result: dict) -> None:
        """Render sessions list."""
        total = result.get('session_count', 0)
        recent = result.get('recent_sessions', [])
        displayed = result.get('displayed_count', len(recent))

        count_line = f"Claude Sessions: {total} total"
        if displayed < total:
            count_line += f" | showing {displayed}"
        count_line += " | --all to show all | --head N for more | --since YYYY-MM-DD (or today)"
        print(count_line)
        print()
        print(f"  {'SESSION':<34} {'MODIFIED':<17} {'SIZE':>6}  {'R':<1}  {'PROJECT':<12}  TITLE")
        print(f"  {'-'*34} {'-'*17} {'-'*6}  {'-':<1}  {'-'*12}  {'-'*25}")
        for s in recent:
            name = s.get('session', '?')
            if len(name) > 34:
                name = name[-34:]
            mod = s.get('modified', '')[:16].replace('T', ' ')
            kb = s.get('size_kb', 0)
            readme = '✓' if s.get('readme_present') else '✗'
            project = (s.get('project', '') or '')[:12]
            title = s.get('title', '') or ''
            if len(title) > 25:
                title = title[:22] + '...'
            print(f"  {name:<34} {mod:<17} {kb:>4}kb  {readme:<1}  {project:<12}  {title}")
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
        title = result.get('title')
        if title:
            print(f"Title: {title}")
        print(f"Messages: {result.get('message_count', 0)}")
        print(f"User: {result.get('user_messages', 0)} | Assistant: {result.get('assistant_messages', 0)}")
        if 'duration' in result:
            print(f"Duration: {result['duration']}")

        # README presence indicator
        readme_present = result.get('readme_present')
        if readme_present is not None:
            marker = '✓' if readme_present else '✗'
            label = 'present' if readme_present else 'absent'
            print(f"README: {marker} {label}")

        print()

        # Files touched
        files_touched = result.get('files_touched', [])
        file_count = result.get('files_touched_count', len(files_touched))
        if file_count > 0:
            top3 = files_touched[:3]
            top3_str = ', '.join(top3)
            if file_count > 3:
                top3_str += f', +{file_count - 3} more'
            print(f"Files: {file_count} ({top3_str})")
            print()

        tools = result.get('tools_used', {})
        if tools:
            print("Tools Used:")
            for tool, count in sorted(tools.items(), key=lambda x: -x[1]):
                print(f"  {tool}: {count}")
            print()

        # Last assistant snippet
        snippet = result.get('last_assistant_snippet')
        if snippet:
            print(f"Last: {snippet}")
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
        details = result.get('details', {})
        for tool, stats in sorted(tools.items(), key=lambda x: -x[1].get('count', 0)):
            count = stats.get('count', 0)
            success_rate = stats.get('success_rate', 'N/A')
            print(f"  {tool}: {count} calls ({success_rate} success)")
            tool_details = [d.get('detail') for d in details.get(tool, []) if d.get('detail')]
            limit = 8
            for d in tool_details[:limit]:
                print(f"    {d}")
            if len(tool_details) > limit:
                print(f"    ...and {len(tool_details) - limit} more")
            if tool_details:
                print()

    @staticmethod
    def _render_claude_analytics(result: dict) -> None:
        """Render detailed analytics summary (?summary view)."""
        print(f"Analytics: {result.get('session', 'unknown')}")
        title = result.get('title')
        if title:
            print(f"Title: {title}")
        duration = result.get('duration')
        if duration:
            print(f"Duration: {duration}")
        print(f"Messages: {result.get('message_count', 0)} "
              f"(user: {result.get('user_messages', 0)}, "
              f"assistant: {result.get('assistant_messages', 0)})")
        print()

        tool_success_rate = result.get('tool_success_rate', {})
        if tool_success_rate:
            print("Tool Success Rates:")
            for tool, stats in sorted(tool_success_rate.items(),
                                      key=lambda x: -x[1].get('total', 0)):
                total = stats.get('total', 0)
                rate = stats.get('success_rate', 0)
                success = stats.get('success', 0)
                failure = stats.get('failure', 0)
                fail_str = f", {failure} failed" if failure else ""
                print(f"  {tool}: {rate}% ({success}/{total}{fail_str})")
            print()

        avg = result.get('avg_message_size', 0)
        max_size = result.get('max_message_size', 0)
        thinking_blocks = result.get('thinking_blocks', 0)
        if avg or max_size:
            print(f"Message Sizes: avg {avg:,} chars, max {max_size:,} chars")
        if thinking_blocks:
            thinking_tokens = result.get('thinking_tokens_approx', 0)
            print(f"Thinking: {thinking_blocks} blocks (~{thinking_tokens:,} tokens)")

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

            # Show error preview — first non-empty line
            for line in err.get('content_preview', '').split('\n')[:3]:
                if line.strip():
                    display = line[:67] + '...' if len(line) > 70 else line
                    print(f"      Error: {display}")
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
                    display_path = '...' + file_path[-67:] if len(file_path) > 70 else file_path
                    print(f"  {count:2}x {display_path}")
                if len(files) > 15:
                    print(f"  ... and {len(files) - 15} more files")
                print()

    @staticmethod
    def _render_claude_workflow(result: dict) -> None:
        """Render workflow sequence."""
        session = result.get('session', 'unknown')
        total = result.get('total_steps', 0)
        displayed = result.get('displayed_steps', None)
        filtered_from = result.get('filtered_from', None)

        display = result.get('_display', {})
        verbose = display.get('verbose', False)
        max_chars = display.get('max_snippet_chars', None)
        # Default truncation: unlimited if verbose or explicit max_chars, else 80
        if verbose:
            truncate_at = None
        elif max_chars is not None:
            truncate_at = max_chars
        else:
            truncate_at = 80

        collapsed_steps = result.get('collapsed_steps')

        print(f"Workflow: {session}")
        total_line = f"Total Steps: {total}"
        if filtered_from is not None:
            total_line += f" (filtered from {filtered_from})"
        elif displayed is not None and displayed < total:
            total_line += f" (showing {displayed})"
        if collapsed_steps is not None and collapsed_steps < total:
            total_line += f" → {collapsed_steps} after collapsing runs"
        print(total_line)
        print()

        workflow = result.get('workflow', [])
        for step in workflow:
            step_num = step.get('step', 0)
            tool = step.get('tool', 'unknown')
            detail = step.get('detail', '') or ''
            run_count = step.get('run_count', 1)
            thinking_hint = step.get('thinking_hint')

            if truncate_at is not None and len(detail) > truncate_at:
                detail = detail[:truncate_at - 3] + '...'

            if run_count > 1:
                detail = f"{detail} (×{run_count})"

            print(f"[{step_num:3}] {tool:12} {detail}")
            if thinking_hint:
                print(f"           → {thinking_hint}")

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
                print("  (tool calls only, no text)")

            print()

    @staticmethod
    def _render_raw_block(block: dict) -> None:
        """Print one content block from a raw message (text, tool_use, thinking, etc.)."""
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
                for block in (b for b in content if isinstance(b, dict)):
                    ClaudeRenderer._render_raw_block(block)
            elif isinstance(content, str):
                print(content)

        if 'hint' in result:
            print(f"\nNote: {result['hint']}")

    @staticmethod
    def _render_claude_cross_session_search(result: dict) -> None:
        """Render cross-session search results."""
        term = result.get('term', '')
        scanned = result.get('sessions_scanned', 0)
        count = result.get('match_count', 0)
        since = result.get('since')
        error = result.get('error')

        since_str = f'  since {since}' if since else ''
        print(f'Cross-session search: "{term}"{since_str}')
        print(f'Scanned {scanned} sessions  |  Found {count} matches')

        if error:
            print(f'Error: {error}')
            return
        if count == 0:
            return

        print()
        matches = result.get('matches', [])
        for match in matches:
            session = match.get('session', '?')
            modified = (match.get('modified') or '')[:16].replace('T', ' ')
            project = match.get('project', '')
            role = match.get('role', '')
            excerpt = (match.get('excerpt') or '').replace('\n', ' ').strip()

            project_tag = f'  [{project}]' if project else ''
            role_tag = f'  {role}' if role else ''
            print(f'{session}{project_tag}  {modified}{role_tag}')
            if excerpt:
                if len(excerpt) > 200:
                    excerpt = excerpt[:200] + '...'
                print(f'  {excerpt}')
            print()

    @staticmethod
    def _render_claude_file_sessions(result: dict) -> None:
        """Render cross-session file tracking results."""
        file_path = result.get('file_path', '')
        scanned = result.get('sessions_scanned', 0)
        count = result.get('match_count', 0)
        since = result.get('since')
        error = result.get('error')

        since_str = f'  since {since}' if since else ''
        print(f'File history: {file_path}{since_str}')
        print(f'Scanned {scanned} sessions  |  Found {count} sessions touching this file')

        if error:
            print(f'Error: {error}')
            return
        if count == 0:
            return

        print()
        for entry in result.get('sessions', []):
            session = entry.get('session', '?')
            modified = (entry.get('modified') or '')[:16].replace('T', ' ')
            project = entry.get('project', '')
            ops = entry.get('ops', {})

            project_tag = f'  [{project}]' if project else ''
            op_parts = []
            for op in ('Read', 'Edit', 'Write'):
                n = ops.get(op, 0)
                if n:
                    op_parts.append(f'{op} ×{n}')
            ops_str = '  ' + '  '.join(op_parts) if op_parts else ''
            print(f'{session}{project_tag}  {modified}{ops_str}')

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

    @staticmethod
    def _render_claude_messages(result: dict) -> None:
        """Render assistant narrative turns (text only, no tool calls)."""
        session = result.get('session', 'unknown')
        total = result.get('total_turns', 0)
        search = result.get('search')

        display = result.get('_display', {})
        verbose = display.get('verbose', False)
        max_chars = display.get('max_snippet_chars', None)
        # Default: 600 chars per turn unless verbose or explicit max_snippet_chars
        if verbose:
            truncate_at = None
        elif max_chars is not None:
            truncate_at = max_chars
        else:
            truncate_at = 600

        header = f"Messages: {session} ({total} assistant turns"
        if search:
            header += f', filtered by "{search}"'
        header += ")"
        print(header)
        print()

        messages = result.get('messages', [])
        for msg in messages:
            turn = msg.get('turn', '?')
            msg_idx = msg.get('message_index', '?')
            ts = msg.get('timestamp', '')
            text = msg.get('text', '')
            char_count = msg.get('char_count', len(text))

            print(f"[turn {turn} / msg {msg_idx}] {ts}")
            if truncate_at is not None and char_count > truncate_at:
                print(text[:truncate_at])
                print(f"  ... ({char_count - truncate_at} more chars — use --verbose or --max-snippet-chars {char_count})")
            else:
                print(text)
            print()

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
