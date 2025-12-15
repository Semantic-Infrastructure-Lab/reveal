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
# Scheme-specific handlers
# ============================================================================

def _handle_env(adapter_class: type, resource: str, element: Optional[str],
                args: 'Namespace') -> None:
    """Handle env:// URIs."""
    from ..rendering import render_env_structure, render_env_variable

    adapter = adapter_class()

    if element or resource:
        var_name = element if element else resource
        result = adapter.get_element(var_name, show_secrets=False)

        if result is None:
            print(f"Error: Environment variable '{var_name}' not found", file=sys.stderr)
            sys.exit(1)

        render_env_variable(result, args.format)
    else:
        result = adapter.get_structure(show_secrets=False)
        render_env_structure(result, args.format)


def _handle_ast(adapter_class: type, resource: str, element: Optional[str],
                args: 'Namespace') -> None:
    """Handle ast:// URIs."""
    from ..rendering import render_ast_structure

    # Parse path and query from resource
    if '?' in resource:
        path, query = resource.split('?', 1)
    else:
        path = resource
        query = None

    # Default to current directory if no path
    if not path:
        path = '.'

    adapter = adapter_class(path, query)
    result = adapter.get_structure()
    render_ast_structure(result, args.format)


def _handle_help(adapter_class: type, resource: str, element: Optional[str],
                 args: 'Namespace') -> None:
    """Handle help:// URIs."""
    from ..rendering import render_help

    adapter = adapter_class(resource)

    if element or resource:
        topic = element if element else resource
        result = adapter.get_element(topic)

        if result is None:
            print(f"Error: Help topic '{topic}' not found", file=sys.stderr)
            available = adapter.get_structure()
            print(f"\nAvailable topics: {', '.join(available['available_topics'])}", file=sys.stderr)
            sys.exit(1)

        render_help(result, args.format)
    else:
        result = adapter.get_structure()
        render_help(result, args.format, list_mode=True)


def _handle_python(adapter_class: type, resource: str, element: Optional[str],
                   args: 'Namespace') -> None:
    """Handle python:// URIs."""
    from ..rendering import render_python_structure, render_python_element

    adapter = adapter_class()

    if element or resource:
        element_name = element if element else resource
        result = adapter.get_element(element_name)

        if result is None:
            print(f"Error: Python element '{element_name}' not found", file=sys.stderr)
            print("\nAvailable elements: version, env, venv, packages, imports, debug/bytecode", file=sys.stderr)
            sys.exit(1)

        render_python_element(result, args.format)
    else:
        result = adapter.get_structure()
        render_python_structure(result, args.format)


def _handle_json(adapter_class: type, resource: str, element: Optional[str],
                 args: 'Namespace') -> None:
    """Handle json:// URIs."""
    from ..rendering import render_json_result

    # Parse path and query from resource
    if '?' in resource:
        path, query = resource.split('?', 1)
    else:
        path = resource
        query = None

    try:
        adapter = adapter_class(path, query)
        result = adapter.get_structure()
        render_json_result(result, args.format)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _handle_reveal(adapter_class: type, resource: str, element: Optional[str],
                   args: 'Namespace') -> None:
    """Handle reveal:// URIs (self-inspection)."""
    from ..rendering import render_reveal_structure

    # Handle --check: run V-series validation rules
    if getattr(args, 'check', False):
        from ..rules import RuleRegistry
        from ..main import safe_json_dumps

        uri = f"reveal://{resource}" if resource else "reveal://"
        select = args.select.split(',') if args.select else None
        ignore = args.ignore.split(',') if args.ignore else None

        # V-series rules don't need structure/content - they inspect reveal source directly
        detections = RuleRegistry.check_file(uri, None, "", select=select, ignore=ignore)

        if args.format == 'json':
            result = {
                'file': uri,
                'detections': [d.to_dict() for d in detections],
                'total': len(detections)
            }
            print(safe_json_dumps(result))
        elif args.format == 'grep':
            for d in detections:
                print(f"{d.file_path}:{d.line}:{d.column}:{d.rule_code}:{d.message}")
        else:
            if not detections:
                print(f"{uri}: ✅ No issues found")
            else:
                print(f"{uri}: Found {len(detections)} issues\n")
                for d in sorted(detections, key=lambda x: (x.line, x.column)):
                    print(d)
                    print()
        return

    adapter = adapter_class(resource if resource else None)
    result = adapter.get_structure()
    render_reveal_structure(result, args.format)


# Dispatch table: scheme -> handler function
# To add a new scheme: create a _handle_<scheme> function and register here
SCHEME_HANDLERS: Dict[str, Callable] = {
    'env': _handle_env,
    'ast': _handle_ast,
    'help': _handle_help,
    'python': _handle_python,
    'json': _handle_json,
    'reveal': _handle_reveal,
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
    from ..adapters import env, ast, help, python, json_adapter, reveal  # noqa: F401 - Trigger registration

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
