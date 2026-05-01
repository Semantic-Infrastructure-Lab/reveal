"""Message-level renderers for the Claude adapter."""
from typing import Optional


def _tool_summary(name: str, inp: dict) -> str:
    """One-line summary of a tool call: ToolName → key param."""
    if name in ('Write', 'Edit', 'Read', 'NotebookEdit'):
        fp = inp.get('file_path') or inp.get('notebook_path', '')
        return f"{name} → {fp.split('/')[-1] or fp}" if fp else name
    if name == 'Bash':
        cmd = inp.get('command', '')
        return f"Bash → {cmd[:60]}" if cmd else 'Bash'
    if name == 'Agent':
        prompt = inp.get('prompt') or inp.get('description', '')
        return f"Agent → {prompt[:60]}" if prompt else 'Agent'
    if name in ('Glob', 'Grep'):
        pat = inp.get('pattern', '')
        return f"{name} → {pat[:40]}" if pat else name
    return name


def _parse_assistant_blocks(blocks: list):
    """Parse content blocks into (text, tool_names, tool_summaries, has_thinking)."""
    text_parts = []
    tool_names = []
    tool_summaries = []
    has_thinking = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get('type', '')
        if btype == 'text':
            text_parts.append(block.get('text', ''))
        elif btype == 'tool_use':
            name = block.get('name', '?')
            inp = block.get('input', {})
            tool_names.append(name)
            tool_summaries.append(_tool_summary(name, inp))
        elif btype == 'thinking':
            has_thinking = True
    return '\n'.join(text_parts).strip(), tool_names, tool_summaries, has_thinking


def _format_tool_params(name: str, inp: dict) -> list:
    """Return a list of key=value strings for the most useful tool params."""
    lines = []
    if name in ('Write', 'Edit', 'Read', 'NotebookEdit'):
        fp = inp.get('file_path') or inp.get('notebook_path', '')
        if fp:
            lines.append(f"  file_path: {fp}")
        if name == 'Write':
            content = inp.get('content', '')
            if content:
                lines.append(f"  content: ({len(content):,} chars)")
        elif name == 'Edit':
            old = inp.get('old_string', '')
            new = inp.get('new_string', '')
            if old or new:
                lines.append(f"  old→new: ({len(old):,} → {len(new):,} chars)")
    elif name == 'Bash':
        cmd = inp.get('command', '')
        if cmd:
            suffix = '...' if len(cmd) > 120 else ''
            lines.append(f"  command: {cmd[:120]}{suffix}")
    elif name == 'Agent':
        prompt = inp.get('prompt') or inp.get('description', '')
        if prompt:
            suffix = '...' if len(prompt) > 100 else ''
            lines.append(f"  prompt: {prompt[:100]}{suffix}")
    elif name in ('Glob', 'Grep'):
        pat = inp.get('pattern', '')
        if pat:
            lines.append(f"  pattern: {pat}")
        path = inp.get('path', '')
        if path:
            lines.append(f"  path: {path}")
    return lines


def _render_raw_block(block: dict, max_chars: Optional[int] = 500) -> None:
    """Print one content block from a raw message (text, tool_use, thinking, etc.).

    max_chars: None = no truncation; int = truncate tool_result at that many chars.
    """
    btype = block.get('type', '?')
    if btype == 'text':
        print(block.get('text', ''))
    elif btype == 'tool_use':
        name = block.get('name', '?')
        inp = block.get('input', {})
        print(f"[tool_use: {name}]")
        for line in _format_tool_params(name, inp):
            print(line)
    elif btype == 'tool_result':
        content = block.get('content', '')
        if isinstance(content, list):
            text = '\n'.join(b.get('text', '') for b in content
                             if isinstance(b, dict) and b.get('type') == 'text')
        else:
            text = str(content) if content else ''
        if text:
            if max_chars is not None and len(text) > max_chars:
                print(f"[tool_result]\n{text[:max_chars]}")
                print(f"  ... ({len(text) - max_chars:,} more chars)")
            else:
                print(f"[tool_result]\n{text}")
        else:
            print("[tool_result: (empty)]")
    elif btype == 'thinking':
        preview = block.get('thinking', '')[:200]
        print(f"[thinking: {preview}...]")
    else:
        print(f"[{btype}]")


def _render_claude_tool_calls(result: dict) -> None:
    """Render tool calls with clear command display for Bash."""
    tool_name = result.get('tool_name', 'unknown')
    call_count = result.get('call_count', 0)
    session = result.get('session', 'unknown')

    display = result.get('_display', {})
    verbose = display.get('verbose', False)
    explicit_max = display.get('max_snippet_chars', None)
    if verbose:
        cmd_limit = None
    elif explicit_max is not None:
        cmd_limit = explicit_max
    else:
        cmd_limit = 100

    print(f"Tool: {tool_name} ({call_count} calls)")
    print(f"Session: {session}")
    print()

    calls = result.get('calls', [])
    for i, call in enumerate(calls, 1):
        inp = call.get('input', {})

        if tool_name == 'Bash':
            cmd = inp.get('command', '?')
            desc = inp.get('description', '')
            if cmd_limit is not None and len(cmd) > cmd_limit:
                display_cmd = cmd[:cmd_limit]
                truncation = f"\n        ... ({len(cmd)} chars — use --verbose or --max-snippet-chars {len(cmd)} for full)"
            else:
                display_cmd = cmd
                truncation = ""
            if desc:
                print(f"[{i:3}] {desc}")
                print(f"      $ {display_cmd}{truncation}")
            else:
                print(f"[{i:3}] $ {display_cmd}{truncation}")
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
            preview = ', '.join(f"{k}={str(v)[:30]}" for k, v in list(inp.items())[:3])
            print(f"[{i:3}] {preview}")


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


