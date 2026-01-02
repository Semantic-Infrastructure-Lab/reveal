"""Handler for json:// URIs."""

import sys
from typing import Optional
from argparse import Namespace


def handle_json(adapter_class: type, resource: str, element: Optional[str],
                args: Namespace) -> None:
    """Handle json:// URIs."""
    from ...rendering import render_json_result

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for json:// URIs", file=sys.stderr)

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
