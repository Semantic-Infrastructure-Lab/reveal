"""File handling operations.

This module is separate from cli.routing to avoid circular dependencies with adapters.

Nginx-specific file handlers live in reveal.adapters.nginx.handlers (BACK-097).
Nav-flag handlers (--outline, --varflow, --calls, etc.) live in reveal.nav_handlers
(BACK-306). Both groups are re-exported here for backward compatibility with existing
test imports.
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

# Nav handlers — canonical location is reveal/nav_handlers.py (BACK-306).
# Re-exported for backward compat with tests that import from file_handler.
from .nav_handlers import (  # noqa: F401
    _IF_KEYWORDS,
    _CATCH_KEYWORDS,
    _resolve_range,
    _parse_line_range,
    _nav_json,
    _NavCtx,
    _nav_outline,
    _nav_varflow,
    _nav_narrow,
    _nav_calls,
    _nav_branchmap,
    _nav_exits,
    _nav_deps,
    _nav_mutations,
    _nav_sideeffects,
    _nav_returns,
    _nav_boundary,
    _nav_scope,
    _nav_around,
    _NAV_DISPATCH,
)


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
    # scope and around are handled before _NAV_DISPATCH in _dispatch_nav
    return (
        getattr(args, 'scope', False)
        or getattr(args, 'around', None) is not None
        or any(check(args) for check, _ in _NAV_DISPATCH)
    )


def _resolve_func_node(analyzer, element: str):
    """Resolve the function/scope node for nav flags that need an element.

    For named functions: returns the function node directly.
    For flat/procedural files: falls back to root_node when the element is a
    line reference (:N or :N-M), enabling nav flags on files without top-level
    function definitions.

    Returns:
        (func_node, func_start, func_end) or exits with an error message.
    """
    from .display.element import _parse_element_syntax  # noqa: I006
    func_node = _find_element_node(analyzer, element)
    if func_node is None:
        syntax = _parse_element_syntax(element) if element else None
        if syntax and syntax['type'] == 'line':
            func_node = analyzer.tree.root_node()
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
        func_start = func_node.start_position().row + 1
        # Dart's grammar splits a function into sibling `function_signature`
        # + `function_body` nodes rather than nesting the body inside one
        # function node (see TreeSitterAnalyzer._function_end_node) — every
        # nav flag walks func_node's own subtree, so without this swap they'd
        # walk only the one-line signature and see the body as empty, no
        # matter what func_end says.
        end_node = getattr(analyzer, '_function_end_node', lambda n: n)(func_node)
        func_end = end_node.end_position().row + 1
        if end_node is not func_node:
            func_node = end_node
    return func_node, func_start, func_end


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

    as_json = output_format == 'json'

    # --scope and --around operate on a line reference, not a func node.
    if getattr(args, 'scope', False):
        _nav_scope(analyzer, element, as_json)
        return
    if getattr(args, 'around', None) is not None:
        _nav_around(analyzer, element, as_json, args.around)
        return

    func_node, func_start, func_end = _resolve_func_node(analyzer, element)
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

    # JS-family `const f = (...) => {}` — not a FUNCTION_NODE_TYPES member at
    # all (it's a filtered variable_declarator, not a flat kind match), so it
    # needs its own resolver (BACK-431 Issue G tier B dogfood audit: found via
    # real excalidraw/.tsx source, reproduces on plain .ts/.js too).
    find_arrow_fn = getattr(analyzer, '_find_named_arrow_function', None)
    if find_arrow_fn is not None:
        node = find_arrow_fn(element)
        if node is not None:
            return node

    return None


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
