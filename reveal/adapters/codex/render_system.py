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
    config = result.get('config', {})
    print("Codex Config")
    print()
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
