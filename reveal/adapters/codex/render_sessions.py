"""Session list and overview renderers for the Codex adapter."""


def _render_codex_session_list(result: dict) -> None:
    total = result.get('total', 0)
    sessions = result.get('sessions', [])
    search = result.get('search')
    header = f"Codex Sessions: {total} total"
    if search:
        header += f" | search: {search!r}"
    print(header)
    print()
    if not sessions:
        print("  (none)")
        return
    print(f"  {'ID':<38} {'UPDATED':<20} {'MODEL':<15} TITLE")
    print(f"  {'-'*38} {'-'*20} {'-'*15} {'-'*30}")
    for s in sessions:
        sid = (s.get('id') or '')[:36]
        updated = (s.get('updated_at') or '')[:19].replace('T', ' ')
        model = (s.get('model') or '')[:15]
        title = (s.get('title') or s.get('first_user_message') or '')[:40]
        print(f"  {sid:<38} {updated:<20} {model:<15} {title}")
    print()


def _render_codex_content_search(result: dict) -> None:
    sessions = result.get('sessions', [])
    total = result.get('total', len(sessions))
    query = result.get('query', '')
    print(f"Codex Content Search: {total} session(s) matching {query!r}")
    print()
    if not sessions:
        print("  (no matches)")
        return
    for s in sessions:
        sid = (s.get('id') or '')[:8]
        title = (s.get('title') or '')[:60]
        updated = (s.get('updated_at') or '')[:10]
        model = (s.get('model') or '')
        print(f"  {sid}  {updated}  [{model}]  {title}")
        for m in s.get('matches', []):
            role = m.get('role', '?').upper()
            ts = (m.get('timestamp') or '')[:19].replace('T', ' ')
            snippet = (m.get('snippet') or '').replace('\n', ' ')[:120]
            print(f"    [{role}] {ts}  {snippet}")
        print()


def _render_codex_session_overview(result: dict) -> None:
    print(f"Codex Session: {result.get('session_id', '?')}")
    title = result.get('title', '')
    if title:
        print(f"Title: {title}")
    model = result.get('model') or result.get('model_provider', '')
    if model:
        effort = result.get('reasoning_effort')
        print(f"Model: {model}" + (f" (reasoning: {effort})" if effort else ''))
    print(f"Turns: user={result.get('user_turns', 0)}, agent={result.get('agent_turns', 0)}")
    print(f"Tool calls: {result.get('tool_calls', 0)}, Shell calls: {result.get('shell_calls', 0)}")
    tokens = result.get('tokens_used')
    if tokens is not None:
        print(f"Tokens used: {tokens:,}")
    dur = result.get('duration_ms')
    if dur is not None:
        print(f"Duration: {dur/1000:.1f}s")
    reasoning = result.get('reasoning_blocks', 0)
    if reasoning:
        print(f"Reasoning blocks: {reasoning} (content opaque)")
    cwd = result.get('cwd')
    if cwd:
        print(f"CWD: {cwd}")
    branch = result.get('git_branch')
    if branch:
        print(f"Git branch: {branch}")
    print()
