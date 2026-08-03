"""System resource renderers for the Codex adapter."""
import json


def _render_codex_info(result: dict) -> None:
    print("Codex Install Info")
    print()
    paths = result.get('paths', {})
    for name, info in paths.items():
        exists = info.get('exists', False)
        marker = '✓' if exists else '✗'
        path = info.get('path', '')
        extra = ''
        if exists:
            if info.get('kind') == 'dir':
                extra = f"  ({info.get('count', 0)} items)"
            else:
                extra = f"  ({info.get('size_bytes', 0)} bytes)"
        print(f"  {marker} {name}: {path}{extra}")
    print()
    db_stats = result.get('db_stats', {})
    if db_stats:
        print("DB Stats:")
        for k, v in db_stats.items():
            print(f"  {k}: {v}")
        print()


def _render_codex_history(result: dict) -> None:
    entries = result.get('entries', [])
    total = result.get('total_entries', len(entries))
    print(f"Codex History: {total} entries")
    print()
    for entry in entries[:50]:
        if isinstance(entry, dict):
            print(f"  {json.dumps(entry, ensure_ascii=False)[:120]}")
        else:
            print(f"  {str(entry)[:120]}")
    if total > 50:
        print(f"  ... ({total - 50} more)")
    print()


def _render_codex_config(result: dict) -> None:
    print("Codex Config")
    print()
    if 'key' in result:
        key = result.get('key', '')
        val = result.get('value')
        if val is None:
            print(f"Key '{key}' not found in config")
        else:
            print(json.dumps(val, indent=2, ensure_ascii=False, default=str) if isinstance(val, (dict, list)) else str(val))
        print()
        if 'error' in result:
            print(f"Error: {result['error']}")
        return
    config = result.get('config', {})
    if config:
        print(json.dumps(config, indent=2, ensure_ascii=False, default=str))
    else:
        print("  (empty or not found)")
    print()
    if 'error' in result:
        print(f"Error: {result['error']}")


def _render_codex_memories(result: dict) -> None:
    memories = result.get('memories', [])
    total = result.get('total', len(memories))
    print(f"Codex Memories: {total} file(s)")
    print()
    for mem in memories:
        print(f"  {mem.get('name', '?')}  ({mem.get('size_bytes', 0)} bytes)")
        content = mem.get('content', '')
        if content:
            preview = content[:200].replace('\n', ' ')
            print(f"    {preview}")
    print()


def _render_codex_rules(result: dict) -> None:
    rules = result.get('rules', [])
    total = result.get('total', len(rules))
    print(f"Codex Rules: {total} file(s)")
    print()
    for rule in rules:
        print(f"  {rule.get('name', '?')}  ({rule.get('size_bytes', 0)} bytes)")
        content = rule.get('content', '')
        if content:
            preview = content[:200].replace('\n', ' ')
            print(f"    {preview}")
    print()


def _render_codex_skills(result: dict) -> None:
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    skills = result.get('skills', [])
    total = result.get('total', len(skills))
    print(f"Codex Skills: {total} skill(s)")
    print()
    for skill in skills:
        print(f"  {skill.get('name', '?')}")
        desc = (skill.get('description') or '')[:200]
        if desc:
            print(f"    {desc}")
    print()


def _render_codex_skill(result: dict) -> None:
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    print(f"Codex Skill: {result.get('name', '?')}")
    desc = result.get('description')
    if desc:
        print(f"Description: {desc}")
    print()
    print(result.get('content', ''))


def _render_codex_plugins(result: dict) -> None:
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    plugins = result.get('plugins', [])
    total = result.get('total', len(plugins))
    print(f"Codex Plugins: {total} installed")
    print()
    for plugin in plugins:
        version = plugin.get('version', '')
        print(f"  {plugin.get('name', '?')}" + (f" ({version})" if version else ''))
        desc = (plugin.get('description') or '')[:200]
        if desc:
            print(f"    {desc}")
    print()


def _render_codex_plugin(result: dict) -> None:
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    print(f"Codex Plugin: {result.get('name', '?')}")
    print()
    print(json.dumps(result.get('manifest', {}), indent=2, ensure_ascii=False, default=str))