def _render_claude_assistant_messages(result: dict) -> None:
    """Render assistant messages: text blocks only (skip thinking/tool_use)."""
    session = result.get('session', 'unknown')
    count = result.get('message_count', 0)
    full = result.get('full', False) or result.get('_display', {}).get('verbose', False)

    print(f"Assistant Messages: {session} ({count} total)")
    print()

    for msg in result.get('messages', []):
        msg_idx = msg.get('message_index', '?')
        ts = (msg.get('timestamp') or '')[:16].replace('T', ' ')
        text, tool_names, tool_summaries, has_thinking = _parse_assistant_blocks(
            msg.get('content', [])
        )

        if not text and not tool_names and not has_thinking:
            continue

        meta_parts = []
        if has_thinking:
            meta_parts.append('thinking')
        if tool_names:
            meta_parts.append(f"tools: {', '.join(tool_names)}")
        meta = f"  [{', '.join(meta_parts)}]" if meta_parts else ''

        print(f"[msg {msg_idx}] {ts}{meta}")

        if text:
            if not full and len(text) > 600:
                print(text[:600])
                print(f"  ... ({len(text) - 600} more chars, use /message/{msg_idx} for full text or add ?full)")
            else:
                print(text)
        elif tool_summaries:
            for summary in tool_summaries:
                print(f"  {summary}")

        print()


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

    display = result.get('_display', {})
    verbose = display.get('verbose', False)
    explicit_max = display.get('max_snippet_chars', None)
    if verbose:
        block_max = None  # no truncation
    elif explicit_max is not None:
        block_max = explicit_max
    else:
        block_max = 500  # default

    text = result.get('text', '')
    if text:
        print(text)
    else:
        msg = result.get('message', {})
        content = msg.get('content', [])
        if isinstance(content, list):
            for block in (b for b in content if isinstance(b, dict)):
                _render_raw_block(block, max_chars=block_max)
        elif isinstance(content, str):
            print(content)

    if 'hint' in result:
        print(f"\nNote: {result['hint']}")


def _render_claude_message_range(result: dict) -> None:
    """Render interleaved user+assistant messages (range slice)."""
    session = result.get('session', 'unknown')
    displayed = result.get('displayed', len(result.get('messages', [])))
    total = result.get('total_messages', displayed)
    filtered_from = result.get('filtered_from')
    full = result.get('full', False) or result.get('_display', {}).get('verbose', False)

    rng = result.get('_display', {}).get('range')
    if rng:
        start, end = rng
        end_str = str(end) if end is not None else 'end'
        header = f"Messages {start}–{end_str}: {session} ({displayed} shown"
    else:
        header = f"Messages: {session} ({displayed} shown"
    if filtered_from:
        header += f" of {filtered_from} total"
    header += ")"
    print(header)
    print()

    for msg in result.get('messages', []):
        turn = msg.get('turn', '?')
        msg_idx = msg.get('message_index', '?')
        role = msg.get('role', '?')
        ts = msg.get('timestamp', '')
        content = msg.get('content', [])

        print(f"[turn {turn} / msg {msg_idx} | {role} | {ts}]")

        if role == 'assistant':
            text, tool_names, tool_summaries, has_thinking = _parse_assistant_blocks(content)
            meta_parts = []
            if has_thinking:
                meta_parts.append('thinking')
            if tool_names:
                meta_parts.append(f"tools: {', '.join(tool_names)}")
            if meta_parts:
                print(f"  [{', '.join(meta_parts)}]")
            if text:
                if not full and len(text) > 600:
                    print(text[:600])
                    print(f"  ... ({len(text) - 600} more chars — use ?full or /message/{msg_idx} for full text)")
                else:
                    print(text)
            elif tool_summaries:
                for summary in tool_summaries:
                    print(f"  {summary}")
        else:
            text_parts = []
            tool_result_count = 0
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get('type', '')
                if btype == 'text':
                    text_parts.append(block.get('text', ''))
                elif btype == 'tool_result':
                    tool_result_count += 1
            text = '\n'.join(text_parts).strip()
            if text:
                if not full and len(text) > 600:
                    print(text[:600])
                    print(f"  ... ({len(text) - 600} more chars — use ?full or /message/{msg_idx} for full text)")
                else:
                    print(text)
            if tool_result_count:
                print(f"  [{tool_result_count} tool result(s)]")
            if not text and not tool_result_count:
                print("  [no text content]")

        print()


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

        status = '❌' if is_error else '✓'

        first_line = content.split('\n')[0][:60]
        print(f"[{i:3}] {status} Message {msg_idx} | {tool}")
        if first_line:
            print(f"      {first_line}")
        print()

    if len(results) > 25:
        print(f"  ... and {len(results) - 25} more results")


def _render_claude_messages(result: dict) -> None:
    """Render assistant narrative turns (text only, no tool calls)."""
    session = result.get('session', 'unknown')
    total = result.get('total_turns', 0)
    search = result.get('search')

    display = result.get('_display', {})
    verbose = display.get('verbose', False) or result.get('full', False)
    max_chars = display.get('max_snippet_chars', None)
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
