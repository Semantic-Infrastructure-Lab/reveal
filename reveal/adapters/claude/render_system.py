"""System/config renderers for the Claude adapter."""


def _render_claude_info(result: dict) -> None:
    """Render diagnostic path dump."""
    paths = result.get('paths', {})
    env = result.get('env', {})
    sessions_dir = result.get('sessions_dir')

    print('Claude Code data locations:')
    print()

    labels = [
        ('claude_home', 'home'),
        ('projects',    'projects (sessions)'),
        ('history',     'history'),
        ('plans',       'plans'),
        ('settings',    'settings'),
        ('config',      'config (~/.claude.json)'),
        ('agents',      'agents'),
        ('hooks',       'hooks'),
    ]
    for key, label in labels:
        info = paths.get(key, {})
        path = info.get('path', '?')
        exists = info.get('exists', False)
        if not exists:
            status = '[not found]'
        elif info.get('kind') == 'dir':
            count = info.get('count', 0)
            status = f'[{count} items]'
        else:
            size = info.get('size_bytes', 0)
            if size >= 1024 * 1024:
                status = f'[{size // (1024 * 1024)}MB]'
            elif size >= 1024:
                status = f'[{size // 1024}KB]'
            else:
                status = f'[{size}B]'
        print(f'  {label:<26} {path}  {status}')

    print()
    print('Environment overrides:')
    for k, v in env.items():
        val = v if v else '(not set)'
        print(f'  {k:<26} {val}')
    if sessions_dir:
        print(f'  sessions dir (resolved)       {sessions_dir}')


def _render_claude_settings(result: dict) -> None:
    """Render ~/.claude/settings.json contents."""
    import json as _json

    error = result.get('error')
    source = result.get('source', '')

    if 'key' in result:
        val = result.get('value')
        if error:
            print(f'Error: {error}')
            return
        formatted = _json.dumps(val, indent=2) if isinstance(val, (dict, list)) else str(val)
        print(f'{result["key"]}:')
        print(f'  {formatted}')
        return

    if error:
        print(f'Error: {error}')
        return

    settings = result.get('settings', {})
    print(f'Settings: {source}')
    print()
    print(_json.dumps(settings, indent=2))


def _render_claude_plans(result: dict) -> None:
    """Render list of ~/.claude/plans/."""
    error = result.get('error')
    if result.get('ambiguous'):
        print(f"Ambiguous plan name '{result.get('query')}' — matches:")
        for name in result.get('matches', []):
            print(f'  {name}')
        return
    if error:
        print(f'Error: {error}')

    plans = result.get('plans', [])
    total = result.get('total', 0)
    displayed = result.get('displayed', total)
    search = result.get('search')

    count_line = f'Plans: {total} total'
    if search:
        count_line += f" | {displayed} matching '{search}'"
    elif displayed < total:
        count_line += f' | showing {displayed}'
    print(count_line)
    print()

    if not plans:
        print('  (no plans found)')
        return

    print(f"  {'NAME':<42} {'MODIFIED':<17} {'SIZE':>6}  TITLE")
    print(f"  {'-'*42} {'-'*17} {'-'*6}  {'-'*35}")
    for p in plans:
        name = p.get('name', '?')
        if len(name) > 42:
            name = name[:39] + '...'
        mod = p.get('modified', '')[:16].replace('T', ' ')
        kb = p.get('size_kb', 0)
        title = p.get('title', '')
        if len(title) > 35:
            title = title[:32] + '...'
        print(f'  {name:<42} {mod:<17} {kb:>4}kb  {title}')
    print()
    print("  reveal 'claude://plans/<name>'        # read a specific plan")
    print("  reveal 'claude://plans?search=<term>' # search plan content")


def _render_claude_plan(result: dict) -> None:
    """Render a single plan's content."""
    error = result.get('error')
    if error:
        print(f'Error: {error}')
        return
    name = result.get('name', '')
    source = result.get('source', '')
    modified = result.get('modified', '')
    content = result.get('content', '')
    print(f'Plan: {name}')
    if modified:
        print(f'Modified: {modified}')
    print(f'File: {source}')
    print()
    print(content)


def _render_claude_config(result: dict) -> None:
    """Render ~/.claude.json config summary."""
    error = result.get('error')

    if 'key' in result:
        key = result.get('key', '')
        val = result.get('value')
        if val is None:
            print(f"Key '{key}' not found in config")
        else:
            import json as _json
            if isinstance(val, (dict, list)):
                print(_json.dumps(val, indent=2))
            else:
                print(str(val))
        return

    source = result.get('source', '')
    projects_count = result.get('projects_count', 0)
    projects = result.get('projects', [])
    flags = result.get('flags', {})

    if error:
        print(f'Error: {error}')

    print(f'Claude Code Config: {source}')
    print()

    print('Flags:')
    if flags:
        for k, v in flags.items():
            print(f'  {k:<30} {v}')
    else:
        print('  (none)')
    print()

    print(f'Projects: {projects_count} total')
    mcp_projects = [p for p in projects if p.get('mcp_servers')]
    if mcp_projects:
        print()
        print(f"  {'PROJECT PATH':<55}  MCP SERVERS")
        print(f"  {'-'*55}  {'-'*30}")
        for p in mcp_projects:
            path = p.get('path', '')
            if len(path) > 55:
                path = '...' + path[-52:]
            servers = ', '.join(p.get('mcp_servers', []))
            print(f'  {path:<55}  {servers}')
    print()
    print("  reveal 'claude://config?key=<dotpath>'  # extract a specific value")


