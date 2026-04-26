"""File handling operations.

This module is separate from cli.routing to avoid circular dependencies with adapters.

Nginx-specific file handlers live in reveal.adapters.nginx.handlers (BACK-097).
Re-exported here for backward compatibility with existing test imports.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

# Nginx handlers — canonical location is adapters/nginx/handlers.py
from .adapters.nginx.handlers import (  # noqa: F401 — re-exported for backward compat
    _handle_domain_extraction,
    _handle_acme_roots_extraction,
    _handle_check_acl,
    _format_acl_col,
    _format_acme_ssl_col,
    _fetch_acme_ssl_data,
    _render_acme_json,
    _render_acme_text,
    _handle_validate_nginx_acme,
    _handle_global_audit,
    _handle_check_conflicts,
    _resolve_log_path,
    _render_diagnose_table,
    _handle_diagnose,
    _load_disk_cert,
    _load_live_cert,
    _cert_match_label,
    _format_disk_col,
    _format_live_col,
    _format_match_col,
    _handle_cpanel_certs,
    _handle_extract_option,
)


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


def _get_analyzer_or_exit(path: str, allow_fallback: bool):
    """Get analyzer for path or exit with error.

    Args:
        path: File path
        allow_fallback: Whether to allow fallback analyzers

    Returns:
        Analyzer instance

    Exits:
        With error code 1 if no analyzer found
    """
    from .registry import get_analyzer, get_all_analyzers  # noqa: I006 — circular avoidance
    from .errors import AnalyzerNotFoundError  # noqa: I006 — circular avoidance

    analyzer_class = get_analyzer(path, allow_fallback=allow_fallback)
    if not analyzer_class:
        # Find similar extensions for suggestions
        ext = Path(path).suffix
        similar_exts = None
        if ext:
            analyzers = get_all_analyzers()
            similar_exts = [e for e in analyzers.keys()
                          if ext.lower() in e.lower() or e.lower() in ext.lower()]

        # Create detailed error with suggestions
        error = AnalyzerNotFoundError(
            path=path,
            allow_fallback=allow_fallback,
            similar_extensions=similar_exts
        )

        print(str(error), file=sys.stderr)
        sys.exit(1)

    return analyzer_class(path)


def _build_file_cli_overrides(args: Optional['Namespace']) -> dict:
    """Build CLI overrides dictionary from args.

    Args:
        args: Argument namespace

    Returns:
        CLI overrides dict
    """
    cli_overrides = {}
    if args and getattr(args, 'no_breadcrumbs', False):
        cli_overrides['display'] = {'breadcrumbs': False}
    return cli_overrides


def _has_nav_flag(args) -> bool:
    """Return True if any sub-function progressive disclosure flag is set."""
    return (
        getattr(args, 'outline', False)
        or getattr(args, 'scope', False)
        or bool(getattr(args, 'varflow', None))
        or getattr(args, 'calls', None) is not None   # nargs='?' — None means absent
        or getattr(args, 'around', None) is not None  # nargs='?' — None means absent
        or getattr(args, 'ifmap', False)
        or getattr(args, 'catchmap', False)
        or getattr(args, 'exits', False)
        or getattr(args, 'flowto', False)
        or getattr(args, 'deps', False)
        or getattr(args, 'mutations', False)
        or getattr(args, 'writes', False)
        or getattr(args, 'sideeffects', False)
        or getattr(args, 'returns', False)
        or getattr(args, 'boundary', False)
        or bool(getattr(args, 'narrow', None))
    )


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
_NAV_DISPATCH: list[tuple[Callable, Callable]] = [
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


def _dispatch_nav(analyzer, element: str, output_format: str, args) -> None:
    """Route to a nav handler based on the active flag.

    Requires a TreeSitterAnalyzer with a parsed tree.  Exits with an error
    message if the file type is not tree-sitter analysable.
    """
    from .treesitter import TreeSitterAnalyzer  # noqa: I006

    if not isinstance(analyzer, TreeSitterAnalyzer) or not analyzer.tree:
        print(
            'Error: nav flags require tree-sitter analysis.\n'
            f'  File type may not be supported: {analyzer.path}',
            file=sys.stderr,
        )
        sys.exit(1)

    from .display.element import _parse_element_syntax  # noqa: I006

    as_json = output_format == 'json'

    # ---- --scope / --around: pre-func_node flags ---------------------------
    if getattr(args, 'scope', False):
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
        chain = scope_chain(analyzer.tree.root_node, line_no, analyzer._get_node_text)
        if as_json:
            _nav_json('scope', analyzer.path, element, line_no, line_no, chain)
        else:
            content_lines = analyzer.content.splitlines()
            line_text = content_lines[line_no - 1].strip() if 0 < line_no <= len(content_lines) else ''
            print(render_scope_chain(line_no, chain, line_text))
        return

    if getattr(args, 'around', None) is not None:
        syntax = _parse_element_syntax(element)
        if syntax['type'] != 'line':
            print(
                f'Error: --around requires a line reference (e.g., reveal file.py :123 --around)\n'
                f'  Got element: {element!r}',
                file=sys.stderr,
            )
            sys.exit(1)
        line_no = syntax['start_line']
        n = args.around
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
        return

    # ---- Find the function/scope node (needed for all _NAV_DISPATCH flags) -
    # For named functions: use the function node directly.
    # For flat/procedural files (no named scope): fall back to root_node when
    # the element is a line reference (:N or :N-M).  This enables --varflow,
    # --calls, --ifmap, --catchmap, --exits, --flowto, --deps, --mutations on
    # files that have no top-level function definitions.
    func_node = _find_element_node(analyzer, element)
    if func_node is None:
        syntax = _parse_element_syntax(element) if element else None
        if syntax and syntax['type'] == 'line':
            func_node = analyzer.tree.root_node
            # Honour the element's own range as the effective scope boundary.
            # :N alone (no end) → start_line to end of file.
            func_start = syntax['start_line']
            func_end = (
                syntax['end_line']
                if syntax.get('end_line')
                else len(analyzer.content.splitlines())
            )
        else:
            print(
                f'Error: could not find function or method {element!r} in {analyzer.path}\n'
                '  Use `reveal <file>` to list available elements.\n'
                '  For methods, use Class.method syntax (e.g., MyClass.my_method).',
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        func_start = func_node.start_point[0] + 1
        func_end = func_node.end_point[0] + 1

    ctx = _NavCtx(
        func_node=func_node,
        element=element,
        analyzer=analyzer,
        as_json=as_json,
        args=args,
        func_start=func_start,
        func_end=func_end,
        depth=getattr(args, 'depth', 3) or 3,
        get_text=analyzer._get_node_text,
    )

    for check, handler in _NAV_DISPATCH:
        if check(args):
            handler(ctx)
            return


def _find_element_node(analyzer, element: str):
    """Find and return the tree-sitter node for a named function/method.

    Supports bare names ('my_func') and Class.method syntax ('MyClass.my_method').
    Returns the node or None if not found.
    """
    from .treesitter import ELEMENT_TYPE_MAP, PARENT_NODE_TYPES  # noqa: I006
    from .display.element import _find_child_in_subtree  # noqa: I006

    if '.' in element:
        parent_name, child_name = element.split('.', 1)
        for node_type in PARENT_NODE_TYPES:
            for parent_node in analyzer._find_nodes_by_type(node_type):
                if analyzer._get_node_name(parent_node) == parent_name:
                    child = _find_child_in_subtree(analyzer, parent_node, child_name)
                    if child:
                        return child
        return None

    for category in ('function', 'class'):
        for node_type in ELEMENT_TYPE_MAP.get(category, []):
            for node in analyzer._find_nodes_by_type(node_type):
                if analyzer._get_node_name(node) == element:
                    return node
    return None


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


def _dispatch_special_flags(analyzer, path: str, output_format: str, args, config) -> bool:
    """Handle flags that short-circuit normal file analysis.

    Returns True if a flag was matched and handled (caller should return
    immediately).  Returns False if none matched and normal routing should
    continue.
    """
    if getattr(args, 'extract', None):
        _handle_extract_option(analyzer, args.extract.lower(), args=args)
        return True

    if getattr(args, 'check_acl', False):
        _handle_check_acl(analyzer)
        return True

    if getattr(args, 'validate_nginx_acme', False):
        _handle_validate_nginx_acme(analyzer, args)
        return True

    if getattr(args, 'global_audit', False):
        _handle_global_audit(analyzer, args)
        return True

    if getattr(args, 'check_conflicts', False):
        _handle_check_conflicts(analyzer)
        return True

    if getattr(args, 'cpanel_certs', False):
        _handle_cpanel_certs(analyzer, args=args)
        return True

    if getattr(args, 'diagnose', False):
        _handle_diagnose(analyzer, log_path=getattr(args, 'log_path', None))
        return True

    if getattr(args, 'validate_schema', None):
        from .checks import run_schema_validation  # noqa: I006 — circular avoidance
        run_schema_validation(analyzer, path, args.validate_schema, output_format, args)
        return True

    return False


def handle_file(path: str, element: Optional[str], show_meta: bool,
                output_format: str, args: Optional['Namespace'] = None) -> None:
    """Handle file analysis.

    Args:
        path: File path
        element: Optional element to extract
        show_meta: Whether to show metadata only
        output_format: Output format ('text', 'json', 'grep')
        args: Full argument namespace (for filter options)
    """
    from .display import show_structure, show_metadata, extract_element  # noqa: I006 — circular avoidance
    from .config import RevealConfig  # noqa: I006 — circular avoidance

    allow_fallback = not getattr(args, 'no_fallback', False) if args else True
    analyzer = _get_analyzer_or_exit(path, allow_fallback)

    cli_overrides = _build_file_cli_overrides(args)
    config = RevealConfig.get(
        start_path=Path(path).parent if Path(path).is_file() else Path(path),
        cli_overrides=cli_overrides if cli_overrides else None
    )

    if show_meta:
        show_metadata(analyzer, output_format, config=config)
        return

    if args and _dispatch_special_flags(analyzer, path, output_format, args, config):
        return

    if args and not element:
        # --scope requires a line ref; fail fast.
        if getattr(args, 'scope', False):
            print(
                'Error: --scope requires a line reference (e.g., reveal file.py :123 --scope)',
                file=sys.stderr,
            )
            sys.exit(1)
        # --around requires a line ref; fail fast.
        if getattr(args, 'around', None) is not None:
            print(
                'Error: --around requires a line reference (e.g., reveal file.py :123 --around)',
                file=sys.stderr,
            )
            sys.exit(1)
        # Flat-file flags: synthesize a full-file element so _dispatch_nav can
        # fall back to root_node.  Note: --outline is intentionally absent here.
        # `reveal file.py --outline` (no element) is handled downstream by
        # show_structure, which renders a top-level structural outline.  Adding
        # --outline here would route it through _dispatch_nav on root_node instead,
        # producing a different (lower-level) output and breaking existing behaviour.
        _FLAT_FLAGS = ('varflow', 'calls', 'ifmap', 'catchmap', 'exits', 'flowto', 'deps', 'mutations', 'writes', 'sideeffects', 'returns', 'boundary')
        for flag in _FLAT_FLAGS:
            if getattr(args, flag, None):
                total = len(analyzer.content.splitlines())
                element = f':1-{total}'
                break

    if element:
        # Sub-function nav flags take priority over normal element extraction
        if args and _has_nav_flag(args):
            _dispatch_nav(analyzer, element, output_format, args)
            return
        extract_element(analyzer, element, output_format, config=config)
        return

    show_structure(analyzer, output_format, args, config=config)
