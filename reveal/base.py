"""Base analyzer class for reveal - clean, simple design."""

import os
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any, List

from reveal.utils import format_size, get_file_type_from_analyzer
from reveal.utils.lines import normalize_newlines, split_lines
from reveal.utils.results import slice_structure

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

    # --head/--tail/--range never reach get_structure(): the display layer cuts the result
    # once (reveal.utils.results.slice_structure, BACK-1548). SLICE_FIELDS names the lists
    # they mean -- None is every top-level list, cut per category. DEFAULT_HEAD is the
    # sample shown when no flag is given, disclosed as a cut.
    SLICE_FIELDS: Optional[tuple] = None
    DEFAULT_HEAD: Optional[int] = None

    def __init__(self, path: str):
        self.path = Path(path)
        self._detected_encoding: str = 'utf-8'
        self.lines = self._read_file()
        self.content = '\n'.join(self.lines)

    MAX_INPUT_SIZE = 100 * 1024 * 1024  # 100 MB

    def _read_file(self) -> List[str]:
        """Read file with automatic encoding detection."""
        stat = os.stat(self.path)
        if stat.st_size > self.MAX_INPUT_SIZE:
            raise ValueError(
                f"File too large ({stat.st_size:,} bytes); "
                f"limit is {self.MAX_INPUT_SIZE:,} bytes."
            )

        encodings = ['utf-8', 'latin-1', 'cp1252']

        for encoding in encodings:
            try:
                with open(self.path, 'r', encoding=encoding) as f:
                    text = f.read()
                    if encoding == 'utf-8' and text.startswith('\ufeff'):
                        # A BOM marks the encoding and is not text: CPython skips it, and
                        # left in, it broke every stdlib-ast parse of the file (BACK-1729).
                        text, encoding = text[1:], 'utf-8-sig'
                    self._detected_encoding = encoding
                    self._ends_with_newline = text.endswith(('\n', '\r'))
                    return split_lines(text)
            except (UnicodeDecodeError, LookupError):
                # Try next encoding
                logger.debug(f"Failed to read {self.path} with {encoding}, trying next")
                continue

        # Last resort: read as binary and decode with errors='replace'
        logger.debug(f"All encodings failed for {self.path}, using binary mode with error replacement")
        self._detected_encoding = 'utf-8'
        with open(self.path, 'rb') as f:
            content = f.read().decode('utf-8', errors='replace')
            self._ends_with_newline = content.endswith(('\n', '\r'))
            # binary mode has no universal newlines: a lone \r ends a line here too, as above
            return split_lines(normalize_newlines(content))

    def get_metadata(self) -> Dict[str, Any]:
        """Return file metadata.

        Automatic - works for all file types.
        """
        import datetime
        stat = os.stat(self.path)

        return {
            'path': str(self.path),
            'name': self.path.name,
            'size': stat.st_size,
            'size_human': format_size(stat.st_size),
            'lines': len(self.lines),
            'encoding': self._detect_encoding(),
            'modified': datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
            'modified_timestamp': stat.st_mtime,
        }

    @abstractmethod
    def get_structure(self, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Return file structure (imports, functions, classes, etc.), complete.

        Args:
            **kwargs: Additional analyzer-specific parameters

        REQUIRED: Must be implemented by all analyzer subclasses.
        This method defines the core contract for file analysis.

        Return every item: --head/--tail/--range are applied to the result by the caller
        (see SLICE_FIELDS), so an analyzer never sees them.
        """
        pass  # Abstract method - must be implemented by subclasses

    def get_outline(self) -> Dict[str, Any]:
        """Return the file's structure for locating code: every element's name and line
        range, in get_structure()'s shape, but an analyzer may leave out what costs more
        than it locates (metrics, calls, imports). --grep uses it to group hits by
        enclosing element (BACK-1560).

        Default: the full get_structure(). TreeSitterAnalyzer overrides it.
        """
        return self.get_structure()

    def cut_structure(self, structure: Any, head: Optional[int] = None, tail: Optional[int] = None,
                      range_: Optional[tuple] = None) -> List[str]:
        """Cut this analyzer's ``get_structure()`` result for --head/--tail/--range, in place.

        The one step the CLI (display.structure.show_structure) and reveal.api.analyze
        share. Returns the fields the flags applied to (see slice_structure).
        """
        return slice_structure(structure, head, tail, range_, fields=self.SLICE_FIELDS,
                               default_head=self.DEFAULT_HEAD)

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
        """Fallback: Extract by grepping for name.

        Returns None — substring matching hits comments, strings, and variable
        references, producing confidently wrong results.  Analyzers that need
        element extraction should override extract_element() directly.
        """
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
        """Return the encoding that successfully read this file."""
        return self._detected_encoding.upper()

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
        fallback_type = self.__class__.__name__.replace('Analyzer', '').lower()
        file_type = get_file_type_from_analyzer(self) or fallback_type

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
