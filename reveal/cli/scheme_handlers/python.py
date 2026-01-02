"""Handler for python:// URIs."""

import sys
from typing import Optional
from argparse import Namespace


def handle_python(adapter_class: type, resource: str, element: Optional[str],
                  args: Namespace) -> None:
    """Handle python:// URIs."""
    from ...rendering import render_python_structure, render_python_element

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for python:// URIs", file=sys.stderr)

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
