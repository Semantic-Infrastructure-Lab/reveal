"""Handler for diff:// URIs."""

import sys
from typing import Optional, Tuple
from argparse import Namespace


def handle_diff(adapter_class: type, resource: str, element: Optional[str],
                args: Namespace) -> None:
    """Handle diff:// URIs.

    Args:
        adapter_class: DiffAdapter class
        resource: Contains "left_uri:right_uri"
        element: Optional element to diff
        args: CLI arguments
    """
    # Parse left:right from resource
    if not resource or ':' not in resource:
        print("Error: diff:// requires format: diff://<left>:<right>", file=sys.stderr)
        print(file=sys.stderr)
        print("Examples:", file=sys.stderr)
        print("  reveal diff://app.py:backup/app.py", file=sys.stderr)
        print("  reveal diff://env://:env://production", file=sys.stderr)
        print("  reveal diff://file:a.py:file:b.py/function_name", file=sys.stderr)
        print(file=sys.stderr)
        print("Learn more: reveal help://diff", file=sys.stderr)
        sys.exit(1)

    # Handle complex URIs (may contain multiple colons)
    try:
        left_uri, right_uri = parse_diff_uris(resource)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Instantiate diff adapter
    try:
        adapter = adapter_class(left_uri, right_uri)
    except Exception as e:
        print(f"Error: Failed to create diff adapter: {e}", file=sys.stderr)
        sys.exit(1)

    # Get diff (full or element-specific)
    try:
        if element:
            result = adapter.get_element(element)
            if result is None or result.get('type') == 'not_found':
                print(f"Error: Element '{element}' not found in either resource",
                      file=sys.stderr)
                sys.exit(1)
        else:
            result = adapter.get_structure()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to compute diff: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Render diff
    from ...rendering.diff import render_diff
    render_diff(result, args.format, element is not None)


def parse_diff_uris(resource: str) -> Tuple[str, str]:
    """Parse left:right from diff resource string.

    Handles complex URIs that may contain colons:
    - Simple: "app.py:backup/app.py" → ("app.py", "backup/app.py")
    - Complex: "mysql://prod/db:mysql://staging/db" → ("mysql://prod/db", "mysql://staging/db")
    - Nested: "env://:env://production" → ("env://", "env://production")

    Strategy:
    1. Look for :// patterns to identify URI boundaries
    2. Split intelligently based on those boundaries

    Args:
        resource: The resource string to parse

    Returns:
        Tuple of (left_uri, right_uri)

    Raises:
        ValueError: If parsing fails
    """
    # Count :// occurrences to determine complexity
    scheme_count = resource.count('://')

    if scheme_count == 0:
        # Simple case: "file1:file2"
        if ':' not in resource:
            raise ValueError("diff:// requires format: left:right")
        left, right = resource.split(':', 1)
        return left, right

    elif scheme_count == 1:
        # One scheme: "scheme://resource:file" or "file:scheme://resource"
        parts = resource.split('://')
        if ':' not in parts[0]:
            # Format: "scheme://resource:file"
            scheme = parts[0]
            rest = parts[1]
            if ':' not in rest:
                raise ValueError(f"Invalid diff format: {resource}")
            resource_part, right = rest.rsplit(':', 1)
            left = f"{scheme}://{resource_part}"
            return left, right
        else:
            # Format: "file:scheme://resource"
            left_parts = parts[0].rsplit(':', 1)
            left = left_parts[-1] if len(left_parts) == 2 else parts[0]
            right = f"{left_parts[0]}://{parts[1]}" if len(left_parts) == 2 else f"{parts[0]}://{parts[1]}"
            # Need to re-parse
            if ':' in parts[0]:
                left, rest = parts[0].split(':', 1)
                right = f"{rest}://{parts[1]}"
                return left, right
            else:
                raise ValueError(f"Invalid diff format: {resource}")

    elif scheme_count == 2:
        # Two schemes: "scheme1://resource1:scheme2://resource2"
        # Split on the : between the two :// patterns
        parts = resource.split('://')
        # parts = ['scheme1', 'resource1:scheme2', 'resource2']
        if len(parts) != 3:
            raise ValueError(f"Invalid diff format: {resource}")

        scheme1 = parts[0]
        middle = parts[1]  # "resource1:scheme2"
        scheme2_resource = parts[2]

        # Split middle on the last colon to separate resource1 and scheme2
        if ':' not in middle:
            raise ValueError(f"Invalid diff format: {resource}")

        resource1, scheme2 = middle.rsplit(':', 1)
        left = f"{scheme1}://{resource1}"
        right = f"{scheme2}://{scheme2_resource}"
        return left, right

    else:
        # Too complex - user should use explicit syntax
        raise ValueError(
            f"Too many schemes in URI (found {scheme_count}). "
            "For complex URIs, use explicit format: diff://scheme1://res1:scheme2://res2"
        )
