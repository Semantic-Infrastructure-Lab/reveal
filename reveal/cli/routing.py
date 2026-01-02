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
    handle_imports,
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
_handle_imports = handle_imports

# File checking functions (extracted to cli/file_checker.py)
_load_gitignore_patterns = load_gitignore_patterns
_should_skip_file = should_skip_file
_collect_files_to_check = collect_files_to_check
_check_and_report_file = check_and_report_file

# Re-export for tests (from scheme_handlers/reveal.py)
from .scheme_handlers.reveal import _format_check_detections  # noqa: E402


# Dispatch table: scheme -> handler function
# To add a new scheme: create a _handle_<scheme> function and register here
SCHEME_HANDLERS: Dict[str, Callable] = {
    'env': _handle_env,
    'ast': _handle_ast,
    'mysql': _handle_mysql,
    'help': _handle_help,
    'python': _handle_python,
    'json': _handle_json,
    'reveal': _handle_reveal,
    'stats': _handle_stats,
    'imports': _handle_imports,
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
    from ..adapters import env, ast, help, python, json_adapter, reveal, mysql, imports  # noqa: F401, E402

    adapter_class = get_adapter_class(scheme)
    if not adapter_class:
        print(f"Error: Unsupported URI scheme: {scheme}://", file=sys.stderr)
        schemes = ', '.join(f"{s}://" for s in list_supported_schemes())
        print(f"Supported schemes: {schemes}", file=sys.stderr)
        sys.exit(1)

    # Dispatch to scheme-specific handler
    handle_adapter(adapter_class, scheme, resource, element, args)


def handle_adapter(adapter_class: type, scheme: str, resource: str,
                   element: Optional[str], args: 'Namespace') -> None:
    """Handle adapter-specific logic for different URI schemes.

    Uses dispatch table for clean, extensible routing.

    Args:
        adapter_class: The adapter class to instantiate
        scheme: URI scheme (env, ast, etc.)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    handler = SCHEME_HANDLERS.get(scheme)
    if handler:
        handler(adapter_class, resource, element, args)
    else:
        # Fallback for unknown schemes (shouldn't happen if registry is in sync)
        print(f"Error: No handler for scheme '{scheme}'", file=sys.stderr)
        sys.exit(1)


def handle_file_or_directory(path_str: str, args: 'Namespace') -> None:
    """Handle regular file or directory path.

    Args:
        path_str: Path string to file or directory
        args: Parsed arguments
    """
    from ..tree_view import show_directory_tree

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
                                         max_entries=args.max_entries, fast=args.fast)
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
    from ..base import get_analyzer
    from ..display import show_structure, show_metadata, extract_element

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

    if show_meta:
        show_metadata(analyzer, output_format)
        return

    if args and getattr(args, 'check', False):
        from ..main import run_pattern_detection
        run_pattern_detection(analyzer, path, output_format, args)
        return

    if element:
        extract_element(analyzer, element, output_format)
        return

    show_structure(analyzer, output_format, args)


# Backward compatibility aliases
_handle_adapter = handle_adapter
_handle_file_or_directory = handle_file_or_directory
