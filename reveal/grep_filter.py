"""Grep filtering utilities."""

import re
from typing import List, Optional


def apply_grep_filter(
    lines: List[tuple[int, str]],
    pattern: str,
    case_sensitive: bool = False,
    context: int = 0
) -> List[tuple[int, str]]:
    """
    Apply grep-style filtering to lines.

    Args:
        lines: List of (line_number, content) tuples
        pattern: Regex pattern to match
        case_sensitive: Whether to use case-sensitive matching
        context: Number of context lines before/after matches

    Returns:
        Filtered list of (line_number, content) tuples
    """
    if not pattern:
        return lines

    try:
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

    matching_indices = set()

    # Find matching lines
    for i, (line_num, content) in enumerate(lines):
        if regex.search(content):
            matching_indices.add(i)

    # Add context
    if context > 0:
        expanded_indices = set()
        for idx in matching_indices:
            for i in range(max(0, idx - context), min(len(lines), idx + context + 1)):
                expanded_indices.add(i)
        matching_indices = expanded_indices

    # Return filtered lines in order
    result = [lines[i] for i in sorted(matching_indices)]

    return result


def filter_structure_output(
    structure_lines: List[str],
    pattern: str,
    case_sensitive: bool = False
) -> List[str]:
    """
    Filter structure output lines by pattern.

    Args:
        structure_lines: List of formatted structure output lines
        pattern: Regex pattern to match
        case_sensitive: Whether to use case-sensitive matching

    Returns:
        Filtered list of lines
    """
    if not pattern:
        return structure_lines

    try:
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

    filtered = []
    for line in structure_lines:
        if regex.search(line):
            filtered.append(line)

    return filtered
