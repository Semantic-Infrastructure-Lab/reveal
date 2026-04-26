"""Session-level renderers for the Claude adapter."""


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
    print(f"  {'SESSION':<36} {'MODIFIED':<17} {'SIZE':>6}  {'R':<1}  {'PROJECT':<12}  TITLE")
    print(f"  {'-'*36} {'-'*17} {'-'*6}  {'-':<1}  {'-'*12}  {'-'*25}")
    for s in recent:
        name = s.get('session', '?')
        if len(name) > 36:
            name = name[:33] + '...'
        mod = s.get('modified', '')[:16].replace('T', ' ')
        kb = s.get('size_kb', 0)
        readme = '✓' if s.get('readme_present') else '✗'
        project = (s.get('project', '') or '')[:12]
        title = s.get('title', '') or ''
        if len(title) > 25:
            title = title[:22] + '...'
        print(f"  {name:<36} {mod:<17} {kb:>4}kb  {readme:<1}  {project:<12}  {title}")
    print()
    usage = result.get('usage', {})
    if usage:
        print("Usage:")
        for key, cmd in list(usage.items())[:3]:
            print(f"  {cmd}")
        print("  ...")


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

    readme_present = result.get('readme_present')
    if readme_present is not None:
        marker = '✓' if readme_present else '✗'
        label = 'present' if readme_present else 'absent'
        print(f"README: {marker} {label}")

    print()

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

    ts = result.get('token_summary')
    if ts and ts.get('messages_with_usage', 0) > 0:
        hit = ts.get('cache_hit_rate', '0%')
        inp = ts.get('input_tokens', 0)
        out = ts.get('output_tokens', 0)
        cache_read = ts.get('cache_read_tokens', 0)
        print(f"Tokens: {inp:,} in / {out:,} out  |  cache hit {hit}  ({cache_read:,} read)")
        print()

    ctx = result.get('context')
    if ctx:
        parts = []
        if ctx.get('cwd'):
            parts.append(ctx['cwd'])
        if ctx.get('git_branch'):
            parts.append(f"branch={ctx['git_branch']}")
        if ctx.get('version'):
            parts.append(f"v{ctx['version']}")
        if parts:
            print(f"Context: {' | '.join(parts)}")
            print()

    snippet = result.get('last_assistant_snippet')
    if snippet:
        print(f"Last: {snippet}")
        print()

    print(f"Conversation: {result.get('conversation_file', 'unknown')}")


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
    for op in ['Read', 'Write', 'Edit', 'Glob', 'Grep']:
        files = by_operation.get(op, {})
        if files:
            print(f"{op}:")
            for file_path, count in sorted(files.items(), key=lambda x: -x[1])[:15]:
                display_path = '...' + file_path[-67:] if len(file_path) > 70 else file_path
                print(f"  {count:2}x {display_path}")
            if len(files) > 15:
                print(f"  ... and {len(files) - 15} more files")
            print()


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


def _render_claude_history(result: dict) -> None:
    """Render prompt history from ~/.claude/history.jsonl."""
    total = result.get('total_entries', 0)
    matched = result.get('match_count', 0)
    displayed = result.get('displayed_count', matched)
    search = result.get('search')
    project = result.get('project')
    since = result.get('since')
    error = result.get('error')

    if matched < total:
        count_str = f'{matched:,} matches from {total:,} entries'
    else:
        count_str = f'{total:,} entries'
    header = f'Prompt history: {count_str} | showing {displayed}'
    if displayed < matched:
        header += ' | --all to show all | --head N for more'
    print(header)

    filters = []
    if search:
        filters.append(f'search: "{search}"')
    if project:
        filters.append(f'project: "{project}"')
    if since:
        filters.append(f'since: {since}')
    if filters:
        print('Filters: ' + ' | '.join(filters))

    if error:
        print(f'Error: {error}')
        return

    entries = result.get('entries', [])
    if not entries:
        return

    groups: list = []
    for entry in entries:
        if groups and groups[-1]['project'] == entry.get('project', ''):
            groups[-1]['entries'].append(entry)
        else:
            groups.append({'project': entry.get('project', ''), 'entries': [entry]})

    print()
    for group in groups:
        print(f'  {group["project"]}')
        for entry in group['entries']:
            ts = (entry.get('timestamp') or '')[:16].replace('T', ' ')
            prompt = (entry.get('prompt') or '').strip()
            if prompt:
                first_line = prompt.split('\n')[0]
                has_more_lines = '\n' in prompt
                if len(first_line) > 120:
                    first_line = first_line[:120].rstrip() + '...'
                elif has_more_lines:
                    first_line += '...'
                print(f'    {ts}  {first_line}')
            else:
                print(f'    {ts}')
        print()


def _render_claude_chain(result: dict) -> None:
    """Render session continuation chain."""
    session = result.get('session', 'unknown')
    chain = result.get('chain', [])
    sessions_dir = result.get('sessions_dir')

    print(f'Session Chain: {session}')
    print('═' * (15 + len(session)))

    if not chain:
        print('No chain data found.')
        return

    for i, entry in enumerate(chain):
        name = entry.get('session', 'unknown')
        date = entry.get('date', '')
        badge = entry.get('badge', '')
        readme = entry.get('readme')
        tests_start = entry.get('tests_start')
        tests_end = entry.get('tests_end')
        commits = entry.get('commits')
        continuing_from = entry.get('continuing_from')

        prefix = '[HEAD]' if i == 0 else f'[{i + 1}]  '
        print(f'\n{prefix} {name}')
        if date:
            print(f'  Date:    {date}')
        if badge:
            print(f'  Badge:   {badge}')
        if tests_start is not None and tests_end is not None:
            delta = tests_end - tests_start
            sign = '+' if delta >= 0 else ''
            print(f'  Tests:   {tests_start} → {tests_end} ({sign}{delta})')
        if commits is not None:
            print(f'  Commits: {commits}')
        if not readme:
            print(f'  README:  not found')
        if continuing_from:
            print(f'  ↓ continues from')

    if not sessions_dir:
        print('\n[hint] Set REVEAL_SESSIONS_DIR to enable README metadata in chain')


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

        if len(excerpt) > 200:
            excerpt = excerpt[:200] + '...'

        excerpt = excerpt.replace('\n', ' ').strip()

        print(f"[{i:3}] msg {msg_idx} | {role} | {btype}  {ts}")
        if excerpt:
            print(f"      {excerpt}")
        print()

    if count > 30:
        print(f"  ... and {count - 30} more matches")
