"""Formatting utilities for reveal."""


def format_size(size: int) -> str:
    """Format file size in human-readable form.

    Args:
        size: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 KB", "3.2 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
