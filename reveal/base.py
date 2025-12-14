"""Base analyzer class for reveal - clean, simple design."""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import hashlib

logger = logging.getLogger(__name__)

# Import type system (lazy to avoid circular imports)
_TYPE_REGISTRY = None
_RELATIONSHIP_REGISTRY = None


def _get_type_system():
    """Lazy import of type system to avoid circular dependencies."""
    global _TYPE_REGISTRY, _RELATIONSHIP_REGISTRY
    if _TYPE_REGISTRY is None:
        try:
            from .types import TypeRegistry, RelationshipRegistry
            _TYPE_REGISTRY = TypeRegistry
            _RELATIONSHIP_REGISTRY = RelationshipRegistry
        except ImportError:
            logger.debug("Type system not available")
            _TYPE_REGISTRY = False
            _RELATIONSHIP_REGISTRY = False
    return _TYPE_REGISTRY, _RELATIONSHIP_REGISTRY


class FileAnalyzer:
    """Base class for all file analyzers.

    Provides automatic functionality:
    - File reading with encoding detection
    - Metadata extraction
    - Line number formatting
    - Source extraction helpers
    - Optional type system and relationships

    Subclasses only need to implement:
    - get_structure(): Return dict of file elements
    - extract_element(type, name): Extract specific element (optional)

    Optional type system (subclasses can define):
    - types: Dict mapping type names to Entity definitions
    - relationships: Dict mapping relationship names to RelationshipDef
    - _extract_relationships(structure): Extract relationship edges
    """

    # Optional: Subclasses can define types and relationships
    types: Optional[Dict[str, Any]] = None
    relationships: Optional[Dict[str, Any]] = None

    def __init__(self, path: str):
        self.path = Path(path)
        self.lines = self._read_file()
        self.content = '\n'.join(self.lines)

        # Initialize type system if types are defined
        self._type_registry = None
        self._relationship_registry = None
        self._init_type_system()

    def _read_file(self) -> List[str]:
        """Read file with automatic encoding detection."""
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
            'size_human': self._format_size(stat.st_size),
            'lines': len(self.lines),
            'encoding': self._detect_encoding(),
        }

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Return file structure (imports, functions, classes, etc.).

        Args:
            head: Show first N semantic units
            tail: Show last N semantic units
            range: Show semantic units in range (start, end) - 1-indexed
            **kwargs: Additional analyzer-specific parameters

        Override in subclasses for custom extraction.
        Default: Returns empty structure.

        Note: head/tail/range are mutually exclusive and apply to semantic units
        (records, functions, sections) not raw text lines.
        """
        return {}

    def _apply_semantic_slice(self, items: List[Dict[str, Any]],
                              head: int = None, tail: int = None,
                              range: tuple = None) -> List[Dict[str, Any]]:
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

    def _init_type_system(self) -> None:
        """Initialize type system if types/relationships are defined.

        This is called automatically in __init__ and handles:
        - Type registry creation
        - Type inheritance resolution
        - Relationship registry creation
        """
        TypeRegistryClass, RelationshipRegistryClass = _get_type_system()

        # Check if type system is available
        if not TypeRegistryClass or not RelationshipRegistryClass:
            return

        # Initialize type registry if types are defined
        if self.types:
            self._type_registry = TypeRegistryClass()
            self._type_registry.register_types(self.types)
            self._type_registry.resolve_inheritance()

        # Initialize relationship registry if relationships are defined
        if self.relationships and self._type_registry:
            self._relationship_registry = RelationshipRegistryClass(self._type_registry)
            self._relationship_registry.register_relationships(self.relationships)

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

    def validate_structure(self, structure: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        """Validate structure against type definitions.

        Args:
            structure: Structure dict to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        if not self._type_registry:
            return []

        errors = []

        for type_name, entities in structure.items():
            if type_name not in self._type_registry.types:
                continue

            for entity in entities:
                entity_errors = self._type_registry.validate_entity(type_name, entity)
                errors.extend(entity_errors)

        return errors

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


# Re-export registry functions for backward compatibility
# New code should import directly from reveal.registry
from .registry import register, get_analyzer, get_all_analyzers

__all__ = ['FileAnalyzer', 'register', 'get_analyzer', 'get_all_analyzers']
