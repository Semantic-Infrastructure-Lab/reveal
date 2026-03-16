"""URI and file routing for reveal CLI.

This module handles dispatching to the correct handler based on:
- URI scheme (env://, ast://, help://, python://, json://, reveal://, etc.)
- File type (determined by extension)
- Directory handling

All URI adapters now use the renderer-based system (Phase 4 complete).
"""

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from argparse import Namespace



# ============================================================================
# Import file handling from shared module to avoid circular dependency
from ..file_handler import handle_file  # noqa: E402


# ============================================================================
# Public API
# ============================================================================

def handle_uri(uri: str, element: Optional[str], args: 'Namespace') -> None:
    """Handle URI-based resources (env://, ast://, etc.).

    Args:
        uri: Full URI (e.g., env://, env://PATH)
        element: Optional element to extract
        args: Parsed command line arguments
    """
    if '://' not in uri:
        print(f"Error: Invalid URI format: {uri}", file=sys.stderr)
        sys.exit(1)

    scheme, resource = uri.split('://', 1)

    # Inject --sort/--desc CLI flags into URI query string for adapters that support them
    sort_field = getattr(args, 'sort', None)
    if sort_field:
        if getattr(args, 'desc', False) and not sort_field.startswith('-'):
            sort_field = f"-{sort_field}"
        sep = '&' if '?' in resource else '?'
        resource = f"{resource}{sep}sort={sort_field}"

    # Look up adapter from registry
    from ..adapters.base import get_adapter_class, list_supported_schemes
    # Import adapters package to trigger all registrations (single source of truth)
    from .. import adapters as _adapters  # noqa: F401

    adapter_class = get_adapter_class(scheme)
    if not adapter_class:
        print(f"Error: Unsupported URI scheme: {scheme}://", file=sys.stderr)
        schemes = ', '.join(f"{s}://" for s in list_supported_schemes())
        print(f"Supported schemes: {schemes}", file=sys.stderr)
        sys.exit(1)

    # Dispatch to scheme-specific handler
    handle_adapter(adapter_class, scheme, resource, element, args)


