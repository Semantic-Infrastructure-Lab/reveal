"""Metadata display for file structure."""

from pathlib import Path
from typing import Optional

from reveal.base import FileAnalyzer
from reveal.utils import safe_json_dumps, print_breadcrumbs


def show_metadata(analyzer: FileAnalyzer, output_format: str, config=None):
    """Show file metadata."""
    meta = analyzer.get_metadata()

    if output_format == 'json':
        print(safe_json_dumps(meta))
    else:
        print(f"File: {meta['name']}\n")
        print(f"Path:     {meta['path']}")
        print(f"Size:     {meta['size_human']}")

        # Optional fields - not all file types have these
        if 'lines' in meta:
            print(f"Lines:    {meta['lines']}")
        if 'encoding' in meta:
            print(f"Encoding: {meta['encoding']}")

        # Show other metadata fields (like parts_count for Office docs)
        for key, value in meta.items():
            if key not in ('name', 'path', 'size', 'size_human', 'lines', 'encoding'):
                # Format key nicely (parts_count -> Parts, created -> Created)
                if key.endswith('_count'):
                    display_key = key.replace('_count', '').replace('_', ' ').title()
                else:
                    display_key = key.replace('_', ' ').title()
                print(f"{display_key}: {value:,}" if isinstance(value, int) else f"{display_key}: {value}")

        print_breadcrumbs('metadata', meta['path'], config=config)


def _print_file_header(path: Path, is_fallback: bool = False, fallback_lang: Optional[str] = None) -> None:
    """Print file header with size metadata and optional fallback indicator."""
    header = f"File: {path.name}"

    # Add size info if file exists and is a regular file
    if path.exists() and path.is_file():
        size_bytes = path.stat().st_size

        # Human-readable size
        if size_bytes < 1024:
            size_str = f"{size_bytes}B"
        elif size_bytes < 1024**2:
            size_str = f"{size_bytes/1024:.1f}KB"
        elif size_bytes < 1024**3:
            size_str = f"{size_bytes/1024**2:.1f}MB"
        else:
            size_str = f"{size_bytes/1024**3:.1f}GB"

        # Count lines efficiently
        try:
            with open(path, 'rb') as f:
                line_count = sum(1 for _ in f)
            header += f" ({size_str}, {line_count:,} lines)"
        except (OSError, UnicodeDecodeError):
            # If we can't read the file, just show size
            header += f" ({size_str})"

    # Add fallback indicator if present
    if is_fallback and fallback_lang:
        header += f" (fallback: {fallback_lang})"

    print(f"{header}\n")
