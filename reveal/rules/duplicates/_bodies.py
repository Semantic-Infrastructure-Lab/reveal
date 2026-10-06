"""Function-body helpers shared by the duplicate-detection rules (D001, D002)."""

from typing import Any, Dict


def extract_function_body(func: Dict[str, Any], content: str) -> str:
    """Extract a function body from ``content`` using the structure's line numbers.

    Skips the definition line (def/func/function) so duplicates are found even
    when parameter names differ. ``line_end`` is the structure's field name.

    Returns:
        The body without its signature line, or "" when the range is unusable.
    """
    start = func.get('line', 0)
    end = func.get('line_end', start)

    if start == 0 or end == 0:
        return ""

    lines = content.splitlines()
    if start > len(lines) or end > len(lines):
        return ""

    # start is 1-indexed, so lines[start:end] begins after the signature line.
    body_lines = lines[start:end]
    return '\n'.join(body_lines) if body_lines else ""
