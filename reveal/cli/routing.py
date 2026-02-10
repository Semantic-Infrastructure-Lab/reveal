"""URI and file routing for reveal CLI.

This module handles dispatching to the correct handler based on:
- URI scheme (env://, ast://, help://, python://, json://, reveal://, etc.)
- File type (determined by extension)
- Directory handling

All URI adapters now use the renderer-based system (Phase 4 complete).
"""

import re
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


# ============================================================================
# File checking functions
# ============================================================================

from .file_checker import (
    handle_recursive_check,
)


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


def generic_adapter_handler(adapter_class: type, renderer_class: type,
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
    # Initialize adapter using multiple fallback strategies
    adapter = _try_initialize_adapter(adapter_class, scheme, resource, element, renderer_class)

    # Handle --check mode if requested
    if getattr(args, 'check', False) and hasattr(adapter, 'check'):
        _handle_check_mode(adapter, renderer_class, args)
        return  # check mode exits directly

    # Render element or structure based on adapter type
    _handle_rendering(adapter, renderer_class, scheme, resource, element, args)


def _try_no_args_init(adapter_class: type) -> tuple[any, Optional[Exception]]:
    """Try no-argument initialization (env, python adapters)."""
    try:
        return adapter_class(), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        return None, None
    except ImportError as e:
        return None, e


def _try_query_parsing_init(adapter_class: type, resource: str) -> tuple[any, Optional[Exception]]:
    """Try query-parsing initialization (ast, json with ?query)."""
    if '?' not in resource:
        return None, None

    try:
        path, query = resource.split('?', 1)
        path = path or '.'  # Default empty path to current directory
        return adapter_class(path, query), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        return None, None
    except ImportError as e:
        return None, e


def _try_keyword_args_init(adapter_class: type, resource: str) -> tuple[any, Optional[Exception]]:
    """Try keyword arguments initialization (markdown with base_path/query)."""
    try:
        if '?' in resource:
            path_part, query = resource.split('?', 1)
            path = path_part.rstrip('/') if path_part else '.'
        else:
            path = resource.rstrip('/') if resource else '.'
            query = None
        return adapter_class(base_path=path, query=query), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        return None, None
    except ImportError as e:
        return None, e


def _try_resource_arg_init(adapter_class: type, resource: str) -> tuple[any, Optional[Exception]]:
    """Try resource argument initialization (help, git, etc)."""
    if resource is None:
        return None, None

    try:
        if '?' not in resource:
            path = resource or '.'
            # Try with query=None for query-parsing adapters
            try:
                return adapter_class(path, None), None
            except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
                # Try simple resource argument
                return adapter_class(resource), None
            except ImportError as e:
                return None, e
        else:
            return adapter_class(resource), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError) as e:
        return None, e
    except ImportError as e:
        return None, e


def _try_full_uri_init(adapter_class: type, scheme: str, resource: str,
                       element: Optional[str]) -> tuple[any, Optional[Exception]]:
    """Try full URI initialization (mysql, sqlite)."""
    try:
        full_uri = f"{scheme}://{resource}"
        if element and '://' in full_uri:
            full_uri = f"{full_uri}/{element}"
        return adapter_class(full_uri), None
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError) as e:
        return None, e
    except ImportError as e:
        return None, e


