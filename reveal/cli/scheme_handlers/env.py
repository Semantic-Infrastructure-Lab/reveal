"""Handler for env:// URIs."""

import sys
from typing import Optional
from argparse import Namespace


def handle_env(adapter_class: type, resource: str, element: Optional[str],
               args: Namespace) -> None:
    """Handle env:// URIs."""
    from ...rendering import render_env_structure, render_env_variable

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for env:// URIs", file=sys.stderr)

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
