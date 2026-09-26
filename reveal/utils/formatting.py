"""Formatting utilities for reveal."""

import re
import shlex


def format_size(size: int) -> str:
    """Format file size in human-readable form.

    Args:
        size: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 KB", "3.2 MB")
    """
    size_float = float(size)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_float < 1024.0:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024.0
    return f"{size_float:.1f} TB"


_BARE_URI = re.compile(r'^[a-z][a-z0-9+]*://\S*')


def shell_command(example: str) -> str:
    """Render a help example as a paste-safe `reveal ...` command line.

    Help data stores examples either as full commands ("reveal src/ --grep x")
    or as bare URIs ("ast://src?complexity>10"). A bare URI gets the `reveal`
    prefix, and a URI with shell metacharacters (? & > < | * [ ~) is
    single-quoted: unquoted, `>10` redirects into a file and `&` backgrounds
    the command. Hand-written commands are returned unchanged.
    """
    m = _BARE_URI.match(example)
    if not m:
        return example
    uri, rest = example[:m.end()], example[m.end():]
    return f'reveal {shlex.quote(uri)}{rest}'
