"""Side-effect taxonomy classifier: collect_effects, render_effects."""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
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
#
# BACK-431 Issue D: patterns that are only meaningful for one language/runtime
# (a builtin function name, a stdlib module path) live in _TAXONOMY_BY_LANG,
# keyed by the analyzer's `language` attribute (aliased via _LANG_GROUP for
# JS/TS variants). Patterns with no single-language home (generic verbs like
# `db_query`, receiver-shape callees like `->execute`) stay in _TAXONOMY_COMMON
# and apply everywhere. classify_call()/collect_effects() take an optional
# `language` — when given, only common + that language's patterns are checked,
# so (e.g.) a Go file can no longer be tagged 'session' by a PHP builtin named
# `session_start`. When omitted, behavior is unchanged from before this split:
# common + every language's patterns are checked (see _COMPILED_ALL).
_TAXONOMY_COMMON: List[Tuple[str, List[str]]] = [
    ('hard_stop', [
        'die', 'exit', 'abort', 'halt',
    ]),
    ('db', [
        'pg_query', 'pg_fetch', 'sqlite_query',
        '->query', '->execute', '->fetch', '->select', '->insert', '->update', '->delete',
        '::query', '::execute',
        'db_query', 'db_insert', 'db_update', 'db_delete',
    ]),
    ('http', [
        'http_get', 'http_post',
        # Re-added 2026-05-05 (BACK-283): segment-boundary matching makes
        # bare 'header' safe — it no longer matches user wrappers like
        # 'printHeader' or 'request_headers'.
        'header',
    ]),
    ('cache', [
        'redis->', 'redis::',
        'cache.get', 'cache.set', 'cache.delete',
    ]),
    ('file', [
        'fopen', 'fwrite', 'fread', 'fclose', 'fputs',
        'rename', 'unlink', 'mkdir', 'rmdir', 'copy',
        'readfile', 'tmpfile', 'open(',
    ]),
    ('env', [
        'getenv', 'putenv',
    ]),
    ('log', [
        'syslog', 'write_log', 'logger.', 'log.', 'app.logger',
    ]),
    ('sleep', [
        'sleep', 'usleep',
    ]),
]

