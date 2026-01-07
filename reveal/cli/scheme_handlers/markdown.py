"""Handler for markdown:// URIs."""

import sys
from typing import Optional
from argparse import Namespace


def handle_markdown(adapter_class: type, resource: str, element: Optional[str],
                    args: Namespace) -> None:
    """Handle markdown:// URIs for querying markdown files by frontmatter.

    URI format: markdown://[path/][?query]

    Examples:
        markdown://                      - All markdown in current dir
        markdown://docs/                 - All markdown in docs/
        markdown://?beth_topics=reveal   - Filter by field value
        markdown://docs/?!status         - Find files missing 'status'
    """
    from ...rendering.adapters.markdown_query import render_markdown_query

    if getattr(args, 'check', False):
        print("Warning: --check is not supported for markdown:// URIs", file=sys.stderr)

    # Parse resource into path and query
    # resource could be: '', 'docs/', 'docs/?query', '?query'
    path = '.'
    query = None

    if resource:
        if '?' in resource:
            path_part, query = resource.split('?', 1)
            if path_part:
                path = path_part.rstrip('/')
        else:
            path = resource.rstrip('/')

    # Create adapter with parsed path and query
    adapter = adapter_class(base_path=path, query=query)

    if element:
        # Get specific file's frontmatter
        result = adapter.get_element(element)
        if result is None:
            print(f"Error: File '{element}' not found", file=sys.stderr)
            sys.exit(1)
        render_markdown_query(result, args.format, single_file=True)
    else:
        # Query files
        result = adapter.get_structure()
        render_markdown_query(result, args.format)
