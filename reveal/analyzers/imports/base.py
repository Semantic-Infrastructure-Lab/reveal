"""Base classes for language-specific import extractors.

This module provides the foundation for a plugin-based architecture where
each programming language implements a standard interface for:
- Import extraction
- Symbol extraction (for unused import detection)
- Import resolution (for circular dependency detection)

New languages can be added by creating a class that inherits from
LanguageExtractor and decorating it with @register_extractor.
"""

import hashlib
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, List, Set, ClassVar, Optional, Tuple, Type, Dict

from .types import ImportStatement
from ...core import disk_cache

logger = logging.getLogger(__name__)

# Registry for auto-discovery of language extractors
_EXTRACTOR_REGISTRY: Dict[str, Type['LanguageExtractor']] = {}


class ImportsDiskCache:
    """Per-file in-process + disk cache for one extractor's extract_imports().

    Factored out of PythonExtractor's BACK-625 fix so the other bespoke
    extractors (JS/Go/Rust/Zig) and the shared generic tree-sitter extractor
    (C/C++/Java/Kotlin/Scala/C#/Ruby/PHP/Swift/Dart/Lua/GDScript) get the same
    cross-invocation win without each hand-rolling the fingerprint/cache-key
    plumbing. ``extract_imports()`` independently re-parses+walks the tree
    per call -- it does not share ``TreeSitterAnalyzer.get_structure()``'s own
    structure cache (BACK-535) -- and is invoked repeatedly per file across
    I001/I002/I005, ``calls://``'s build_symbol_map, ``depends://``, and
    ``imports://``, both within one CLI invocation and across fresh ones.

    One instance per language module (module-level singleton), keyed by a
    caller-chosen ``namespace`` so each language's entries live in their own
    disk-cache bucket with an independent prune cap.
    """

    def __init__(self, namespace: str, env_var: str = "REVEAL_IMPORTS_CACHE_MAX_FILES",
                 default_max_files: int = 100_000):
        self.namespace = namespace
        self._env_var = env_var
        self._default_max_files = default_max_files
        self._mem_cache: Dict[Tuple[str, int], List[ImportStatement]] = {}

    def max_files(self) -> int:
        """Read the entry cap, honoring this cache's env var override."""
        raw = os.environ.get(self._env_var)
        if raw is None:
            return self._default_max_files
        try:
            return int(raw)
        except ValueError:
            logger.debug("Invalid %s=%r, using default", self._env_var, raw)
            return self._default_max_files

    def fingerprint(self, path_str: str, mtime_ns: int) -> Optional[str]:
        """Disk-cache key for one file's extracted imports, or None to skip caching."""
        try:
            size = os.path.getsize(path_str)
        except OSError:
            return None
        hasher = hashlib.sha256()
        hasher.update(path_str.encode("utf-8", "replace"))
        hasher.update(b"\x00")
        hasher.update(str(mtime_ns).encode("ascii"))
        hasher.update(b"\x00")
        hasher.update(str(size).encode("ascii"))
        return hasher.hexdigest()

    def get_or_compute(
        self, file_path: Path, compute: Callable[[], List[ImportStatement]]
    ) -> List[ImportStatement]:
        """Return cached imports for *file_path*, computing (and caching) on a miss."""
        path_str = os.path.abspath(str(file_path))
        try:
            mtime_ns = os.stat(path_str).st_mtime_ns
        except OSError:
            mtime_ns = 0
        cache_key = (path_str, mtime_ns)
        if cache_key in self._mem_cache:
            return self._mem_cache[cache_key]

        fingerprint = self.fingerprint(path_str, mtime_ns)
        if fingerprint is not None:
            cached = disk_cache.get(self.namespace, fingerprint)
            if cached is not None:
                self._mem_cache[cache_key] = cached
                return cached

        imports = compute()
        self._mem_cache[cache_key] = imports
        if fingerprint is not None:
            disk_cache.put(self.namespace, fingerprint, imports, max_entries=self.max_files())
        return imports

    def clear(self) -> None:
        """Drop the in-process layer (tests only; disk entries are untouched)."""
        self._mem_cache.clear()


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
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
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

    def resolve_import_targets(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
    ) -> List[Path]:
        """Resolve an import statement to *all* files it depends on.

        A single import statement can pull in more than one file — most
        commonly ``from pkg import a, b`` where ``a`` and ``b`` are each
        submodules (BACK-542). :meth:`resolve_import` returns only the single
        primary target (the module named in the statement), so consumers that
        need the complete dependency set (``depends://``) use this instead.

        Default implementation wraps :meth:`resolve_import` in a one-element
        list (or empty), so languages without multi-target imports need no
        override. Python overrides this to add ``from pkg import submodule``
        edges.
        """
        primary = self.resolve_import(stmt, base_path, search_paths=search_paths)
        return [primary] if primary is not None else []

    def is_intra_project_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        project_namespaces: Optional[Set[str]] = None,
    ) -> Optional[bool]:
        """Classify an import as intra-project vs external, for honest-decline.

        Powers ``depends://``'s honest-decline invariant (BACK-547): when an
        import statement was extracted but produced **no** graph edge, this
        distinguishes the two very different reasons —

          * ``True``  — the import points **inside this project** but did not
            resolve to a file (a real resolution-level miss, or a target outside
            the scanned scope). These are the false-negative risk a blast-radius
            negative must disclose.
          * ``False`` — the import is **external** (stdlib / third-party
            dependency) and *correctly* has no in-tree edge. Not a concern.
          * ``None``  — the extractor cannot cheaply tell. Callers must treat
            ``None`` conservatively (do **not** count it as a miss), so the
            default is deliberately ``None`` rather than a guess: a wrong
            "intra-project" would cry wolf, the exact failure honest-decline
            exists to avoid.

        ``project_namespaces`` (optional): the set of namespaces/packages the
        scanned tree *declares* — supplied by the caller for namespace-resolved
        languages (C#) so a qualified import can be classed intra-project iff
        the project declares a matching namespace. Extractors that don't need it
        ignore it.

        Only consulted for statements that did not resolve; a resolved import is
        by definition intra-project and never reaches here.
        """
        return None
