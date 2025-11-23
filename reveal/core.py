"""Core data models and utilities for Progressive Reveal CLI."""

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class FileSummary:
    """Internal data model for file analysis."""

    path: Path
    type: str
    size: int
    modified: datetime
    linecount: int
    sha256: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    structure: Dict[str, Any] = field(default_factory=dict)
    preview: str = ""
    lines: List[str] = field(default_factory=list)
    is_binary: bool = False
    parse_error: Optional[str] = None


def read_file_safe(file_path: Path, max_bytes: int = 2 * 1024 * 1024, force: bool = False) -> tuple[bool, str, List[str]]:
    """
    Safely read a file with size and binary checks.

    Tries multiple encodings in order of likelihood:
    1. UTF-8 (with BOM handling)
    2. CP1252 (Windows Western European)
    3. ISO-8859-1 (Latin-1, never fails but may produce garbage)
    4. UTF-16 (Windows applications)

    Returns:
        tuple: (success, error_message, lines)
    """
    if not file_path.exists():
        return False, f"File not found: {file_path}", []

    file_size = file_path.stat().st_size

    if file_size > max_bytes and not force:
        return False, f"File too large ({file_size} bytes > {max_bytes} bytes). Use --force to override.", []

    # Try multiple encodings in order of preference
    encodings_to_try = [
        'utf-8-sig',  # UTF-8 with BOM handling
        'utf-8',      # UTF-8 without BOM
        'cp1252',     # Windows Western European
        'iso-8859-1', # Latin-1 (fallback, accepts all bytes)
        'utf-16',     # Windows UTF-16 LE/BE
    ]

    last_error = None

    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
                lines = content.splitlines()
            return True, "", lines
        except UnicodeDecodeError as e:
            last_error = e
            continue
        except Exception as e:
            # Other errors (permissions, etc.) should be reported immediately
            return False, f"Error reading file: {str(e)}", []

    # If all encodings failed, it's likely a binary file
    return False, "Binary file detected. Use --force for hexdump.", []


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return "ERROR"


def create_file_summary(file_path: Path, force: bool = False) -> FileSummary:
    """
    Create a FileSummary object from a file path.

    Args:
        file_path: Path to the file
        force: Whether to force read large/binary files

    Returns:
        FileSummary object
    """
    from .detectors import detect_file_type

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    stat = file_path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime)

    # Read file content
    success, error, lines = read_file_safe(file_path, force=force)

    if not success:
        # Create minimal summary with error
        return FileSummary(
            path=file_path,
            type="unknown",
            size=stat.st_size,
            modified=modified,
            linecount=0,
            sha256=compute_sha256(file_path),
            is_binary="Binary file" in error,
            parse_error=error,
            lines=[]
        )

    file_type = detect_file_type(file_path)

    return FileSummary(
        path=file_path,
        type=file_type,
        size=stat.st_size,
        modified=modified,
        linecount=len(lines),
        sha256=compute_sha256(file_path),
        lines=lines
    )