_TAXONOMY_BY_LANG: Dict[str, List[Tuple[str, List[str]]]] = {
    'php': [
        ('db', [
            'mysql_query', 'mysql_fetch', 'mysqli_query', 'mysqli_fetch',
            'wpdb', '$wpdb', 'pdo->', 'pdo::', 'new pdo',
        ]),
        ('http', [
            'curl_exec', 'curl_setopt', 'curl_init',
            'file_get_contents',
            'wp_remote_get', 'wp_remote_post', 'wp_remote_request',
            'setcookie', 'setrawcookie', 'mail',
        ]),
        ('cache', [
            'memcache_get', 'memcache_set', 'memcache_delete', 'memcache_add',
            'apc_store', 'apcu_store', 'apcu_fetch',
            'apc_fetch', 'apc_delete', 'apcu_delete',
            'wp_cache_get', 'wp_cache_set', 'wp_cache_delete',
        ]),
        ('session', [
            'session_start', 'session_destroy', 'session_regenerate_id',
            'session_unset', 'session_write_close', 'session_id',
        ]),
        ('file', [
            'file_put_contents', 'file_get_contents',
        ]),
        ('log', [
            'error_log', 'trigger_error', 'var_dump', 'phpinfo',
        ]),
    ],
    'python': [
        ('hard_stop', ['sys.exit', 'os._exit']),
        ('http', [
            'requests.get', 'requests.post', 'requests.put', 'requests.delete',
            'urllib.request', 'httpx.', 'aiohttp.',
        ]),
        ('file', [
            'os.rename', 'os.unlink', 'os.mkdir', 'shutil.',
            # 'pathlib' (module) stays; the bare 'Path(' constructor pattern
            # was removed (BACK-416) — it tokenizes to just ['path'] and so
            # matched any segment named `path` (e.g. a local var in
            # `path.resolveIndex()`), and constructing a Path is not itself a
            # filesystem side effect anyway.
            'pathlib',
        ]),
        ('env', ['os.environ', 'os.getenv']),
        ('log', ['logging.']),
        ('sleep', ['time.sleep', 'asyncio.sleep', 'gevent.sleep']),
    ],
    'js': [
        ('http', ['fetch(']),
        ('log', ['console.log', 'console.error', 'console.warn']),
        ('sleep', ['setTimeout', 'setInterval']),
    ],
    'go': [
        ('file', [
            'os.open', 'os.openfile', 'os.create', 'os.remove', 'os.mkdirall',
            'ioutil.readfile', 'ioutil.writefile',
        ]),
    ],
    'rust': [
        ('hard_stop', ['std::process::exit']),
        ('file', ['std::fs']),
        ('env', ['std::env']),
    ],
    'java': [
        ('env', ['system.getenv']),
    ],
    # BACK-477: Kotlin's kotlin.io File extension functions — none of these
    # match any existing pattern (verified: 'writeText'/'appendText'/etc are
    # single camelCase tokens, tokenizing to e.g. 'writetext', not 'write').
    'kotlin': [
        ('file', [
            'writetext', 'appendtext', 'readtext',
            'writebytes', 'appendbytes', 'readbytes',
            'copyto', 'deleterecursively', 'mkdirs', 'createnewfile',
        ]),
    ],
    # BACK-477: Swift's dominant file-write idiom is `"...".write(toFile:...)`
    # / `data.write(to: url)` — the argument label carrying the file-specific
    # meaning isn't visible to classify_call (callee text only), but a bare
    # `write` callee is Swift-specific enough here (scoped via `language`) to
    # not collide with other 'write' meanings the way an unscoped common
    # pattern would.
    'swift': [
        ('file', ['write']),
        # BACK-498 quick win: NSLog/os_log are Swift/Cocoa's logging calls —
        # bare `print` deliberately stays unclassified (matches tier1 Java/C#/
        # Python treatment of stdout writes as non-log), but NSLog/os_log are
        # unambiguous logging APIs, not print wrappers.
        ('log', ['nslog', 'os_log']),
    ],
}

# Analyzer `language` values that share one _TAXONOMY_BY_LANG bucket.
_LANG_GROUP: Dict[str, str] = {
    'javascript': 'js', 'typescript': 'js', 'tsx': 'js', 'jsx': 'js',
}

# classify_call()'s kind-priority order (first match wins) — preserved from
# the original flat _TAXONOMY so merging common + per-language tables can't
# silently reorder which kind a dual-matching callee resolves to.
_KIND_ORDER = ['hard_stop', 'db', 'http', 'cache', 'session', 'file', 'env', 'log', 'sleep']


def _merge_by_kind(*taxonomies: List[Tuple[str, List[str]]]) -> List[Tuple[str, List[str]]]:
    """Merge (kind, patterns) tables, concatenating patterns per kind and
    ordering kinds by _KIND_ORDER regardless of input order."""
    merged: Dict[str, List[str]] = {}
    for taxonomy in taxonomies:
        for kind, patterns in taxonomy:
            merged.setdefault(kind, []).extend(patterns)
    return [(kind, merged[kind]) for kind in _KIND_ORDER if kind in merged]


_DELIM_RE = re.compile(r'->|::|\.|\s+')


def _tokenize(s: str) -> List[str]:
    """Lowercase, strip PHP `$` sigil and trailing `(`, split on delimiters."""
    s = s.lower().strip()
    if s.endswith('('):
        s = s[:-1].rstrip()
    s = s.lstrip('$')
    parts = _DELIM_RE.split(s)
    return [p for p in parts if p]


def _compile(taxonomy: List[Tuple[str, List[str]]]) -> List[Tuple[str, List[List[str]]]]:
    return [(kind, [_tokenize(p) for p in patterns]) for kind, patterns in taxonomy]


