"""URI parsing for diff adapter."""

import re
from typing import Tuple


def _find_separator_colon(resource: str) -> int:
    """Find the colon that separates left and right URIs, skipping Windows drive letters.

    Returns the index of the separator colon, or -1 if not found.
    Windows drive letters like C: or D: should not be treated as separators.
    """
    # Find all colons that are NOT part of Windows drive letters (pattern: [A-Z]:)
    for i, char in enumerate(resource):
        if char == ':':
            # Check if this is a Windows drive letter (single letter followed by :)
            is_drive_letter = (
                i == 1  # Second character (like "C:")
                and i > 0
                and resource[i-1].isalpha()
                and resource[i-1].isupper()
            )
            # Also check for absolute Windows path in middle of string (like "path:C:\file")
            is_mid_drive_letter = (
                i > 0
                and resource[i-1].isalpha()
                and resource[i-1].isupper()
                and (i == 1 or resource[i-2] in (':', '/', '\\'))
            )

            if not (is_drive_letter or is_mid_drive_letter):
                return i
    return -1


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
        # Simple case: "file1:file2" or Windows paths "C:\file1:D:\file2"
        sep_idx = _find_separator_colon(resource)
        if sep_idx == -1:
            raise ValueError("diff:// requires format: left:right")
        left = resource[:sep_idx]
        right = resource[sep_idx+1:]
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
