"""Base analyzer class for reveal - clean, simple design."""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import hashlib


class FileAnalyzer:
    """Base class for all file analyzers.

    Provides automatic functionality:
    - File reading with encoding detection
    - Metadata extraction
    - Line number formatting
    - Source extraction helpers

    Subclasses only need to implement:
    - get_structure(): Return dict of file elements
    - extract_element(type, name): Extract specific element (optional)
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self.lines = self._read_file()
        self.content = '\n'.join(self.lines)

    def _read_file(self) -> List[str]:
        """Read file with automatic encoding detection."""
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']

        for encoding in encodings:
            try:
                with open(self.path, 'r', encoding=encoding) as f:
                    return f.read().splitlines()
            except (UnicodeDecodeError, LookupError):
                continue

        # Last resort: read as binary and decode with errors='replace'
        with open(self.path, 'rb') as f:
            content = f.read().decode('utf-8', errors='replace')
            return content.splitlines()

    def get_metadata(self) -> Dict[str, Any]:
        """Return file metadata.

        Automatic - works for all file types.
        """
        stat = os.stat(self.path)

        return {
            'path': str(self.path),
            'name': self.path.name,
            'size': stat.st_size,
            'size_human': self._format_size(stat.st_size),
            'lines': len(self.lines),
            'encoding': self._detect_encoding(),
        }

    def get_structure(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return file structure (imports, functions, classes, etc.).

        Override in subclasses for custom extraction.
        Default: Returns empty structure.
        """
        return {}

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a specific element from the file.

        Args:
            element_type: Type of element ('function', 'class', 'section', etc.)
            name: Name of the element

        Returns:
            Dict with 'line_start', 'line_end', 'source', etc. or None

        Override in subclasses for semantic extraction.
        Default: Falls back to grep-based search.
        """
        # Default: simple grep-based extraction
        return self._grep_extract(name)

    def _grep_extract(self, name: str) -> Optional[Dict[str, Any]]:
        """Fallback: Extract by grepping for name."""
        for i, line in enumerate(self.lines, 1):
            if name in line:
                # Found it - extract this line and a few after
                line_start = i
                line_end = min(i + 20, len(self.lines))  # Up to 20 lines

                return {
                    'name': name,
                    'line_start': line_start,
                    'line_end': line_end,
                    'source': '\n'.join(self.lines[line_start-1:line_end]),
                }
        return None

    def format_with_lines(self, source: str, start_line: int) -> str:
        """Format source code with line numbers.

        Args:
            source: Source code to format
            start_line: Starting line number

        Returns:
            Formatted string with line numbers
        """
        lines = source.split('\n')
        result = []

        for i, line in enumerate(lines):
            line_num = start_line + i
            result.append(f"   {line_num:4d}  {line}")

        return '\n'.join(result)

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable form."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def _detect_encoding(self) -> str:
        """Detect file encoding."""
        # Simple heuristic for now
        try:
            self.content.encode('ascii')
            return 'ASCII'
        except UnicodeEncodeError:
            return 'UTF-8'

    def get_directory_entry(self) -> Dict[str, Any]:
        """Return info for directory listing.

        Automatic - works for all file types.
        """
        meta = self.get_metadata()
        file_type = self.__class__.__name__.replace('Analyzer', '')

        return {
            'path': str(self.path),
            'name': self.path.name,
            'size': meta['size_human'],
            'lines': meta['lines'],
            'type': file_type,
        }


# Registry for file type analyzers
_ANALYZER_REGISTRY: Dict[str, type] = {}


def register(*extensions, name: str = '', icon: str = '📄'):
    """Decorator to register an analyzer for file extensions.

    Usage:
        @register('.py', name='Python', icon='🐍')
        class PythonAnalyzer(FileAnalyzer):
            ...

    Args:
        extensions: File extensions to register (e.g., '.py', '.rs')
        name: Display name for this file type
        icon: Emoji icon for this file type
    """
    def decorator(cls):
        for ext in extensions:
            _ANALYZER_REGISTRY[ext.lower()] = cls

        # Store metadata on class
        cls.type_name = name or cls.__name__.replace('Analyzer', '')
        cls.icon = icon

        return cls

    return decorator


def get_analyzer(path: str) -> Optional[type]:
    """Get analyzer class for a file path.

    Args:
        path: File path

    Returns:
        Analyzer class or None if not found
    """
    file_path = Path(path)
    ext = file_path.suffix.lower()

    # If we have an extension, use it
    if ext and ext in _ANALYZER_REGISTRY:
        return _ANALYZER_REGISTRY.get(ext)

    # No extension or not found - check special filenames (Dockerfile, Makefile)
    filename = file_path.name.lower()
    if filename in _ANALYZER_REGISTRY:
        return _ANALYZER_REGISTRY.get(filename)

    # Still no match - check shebang for extensionless scripts
    if not ext or ext not in _ANALYZER_REGISTRY:
        shebang_ext = _detect_shebang(path)
        if shebang_ext:
            return _ANALYZER_REGISTRY.get(shebang_ext)

    return None


def _detect_shebang(path: str) -> Optional[str]:
    """Detect file type from shebang line.

    Args:
        path: File path

    Returns:
        Extension to use (e.g., '.py', '.sh') or None
    """
    try:
        with open(path, 'rb') as f:
            first_line = f.readline()

        # Decode with error handling
        try:
            shebang = first_line.decode('utf-8', errors='ignore').strip()
        except:
            return None

        if not shebang.startswith('#!'):
            return None

        # Map shebangs to extensions
        shebang_lower = shebang.lower()

        # Python
        if 'python' in shebang_lower:
            return '.py'

        # Shell scripts (bash, sh, zsh)
        if any(shell in shebang_lower for shell in ['bash', '/sh', 'zsh']):
            return '.sh'

        return None

    except (IOError, OSError):
        return None


def get_all_analyzers() -> Dict[str, Dict[str, Any]]:
    """Get all registered analyzers with metadata.

    Returns:
        Dict mapping extension to analyzer metadata
        e.g., {'.py': {'name': 'Python', 'icon': '🐍', 'class': PythonAnalyzer}}
    """
    result = {}
    for ext, cls in _ANALYZER_REGISTRY.items():
        result[ext] = {
            'extension': ext,
            'name': getattr(cls, 'type_name', cls.__name__.replace('Analyzer', '')),
            'icon': getattr(cls, 'icon', '📄'),
            'class': cls,
        }
    return result
