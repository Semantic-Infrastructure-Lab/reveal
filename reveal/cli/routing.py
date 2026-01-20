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
    load_gitignore_patterns,
    should_skip_file,
    collect_files_to_check,
    check_and_report_file,
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


def _try_initialize_adapter(adapter_class: type, scheme: str, resource: str,
                            element: Optional[str], renderer_class: type):
    """Try multiple initialization patterns to instantiate adapter.

    Different adapters have different conventions:
    - No-arg: env, python (take no resource in __init__)
    - Resource-arg: help (take resource string)
    - Query-parsing: ast, json (parse resource to extract path/query)
    - URI: mysql (expect full URI like mysql://host:port)

    Returns:
        Initialized adapter instance

    Raises:
        SystemExit: If initialization fails
    """
    adapter = None
    init_error = None

    # Try 1: No arguments (env, python)
    try:
        adapter = adapter_class()
    except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
        pass  # Not a no-arg adapter
    except ImportError as e:
        init_error = e  # Capture import errors for special handling

    # Try 2: Resource with query parsing (ast, json)
    if adapter is None and '?' in resource:
        try:
            path, query = resource.split('?', 1)
            # Default empty path to current directory for ast-like adapters
            if not path:
                path = '.'
            adapter = adapter_class(path, query)
        except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
            pass  # Not a query-parsing adapter
        except ImportError as e:
            init_error = e

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
        except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
            pass  # Not a keyword-arg adapter
        except ImportError as e:
            init_error = e

    # Try 4: Resource argument (help, ast without query, json without query)
    # Handle empty resource from bare URIs like "git://"
    if adapter is None and resource is not None:
        try:
            # For ast/json, if no query, just pass path
            if '?' not in resource:
                path = resource if resource else '.'
                try:
                    # Try with query=None for query-parsing adapters
                    adapter = adapter_class(path, None)
                except (TypeError, ValueError, FileNotFoundError, IsADirectoryError):
                    # Try simple resource argument
                    adapter = adapter_class(resource)
                except ImportError as e:
                    init_error = e
            else:
                adapter = adapter_class(resource)
        except (TypeError, ValueError, FileNotFoundError, IsADirectoryError) as e:
            init_error = e
        except ImportError as e:
            init_error = e

    # Try 5: Full URI (mysql, sqlite with element)
    if adapter is None:
        try:
            # Construct full URI with element if provided (for sqlite://path/table pattern)
            full_uri = f"{scheme}://{resource}"
            if element and '://' in full_uri:  # Only append element for URI-based adapters
                full_uri = f"{full_uri}/{element}"
            adapter = adapter_class(full_uri)
        except (TypeError, ValueError, FileNotFoundError, IsADirectoryError) as e:
            init_error = e
        except ImportError as e:
            init_error = e

    # Check if initialization failed
    if adapter is None:
        if isinstance(init_error, ImportError):
            # Render user-friendly error for missing dependencies
            renderer_class.render_error(init_error)
        else:
            print(f"Error initializing {scheme}:// adapter: {init_error}", file=sys.stderr)
        sys.exit(1)

    return adapter


def _handle_check_mode(adapter, renderer_class: type, args: 'Namespace') -> None:
    """Execute check mode and exit.

    Args:
        adapter: Initialized adapter with check() method
        renderer_class: Renderer for check results
        args: CLI arguments with check flags
    """
    import json
    import inspect

    # Pass select/ignore args if adapter's check() method supports them
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
    import inspect

    # Structure-based adapters: always use get_structure()
    # Pass adapter-specific parameters if supported (similar to check() handling)
    structure_kwargs = {}

    # For stats adapter: pass hotspots, min_lines, etc. if get_structure() supports them
    if hasattr(adapter, 'get_structure'):
        sig = inspect.signature(adapter.get_structure)

        # URI parameter - reconstruct full URI for adapters that need it (e.g., imports)
        if 'uri' in sig.parameters and scheme and resource is not None:
            structure_kwargs['uri'] = f"{scheme}://{resource}"

        # Hotspots parameter
        if 'hotspots' in sig.parameters and hasattr(args, 'hotspots'):
            structure_kwargs['hotspots'] = args.hotspots

        # Code-only parameter
        if 'code_only' in sig.parameters and hasattr(args, 'code_only'):
            structure_kwargs['code_only'] = args.code_only

        # Filter parameters for stats adapter (only pass if not None)
        if 'min_lines' in sig.parameters:
            min_lines = getattr(args, 'min_lines', None)
            if min_lines is not None:
                structure_kwargs['min_lines'] = min_lines

        if 'max_lines' in sig.parameters:
            max_lines = getattr(args, 'max_lines', None)
            if max_lines is not None:
                structure_kwargs['max_lines'] = max_lines

        if 'min_complexity' in sig.parameters:
            min_complexity = getattr(args, 'min_complexity', None)
            if min_complexity is not None:
                structure_kwargs['min_complexity'] = min_complexity

        if 'max_complexity' in sig.parameters:
            max_complexity = getattr(args, 'max_complexity', None)
            if max_complexity is not None:
                structure_kwargs['max_complexity'] = max_complexity

        if 'min_functions' in sig.parameters:
            min_functions = getattr(args, 'min_functions', None)
            if min_functions is not None:
                structure_kwargs['min_functions'] = min_functions

    try:
        result = adapter.get_structure(**structure_kwargs)
    except Exception as e:
        # Handle adapter errors cleanly (e.g., MySQL connection failures)
        error_msg = str(e)
        # If error message already has structure (multi-line), use it as-is
        if '\n' in error_msg:
            print(f"Error: {error_msg}", file=sys.stderr)
        else:
            scheme_hint = f" ({scheme}://)" if scheme else ""
            print(f"Error{scheme_hint}: {error_msg}", file=sys.stderr)
        sys.exit(1)

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
    element_from_path = None

    # Support file:line and file:line-line syntax (e.g., app.py:50, app.py:50-60)
    # This matches common editor/grep output format
    if not path.exists() and ':' in path_str:
        match = re.match(r'^(.+?):(\d+(?:-\d+)?)$', path_str)
        if match:
            potential_path = Path(match.group(1))
            if potential_path.exists():
                path = potential_path
                path_str = str(potential_path)
                element_from_path = f":{match.group(2)}"  # Preserve line extraction format

    if not path.exists():
        # Provide helpful error for line extraction syntax
        if ':' in path_str and re.search(r':\d+', path_str):
            base_path = path_str.rsplit(':', 1)[0]
            print(f"Error: {path_str} not found", file=sys.stderr)
            print(f"Hint: If extracting lines, use: reveal {base_path} :{path_str.rsplit(':', 1)[1]}", file=sys.stderr)
        else:
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
                                         exclude_patterns=args.exclude,
                                         dir_limit=getattr(args, 'dir_limit', 0))
            print(output)
    elif path.is_file():
        # --section is an alias for element extraction on markdown files
        # element_from_path takes priority (from file:line syntax)
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
