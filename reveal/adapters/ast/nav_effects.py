"""Side-effect taxonomy classifier: collect_effects, render_effects."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .nav_calls import range_calls

# Each entry: (kind_label, list_of_patterns).
#
# Matching model (BACK-283): patterns and callees are tokenized into segments
# on the delimiters `.`, `->`, `::`, and whitespace. A pattern matches if its
# segment sequence appears consecutively in the callee's segment sequence
# (sliding-window equality, case-insensitive). This is segment-boundary
# matching, not substring containment, so `header` no longer matches
# `printHeader` and `mail` no longer matches `gmail`.
#
# Order matters — first match wins.
_TAXONOMY: List[Tuple[str, List[str]]] = [
    ('hard_stop', [
        'die', 'exit', 'abort', 'sys.exit', 'os._exit', 'halt',
        'std::process::exit',
    ]),
    ('db', [
        'mysql_query', 'mysql_fetch', 'mysqli_query', 'mysqli_fetch',
        'pg_query', 'pg_fetch', 'sqlite_query',
        '->query', '->execute', '->fetch', '->select', '->insert', '->update', '->delete',
        '::query', '::execute',
        'db_query', 'db_insert', 'db_update', 'db_delete',
        'wpdb', '$wpdb',
        'pdo->', 'pdo::', 'new pdo',
    ]),
    ('http', [
        'curl_exec', 'curl_setopt', 'curl_init',
        'file_get_contents', 'http_get', 'http_post',
        'wp_remote_get', 'wp_remote_post', 'wp_remote_request',
        'requests.get', 'requests.post', 'requests.put', 'requests.delete',
        'urllib.request', 'httpx.', 'aiohttp.',
        'fetch(',
        # Re-added 2026-05-05 (BACK-283): segment-boundary matching makes
        # bare 'header' safe — it no longer matches user wrappers like
        # 'printHeader' or 'request_headers'.
        'header',
        'setcookie', 'setrawcookie', 'mail',
    ]),
    ('cache', [
        'memcache_get', 'memcache_set', 'memcache_delete', 'memcache_add',
        'redis->', 'redis::', 'apc_store', 'apcu_store', 'apcu_fetch',
        'apc_fetch', 'apc_delete', 'apcu_delete',
        'wp_cache_get', 'wp_cache_set', 'wp_cache_delete',
        'cache.get', 'cache.set', 'cache.delete',
    ]),
    ('session', [
        'session_start', 'session_destroy', 'session_regenerate_id',
        'session_unset', 'session_write_close', 'session_id',
    ]),
    ('file', [
        'fopen', 'fwrite', 'fread', 'fclose', 'fputs',
        'file_put_contents', 'file_get_contents',
        'rename', 'unlink', 'mkdir', 'rmdir', 'copy',
        'readfile', 'tmpfile',
        'open(', 'os.rename', 'os.unlink', 'os.mkdir', 'shutil.',
        'pathlib', 'Path(',
        # Go stdlib (BACK-401): os.Open/os.Create/os.Remove/os.MkdirAll,
        # ioutil.ReadFile/WriteFile — 'os.getenv' below is checked separately
        # so it doesn't collide with these (first-match-wins, this list first).
        'os.open', 'os.create', 'os.remove', 'os.mkdirall',
        'ioutil.readfile', 'ioutil.writefile',
        # Rust stdlib (BACK-401)
        'std::fs',
    ]),
    ('env', [
        'getenv', 'putenv', 'os.environ', 'os.getenv',
        'system.getenv',  # Java (BACK-401)
        'std::env',        # Rust (BACK-401)
    ]),
    ('log', [
        'error_log', 'syslog', 'write_log', 'trigger_error',
        'logger.', 'logging.', 'log.', 'app.logger',
        'console.log', 'console.error', 'console.warn',
        'var_dump', 'phpinfo',
    ]),
    ('sleep', [
        'sleep', 'usleep', 'time.sleep', 'setTimeout', 'setInterval',
        'asyncio.sleep', 'gevent.sleep',
    ]),
]


_DELIM_RE = re.compile(r'->|::|\.|\s+')


def _tokenize(s: str) -> List[str]:
    """Lowercase, strip PHP `$` sigil and trailing `(`, split on delimiters."""
    s = s.lower().strip()
    if s.endswith('('):
        s = s[:-1].rstrip()
    s = s.lstrip('$')
    parts = _DELIM_RE.split(s)
    return [p for p in parts if p]


# Pre-tokenize patterns once at module load.
_COMPILED_TAXONOMY: List[Tuple[str, List[List[str]]]] = [
    (kind, [_tokenize(p) for p in patterns])
    for kind, patterns in _TAXONOMY
]


# BACK-285a: receiver-shape heuristics. After full-pattern matching fails,
# fall back to matching on a non-final segment of the callee. Catches calls
# like `cursor.execute`, `_log.warning`, `redis.get` where the verb varies
# but the receiver name is canonical. Non-final-only — `dict.get` (where
# `dict` is final-prefix and `get` is the trailing verb) does not match,
# and bare `cursor` (single segment) does not match. Project-specific
# receivers (tsx, evlog, services.trade_db, ...) belong in BACK-238's
# `.reveal.yaml` extension, not here.
_RECEIVER_TAXONOMY: List[Tuple[str, List[str]]] = [
    ('db', ['cursor', 'conn', 'connection', 'session', 'db', 'engine']),
    ('cache', ['cache', 'redis', 'memcache']),
    ('log', ['logger', '_log', 'log', '_logger', 'ilogger', 'slf4j']),
    ('http', ['httpx', 'aiohttp', 'requests', 'httpclient', '_httpclient']),
    # BACK-401: .NET BCL / JVM stdlib receivers for File/Directory/Path-style
    # I/O and env access — safe as non-final-only receiver matches (see
    # module docstring caution on why these aren't bare _TAXONOMY patterns).
    ('file', ['file', 'directory', 'path', 'files', 'paths']),
    ('env', ['environment']),
]


def _segments_contain(callee_segs: List[str], pattern_segs: List[str]) -> bool:
    """True if pattern_segs appears as a consecutive sub-sequence of callee_segs."""
    n = len(pattern_segs)
    if n == 0 or n > len(callee_segs):
        return False
    for i in range(len(callee_segs) - n + 1):
        if callee_segs[i:i + n] == pattern_segs:
            return True
    return False


def _classify_by_receiver(callee_segs: List[str]) -> Optional[str]:
    """Classify by matching a non-final segment against receiver names."""
    if len(callee_segs) < 2:
        return None
    non_final = callee_segs[:-1]
    for kind, receivers in _RECEIVER_TAXONOMY:
        for receiver in receivers:
            if receiver in non_final:
                return kind
    return None


def classify_call(callee: str) -> Optional[str]:
    """Return the taxonomy kind for a callee string, or None if unclassified."""
    if not callee:
        return None
    callee_segs = _tokenize(callee)
    if not callee_segs:
        return None
    for kind, pattern_list in _COMPILED_TAXONOMY:
        for pattern_segs in pattern_list:
            if _segments_contain(callee_segs, pattern_segs):
                return kind
    return _classify_by_receiver(callee_segs)


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