def generic_adapter_handler(adapter_class: type, renderer_class: type[Any],
                           scheme: str, resource: str, element: Optional[str],
                           args: 'Namespace') -> None:
    """Generic handler for adapters with registered renderers.

    This is the new simplified handler that works with any adapter/renderer pair.
    Replaces the need for scheme-specific handlers in most cases.

    Args:
        adapter_class: The adapter class to instantiate
        renderer_class: The renderer class for output
        scheme: URI scheme (for building full URI if needed)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # Initialize adapter via from_uri.  Use _default_from_uri when adapter_class is
    # not a real type (e.g. a Mock callable in tests) or lacks from_uri.
    from ..adapters.base import _default_from_uri
    try:
        if isinstance(adapter_class, type) and hasattr(adapter_class, 'from_uri'):
            adapter = adapter_class.from_uri(scheme, resource, element)
        else:
            adapter = _default_from_uri(adapter_class, scheme, resource, element)
    except ImportError as e:
        renderer_class.render_error(e)
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing {scheme}:// adapter: {e}", file=sys.stderr)
        sys.exit(1)

    # Apply --base-path override for adapters that use a base directory (e.g., claude://)
    path_override = getattr(args, 'base_path', None)
    if path_override and hasattr(adapter, 'CONVERSATION_BASE'):
        from pathlib import Path as _Path
        adapter.CONVERSATION_BASE = _Path(path_override)
        # Re-locate the conversation file under the new base
        if hasattr(adapter, '_find_conversation'):
            adapter.conversation_path = adapter._find_conversation()

    # Handle --check mode if requested
    if getattr(args, 'check', False) and hasattr(adapter, 'check'):
        _handle_check_mode(adapter, renderer_class, args)
        return  # check mode exits directly

    # Render element or structure based on adapter type
    _handle_rendering(adapter, renderer_class, scheme, resource, element, args)


def _build_check_kwargs(adapter, args: 'Namespace') -> dict:
    """Build kwargs for adapter.check() by inspecting signature.

    Args:
        adapter: Adapter with check() method
        args: CLI arguments

    Returns:
        Dict of kwargs to pass to check()
    """
    import inspect

    sig = inspect.signature(adapter.check)
    kwargs = {}
    has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

    # Helper to add param if supported
    def add_if_supported(param_name, arg_name=None):
        arg_name = arg_name or param_name
        if (has_var_keyword or param_name in sig.parameters) and hasattr(args, arg_name):
            value = getattr(args, arg_name)
            if value is not None:
                # Split comma-separated strings
                if param_name in ('select', 'ignore') and isinstance(value, str):
                    value = value.split(',')
                kwargs[param_name] = value

    add_if_supported('select')
    add_if_supported('ignore')
    add_if_supported('advanced')
    add_if_supported('validate_nginx')
    add_if_supported('local_certs')
    add_if_supported('expiring_within')

    return kwargs


def _build_render_opts(renderer_class: type[Any], args: 'Namespace') -> dict:
    """Build render options by inspecting renderer signature.

    Args:
        renderer_class: Renderer class
        args: CLI arguments

    Returns:
        Dict of options to pass to render method
    """
    import inspect

    if not hasattr(renderer_class, 'render_check'):
        return {}

    render_sig = inspect.signature(renderer_class.render_check)
    opts = {}

    # Map CLI args to render options
    for opt_name in ['only_failures', 'summary', 'expiring_within']:
        if opt_name in render_sig.parameters and hasattr(args, opt_name):
            value = getattr(args, opt_name)
            if value is not None:
                opts[opt_name] = value

    return opts


def _handle_check_mode(adapter, renderer_class: type[Any], args: 'Namespace') -> None:
    """Execute check mode and exit.

    Args:
        adapter: Initialized adapter with check() method
        renderer_class: Renderer for check results
        args: CLI arguments with check flags
    """
    import json

    # Build check kwargs and execute
    check_kwargs = _build_check_kwargs(adapter, args)
    result = adapter.check(**check_kwargs)

    # Render check results
    if hasattr(renderer_class, 'render_check'):
        render_opts = _build_render_opts(renderer_class, args)
        renderer_class.render_check(result, args.format, **render_opts)
    else:
        # Fallback to generic JSON rendering
        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            print(result)

    # Exit with appropriate code
    if isinstance(result, dict):
        exit_code = result.get('exit_code', 0)
    else:
        logger.warning("check() returned non-dict result; treating as pass (exit 0)")
        exit_code = 0
    sys.exit(exit_code)


def _handle_rendering(adapter, renderer_class: type[Any], scheme: str,
                      resource: str, element: Optional[str], args: 'Namespace') -> None:
    """Render element or structure based on adapter capabilities.

    Args:
        adapter: Initialized adapter
        renderer_class: Renderer class for output
        scheme: URI scheme
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # Get element or structure based on adapter capabilities
    # Adapters with render_element (env, python, help) support element-based access
    # Others (ast, json, stats) always use get_structure() unless element explicitly provided
    supports_elements = hasattr(renderer_class, 'render_element')

    # Adapters where resource is part of element namespace (not initialization path)
    # For these, `scheme://RESOURCE` means "get element RESOURCE"
    # For others, `scheme://RESOURCE` means "analyze path RESOURCE"
    ELEMENT_NAMESPACE_ADAPTERS = {'env', 'python', 'help'}

    resource_is_element = scheme in ELEMENT_NAMESPACE_ADAPTERS

    if supports_elements and (element or (resource and resource_is_element)):
        _render_element(adapter, renderer_class, element, resource, args)
    else:
        _render_structure(adapter, renderer_class, args, scheme=scheme, resource=resource)


def _render_element(adapter, renderer_class: type[Any], element: Optional[str],
                    resource: str, args: 'Namespace') -> None:
    """Render a specific element from adapter.

    Args:
        adapter: Adapter with get_element() method
        renderer_class: Renderer for element output
        element: Element name (or None to use resource)
        resource: Fallback element name if element is None
        args: CLI arguments
    """
    element_name = element if element else resource
    result = adapter.get_element(element_name)

    if result is None:
        print(f"Error: Element '{element_name}' not found", file=sys.stderr)
        # Try to show available elements if adapter provides them
        if hasattr(adapter, 'list_elements'):
            elements = adapter.list_elements()
            print(f"Available elements: {', '.join(elements)}", file=sys.stderr)
        sys.exit(1)

    renderer_class.render_element(result, args.format)


