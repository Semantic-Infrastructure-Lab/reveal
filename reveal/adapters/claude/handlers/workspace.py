"""Workspace resource handlers for the claude:// adapter — plans, memory, agents, hooks."""
from pathlib import Path
from typing import Any, Dict
from datetime import datetime


def _parse_agent_frontmatter(content: str) -> Dict[str, Any]:
    """Extract YAML-ish frontmatter from an agent markdown file."""
    fm: Dict[str, Any] = {}
    if not content.startswith('---'):
        return fm
    end = content.find('\n---', 3)
    if end < 0:
        return fm
    for line in content[3:end].splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            k = k.strip()
            v = v.strip()
            if k == 'tools':
                fm[k] = [t.strip() for t in v.split(',') if t.strip()]
            else:
                fm[k] = v
    return fm


def get_plans(plans_dir: Path, resource: str, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """List or read plans from ~/.claude/plans/."""
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'claude_plans',
        'source': str(plans_dir),
        'source_type': 'directory',
    }

    # claude://plans/<name> — read specific plan
    parts = resource.split('/', 1)
    plan_name = parts[1].strip() if len(parts) > 1 else ''
    if plan_name:
        plan_path = plans_dir / plan_name
        if not plan_path.suffix:
            plan_path = plans_dir / (plan_name + '.md')
        if not plan_path.exists():
            matches = sorted(plans_dir.glob(f'{plan_name}*.md')) if plans_dir.exists() else []
            if len(matches) == 1:
                plan_path = matches[0]
            elif len(matches) > 1:
                return {**base, 'type': 'claude_plans', 'ambiguous': True,
                        'matches': [p.stem for p in matches], 'query': plan_name}
            else:
                return {**base, 'type': 'claude_plan', 'error': f'Plan not found: {plan_name}', 'name': plan_name}
        try:
            content = plan_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            return {**base, 'type': 'claude_plan', 'error': str(e), 'name': plan_name}
        stat = plan_path.stat()
        return {
            **base,
            'type': 'claude_plan',
            'source': str(plan_path),
            'name': plan_path.stem,
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
            'content': content,
        }

    # claude://plans — list all plans
    if not plans_dir.exists():
        return {**base, 'plans': [], 'total': 0, 'error': f'Plans directory not found: {plans_dir}'}

    search = query_params.get('search', '').lower()
    all_files = sorted(plans_dir.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
    plans = []
    for plan_file in all_files:
        try:
            stat = plan_file.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')
            title = ''
            with open(plan_file, 'r', encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped.startswith('#'):
                        title = stripped.lstrip('#').strip()
                        break
                    elif stripped:
                        title = stripped
                        break
            if search:
                content = plan_file.read_text(encoding='utf-8', errors='replace')
                if search not in content.lower():
                    continue
            plans.append({
                'name': plan_file.stem,
                'modified': modified,
                'size_kb': round(stat.st_size / 1024, 1),
                'title': title,
            })
        except Exception:
            continue

    return {
        **base,
        'plans': plans,
        'total': len(all_files),
        'displayed': len(plans),
        'search': search or None,
    }


def get_memory(conversation_base: Path, resource: str, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Walk ~/.claude/projects/ for memory/ subdirs and list memory files."""
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'claude_memory',
        'source': str(conversation_base),
        'source_type': 'directory',
    }

    # claude://memory/<project-fragment> — filter to matching projects
    parts = resource.split('/', 1)
    filter_project = parts[1].strip() if len(parts) > 1 else ''
    search = query_params.get('search', '').lower()

    if not conversation_base.exists():
        return {**base, 'memories': [], 'total': 0,
                'error': f'Projects dir not found: {conversation_base}'}

    memories = []
    for project_dir in sorted(conversation_base.iterdir()):
        if not project_dir.is_dir():
            continue
        project_name = project_dir.name
        if filter_project and filter_project not in project_name:
            continue
        memory_dir = project_dir / 'memory'
        if not memory_dir.is_dir():
            continue
        for mem_file in sorted(memory_dir.glob('*.md'),
                               key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                content = mem_file.read_text(encoding='utf-8', errors='replace')
                if search and search not in content.lower():
                    continue
                stat = mem_file.stat()
                fm = _parse_agent_frontmatter(content)
                memories.append({
                    'project': project_name,
                    'name': mem_file.stem,
                    'type': fm.get('type', ''),
                    'description': fm.get('description', ''),
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
                    'size_bytes': stat.st_size,
                    'path': str(mem_file),
                })
            except Exception:
                continue

    return {
        **base,
        'memories': memories,
        'total': len(memories),
        'filter_project': filter_project or None,
        'search': search or None,
    }


def get_agents(agents_dir: Path, resource: str, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """List or read agent definitions from ~/.claude/agents/."""
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'claude_agents',
        'source': str(agents_dir),
        'source_type': 'directory',
    }

    # claude://agents/<name> — read specific agent
    parts = resource.split('/', 1)
    agent_name = parts[1].strip() if len(parts) > 1 else ''
    if agent_name:
        agent_path = agents_dir / agent_name
        if not agent_path.suffix:
            agent_path = agents_dir / (agent_name + '.md')
        if not agent_path.exists():
            matches = sorted(agents_dir.glob(f'{agent_name}*.md')) if agents_dir.exists() else []
            if len(matches) == 1:
                agent_path = matches[0]
            elif len(matches) > 1:
                return {**base, 'type': 'claude_agents', 'ambiguous': True,
                        'matches': [p.stem for p in matches], 'query': agent_name}
            else:
                return {**base, 'type': 'claude_agent',
                        'error': f'Agent not found: {agent_name}', 'name': agent_name}
        try:
            content = agent_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            return {**base, 'type': 'claude_agent', 'error': str(e), 'name': agent_name}
        stat = agent_path.stat()
        fm = _parse_agent_frontmatter(content)
        return {
            **base,
            'type': 'claude_agent',
            'source': str(agent_path),
            'name': agent_path.stem,
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
            'description': fm.get('description', ''),
            'tools': fm.get('tools', []),
            'model': fm.get('model', ''),
            'content': content,
        }

    # claude://agents — list all agents
    if not agents_dir.exists():
        return {**base, 'agents': [], 'total': 0,
                'error': f'Agents directory not found: {agents_dir}'}

    search = query_params.get('search', '').lower()
    all_files = sorted(agents_dir.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
    agents = []
    for agent_file in all_files:
        try:
            content = agent_file.read_text(encoding='utf-8', errors='replace')
            if search and search not in content.lower():
                continue
            stat = agent_file.stat()
            fm = _parse_agent_frontmatter(content)
            agents.append({
                'name': agent_file.stem,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
                'size_kb': round(stat.st_size / 1024, 1),
                'description': fm.get('description', ''),
                'tools': fm.get('tools', []),
                'model': fm.get('model', ''),
            })
        except Exception:
            continue

    return {
        **base,
        'agents': agents,
        'total': len(all_files),
        'displayed': len(agents),
        'search': search or None,
    }


def get_hooks(hooks_dir: Path, resource: str) -> Dict[str, Any]:
    """List or read hook scripts from ~/.claude/hooks/."""
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'claude_hooks',
        'source': str(hooks_dir),
        'source_type': 'directory',
    }

    if not hooks_dir.exists():
        return {**base, 'hooks': [], 'total': 0,
                'error': f'Hooks directory not found: {hooks_dir}'}

    # claude://hooks/<event> — read or list scripts for a specific event
    parts = resource.split('/', 1)
    event_name = parts[1].strip() if len(parts) > 1 else ''
    if event_name:
        event_path = hooks_dir / event_name
        if not event_path.exists():
            return {**base, 'error': f'Hook event not found: {event_name}', 'event': event_name}
        if event_path.is_file():
            # Single script file directly under hooks/
            try:
                content = event_path.read_text(encoding='utf-8', errors='replace')
            except Exception as e:
                return {**base, 'type': 'claude_hooks', 'error': str(e), 'event': event_name}
            stat = event_path.stat()
            is_exec = bool(stat.st_mode & 0o111)
            return {
                **base,
                'event': event_name,
                'kind': 'file',
                'path': str(event_path),
                'size_bytes': stat.st_size,
                'executable': is_exec,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
                'content': content,
            }
        # Directory: list scripts within it
        scripts = []
        for script in sorted(event_path.iterdir()):
            try:
                stat = script.stat()
                is_exec = bool(stat.st_mode & 0o111)
                scripts.append({
                    'name': script.name,
                    'path': str(script),
                    'size_bytes': stat.st_size,
                    'executable': is_exec,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
                })
            except Exception:
                continue
        return {**base, 'event': event_name, 'kind': 'directory', 'scripts': scripts}

    # claude://hooks — list all event types
    hooks = []
    for entry in sorted(hooks_dir.iterdir(), key=lambda p: p.name):
        try:
            stat = entry.stat()
            if entry.is_file():
                is_exec = bool(stat.st_mode & 0o111)
                hooks.append({
                    'event': entry.name,
                    'kind': 'file',
                    'path': str(entry),
                    'size_bytes': stat.st_size,
                    'executable': is_exec,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
                })
            elif entry.is_dir():
                script_count = sum(1 for _ in entry.iterdir())
                hooks.append({
                    'event': entry.name,
                    'kind': 'directory',
                    'path': str(entry),
                    'script_count': script_count,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
                })
        except Exception:
            continue

    return {
        **base,
        'hooks': hooks,
        'total': len(hooks),
    }
