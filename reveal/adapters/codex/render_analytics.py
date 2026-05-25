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