def _build_adapter_kwargs(adapter, args: 'Namespace', scheme: Optional[str] = None, resource: Optional[str] = None) -> dict:
    """Build kwargs for adapter.get_structure() by inspecting signature.

    Args:
        adapter: Adapter instance
        args: CLI arguments
        scheme: Optional URI scheme
        resource: Optional resource string

    Returns:
        Dict of kwargs to pass to get_structure()
    """
    import inspect

    if not hasattr(adapter, 'get_structure'):
        return {}

    sig = inspect.signature(adapter.get_structure)
    kwargs = {}

    # URI parameter - reconstruct full URI for adapters that need it
    if 'uri' in sig.parameters and scheme and resource is not None:
        kwargs['uri'] = f"{scheme}://{resource}"

    # Map CLI args to adapter params (only if param exists and value is not None)
    param_mapping = {
        'hotspots': 'hotspots',
        'code_only': 'code_only',
        'min_lines': 'min_lines',
        'max_lines': 'max_lines',
        'min_complexity': 'min_complexity',
        'max_complexity': 'max_complexity',
        'min_functions': 'min_functions',
        'dns_verified': 'dns_verified',
        'only_failures': 'only_failures',
        'summary': 'summary',
        'user': 'user',
        'check_live': 'check_live',
    }

    for arg_name, param_name in param_mapping.items():
        if param_name in sig.parameters:
            value = getattr(args, arg_name, None)
            if value is not None:
                kwargs[param_name] = value

    return kwargs


def _apply_field_selection(result: dict, args: 'Namespace') -> dict:
    """Apply field selection if --fields specified."""
    if hasattr(args, 'fields') and args.fields:
        from reveal.display.formatting import filter_fields
        fields = [f.strip() for f in args.fields.split(',')]
        return filter_fields(result, fields)
    return result


def _apply_budget_constraints(result: dict, args: 'Namespace', adapter=None) -> dict:
    """Apply budget constraints to result list fields."""
    if not isinstance(result, dict):
        return result

    # Adapter declares which field is budget-limitable; fall back to probing for
    # adapters that predate BUDGET_LIST_FIELD (transition period only).
    declared = getattr(adapter, 'BUDGET_LIST_FIELD', None) if adapter is not None else None
    if declared:
        list_field = declared if (declared in result and isinstance(result[declared], list)) else None
    else:
        list_field = None
        for field_name in ['items', 'results', 'checks', 'commits', 'files']:
            if field_name in result and isinstance(result[field_name], list):
                list_field = field_name
                break

    if not list_field:
        return result

    from reveal.utils.query import apply_budget_limits

    budget_result = apply_budget_limits(
        result[list_field],
        max_items=getattr(args, 'max_items', None),
        max_bytes=getattr(args, 'max_bytes', None),
        max_depth=getattr(args, 'max_depth', None),
        truncate_strings=getattr(args, 'max_snippet_chars', None)
    )

    # Update result with budget-limited items
    result[list_field] = budget_result['items']
    if budget_result['meta']['truncated']:
        # Merge budget metadata
        if 'meta' in result and isinstance(result['meta'], dict):
            result['meta']['budget'] = budget_result['meta']
        else:
            result['meta'] = budget_result['meta']

    return result


def _render_structure(adapter, renderer_class: type[Any], args: 'Namespace',
                      scheme: Optional[str] = None, resource: Optional[str] = None) -> None:
    """Render full structure from adapter.

    Args:
        adapter: Adapter with get_structure() method
        renderer_class: Renderer for structure output
        args: CLI arguments with optional filter parameters
        scheme: Optional URI scheme (for adapters that need full URI)
        resource: Optional resource string (for adapters that need full URI)
    """
    # Build adapter kwargs
    structure_kwargs = _build_adapter_kwargs(adapter, args, scheme, resource)

    # Get structure from adapter
    try:
        result = adapter.get_structure(**structure_kwargs)
    except Exception as e:
        error_msg = str(e)
        if '\n' in error_msg:
            print(f"Error: {error_msg}", file=sys.stderr)
        else:
            scheme_hint = f" ({scheme}://)" if scheme else ""
            print(f"Error{scheme_hint}: {error_msg}", file=sys.stderr)
        sys.exit(1)

    # Apply post-processing
    result = _apply_field_selection(result, args)
    result = _apply_budget_constraints(result, args, adapter)
    # Check class hierarchy (not instance attr) to avoid triggering Mock auto-attrs
    if any('post_process' in cls.__dict__ for cls in type(adapter).__mro__[:-1]):
        result = adapter.post_process(result, args)

    # Add available elements if adapter supports discovery
    if hasattr(adapter, 'get_available_elements'):
        available_elements = adapter.get_available_elements()
        if available_elements:
            result['available_elements'] = available_elements

    renderer_class.render_structure(result, args.format)


