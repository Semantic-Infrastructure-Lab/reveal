"""Handler for help:// URIs."""

import sys
from typing import Optional
from argparse import Namespace


def handle_help(adapter_class: type, resource: str, element: Optional[str],
                args: Namespace) -> None:
    """Handle help:// URIs."""
    from ...rendering import render_help

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for help:// URIs", file=sys.stderr)

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