def _render_claude_memory(result: dict) -> None:
    """Render memory files listing."""
    error = result.get('error')
    if error:
        print(f'Error: {error}')
    memories = result.get('memories', [])
    total = result.get('total', 0)
    search = result.get('search')
    filter_project = result.get('filter_project')

    count_line = f'Memory files: {total}'
    if filter_project:
        count_line += f" | project filter: '{filter_project}'"
    if search:
        count_line += f" | search: '{search}'"
    print(count_line)

    if not memories:
        print('  (no memory files found)')
        return
    print()

    by_project: dict = {}
    for m in memories:
        proj = m.get('project', '')
        by_project.setdefault(proj, []).append(m)

    for proj, mems in by_project.items():
        print(f'  {proj}/')
        for m in mems:
            name = m.get('name', '?')
            mtype = m.get('type', '')
            desc = m.get('description', '')
            mod = (m.get('modified', '') or '')[:16].replace('T', ' ')
            tag = f'[{mtype}] ' if mtype else ''
            line = f'    {name:<35} {mod}  {tag}{desc}'
            if len(line) > 110:
                line = line[:107] + '...'
            print(line)
    print()
    print("  reveal 'claude://memory/<project>'        # filter to one project")
    print("  reveal 'claude://memory?search=<term>'   # search content")


def _render_claude_agents(result: dict) -> None:
    """Render list of agent definitions."""
    if result.get('ambiguous'):
        print(f"Ambiguous agent name '{result.get('query')}' — matches:")
        for name in result.get('matches', []):
            print(f'  {name}')
        return

    error = result.get('error')
    if error:
        print(f'Error: {error}')

    agents = result.get('agents', [])
    total = result.get('total', 0)
    displayed = result.get('displayed', total)
    search = result.get('search')

    count_line = f'Agents: {total} total'
    if search:
        count_line += f" | {displayed} matching '{search}'"
    print(count_line)
    print()

    if not agents:
        print('  (no agents found)')
        return

    print(f"  {'NAME':<32} {'MODIFIED':<17} {'SIZE':>5}  {'MODEL':<10}  DESCRIPTION")
    print(f"  {'-'*32} {'-'*17} {'-'*5}  {'-'*10}  {'-'*30}")
    for a in agents:
        name = a.get('name', '?')
        if len(name) > 32:
            name = name[:29] + '...'
        mod = (a.get('modified', '') or '')[:16].replace('T', ' ')
        kb = a.get('size_kb', 0)
        model = (a.get('model', '') or '')[:10]
        desc = a.get('description', '') or ''
        if len(desc) > 30:
            desc = desc[:27] + '...'
        print(f'  {name:<32} {mod:<17} {kb:>3}kb  {model:<10}  {desc}')
    print()
    print("  reveal 'claude://agents/<name>'        # read a specific agent")


def _render_claude_agent(result: dict) -> None:
    """Render a single agent definition."""
    error = result.get('error')
    if error:
        print(f'Error: {error}')
        return
    name = result.get('name', '')
    modified = result.get('modified', '')
    desc = result.get('description', '')
    tools = result.get('tools', [])
    model = result.get('model', '')
    source = result.get('source', '')
    content = result.get('content', '')
    print(f'Agent: {name}')
    if desc:
        print(f'Description: {desc}')
    if model:
        print(f'Model: {model}')
    if tools:
        print(f'Tools: {", ".join(tools) if isinstance(tools, list) else tools}')
    if modified:
        print(f'Modified: {modified}')
    print(f'File: {source}')
    print()
    print(content)


def _render_claude_hooks(result: dict) -> None:
    """Render hook event types and scripts."""
    error = result.get('error')
    if error:
        print(f'Error: {error}')

    if 'event' in result and result.get('kind') == 'file':
        event = result.get('event', '')
        path = result.get('path', '')
        is_exec = result.get('executable', False)
        modified = result.get('modified', '')
        content = result.get('content', '')
        exec_flag = ' (executable)' if is_exec else ''
        print(f'Hook: {event}{exec_flag}')
        print(f'File: {path}')
        if modified:
            print(f'Modified: {modified}')
        print()
        print(content)
        return

    if 'event' in result and result.get('kind') == 'directory':
        event = result.get('event', '')
        scripts = result.get('scripts', [])
        print(f'Hook event: {event}  ({len(scripts)} script{"s" if len(scripts) != 1 else ""})')
        for s in scripts:
            name = s.get('name', '?')
            is_exec = ' *' if s.get('executable') else ''
            mod = (s.get('modified', '') or '')[:16].replace('T', ' ')
            size = s.get('size_bytes', 0)
            print(f'  {name:<40} {mod}  {size}B{is_exec}')
        return

    hooks = result.get('hooks', [])
    total = result.get('total', 0)
    print(f'Hooks: {total} event{"s" if total != 1 else ""}')
    if not hooks:
        print('  (no hooks configured)')
        return
    print()
    print(f"  {'EVENT':<25} {'KIND':<10} {'MODIFIED':<17}  DETAIL")
    print(f"  {'-'*25} {'-'*10} {'-'*17}  {'-'*20}")
    for h in hooks:
        event = h.get('event', '?')
        kind = h.get('kind', '?')
        mod = (h.get('modified', '') or '')[:16].replace('T', ' ')
        if kind == 'file':
            size = h.get('size_bytes', 0)
            is_exec = ' (exec)' if h.get('executable') else ''
            detail = f'{size}B{is_exec}'
        else:
            count = h.get('script_count', 0)
            detail = f'{count} script{"s" if count != 1 else ""}'
        print(f'  {event:<25} {kind:<10} {mod}  {detail}')
    print()
    print("  reveal 'claude://hooks/<event>'  # read or list scripts for an event")
