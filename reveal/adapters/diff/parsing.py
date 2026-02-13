"""URI parsing for diff adapter."""

from typing import Tuple


def parse_diff_uris(resource: str) -> Tuple[str, str]:
    """Parse left:right from diff resource string.

    Handles complex URIs that may contain colons:
    - Simple: "app.py:backup/app.py" → ("app.py", "backup/app.py")
    - Complex: "mysql://prod/db:mysql://staging/db" → ("mysql://prod/db", "mysql://staging/db")
    - Nested: "env://:env://production" → ("env://", "env://production")

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
            left, rest = parts[0].split(':', 1)
            right = f"{rest}://{parts[1]}"
            return left, right

    elif scheme_count == 2:
        # Two schemes: "scheme1://resource1:scheme2://resource2"
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
        # Too complex
        raise ValueError(
            f"Too many schemes in URI (found {scheme_count}). "
            "For complex URIs, use explicit format: diff://scheme1://res1:scheme2://res2"
        )