def _try_initialize_adapter(adapter_class: type, scheme: str, resource: str,
                            element: Optional[str], renderer_class: type):
    """Try multiple initialization patterns to instantiate adapter.

    Different adapters have different conventions:
    - No-arg: env, python (take no resource in __init__)
    - Resource-arg: help, reveal (take resource string as first arg)
    - Query-parsing: ast, json (parse resource to extract path/query)
    - URI: mysql (expect full URI like mysql://host:port)

    Returns:
        Initialized adapter instance

    Raises:
        SystemExit: If initialization fails
    """
    # Try initialization patterns in order
    # If resource is provided, try using it before trying no-args
    # This ensures reveal://config passes "config" to RevealAdapter(component="config")
    if resource:
        init_attempts = [
            lambda: _try_query_parsing_init(adapter_class, resource),
            lambda: _try_resource_arg_init(adapter_class, resource),
            lambda: _try_keyword_args_init(adapter_class, resource),
            lambda: _try_no_args_init(adapter_class),
            lambda: _try_full_uri_init(adapter_class, scheme, resource, element)
        ]
    else:
        init_attempts = [
            lambda: _try_no_args_init(adapter_class),
            lambda: _try_query_parsing_init(adapter_class, resource),
            lambda: _try_keyword_args_init(adapter_class, resource),
            lambda: _try_resource_arg_init(adapter_class, resource),
            lambda: _try_full_uri_init(adapter_class, scheme, resource, element)
        ]

    adapter = None
    init_error = None

    for attempt in init_attempts:
        adapter, error = attempt()
        if adapter is not None:
            return adapter
        if error is not None:
            init_error = error  # Keep last error

    # All attempts failed
    if isinstance(init_error, ImportError):
        renderer_class.render_error(init_error)
    else:
        print(f"Error initializing {scheme}:// adapter: {init_error}", file=sys.stderr)
    sys.exit(1)


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

    return kwargs


def _build_render_opts(renderer_class: type, args: 'Namespace') -> dict:
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


def _handle_check_mode(adapter, renderer_class: type, args: 'Namespace') -> None:
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
    exit_code = result.get('exit_code', 0) if isinstance(result, dict) else 0
    sys.exit(exit_code)