# Pre-compiled once at module load: the "no language given" table (identical
# match set to the pre-BACK-431-Issue-D flat _TAXONOMY) and one table per
# known language (common + that language's patterns only).
_COMPILED_ALL: List[Tuple[str, List[List[str]]]] = _compile(
    _merge_by_kind(_TAXONOMY_COMMON, *_TAXONOMY_BY_LANG.values())
)
_COMPILED_BY_LANG: Dict[str, List[Tuple[str, List[List[str]]]]] = {
    lang: _compile(_merge_by_kind(_TAXONOMY_COMMON, patterns))
    for lang, patterns in _TAXONOMY_BY_LANG.items()
}


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
    # 'path' (singular) removed BACK-416: it's an extremely common local-var
    # name and a Path object's methods (`path.resolveIndex()`, `path.getParent()`,
    # C# `Path.Combine`) are string/path manipulation, not I/O — real filesystem
    # work goes through the File/Directory/Files/Paths static classes (kept).
    # 'fs' added BACK-416: Node's filesystem module (`fs.writeFileSync`,
    # `fs.readFileSync`, `fs.promises.writeFile`) and Rust's aliased `fs::read`
    # — both were previously unclassified despite being clear file I/O.
    ('file', ['file', 'directory', 'files', 'paths', 'fs']),
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


def classify_call(callee: str, language: Optional[str] = None) -> Optional[str]:
    """Return the taxonomy kind for a callee string, or None if unclassified.

    *language* scopes matching to common + that language's patterns (e.g. a
    PHP-only builtin like `session_start` won't fire for a Go file). Omit it
    to match against common + every known language's patterns (unscoped).
    """
    if not callee:
        return None
    callee_segs = _tokenize(callee)
    if not callee_segs:
        return None
    lang = _LANG_GROUP.get(language, language) if language else None
    taxonomy = _COMPILED_BY_LANG.get(lang, _COMPILED_ALL) if lang else _COMPILED_ALL
    for kind, pattern_list in taxonomy:
        for pattern_segs in pattern_list:
            if _segments_contain(callee_segs, pattern_segs):
                return kind
    return _classify_by_receiver(callee_segs)


