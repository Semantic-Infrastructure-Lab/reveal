"""URI and file routing for reveal CLI.

This module handles dispatching to the correct handler based on:
- URI scheme (env://, ast://, help://, python://, json://, reveal://)
- File type (determined by extension)
- Directory handling
"""

import sys
from pathlib import Path
from typing import Optional, Callable, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


# ============================================================================
# Scheme-specific handlers (extracted to cli/scheme_handlers/)
# ============================================================================

from .scheme_handlers import (
    handle_env,
    handle_ast,
    handle_help,
    handle_python,
    handle_json,
    handle_reveal,
    handle_stats,
    handle_mysql,
    handle_sqlite,
    handle_imports,
    handle_diff,
    handle_markdown,
)

from .file_checker import (
    load_gitignore_patterns,
    should_skip_file,
    collect_files_to_check,
    check_and_report_file,
    handle_recursive_check,
)


# Legacy function names for backwards compatibility (to be removed later)
_handle_env = handle_env
_handle_ast = handle_ast
_handle_help = handle_help
_handle_python = handle_python
_handle_json = handle_json
_handle_reveal = handle_reveal
_handle_stats = handle_stats
_handle_mysql = handle_mysql
_handle_sqlite = handle_sqlite
_handle_imports = handle_imports
_handle_diff = handle_diff
_handle_markdown = handle_markdown

# File checking functions (extracted to cli/file_checker.py)
_load_gitignore_patterns = load_gitignore_patterns
_should_skip_file = should_skip_file
_collect_files_to_check = collect_files_to_check
_check_and_report_file = check_and_report_file

# Re-export for tests (from scheme_handlers/reveal.py)
from .scheme_handlers.reveal import _format_check_detections  # noqa: E402


# Dispatch table: scheme -> handler function
# To add a new scheme: create a _handle_<scheme> function and register here
# NOTE: Schemes migrated to renderer-based system don't need entries here
SCHEME_HANDLERS: Dict[str, Callable] = {
    # Simple adapters migrated to renderer-based system (Phase 3.1):
    # 'ast': _handle_ast,        # Migrated to AstRenderer
    # 'env': _handle_env,        # Migrated to EnvRenderer
    # 'json': _handle_json,      # Migrated to JsonRenderer
    # 'python': _handle_python,  # Migrated to PythonRenderer
    # 'help': _handle_help,      # Migrated to HelpRenderer
    # 'mysql': _handle_mysql,    # Migrated to MySQLRenderer (Phase 2)

    # Medium adapters migrated (Phase 3.2):
    # 'markdown': _handle_markdown,  # Migrated to MarkdownRenderer
    # 'stats': _handle_stats,        # Migrated to StatsRenderer

    # Complex adapters migrated (Phase 3.3):
    # 'sqlite': _handle_sqlite,      # Migrated to SqliteRenderer

    # Remaining adapters (to be migrated):
    'reveal': _handle_reveal,  # Special handling for element extraction
    'imports': _handle_imports,
    'diff': _handle_diff,
}


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
    # Import adapters to trigger registration
    from ..adapters import env, ast, help, python, json_adapter, reveal, mysql, sqlite, imports, diff, markdown  # noqa: F401, E402

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
    import json

    # Try to instantiate adapter with different initialization patterns
    # Different adapters have different conventions:
    # - No-arg: env, python (take no resource in __init__)
    # - Resource-arg: help (take resource string)
    # - Query-parsing: ast, json (parse resource to extract path/query)
    # - URI: mysql (expect full URI like mysql://host:port)
    adapter = None
    init_error = None

    # Try 1: No arguments (env, python)
    try:
        adapter = adapter_class()
    except TypeError:
        pass  # Not a no-arg adapter

    # Try 2: Resource with query parsing (ast, json)
    if adapter is None and '?' in resource:
        try:
            path, query = resource.split('?', 1)
            # Default empty path to current directory for ast-like adapters
            if not path:
                path = '.'
            adapter = adapter_class(path, query)
        except (TypeError, ValueError):
            pass  # Not a query-parsing adapter

    # Try 3: Keyword args (markdown with base_path/query)
    if adapter is None:
        try:
            if '?' in resource:
                path_part, query = resource.split('?', 1)
                path = path_part.rstrip('/') if path_part else '.'
            else:
                path = resource.rstrip('/') if resource else '.'
                query = None
            adapter = adapter_class(base_path=path, query=query)
        except TypeError:
            pass  # Not a keyword-arg adapter

    # Try 4: Resource argument (help, ast without query, json without query)
    if adapter is None and resource:
        try:
            # For ast/json, if no query, just pass path
            if '?' not in resource:
                path = resource if resource else '.'
                try:
                    # Try with query=None for query-parsing adapters
                    adapter = adapter_class(path, None)
                except TypeError:
                    # Try simple resource argument
                    adapter = adapter_class(resource)
            else:
                adapter = adapter_class(resource)
        except (TypeError, ValueError) as e:
            init_error = e

    # Try 5: Full URI (mysql, sqlite with element)
    if adapter is None:
        try:
            # Construct full URI with element if provided (for sqlite://path/table pattern)
            full_uri = f"{scheme}://{resource}"
            if element and '://' in full_uri:  # Only append element for URI-based adapters
                full_uri = f"{full_uri}/{element}"
            adapter = adapter_class(full_uri)
        except (TypeError, ValueError) as e:
            init_error = e

    # Check if initialization failed
    if adapter is None:
        if isinstance(init_error, ImportError):
            # Render user-friendly error for missing dependencies
            renderer_class.render_error(init_error)
        else:
            print(f"Error initializing {scheme}:// adapter: {init_error}", file=sys.stderr)
        sys.exit(1)

    # Handle --check flag if adapter supports it
    if getattr(args, 'check', False) and hasattr(adapter, 'check'):
        # Pass select/ignore args if adapter's check() method supports them
        import inspect
        sig = inspect.signature(adapter.check)
        check_kwargs = {}

        if 'select' in sig.parameters and hasattr(args, 'select') and args.select:
            check_kwargs['select'] = args.select.split(',') if isinstance(args.select, str) else args.select
        if 'ignore' in sig.parameters and hasattr(args, 'ignore') and args.ignore:
            check_kwargs['ignore'] = args.ignore.split(',') if isinstance(args.ignore, str) else args.ignore

        result = adapter.check(**check_kwargs)

        # Render check results
        if hasattr(renderer_class, 'render_check'):
            renderer_class.render_check(result, args.format)
        else:
            # Fallback to generic JSON rendering
            if args.format == 'json':
                print(json.dumps(result, indent=2))
            else:
                print(result)

        # Exit with appropriate code if provided
        exit_code = result.get('exit_code', 0) if isinstance(result, dict) else 0
        sys.exit(exit_code)

    # Get element or structure based on adapter capabilities
    # Adapters with render_element (env, python, help) support element-based access
    # Others (ast, json) always use get_structure()
    supports_elements = hasattr(renderer_class, 'render_element')

    if supports_elements and (element or resource):
        # Element-based adapters: check element or resource
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
    else:
        # Structure-based adapters: always use get_structure()
        result = adapter.get_structure()
        renderer_class.render_structure(result, args.format)


