"""File type detection utilities."""

from pathlib import Path


FILE_TYPE_MAP = {
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.json': 'json',
    '.ipynb': 'jupyter',
    '.toml': 'toml',
    '.md': 'markdown',
    '.markdown': 'markdown',
    '.py': 'python',
}


def detect_file_type(file_path: Path) -> str:
    """
    Detect file type based on extension.

    Args:
        file_path: Path to the file

    Returns:
        File type string (e.g., 'yaml', 'json', 'markdown', 'python', 'text')
    """
    suffix = file_path.suffix.lower()
    return FILE_TYPE_MAP.get(suffix, 'text')