def collect_effects(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
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
        kind = classify_call(call.get('callee') or '', language)
        results.append({**call, 'kind': kind})
    return results


def _resolve_definition_node(file_path: str, name: str, analyzer_cache: Dict[str, Any]):
    """Best-effort: find *name*'s function node in *file_path*, caching the analyzer.

    Returns (node, start_line, end_line, get_text, language) or None if the
    file isn't tree-sitter analysable or the name can't be located — callers
    should skip that hop rather than treat it as fatal (this walk is a
    best-effort blast-radius read, not a correctness-critical resolution).
    """
    from ...file_handler import _find_element_node  # noqa: I006 — deferred, avoids cli/adapters cycle
    from ...registry import get_analyzer  # noqa: I006
    from ...treesitter import TreeSitterAnalyzer  # noqa: I006

    analyzer = analyzer_cache.get(file_path)
    if analyzer is None:
        analyzer_class = get_analyzer(file_path, allow_fallback=True)
        if analyzer_class is None:
            analyzer_cache[file_path] = False
        else:
            try:
                analyzer = analyzer_class(file_path)
            except Exception:
                analyzer = False
            analyzer_cache[file_path] = analyzer
    if not analyzer or not isinstance(analyzer, TreeSitterAnalyzer) or not analyzer.tree:
        return None

    node = _find_element_node(analyzer, name)
    if node is None:
        return None
    start = node.start_position().row + 1
    end_node = getattr(analyzer, '_function_end_node', lambda n: n)(node)
    end = end_node.end_position().row + 1
    return end_node, start, end, analyzer._get_node_text, getattr(analyzer, 'language', None)


def collect_effects_transitive(
    path: str,
    root_name: str,
    root_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
    depth: int = 2,
) -> List[Dict[str, Any]]:
    """Follow calls into project-local helpers, classifying effects across hops.

    Hop 0 is the entry function's own body (identical to collect_effects). Each
    subsequent hop resolves calls that land on a project-local definition —
    reusing the same bare-name + language-family scoping the calls:// recursive
    walk (find_callees_recursive) already relies on — and classifies that
    definition's own body too. An unresolved or cross-language call terminates
    that branch: it's already covered by collect_effects's direct name-pattern
    match at the hop that made it (BACK-545 design doc), so nothing is lost by
    not chasing it further.

    Each returned effect carries 'hop' (0-indexed) and 'chain' (the call path
    that reached it, e.g. ['handle_request', '_save', 'db_execute']).
    """
    from .analysis import collect_structures  # noqa: I006
    from ..calls.index import _build_forward_index, _bare_callee_name, _lang_family  # noqa: I006

    depth = max(1, min(depth, 5))

    hop0 = collect_effects(root_node, from_line, to_line, get_text, language)
    for e in hop0:
        e['hop'] = 0
        e['chain'] = [root_name]
    results: List[Dict[str, Any]] = list(hop0)

    path_obj = Path(path)
    directory = path_obj if path_obj.is_dir() else path_obj.parent
    structures = collect_structures(str(directory))
    forward = _build_forward_index(structures, include_builtins=False)

    root_family = _lang_family(path) if path else ''
    visited = {root_name}
    frontier = [(root_name, root_family, [root_name])]
    analyzer_cache: Dict[str, Any] = {}

    for hop in range(1, depth + 1):
        next_frontier: List[Tuple[str, str, List[str]]] = []
        for name, family, chain in frontier:
            defs = forward.get(name, [])
            if family:
                defs = [d for d in defs if _lang_family(d['file']) == family]
            for defn in defs:
                for callee in defn['calls']:
                    tail = _bare_callee_name(callee)
                    if tail in visited:
                        continue
                    candidates = forward.get(tail, [])
                    if family:
                        candidates = [c for c in candidates if _lang_family(c['file']) == family]
                    if not candidates:
                        continue
                    visited.add(tail)
                    callee_file = candidates[0]['file']
                    resolved = _resolve_definition_node(callee_file, tail, analyzer_cache)
                    if resolved is None:
                        continue
                    node, start, end, callee_get_text, callee_language = resolved
                    new_chain = chain + [tail]
                    hop_effects = collect_effects(node, start, end, callee_get_text, callee_language)
                    for e in hop_effects:
                        e['hop'] = hop
                        e['chain'] = new_chain
                        e['file'] = callee_file
                    results.extend(hop_effects)
                    next_frontier.append((tail, family or _lang_family(callee_file), new_chain))
        if not next_frontier:
            break
        frontier = next_frontier

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


def render_effects_transitive(
    effects: List[Dict[str, Any]],
    root_name: str,
    depth: int,
    include_unclassified: bool = False,
) -> str:
    """Render collect_effects_transitive output, grouped by hop/call chain."""
    visible = [e for e in effects if e['kind'] is not None or include_unclassified]
    if not visible:
        return (
            f'No classified side effects found in {root_name} '
            f'or its callees (--transitive, depth={depth})'
        )

    kind_width = max(len(e['kind'] or '?') for e in visible)
    groups: Dict[Tuple[str, ...], List[Dict[str, Any]]] = OrderedDict()
    for e in visible:
        key = tuple(e.get('chain') or [root_name])
        groups.setdefault(key, []).append(e)

    blocks = []
    for chain, group_effects in groups.items():
        hop = group_effects[0].get('hop', 0)
        if hop == 0:
            header = f'[hop 0] {root_name} (own body)'
        else:
            header = f"[hop {hop}] via {' → '.join(chain)}"
        lines = [header]
        for e in group_effects:
            kind = e['kind'] or '?'
            callee = e['callee'] or '(unknown)'
            lineno = e['line']
            first_arg = e.get('first_arg')
            has_more = e.get('has_more_args', False)
            arg_str = f'({first_arg}{"..." if has_more else ""})' if first_arg else '()'
            lines.append(f'  L{lineno:<6}  {kind:<{kind_width}}  {callee}{arg_str}')
        blocks.append('\n'.join(lines))
    return '\n'.join(blocks)
