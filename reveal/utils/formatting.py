"""Formatting utilities for reveal."""


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