def handle_adapter(adapter_class: type, scheme: str, resource: str,
                   element: Optional[str], args: 'Namespace') -> None:
    """Handle adapter-specific logic for different URI schemes.

    Uses dispatch table for clean, extensible routing. Falls back to generic
    handler if adapter has a registered renderer.

    Args:
        adapter_class: The adapter class to instantiate
        scheme: URI scheme (env, ast, etc.)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # Try old-style scheme handler first (backward compatibility)
    handler = SCHEME_HANDLERS.get(scheme)
    if handler:
        handler(adapter_class, resource, element, args)
        return

    # Try new-style renderer-based handler
    from ..adapters.base import get_renderer_class
    renderer_class = get_renderer_class(scheme)
    if renderer_class:
        generic_adapter_handler(adapter_class, renderer_class, scheme, resource, element, args)
        return

    # No handler found (shouldn't happen if registry is in sync)
    print(f"Error: No handler for scheme '{scheme}'", file=sys.stderr)
    sys.exit(1)


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

    path = Path(path_str)
    if not path.exists():
        print(f"Error: {path_str} not found", file=sys.stderr)
        sys.exit(1)

    if path.is_dir():
        # Check if recursive mode is enabled with --check
        if getattr(args, 'recursive', False) and getattr(args, 'check', False):
            handle_recursive_check(path, args)
        else:
            output = show_directory_tree(str(path), depth=args.depth,
                                         max_entries=args.max_entries, fast=args.fast,
                                         respect_gitignore=args.respect_gitignore,
                                         exclude_patterns=args.exclude)
            print(output)
    elif path.is_file():
        handle_file(str(path), args.element, args.meta, args.format, args)
    else:
        print(f"Error: {path_str} is neither file nor directory", file=sys.stderr)
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
    from ..registry import get_analyzer
    from ..display import show_structure, show_metadata, extract_element
    from ..config import RevealConfig

    allow_fallback = not getattr(args, 'no_fallback', False) if args else True

    analyzer_class = get_analyzer(path, allow_fallback=allow_fallback)
    if not analyzer_class:
        ext = Path(path).suffix or '(no extension)'
        print(f"Error: No analyzer found for {path} ({ext})", file=sys.stderr)
        print(f"\nError: File type '{ext}' is not supported yet", file=sys.stderr)
        print("Run 'reveal --list-supported' to see all supported file types", file=sys.stderr)
        print("Visit https://github.com/Semantic-Infrastructure-Lab/reveal to request new file types", file=sys.stderr)
        sys.exit(1)

    analyzer = analyzer_class(path)

    # Build CLI overrides for config (including --no-breadcrumbs)
    cli_overrides = {}
    if args and getattr(args, 'no_breadcrumbs', False):
        cli_overrides['display'] = {'breadcrumbs': False}

    # Load config with CLI overrides
    config = RevealConfig.get(
        start_path=Path(path).parent if Path(path).is_file() else Path(path),
        cli_overrides=cli_overrides if cli_overrides else None
    )

    if show_meta:
        show_metadata(analyzer, output_format, config=config)
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
