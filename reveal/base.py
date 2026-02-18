"""Base analyzer class for reveal - clean, simple design."""

import os
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any, List

from reveal.utils import format_size

logger = logging.getLogger(__name__)


class FileAnalyzer(ABC):
    """Abstract base class for all file analyzers.

    Provides automatic functionality:
    - File reading with encoding detection
    - Metadata extraction
    - Line number formatting
    - Source extraction helpers

    Subclasses MUST implement:
    - get_structure(): Return dict of file elements (REQUIRED)

    Subclasses MAY override:
    - extract_element(type, name): Extract specific element (optional, has default)

    This is an Abstract Base Class - attempting to instantiate FileAnalyzer directly
    will raise TypeError. All concrete analyzer classes must implement get_structure().
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self.lines = self._read_file()
        self.content = '\n'.join(self.lines)

    MAX_INPUT_SIZE = 100 * 1024 * 1024  # 100 MB

    def _read_file(self) -> List[str]:
        """Read file with automatic encoding detection."""
        stat = os.stat(self.path)
        if stat.st_size > self.MAX_INPUT_SIZE:
            raise ValueError(
                f"File too large ({stat.st_size:,} bytes); "
                f"limit is {self.MAX_INPUT_SIZE:,} bytes. Use --max-bytes to truncate output."
            )

        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']

        for encoding in encodings:
            try:
                with open(self.path, 'r', encoding=encoding) as f:
                    return f.read().splitlines()
            except (UnicodeDecodeError, LookupError):
                # Try next encoding
                logger.debug(f"Failed to read {self.path} with {encoding}, trying next")
                continue

        # Last resort: read as binary and decode with errors='replace'
        logger.debug(f"All encodings failed for {self.path}, using binary mode with error replacement")
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
            'size_human': format_size(stat.st_size),
            'lines': len(self.lines),
            'encoding': self._detect_encoding(),
        }

    @abstractmethod
    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Return file structure (imports, functions, classes, etc.).

        Args:
            head: Show first N semantic units
            tail: Show last N semantic units
            range: Show semantic units in range (start, end) - 1-indexed
            **kwargs: Additional analyzer-specific parameters

        REQUIRED: Must be implemented by all analyzer subclasses.
        This method defines the core contract for file analysis.

        Note: head/tail/range are mutually exclusive and apply to semantic units
        (records, functions, sections) not raw text lines.
        """
        pass  # Abstract method - must be implemented by subclasses

    def _apply_semantic_slice(self, items: List[Dict[str, Any]],
                              head: Optional[int] = None, tail: Optional[int] = None,
                              range: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Apply head/tail/range slicing to a list of semantic units.

        Args:
            items: List of semantic units (records, functions, sections, etc.)
            head: Show first N units
            tail: Show last N units
            range: Show units in range (start, end) - 1-indexed

        Returns:
            Sliced list of items

        This is a shared helper that all analyzers can use to implement
        semantic navigation consistently.
        """
        if not items:
            return items

        if head is not None:
            return items[:head]
        elif tail is not None:
            return items[-tail:]
        elif range is not None:
            start, end = range
            # Convert 1-indexed to 0-indexed, inclusive range
            return items[start-1:end]
        else:
            return items

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

    def _detect_encoding(self) -> str:
        """Detect file encoding."""
        # Simple heuristic for now
        try:
            self.content.encode('ascii')
            return 'ASCII'
        except UnicodeEncodeError:
            return 'UTF-8'

    def _extract_relationships(self, structure: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
        """Extract relationships from structure.

        Override in subclasses to provide relationship extraction.
        Default: Returns empty dict.

        Args:
            structure: Structure dict returned by get_structure()

        Returns:
            Dict mapping relationship names to edge lists
            e.g., {'calls': [{'from': {...}, 'to': {...}, 'line': 42}]}
        """
        return {}

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


# Note: registry functions (register, get_analyzer, etc.) should be imported
# directly from reveal.registry to avoid circular dependencies
__all__ = ['FileAnalyzer']
