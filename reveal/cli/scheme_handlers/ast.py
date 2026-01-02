"""Handler for ast:// URIs."""

import sys
from typing import Optional
from argparse import Namespace


def handle_ast(adapter_class: type, resource: str, element: Optional[str],
               args: Namespace) -> None:
    """Handle ast:// URIs."""
    from ...rendering import render_ast_structure

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for ast:// URIs", file=sys.stderr)

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