def handle_adapter(adapter_class: type, scheme: str, resource: str,
                   element: Optional[str], args: 'Namespace') -> None:
    """Handle adapter-specific logic for different URI schemes.

    All adapters now use the renderer-based system with generic handler.

    Args:
        adapter_class: The adapter class to instantiate
        scheme: URI scheme (env, ast, etc.)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # Get renderer for this adapter
    from ..adapters.base import get_renderer_class
    renderer_class = get_renderer_class(scheme)

    if not renderer_class:
        # This shouldn't happen if adapter is properly registered
        print(f"Error: No renderer registered for scheme '{scheme}'", file=sys.stderr)
        print("This is a bug - adapter is registered but renderer is not.", file=sys.stderr)
        sys.exit(1)

    # Use generic handler for all adapters
    generic_adapter_handler(adapter_class, renderer_class, scheme, resource, element, args)


def _parse_file_line_syntax(path_str: str) -> tuple[Path, Optional[str]]:
    """Parse file:line or file:line-line syntax.

    Args:
        path_str: Path string potentially with :line suffix

    Returns:
        Tuple of (Path, element_from_path)
    """
    path = Path(path_str)
    element_from_path = None

    # Support file:line and file:line-line syntax (e.g., app.py:50, app.py:50-60)
    if not path.exists() and ':' in path_str:
        match = re.match(r'^(.+?):(\d+(?:-\d+)?)$', path_str)
        if match:
            potential_path = Path(match.group(1))
            if potential_path.exists():
                path = potential_path
                element_from_path = f":{match.group(2)}"

    return path, element_from_path


def _validate_path_exists(path: Path, path_str: str) -> None:
    """Validate that path exists, providing helpful error messages."""
    if not path.exists():
        cwd = os.getcwd()
        if ':' in path_str and re.search(r':\d+', path_str):
            base_path = path_str.rsplit(':', 1)[0]
            print(f"Error: {path_str} not found", file=sys.stderr)
            print(f"Hint: If extracting lines, use: reveal {base_path} :{path_str.rsplit(':', 1)[1]}", file=sys.stderr)
        else:
            abs_suggestion = os.path.join(cwd, path_str)
            print(f"Error: {path_str} not found", file=sys.stderr)
            print(f"Hint: Running from {cwd}", file=sys.stderr)
            print(f"      Try: reveal {abs_suggestion}", file=sys.stderr)
        sys.exit(1)


def _stat_one_file(fpath: Path, ext_counts: dict) -> Optional[tuple]:
    """Stat a single file and update ext_counts. Returns (size, mtime) or None."""
    try:
        stat = fpath.stat()
    except OSError:
        return None
    ext_counts[fpath.suffix.lower().lstrip('.') or '(no ext)'] += 1
    return stat.st_size, stat.st_mtime


def _collect_dir_stats(path: Path) -> tuple:
    """Walk a directory and collect file count, size, mtime, extension counts.

    Returns:
        (ext_counts, total_files, total_size, newest_mtime, oldest_mtime)
    """
    import os
    from collections import defaultdict
    ext_counts: dict = defaultdict(int)
    total_files = 0
    total_size = 0
    newest_mtime = 0.0
    oldest_mtime = float('inf')
    for root, _dirs, files in os.walk(path):
        for fname in files:
            result = _stat_one_file(Path(root) / fname, ext_counts)
            if result is None:
                continue
            size, mtime = result
            total_files += 1
            total_size += size
            newest_mtime = max(newest_mtime, mtime)
            oldest_mtime = min(oldest_mtime, mtime)
    return ext_counts, total_files, total_size, newest_mtime, oldest_mtime


def _render_dir_meta_text(meta: dict) -> None:
    """Print directory metadata in human-readable text format."""
    print(f"Directory: {meta['name']}\n")
    print(f"Path:       {meta['path']}")
    print(f"Files:      {meta['total_files']:,}")
    print(f"Size:       {meta['size_human']}")
    if meta['modified']:
        print(f"Modified:   {meta['modified']}")
    if meta['oldest_file']:
        print(f"Oldest:     {meta['oldest_file']}")
    if meta['by_extension']:
        print(f"\nBy extension:")
        for ext, count in meta['by_extension'].items():
            print(f"  .{ext:<12} {count:>6,}")


def _show_directory_meta(path: Path, args: 'Namespace') -> None:
    """Show metadata summary for a directory.

    Args:
        path: Directory path
        args: Parsed arguments (uses args.format for JSON output)
    """
    import datetime
    from ..utils import safe_json_dumps, format_size

    ext_counts, total_files, total_size, newest_mtime, oldest_mtime = _collect_dir_stats(path)
    meta = {
        'path': str(path), 'name': path.name,
        'total_files': total_files, 'total_size': total_size,
        'size_human': format_size(total_size),
        'modified': datetime.datetime.fromtimestamp(newest_mtime).isoformat(timespec='seconds') if newest_mtime else None,
        'oldest_file': datetime.datetime.fromtimestamp(oldest_mtime).isoformat(timespec='seconds') if oldest_mtime != float('inf') else None,
        'by_extension': dict(sorted(ext_counts.items(), key=lambda x: -x[1])),
    }
    output_format = getattr(args, 'format', 'text')
    if output_format == 'json':
        print(safe_json_dumps(meta))
    else:
        _render_dir_meta_text(meta)


def _parse_ext_arg(ext_arg: Optional[str]) -> Optional[list]:
    """Parse --ext argument into a list of normalized extensions.

    Args:
        ext_arg: Raw --ext value (e.g., 'md', 'py,md', '.py,.md')

    Returns:
        List of lowercase extensions without dots, or None if not specified
    """
    if not ext_arg:
        return None
    return [e.strip().lower().lstrip('.') for e in ext_arg.split(',') if e.strip()]


def _build_ast_query_from_flags(path: Path, args: 'Namespace') -> str:
    """Build AST query URI from convenience flags."""
    query_params = []
    if getattr(args, 'search', None):
        query_params.append(f"name~={args.search}")
    if getattr(args, 'type', None):
        query_params.append(f"type={args.type}")
    if getattr(args, 'sort', None):
        sort_field = args.sort
        if getattr(args, 'desc', False) and not sort_field.startswith('-'):
            sort_field = f"-{sort_field}"
        query_params.append(f"sort={sort_field}")

    query_string = '&'.join(query_params)
    return f"ast://{path}?{query_string}"


_NGINX_ADAPTER_FLAGS = {
    'check_acl': '--check-acl',
    'validate_nginx_acme': '--validate-nginx-acme',
    'check_conflicts': '--check-conflicts',
    'cpanel_certs': '--cpanel-certs',
    'diagnose': '--diagnose',
}
_SSL_ADAPTER_FLAGS = {
    'expiring_within': '--expiring-within',
    'summary': '--summary',
    'validate_nginx': '--validate-nginx',
}
_NGINX_EXTENSIONS = {'.conf', '.ini', ''}  # '' = files with no extension (e.g. nginx, site.conf)
_MARKDOWN_EXTENSIONS = {'.md', '.markdown', '.rst', '.txt', ''}


def _guard_hotspots_flag(args: 'Namespace', path_str: str) -> None:
    if not getattr(args, 'hotspots', False):
        return
    print("❌ Error: --hotspots only works with stats:// adapter", file=sys.stderr)
    print(file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print(f"  reveal stats://{path_str}?hotspots=true    # URI param (preferred)", file=sys.stderr)
    print(f"  reveal stats://{path_str} --hotspots        # Flag (legacy)", file=sys.stderr)
    print(file=sys.stderr)
    print("Learn more: reveal help://stats", file=sys.stderr)
    sys.exit(1)


def _guard_nginx_flags(args: 'Namespace', path_str: str) -> None:
    """Exit with error if nginx-specific flags are used on non-nginx file extensions."""
    path_ext = Path(path_str).suffix.lower() if '.' in Path(path_str).name else ''
    if path_ext in _NGINX_EXTENSIONS:
        return
    for attr, flag in _NGINX_ADAPTER_FLAGS.items():
        if getattr(args, attr, False):
            print(f"❌ Error: {flag} only works with nginx config files", file=sys.stderr)
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print(f"  reveal nginx.conf {flag}                    # with a .conf file", file=sys.stderr)
            print(f"  reveal nginx://nginx.conf?{attr.replace('_', '-')}=true  # URI param", file=sys.stderr)
            print(file=sys.stderr)
            print("Learn more: reveal help://nginx", file=sys.stderr)
            sys.exit(1)


def _guard_ssl_flags(args: 'Namespace') -> None:
    """Exit with error if ssl:// adapter flags are used on plain file paths."""
    for attr, flag in _SSL_ADAPTER_FLAGS.items():
        if getattr(args, attr, False):
            print(f"❌ Error: {flag} only works with the ssl:// adapter", file=sys.stderr)
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print(f"  reveal ssl://example.com {flag}           # with a domain", file=sys.stderr)
            print(f"  reveal ssl://example.com?{attr.replace('_', '-')}=true  # URI param", file=sys.stderr)
            print(file=sys.stderr)
            print("Learn more: reveal help://ssl", file=sys.stderr)
            sys.exit(1)


