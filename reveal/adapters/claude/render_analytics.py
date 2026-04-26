"""Analytics and workflow renderers for the Claude adapter."""


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

        tool_input = context.get('tool_input_preview')
        if tool_input:
            if len(tool_input) > 70:
                tool_input = tool_input[:67] + '...'
            print(f"      Input: {tool_input}")

        for line in err.get('content_preview', '').split('\n')[:3]:
            if line.strip():
                display = line[:67] + '...' if len(line) > 70 else line
                print(f"      Error: {display}")
                break
        print()

    if len(errors) > 20:
        print(f"  ... and {len(errors) - 20} more errors")


def _render_claude_workflow(result: dict) -> None:
    """Render workflow sequence."""
    session = result.get('session', 'unknown')
    total = result.get('total_steps', 0)
    displayed = result.get('displayed_steps', None)
    filtered_from = result.get('filtered_from', None)

    display = result.get('_display', {})
    verbose = display.get('verbose', False)
    max_chars = display.get('max_snippet_chars', None)
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
        outcome = step.get('outcome')
        backgrounded = step.get('backgrounded', False)

        if truncate_at is not None and len(detail) > truncate_at:
            detail = detail[:truncate_at - 3] + '...'

        if run_count > 1:
            detail = f"{detail} (×{run_count})"

        suffix = ''
        if outcome == 'error':
            suffix += ' ✗'
        if backgrounded:
            suffix += ' [bg]'

        print(f"[{step_num:3}] {tool:12} {detail}{suffix}")
        if thinking_hint:
            print(f"           → {thinking_hint}")


def _render_claude_token_breakdown(result: dict) -> None:
    """Render per-message token breakdown (claude://session/NAME?tokens)."""
    session = result.get('session', 'unknown')
    entries = result.get('messages', [])
    totals = result.get('totals', {})

    print(f"Token Breakdown: {session}")
    print(f"Turns: {len(entries)}")
    print()

    if entries:
        print(f"{'#':>4}  {'timestamp':<22}  {'input':>8}  {'output':>8}  {'cache_read':>12}  {'cache_crt':>10}  {'cumul_in':>10}")
        print(f"{'─'*4}  {'─'*22}  {'─'*8}  {'─'*8}  {'─'*12}  {'─'*10}  {'─'*10}")
        for i, entry in enumerate(entries, 1):
            ts = (entry.get('timestamp') or '')[:19].replace('T', ' ')
            inp = entry.get('input_tokens', 0)
            out = entry.get('output_tokens', 0)
            cread = entry.get('cache_read_tokens', 0)
            ccrt = entry.get('cache_created_tokens', 0)
            cumul = entry.get('cumulative_input', 0)
            print(f"{i:>4}  {ts:<22}  {inp:>8,}  {out:>8,}  {cread:>12,}  {ccrt:>10,}  {cumul:>10,}")
        print()

    if totals:
        hit = totals.get('cache_hit_rate', '0%')
        print(f"Totals: {totals.get('input_tokens', 0):,} in / {totals.get('output_tokens', 0):,} out")
        print(f"Cache:  {totals.get('cache_read_tokens', 0):,} read / {totals.get('cache_created_tokens', 0):,} created  (hit rate {hit})")


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

        if len(value) > 70:
            value = '...' + value[-67:]

        if change_type == 'cwd':
            print(f"[{msg_idx:3}] Changed directory → {value}")
        elif change_type == 'branch':
            print(f"[{msg_idx:3}] Switched branch → {value}")