def _handle_rendering(adapter, renderer_class: type, scheme: str,
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


def _render_element(adapter, renderer_class: type, element: Optional[str],
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


def _build_adapter_kwargs(adapter, args: 'Namespace', scheme: str = None, resource: str = None) -> dict:
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
        'min_functions': 'min_functions'
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


def _apply_budget_constraints(result: dict, args: 'Namespace') -> dict:
    """Apply budget constraints to result list fields."""
    if not (hasattr(result, 'get') and isinstance(result, dict)):
        return result

    # Find list field to apply budget limits to
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


def _render_structure(adapter, renderer_class: type, args: 'Namespace',
                      scheme: str = None, resource: str = None) -> None:
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
    result = _apply_budget_constraints(result, args)

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
        print(f"This is a bug - adapter is registered but renderer is not.", file=sys.stderr)
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
        if ':' in path_str and re.search(r':\d+', path_str):
            base_path = path_str.rsplit(':', 1)[0]
            print(f"Error: {path_str} not found", file=sys.stderr)
            print(f"Hint: If extracting lines, use: reveal {base_path} :{path_str.rsplit(':', 1)[1]}", file=sys.stderr)
        else:
            print(f"Error: {path_str} not found", file=sys.stderr)
        sys.exit(1)


def _build_ast_query_from_flags(path: Path, args: 'Namespace') -> str:
    """Build AST query URI from convenience flags."""
    query_params = []
    if getattr(args, 'search', None):
        query_params.append(f"name~={args.search}")
    if getattr(args, 'type', None):
        query_params.append(f"type={args.type}")
    if getattr(args, 'sort', None):
        query_params.append(f"sort={args.sort}")

    query_string = '&'.join(query_params)
    return f"ast://{path}?{query_string}"


def handle_file_or_directory(path_str: str, args: 'Namespace') -> None:
    """Handle regular file or directory path.

    Args:
        path_str: Path string to file or directory
        args: Parsed arguments
    """
    from ..tree_view import show_directory_tree

    # Validate adapter-specific flags
    if getattr(args, 'hotspots', False):
        print("❌ Error: --hotspots only works with stats:// adapter", file=sys.stderr)
        print(file=sys.stderr)
        print("Examples:", file=sys.stderr)
        print(f"  reveal stats://{path_str}?hotspots=true    # URI param (preferred)", file=sys.stderr)
        print(f"  reveal stats://{path_str} --hotspots        # Flag (legacy)", file=sys.stderr)
        print(file=sys.stderr)
        print("Learn more: reveal help://stats", file=sys.stderr)
        sys.exit(1)

    # Parse path and check existence
    path, element_from_path = _parse_file_line_syntax(path_str)
    _validate_path_exists(path, path_str)

    if path.is_dir():
        # Check if recursive mode is enabled with --check
        if getattr(args, 'recursive', False) and getattr(args, 'check', False):
            handle_recursive_check(path, args)
        else:
            output = show_directory_tree(str(path), depth=args.depth,
                                         max_entries=args.max_entries, fast=args.fast,
                                         respect_gitignore=args.respect_gitignore,
                                         exclude_patterns=args.exclude,
                                         dir_limit=getattr(args, 'dir_limit', 0))
            print(output)
    elif path.is_file():
        # Check if convenience flags are set (--search, --sort, --type)
        has_convenience_flags = (
            getattr(args, 'search', None) or
            getattr(args, 'sort', None) or
            getattr(args, 'type', None)
        )

        if has_convenience_flags:
            # Convert to AST query for ergonomic within-file filtering
            ast_uri = _build_ast_query_from_flags(path, args)
            handle_uri(ast_uri, args.element, args)
        else:
            # Normal file handling
            element = element_from_path or args.element
            if not element and getattr(args, 'section', None):
                if path.suffix.lower() in ('.md', '.markdown'):
                    element = args.section
                else:
                    print(f"Error: --section only works with markdown files (.md, .markdown)", file=sys.stderr)
                    print(f"For other files, use: reveal {path_str} \"element_name\"", file=sys.stderr)
                    sys.exit(1)
            handle_file(str(path), element, args.meta, args.format, args)
    else:
        print(f"Error: {path_str} is neither file nor directory", file=sys.stderr)
        sys.exit(1)


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
    from ..registry import get_analyzer, get_all_analyzers
    from ..errors import AnalyzerNotFoundError

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


def _handle_domain_extraction(analyzer) -> None:
    """Handle domain extraction from analyzer.

    Args:
        analyzer: Analyzer instance

    Exits:
        With error code 1 if domain extraction not supported
    """
    if hasattr(analyzer, 'extract_ssl_domains'):
        domains = analyzer.extract_ssl_domains()
        for domain in domains:
            print(f"ssl://{domain}")
    else:
        print(f"Error: --extract domains not supported for {type(analyzer).__name__}", file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)


def _handle_extract_option(analyzer, extract_type: str) -> None:
    """Handle --extract option with validation.

    Args:
        analyzer: Analyzer instance
        extract_type: Type to extract (e.g., 'domains')

    Exits:
        With error code 1 if extract type unknown
    """
    if extract_type == 'domains':
        _handle_domain_extraction(analyzer)
    else:
        print(f"Error: Unknown extract type '{extract_type}'", file=sys.stderr)
        print("Supported types: domains (for nginx configs)", file=sys.stderr)
        sys.exit(1)


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
    from ..display import show_structure, show_metadata, extract_element
    from ..config import RevealConfig

    # Get analyzer
    allow_fallback = not getattr(args, 'no_fallback', False) if args else True
    analyzer = _get_analyzer_or_exit(path, allow_fallback)

    # Load config with CLI overrides
    cli_overrides = _build_file_cli_overrides(args)
    config = RevealConfig.get(
        start_path=Path(path).parent if Path(path).is_file() else Path(path),
        cli_overrides=cli_overrides if cli_overrides else None
    )

    # Route to appropriate handler based on flags
    if show_meta:
        show_metadata(analyzer, output_format, config=config)
        return

    if args and getattr(args, 'extract', None):
        _handle_extract_option(analyzer, args.extract.lower())
        return

    if args and getattr(args, 'validate_schema', None):
        from ..main import run_schema_validation
        run_schema_validation(analyzer, path, args.validate_schema, output_format, args)
        return

    if args and getattr(args, 'check', False):
        from ..main import run_pattern_detection
        run_pattern_detection(analyzer, path, output_format, args, config=config)
        return

    if element:
        extract_element(analyzer, element, output_format, config=config)
        return

    show_structure(analyzer, output_format, args, config=config)


# Backward compatibility aliases
_handle_adapter = handle_adapter
_handle_file_or_directory = handle_file_or_directory