def _guard_related_flags(args: 'Namespace', path_str: str) -> None:
    """Exit with error if --related/--related-all are used on non-markdown files."""
    if not (getattr(args, 'related', False) or getattr(args, 'related_all', False)):
        return
    md_ext = Path(path_str).suffix.lower() if '.' in Path(path_str).name else ''
    if md_ext in _MARKDOWN_EXTENSIONS:
        return
    flag = '--related-all' if getattr(args, 'related_all', False) else '--related'
    print(f"❌ Error: {flag} only works with markdown files", file=sys.stderr)
    print(file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print(f"  reveal docs/ --related          # on a markdown directory", file=sys.stderr)
    print(f"  reveal doc.md --related         # on a .md file", file=sys.stderr)
    print(file=sys.stderr)
    print("Learn more: reveal help://markdown", file=sys.stderr)
    sys.exit(1)


def _handle_directory_path(path: Path, args: 'Namespace') -> None:
    """Route a resolved directory path to directory-meta, file-list, or tree view."""
    from ..tree_view import show_directory_tree, show_file_list
    if getattr(args, 'meta', False):
        _show_directory_meta(path, args)
        return
    sort_by = getattr(args, 'sort', None)
    include_extensions = _parse_ext_arg(getattr(args, 'ext', None))
    if getattr(args, 'files', False):
        # --files defaults to newest-first; --asc flips it
        sort_desc = not getattr(args, 'asc', False)
        print(show_file_list(str(path),
                             respect_gitignore=args.respect_gitignore,
                             exclude_patterns=args.exclude,
                             sort_by=sort_by, sort_desc=sort_desc,
                             include_extensions=include_extensions))
    else:
        sort_desc = getattr(args, 'desc', False)
        print(show_directory_tree(str(path), depth=args.depth,
                                  max_entries=args.max_entries, fast=args.fast,
                                  respect_gitignore=args.respect_gitignore,
                                  exclude_patterns=args.exclude,
                                  dir_limit=getattr(args, 'dir_limit', 0),
                                  sort_by=sort_by, sort_desc=sort_desc,
                                  include_extensions=include_extensions))


def _handle_file_path(path: Path, element_from_path: Optional[str], args: 'Namespace') -> None:
    """Route a resolved file path — to ast query if convenience flags set, else normal handler."""
    if getattr(args, 'search', None) or getattr(args, 'sort', None) or getattr(args, 'type', None):
        handle_uri(_build_ast_query_from_flags(path, args), args.element, args)
        return

    element = element_from_path or args.element
    if not element and getattr(args, 'section', None):
        if path.suffix.lower() in ('.md', '.markdown'):
            element = args.section
        else:
            print("Error: --section only works with markdown files (.md, .markdown)", file=sys.stderr)
            print(f"For other files, use: reveal {path} \"element_name\"", file=sys.stderr)
            sys.exit(1)
    handle_file(str(path), element, args.meta, args.format, args)


def handle_file_or_directory(path_str: str, args: 'Namespace') -> None:
    """Handle regular file or directory path.

    Args:
        path_str: Path string to file or directory
        args: Parsed arguments
    """
    if getattr(args, 'check', False):
        print("hint: --check is deprecated; use `reveal check <path>` instead", file=sys.stderr)
        from ..cli.commands.check import run_check
        run_check(args)
        return

    _guard_hotspots_flag(args, path_str)
    _guard_nginx_flags(args, path_str)
    _guard_ssl_flags(args)
    _guard_related_flags(args, path_str)

    path, element_from_path = _parse_file_line_syntax(path_str)
    _validate_path_exists(path, path_str)

    if path.is_dir():
        _handle_directory_path(path, args)
    elif path.is_file():
        _handle_file_path(path, element_from_path, args)
    else:
        print(f"Error: {path_str} is neither file nor directory", file=sys.stderr)
        sys.exit(1)

