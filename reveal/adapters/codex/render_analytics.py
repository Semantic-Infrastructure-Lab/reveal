"""Analytics renderers for the Codex adapter — tools, errors, shell, tokens."""


def _render_codex_tools(result: dict) -> None:
    tools = result.get('tools', [])
    total = result.get('total', len(tools))
    print(f"Codex Tool Calls: {total}")
    print()
    for pair in tools:
        call = pair.get('call', {})
        output = pair.get('output')
        name = call.get('name', '?')
        cid = call.get('call_id', '')
        args_preview = str(call.get('arguments', ''))[:80]
        print(f"  [{name}]  call_id={cid}")
        if args_preview:
            print(f"    args: {args_preview}")
        if output:
            out_preview = str(output.get('output', ''))[:120]
            print(f"    output: {out_preview}")
        print()


def _render_codex_errors(result: dict) -> None:
    errors = result.get('errors', [])
    total = result.get('total', len(errors))
    print(f"Codex Errors/Warnings: {total}")
    print()
    for err in errors:
        severity = err.get('severity', 'error').upper()
        ts = (err.get('timestamp') or '')[:19]
        msg = err.get('message', '')
        print(f"  [{severity}]  {ts}")
        print(f"    {msg}")
        print()


def _render_codex_shell(result: dict) -> None:
    calls = result.get('shell_calls', [])
    total = result.get('total', len(calls))
    print(f"Codex Shell Calls: {total}")
    print()
    for cmd_rec in calls:
        ts = (cmd_rec.get('_timestamp') or '')[:19]
        raw_cmd = cmd_rec.get('command', '')
        # command is a list like ['/bin/bash', '-lc', 'pwd'] — show the user command
        if isinstance(raw_cmd, list) and len(raw_cmd) >= 3 and raw_cmd[1] == '-lc':
            cmd_str = raw_cmd[2]
        elif isinstance(raw_cmd, list):
            cmd_str = ' '.join(str(c) for c in raw_cmd)
        else:
            cmd_str = str(raw_cmd)
        print(f"  $ {cmd_str[:100]}  [{ts}]")
        exit_code = cmd_rec.get('exit_code')
        dur_obj = cmd_rec.get('duration', {})
        secs = dur_obj.get('secs', 0) if isinstance(dur_obj, dict) else 0
        nanos = dur_obj.get('nanos', 0) if isinstance(dur_obj, dict) else 0
        dur_ms = secs * 1000 + nanos // 1_000_000
        status = f"exit={exit_code}" if exit_code is not None else ''
        if dur_ms:
            status += f"  {dur_ms}ms"
        if status:
            print(f"    → {status}")
        out = (cmd_rec.get('aggregated_output') or '').strip()
        if out:
            for line in out.splitlines()[:3]:
                print(f"    {line}")
        print()


def _render_codex_workflow(result: dict) -> None:
    events = result.get('events', [])
    total = result.get('total', len(events))
    print(f"Codex Workflow: {total} action(s)")
    print()
    for ev in events:
        kind = ev.get('kind', '?')
        ts = (ev.get('timestamp') or '')[:19]
        if kind == 'tool_call':
            name = ev.get('name', '?')
            args = str(ev.get('arguments', ''))[:60]
            status = '✓' if ev.get('success') else '✗'
            print(f"  [{status}] tool  {name}({args})  [{ts}]")
            out = str(ev.get('output') or '')
            if out:
                print(f"      → {out[:100]}")
        elif kind == 'shell':
            cmd = ev.get('command', [])
            if isinstance(cmd, list) and len(cmd) >= 3 and cmd[1] == '-lc':
                cmd_str = cmd[2]
            elif isinstance(cmd, list):
                cmd_str = ' '.join(str(c) for c in cmd)
            else:
                cmd_str = str(cmd)
            exit_code = ev.get('exit_code')
            dur = ev.get('duration_ms', 0)
            status = '✓' if ev.get('success') else '✗'
            print(f"  [{status}] shell $ {cmd_str[:80]}  [{ts}]")
            parts = []
            if exit_code is not None:
                parts.append(f"exit={exit_code}")
            if dur:
                parts.append(f"{dur}ms")
            if parts:
                print(f"      → {' '.join(parts)}")
        print()


def _render_codex_timeline(result: dict) -> None:
    events = result.get('events', [])
    total = result.get('total', len(events))
    print(f"Codex Timeline: {total} event(s)")
    print()
    for ev in events:
        ts = (ev.get('timestamp') or '')[:19]
        etype = ev.get('event_type', '?')
        ptype = ev.get('payload_type', '')
        label = f"{etype}/{ptype}" if ptype else etype
        summary = ev.get('summary', '')
        print(f"  {ts}  [{label:<30}]  {summary[:80]}")
    print()


def _render_codex_goal(result: dict) -> None:
    goal = result.get('goal')
    thread_id = result.get('thread_id', result.get('session_id', ''))
    if not goal:
        print(f"Codex Goal: (none set for {thread_id[:8]})")
        return
    print(f"Codex Goal: {thread_id[:8]}")
    print()
    print(f"  Objective:  {goal.get('objective', '')}")
    print(f"  Status:     {goal.get('status', '?')}")
    budget = goal.get('token_budget')
    used = goal.get('tokens_used', 0)
    if budget:
        pct = round(100 * used / budget) if budget else 0
        print(f"  Tokens:     {used:,} / {budget:,} ({pct}%)")
    else:
        print(f"  Tokens:     {used:,} (no budget)")
    time_s = goal.get('time_used_seconds', 0)
    if time_s:
        print(f"  Time used:  {time_s}s")
    print()


def _render_codex_memories_pipeline(result: dict) -> None:
    stage1 = result.get('stage1_total', 0)
    stage2 = result.get('stage2_selected', 0)
    recent = result.get('recent_outputs', [])
    print(f"Codex Memory Pipeline")
    print()
    print(f"  Stage 1 outputs:     {stage1}")
    print(f"  Selected for Stage 2: {stage2}")
    print()
    if recent:
        print(f"  Recent Stage 1 outputs (up to 20):")
        for row in recent:
            tid = (row.get('thread_id') or '')[:8]
            slug = row.get('rollout_slug') or ''
            phase2 = '✓' if row.get('selected_for_phase2') else ' '
            uses = row.get('usage_count') or 0
            print(f"    [{phase2}] {tid}  {slug[:30]}  uses={uses}")
    else:
        print("  (no stage1_outputs yet)")
    print()


def _render_codex_tokens(result: dict) -> None:
    turns = result.get('token_turns', [])
    total_turns = result.get('total_turns', len(turns))
    grand = result.get('grand_total')
    header = f"Codex Token Usage: {total_turns} turn(s)"
    if grand is not None:
        header += f"  |  running total: {grand:,}"
    print(header)
    print()
    if not turns:
        print("  (no token_count events found)")
        return
    print(f"  {'TURN':<5} {'TIMESTAMP':<20} {'INPUT':>8} {'CACHED':>8} {'OUTPUT':>8} {'REASON':>8} {'TOTAL':>8}")
    print(f"  {'-'*5} {'-'*20} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for t in turns:
        ts = (t.get('timestamp') or '')[:19].replace('T', ' ')
        inp = t.get('input_tokens', 0) or 0
        cached = t.get('cached_input_tokens', 0) or 0
        out = t.get('output_tokens', 0) or 0
        reason = t.get('reasoning_output_tokens', 0) or 0
        total = t.get('total_tokens', 0) or 0
        print(f"  {t['turn']:<5} {ts:<20} {inp:>8,} {cached:>8,} {out:>8,} {reason:>8,} {total:>8,}")
    print()
