"""Side-effect taxonomy classifier: collect_effects, render_effects."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .nav_calls import range_calls

# Each entry: (kind_label, list_of_substrings_to_match_in_callee)
# Matching is case-insensitive substring on the callee name.
# Order matters — first match wins.
_TAXONOMY: List[Tuple[str, List[str]]] = [
    ('hard_stop', ['die', 'exit', 'abort', 'sys.exit', 'os._exit', 'halt']),
    ('db', [
        'mysql_query', 'mysql_fetch', 'mysqli_query', 'mysqli_fetch',
        'pg_query', 'pg_fetch', 'sqlite_query',
        '->query', '->execute', '->fetch', '->select', '->insert', '->update', '->delete',
        '::query', '::execute',
        'db_query', 'db_insert', 'db_update', 'db_delete',
        'wpdb', '$wpdb',
    ]),
    ('http', [
        'curl_exec', 'curl_setopt', 'curl_init',
        'file_get_contents', 'http_get', 'http_post',
        'wp_remote_get', 'wp_remote_post', 'wp_remote_request',
        'requests.get', 'requests.post', 'requests.put', 'requests.delete',
        'urllib.request', 'httpx.', 'aiohttp.',
        'fetch(', '->get(', '->post(',
    ]),
    ('cache', [
        'memcache_get', 'memcache_set', 'memcache_delete', 'memcache_add',
        'redis->', 'redis::', 'apc_store', 'apcu_store', 'apcu_fetch',
        'wp_cache_get', 'wp_cache_set', 'wp_cache_delete',
        'cache.get', 'cache.set', 'cache.delete',
    ]),
    ('file', [
        'fopen', 'fwrite', 'fread', 'fclose', 'fputs',
        'file_put_contents', 'file_get_contents',
        'rename', 'unlink', 'mkdir', 'rmdir', 'copy',
        'open(', 'os.rename', 'os.unlink', 'os.mkdir', 'shutil.',
        'pathlib', 'Path(',
    ]),
    ('log', [
        'error_log', 'syslog', 'write_log',
        'logger.', 'logging.', 'log.', 'app.logger',
        'console.log', 'console.error', 'console.warn',
        'var_dump',
    ]),
    ('sleep', [
        'sleep', 'usleep', 'time.sleep', 'setTimeout', 'setInterval',
        'asyncio.sleep', 'gevent.sleep',
    ]),
]


def classify_call(callee: str) -> Optional[str]:
    """Return the taxonomy kind for a callee string, or None if unclassified."""
    if not callee:
        return None
    lower = callee.lower()
    for kind, patterns in _TAXONOMY:
        for pattern in patterns:
            if pattern.lower() in lower:
                return kind
    return None


def collect_effects(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Return classified side-effect call sites in a line range.

    Each item is a dict:
        line      -- 1-indexed line of the call
        callee    -- callee name string
        first_arg -- first argument text (or None)
        kind      -- taxonomy label, or None if unclassified
    """
    calls = range_calls(func_node, from_line, to_line, get_text)
    results = []
    for call in calls:
        kind = classify_call(call.get('callee') or '')
        results.append({**call, 'kind': kind})
    return results


def render_effects(
    effects: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
    include_unclassified: bool = False,
) -> str:
    """Render collect_effects output as text (flat, in line order)."""
    visible = [e for e in effects if e['kind'] is not None or include_unclassified]
    if not visible:
        return f'No classified side effects found in lines {from_line}–{to_line}'

    kind_width = max(len(e['kind'] or '?') for e in visible)
    lines = []
    for e in visible:
        kind = e['kind'] or '?'
        callee = e['callee'] or '(unknown)'
        lineno = e['line']
        first_arg = e.get('first_arg')
        has_more = e.get('has_more_args', False)
        if first_arg:
            arg_str = f'({first_arg}{"..." if has_more else ""})'
        else:
            arg_str = '()'
        lines.append(f'L{lineno:<6}  {kind:<{kind_width}}  {callee}{arg_str}')
    return '\n'.join(lines)
