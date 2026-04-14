"""File handling operations.

This module is separate from cli.routing to avoid circular dependencies with adapters.

Nginx-specific file handlers live in reveal.adapters.nginx.handlers (BACK-097).
Re-exported here for backward compatibility with existing test imports.
"""

import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

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
    )


def _dispatch_nav(analyzer, element: str, output_format: str, args) -> None:
    """Route to a sub-function nav handler based on the active flag.

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

    from .adapters.ast.nav import (  # noqa: I006
        element_outline, scope_chain, var_flow, range_calls,
        collect_exits, collect_deps, collect_mutations,
        render_outline, render_scope_chain, render_var_flow, render_range_calls,
        render_branchmap, render_exits, render_deps, render_mutations,
    )
    from .display.element import _parse_element_syntax  # noqa: I006
    from .treesitter import ELEMENT_TYPE_MAP  # noqa: I006

    get_text = analyzer._get_node_text

    # ---- --scope: ancestor chain for :LINE --------------------------------
    if getattr(args, 'scope', False):
        syntax = _parse_element_syntax(element)
        if syntax['type'] != 'line':
            print(
                f'Error: --scope requires a line reference (e.g., reveal file.py :123 --scope)\n'
                f'  Got element: {element!r}',
                file=sys.stderr,
            )
            sys.exit(1)
        line_no = syntax['start_line']
        chain = scope_chain(analyzer.tree.root_node, line_no, get_text)
        content_lines = analyzer.content.splitlines()
        line_text = content_lines[line_no - 1].strip() if 0 < line_no <= len(content_lines) else ''
        print(render_scope_chain(line_no, chain, line_text))
        return

    # ---- --around: verbatim lines centered on a target --------------------
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
        n = args.around  # int, default 20
        content_lines = analyzer.content.splitlines()
        total = len(content_lines)
        start = max(1, line_no - n)
        end = min(total, line_no + n)
        for i in range(start - 1, end):
            prefix = '▶' if (i + 1) == line_no else ' '
            print(f'{prefix}{i + 1:5}  {content_lines[i]}')
        return

    # ---- Find the function/scope node (needed for all remaining flags) -----
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

    depth = getattr(args, 'depth', 3) or 3

    # ---- --outline: control-flow skeleton ----------------------------------
    if getattr(args, 'outline', False):
        from_line, to_line = _resolve_range(args, func_start, func_end)
        items = element_outline(func_node, get_text, max_depth=depth)
        range_arg = getattr(args, 'range', None)
        if range_arg:
            items = [i for i in items if from_line <= i['line_start'] <= to_line]
        print(render_outline(element, func_start, func_end, items, depth=depth))
        return

    # ---- --varflow: variable read/write trace ------------------------------
    if getattr(args, 'varflow', None):
        var_name = args.varflow
        from_line, to_line = _resolve_range(args, func_start, func_end)
        events = var_flow(func_node, var_name, from_line, to_line, get_text)
        content_lines = analyzer.content.splitlines()
        print(render_var_flow(var_name, events, content_lines))
        return

    # ---- --calls: call sites in a line range -------------------------------
    if getattr(args, 'calls', None) is not None:
        # args.calls is 'FULL' (bare --calls), a range string (--calls 89-120), or
        # None (flag absent).  _parse_line_range handles 'FULL' via its fallback.
        from_line, to_line = _parse_line_range(args.calls, func_start, func_end)
        calls = range_calls(func_node, from_line, to_line, get_text)
        print(render_range_calls(calls, from_line, to_line))
        return

    # ---- --ifmap / --catchmap: branching skeleton -------------------------
    if getattr(args, 'ifmap', False) or getattr(args, 'catchmap', False):
        keywords = _IF_KEYWORDS if getattr(args, 'ifmap', False) else _CATCH_KEYWORDS
        from_line, to_line = _resolve_range(args, func_start, func_end)
        items = element_outline(func_node, get_text, max_depth=depth)
        filtered = [
            i for i in items
            if i['keyword'] in keywords and from_line <= i['line_start'] <= to_line
        ]
        print(render_branchmap(filtered, from_line, to_line))
        return

    # ---- --exits / --flowto: exit-node collector --------------------------
    if getattr(args, 'exits', False) or getattr(args, 'flowto', False):
        from_line, to_line = _resolve_range(args, func_start, func_end)
        exits = collect_exits(func_node, from_line, to_line, get_text)
        print(render_exits(exits, from_line, to_line, verdict=getattr(args, 'flowto', False)))
        return

    # ---- --deps: variables flowing into a range ----------------------------
    if getattr(args, 'deps', False):
        from_line, to_line = _resolve_range(args, func_start, func_end)
        deps = collect_deps(func_node, from_line, to_line, get_text)
        print(render_deps(deps, from_line, to_line))
        return

    # ---- --mutations: variables written in range and read after ------------
    if getattr(args, 'mutations', False):
        from_line, to_line = _resolve_range(args, func_start, func_end)
        mutations = collect_mutations(func_node, from_line, to_line, get_text)
        print(render_mutations(mutations, from_line, to_line))
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
        _FLAT_FLAGS = ('varflow', 'calls', 'ifmap', 'catchmap', 'exits', 'flowto', 'deps', 'mutations')
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
