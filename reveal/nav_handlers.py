"""Nav-flag handlers — implementations of --outline, --varflow, --calls, etc.

This module owns the per-flag handler functions and the _NAV_DISPATCH table.
file_handler.py orchestrates: it parses the file, builds a _NavCtx, then
delegates to the handler matched by _NAV_DISPATCH.

Imports from adapters.ast.nav are deferred inside each handler to avoid the
cli/adapters circular import at module-load time (see file_handler.py header).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional


# Branch keywords for --ifmap and --catchmap filtering
_IF_KEYWORDS: frozenset = frozenset({'IF', 'ELIF', 'ELSE', 'SWITCH', 'CASE', 'DEFAULT'})
_CATCH_KEYWORDS: frozenset = frozenset({'TRY', 'CATCH', 'EXCEPT', 'FINALLY'})


def _resolve_range(args, func_start: int, func_end: int):
    """Return (from_line, to_line) for a nav flag, respecting --range if present.

    ``args.range`` may be a pre-parsed (start, end) tuple (set by
    validate_navigation_args) or None when --range was not supplied.
    """
    range_arg = getattr(args, 'range', None)
    if range_arg:
        return _parse_line_range(range_arg, func_start, func_end)
    return func_start, func_end


def _parse_line_range(range_str, default_start: int, default_end: int):
    """Parse 'START-END' range string (or pre-parsed tuple) into (start, end) ints.

    Accepts either a 'START-END' string or a (start, end) tuple as produced by
    validate_navigation_args().  Falls back to (default_start, default_end) on
    None input or parse failure.
    """
    import re  # noqa: I006
    if range_str is None:
        return default_start, default_end
    if isinstance(range_str, tuple):
        start, end = range_str
        return start, (end if end is not None else default_end)
    m = re.match(r'^(\d+)-(\d+)$', range_str.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    # Single number: treat as start, use default_end
    m2 = re.match(r'^(\d+)$', range_str.strip())
    if m2:
        return int(m2.group(1)), default_end
    return default_start, default_end


def _nav_json(flag: str, path: str, element: str, from_line: int, to_line: int,
              findings, extra_meta: Optional[dict] = None) -> None:
    """Serialize nav findings as a JSON envelope and print to stdout."""
    import json  # noqa: I006
    meta = {'flag': flag, 'file': str(path), 'element': element,
            'from_line': from_line, 'to_line': to_line}
    if extra_meta:
        meta.update(extra_meta)
    print(json.dumps({'meta': meta, 'findings': findings, 'warnings': []}, indent=2))


@dataclass
class _NavCtx:
    func_node: Any
    element: str
    analyzer: Any
    as_json: bool
    args: Any
    func_start: int
    func_end: int
    depth: int
    get_text: Callable


def _nav_outline(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import element_outline, render_outline  # noqa: I006
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    items = element_outline(ctx.func_node, ctx.get_text, max_depth=ctx.depth)
    if getattr(ctx.args, 'range', None):
        items = [i for i in items if from_line <= i['line_start'] <= to_line]
    if ctx.as_json:
        _nav_json('outline', ctx.analyzer.path, ctx.element, from_line, to_line, items)
    else:
        print(render_outline(ctx.element, ctx.func_start, ctx.func_end, items, depth=ctx.depth))


def _nav_varflow(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import (  # noqa: I006
        var_flow, render_var_flow, cross_var_flow, render_cross_var_flow,
    )
    var_name = ctx.args.varflow
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    if getattr(ctx.args, 'cross_calls', False):
        frames = cross_var_flow(ctx.analyzer, ctx.func_node, var_name, from_line, to_line, ctx.get_text)
        if ctx.as_json:
            _nav_json('cross_varflow', ctx.analyzer.path, ctx.element, from_line, to_line, frames,
                      extra_meta={'var': var_name})
        else:
            print(render_cross_var_flow(var_name, frames, ctx.analyzer.content.splitlines()))
        return
    events = var_flow(ctx.func_node, var_name, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        findings = [{'kind': e['kind'], 'line': e['line']} for e in events]
        _nav_json('varflow', ctx.analyzer.path, ctx.element, from_line, to_line, findings,
                  extra_meta={'var': var_name})
    else:
        print(render_var_flow(var_name, events, ctx.analyzer.content.splitlines()))


def _nav_narrow(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import collect_narrowing, render_narrowing  # noqa: I006
    var_name = ctx.args.narrow
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    events = collect_narrowing(ctx.func_node, var_name, ctx.get_text)
    if ctx.as_json:
        findings = [] if events is None else [
            {'kind': e['kind'], 'line': e['line'],
             'type_set': sorted(e['type_set']), 'depth': e['depth']}
            for e in events
        ]
        _nav_json('narrow', ctx.analyzer.path, ctx.element, from_line, to_line,
                  findings, extra_meta={'var': var_name})
    else:
        print(render_narrowing(var_name, events, ctx.analyzer.content.splitlines()))


def _nav_calls(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import range_calls, render_range_calls  # noqa: I006
    # args.calls is 'FULL' (bare --calls), a range string (--calls 89-120), or
    # None (flag absent).  _parse_line_range handles 'FULL' via its fallback.
    from_line, to_line = _parse_line_range(ctx.args.calls, ctx.func_start, ctx.func_end)
    calls = range_calls(ctx.func_node, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        _nav_json('calls', ctx.analyzer.path, ctx.element, from_line, to_line, calls)
    else:
        print(render_range_calls(calls, from_line, to_line))


def _nav_branchmap(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import element_outline, render_branchmap  # noqa: I006
    flag = 'ifmap' if getattr(ctx.args, 'ifmap', False) else 'catchmap'
    keywords = _IF_KEYWORDS if flag == 'ifmap' else _CATCH_KEYWORDS
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    items = element_outline(ctx.func_node, ctx.get_text, max_depth=ctx.depth)
    filtered = [
        i for i in items
        if i['keyword'] in keywords and from_line <= i['line_start'] <= to_line
    ]
    if ctx.as_json:
        _nav_json(flag, ctx.analyzer.path, ctx.element, from_line, to_line, filtered)
    else:
        print(render_branchmap(filtered, from_line, to_line))


def _nav_exits(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import collect_exits, render_exits  # noqa: I006
    is_flowto = getattr(ctx.args, 'flowto', False)
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    exits = collect_exits(ctx.func_node, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        _nav_json('flowto' if is_flowto else 'exits',
                  ctx.analyzer.path, ctx.element, from_line, to_line, exits)
    else:
        print(render_exits(exits, from_line, to_line, verdict=is_flowto))


def _nav_deps(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import collect_deps, render_deps  # noqa: I006
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    deps = collect_deps(ctx.func_node, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        findings = [
            {'kind': 'dep', 'var': d['var'], 'line': d['first_read_line'],
             'first_write_line': d['first_write_line']}
            for d in deps
        ]
        _nav_json('deps', ctx.analyzer.path, ctx.element, from_line, to_line, findings)
    else:
        print(render_deps(deps, from_line, to_line))


def _nav_mutations(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import collect_mutations, render_mutations  # noqa: I006
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    mutations = collect_mutations(ctx.func_node, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        findings = [
            {'kind': 'mutation', 'var': m['var'], 'line': m['last_write_line'],
             'next_read_line': m['next_read_line']}
            for m in mutations
        ]
        _nav_json('mutations', ctx.analyzer.path, ctx.element, from_line, to_line, findings)
    else:
        print(render_mutations(mutations, from_line, to_line))


def _nav_sideeffects(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import collect_effects, render_effects  # noqa: I006
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    effects = collect_effects(ctx.func_node, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        findings = [
            {'kind': e['kind'], 'line': e['line'], 'callee': e['callee'],
             'first_arg': e.get('first_arg'), 'has_more_args': e.get('has_more_args', False)}
            for e in effects if e['kind'] is not None
        ]
        _nav_json('sideeffects', ctx.analyzer.path, ctx.element, from_line, to_line, findings)
    else:
        print(render_effects(effects, from_line, to_line))


def _nav_returns(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import collect_gate_chains, render_gate_chains  # noqa: I006
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    chains = collect_gate_chains(ctx.func_node, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        _nav_json('returns', ctx.analyzer.path, ctx.element, from_line, to_line, chains)
    else:
        print(render_gate_chains(chains, from_line, to_line))


def _nav_boundary(ctx: _NavCtx) -> None:
    from .adapters.ast.nav import collect_boundary, render_boundary  # noqa: I006
    from_line, to_line = _resolve_range(ctx.args, ctx.func_start, ctx.func_end)
    boundary = collect_boundary(ctx.func_node, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        findings = (
            [{'kind': 'input', 'var': d['var'], 'line': d['first_read_line'],
              'first_write_line': d['first_write_line']}
             for d in boundary['inputs']]
            + [{'kind': 'superglobal', 'var': d['var'], 'line': d['first_read_line']}
               for d in boundary['superglobals']]
            + [{'kind': e['kind'], 'line': e['line'], 'callee': e['callee'],
                'first_arg': e.get('first_arg')}
               for e in boundary['effects'] if e['kind'] is not None]
        )
        _nav_json('boundary', ctx.analyzer.path, ctx.element, from_line, to_line, findings)
    else:
        print(render_boundary(boundary, from_line, to_line))


# Maps each nav flag (or flag pair) to its handler.  Adding a new nav flag:
# 1 entry here + 1 new _nav_* function above.
_NAV_DISPATCH: List[tuple] = [
    (lambda a: getattr(a, 'outline', False),                                      _nav_outline),
    (lambda a: getattr(a, 'varflow', None),                                       _nav_varflow),
    (lambda a: getattr(a, 'narrow', None),                                        _nav_narrow),
    (lambda a: getattr(a, 'calls', None) is not None,                             _nav_calls),
    (lambda a: getattr(a, 'ifmap', False) or getattr(a, 'catchmap', False),       _nav_branchmap),
    (lambda a: getattr(a, 'exits', False) or getattr(a, 'flowto', False),         _nav_exits),
    (lambda a: getattr(a, 'deps', False),                                         _nav_deps),
    (lambda a: getattr(a, 'mutations', False) or getattr(a, 'writes', False),     _nav_mutations),
    (lambda a: getattr(a, 'sideeffects', False),                                  _nav_sideeffects),
    (lambda a: getattr(a, 'returns', False),                                      _nav_returns),
    (lambda a: getattr(a, 'boundary', False),                                     _nav_boundary),
]


def _nav_scope(analyzer, element: str, as_json: bool) -> None:
    """Handle --scope: show lexical scope chain for a line reference."""
    from .display.element import _parse_element_syntax  # noqa: I006
    from .adapters.ast.nav import scope_chain, render_scope_chain  # noqa: I006
    syntax = _parse_element_syntax(element)
    if syntax['type'] != 'line':
        print(
            f'Error: --scope requires a line reference (e.g., reveal file.py :123 --scope)\n'
            f'  Got element: {element!r}',
            file=sys.stderr,
        )
        sys.exit(1)
    line_no = syntax['start_line']
    chain = scope_chain(analyzer.tree.root_node(), line_no, analyzer._get_node_text)
    if as_json:
        _nav_json('scope', analyzer.path, element, line_no, line_no, chain)
    else:
        content_lines = analyzer.content.splitlines()
        line_text = content_lines[line_no - 1].strip() if 0 < line_no <= len(content_lines) else ''
        print(render_scope_chain(line_no, chain, line_text))


def _nav_around(analyzer, element: str, as_json: bool, n: int) -> None:
    """Handle --around N: show N lines of context around a line reference."""
    from .display.element import _parse_element_syntax  # noqa: I006
    syntax = _parse_element_syntax(element)
    if syntax['type'] != 'line':
        print(
            f'Error: --around requires a line reference (e.g., reveal file.py :123 --around)\n'
            f'  Got element: {element!r}',
            file=sys.stderr,
        )
        sys.exit(1)
    line_no = syntax['start_line']
    content_lines = analyzer.content.splitlines()
    total = len(content_lines)
    start = max(1, line_no - n)
    end = min(total, line_no + n)
    if as_json:
        findings = [
            {'line': i + 1, 'text': content_lines[i], 'is_target': (i + 1) == line_no}
            for i in range(start - 1, end)
        ]
        _nav_json('around', analyzer.path, element, start, end, findings,
                  extra_meta={'target_line': line_no, 'context': n})
    else:
        for i in range(start - 1, end):
            prefix = '▶' if (i + 1) == line_no else ' '
            print(f'{prefix}{i + 1:5}  {content_lines[i]}')
