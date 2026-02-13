"""Base classes for language-specific import extractors.

This module provides the foundation for a plugin-based architecture where
each programming language implements a standard interface for:
- Import extraction
- Symbol extraction (for unused import detection)
- Import resolution (for circular dependency detection)

New languages can be added by creating a class that inherits from
LanguageExtractor and decorating it with @register_extractor.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Set, ClassVar, Optional, Type, Dict

from .types import ImportStatement

# Registry for auto-discovery of language extractors
_EXTRACTOR_REGISTRY: Dict[str, Type['LanguageExtractor']] = {}


def register_extractor(cls: Type['LanguageExtractor']) -> Type['LanguageExtractor']:
    """Decorator to auto-register language extractors.

    Usage:
        @register_extractor
        class PythonExtractor(LanguageExtractor):
            extensions = {'.py', '.pyi'}
            language_name = 'Python'

            def extract_imports(self, file_path):
                ...

    Args:
        cls: LanguageExtractor subclass to register

    Returns:
        The same class (decorator pattern)

    Raises:
        ValueError: If an extractor for any of the extensions already exists
    """
    for ext in cls.extensions:
        if ext in _EXTRACTOR_REGISTRY:
            existing = _EXTRACTOR_REGISTRY[ext].__name__
            raise ValueError(
                f"Duplicate extractor for extension '{ext}': "
                f"{cls.__name__} conflicts with {existing}"
            )
        _EXTRACTOR_REGISTRY[ext] = cls
    return cls


def get_extractor(file_path: Path) -> Optional['LanguageExtractor']:
    """Get appropriate extractor instance for file extension.

    Args:
        file_path: Path to source file

    Returns:
        Extractor instance for the file's extension, or None if unsupported
    """
    ext = file_path.suffix
    extractor_cls = _EXTRACTOR_REGISTRY.get(ext)
    return extractor_cls() if extractor_cls else None


def get_all_extensions() -> Set[str]:
    """Get all supported file extensions from registered extractors.

    Returns:
        Set of file extensions (e.g., {'.py', '.js', '.go', '.rs'})
    """
    return set(_EXTRACTOR_REGISTRY.keys())


def get_supported_languages() -> List[str]:
    """Get list of all supported language names.

    Returns:
        List of unique language names (e.g., ['Python', 'JavaScript', 'Go'])
    """
    seen = set()
    languages = []
    for extractor_cls in _EXTRACTOR_REGISTRY.values():
        if extractor_cls.language_name not in seen:
            seen.add(extractor_cls.language_name)
            languages.append(extractor_cls.language_name)
    return sorted(languages)


class LanguageExtractor(ABC):
    """Abstract base class for language-specific import extractors.

    Each programming language implements this interface to provide:
    1. File extensions it handles (.py, .js, etc.)
    2. Import extraction from source files
    3. Symbol extraction for unused import detection
    4. Import resolution for circular dependency detection

    Subclasses must:
    - Define class variables: extensions, language_name
    - Implement: extract_imports(), extract_symbols()
    - Optionally override: resolve_import() (if supporting cycle detection)

    Example:
        @register_extractor
        class PythonExtractor(LanguageExtractor):
            extensions = {'.py', '.pyi'}
            language_name = 'Python'

            def extract_imports(self, file_path: Path) -> List[ImportStatement]:
                # Use AST to parse Python imports
                ...

            def extract_symbols(self, file_path: Path) -> Set[str]:
                # Extract all names used in the file
                ...

            def resolve_import(self, stmt: ImportStatement, base_path: Path) -> Optional[Path]:
                # Resolve 'import foo' to /path/to/foo.py
                ...
    """

    # Subclasses MUST define these class variables
    extensions: ClassVar[Set[str]]  # {'.py', '.pyi'}
    language_name: ClassVar[str]    # 'Python'

    @abstractmethod
    def extract_imports(self, file_path: Path) -> List[ImportStatement]:
        """Extract all import statements from source file.

        Args:
            file_path: Path to source file to analyze

        Returns:
            List of ImportStatement objects found in the file

        Note:
            Should return empty list (not None) if file can't be parsed.
            Should handle encoding errors gracefully.
        """
        pass

    @abstractmethod
    def extract_symbols(self, file_path: Path) -> Set[str]:
        """Extract all symbols defined/used in file (for unused detection).

        This is used to detect which imports are actually used in the code.
        Should extract:
        - Function/method calls
        - Variable references
        - Class instantiations
        - Attribute accesses

        Args:
            file_path: Path to source file to analyze

        Returns:
            Set of symbol names referenced in the file

        Note:
            Can return empty set if symbol extraction not yet implemented.
            Phase 5.1 will add this for non-Python languages.
        """
        pass

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path
    ) -> Optional[Path]:
        """Resolve import statement to absolute file path (for cycle detection).

        This enables circular dependency detection by mapping import statements
        to actual file paths, building the dependency graph.

        Args:
            stmt: Import statement to resolve
            base_path: Directory of the file containing the import

        Returns:
            Absolute path to the imported file, or None if not resolvable

        Note:
            Default implementation returns None (no resolution).
            Override this for languages that need dependency graph analysis.

        Example:
            stmt.module_name = './utils'
            base_path = Path('/project/src')
            return Path('/project/src/utils.js')
        """
        return None
