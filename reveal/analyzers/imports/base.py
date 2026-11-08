"""Base classes for language-specific import extractors.

This module provides the foundation for a plugin-based architecture where
each programming language implements a standard interface for:
- Import extraction
- Symbol extraction (for unused import detection)
- Import resolution (for circular dependency detection)

New languages can be added by creating a class that inherits from
LanguageExtractor and decorating it with @register_extractor.
"""

from copy import deepcopy
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Iterable, List, Set, ClassVar, Optional, Tuple, Type, Dict

from .packages import PackageModel, PackageUnit
from .types import ImportExtraction, ImportStatement, restamp_file_path
from ...core import disk_cache
from ...registry import get_analyzer
from ...utils.path_utils import search_parents_within_ceiling
from ...utils.request_cache import register_request_cache

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
    I001/I002/I005, ``depends://``, and
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
        # Persist the complete artifact, including future diagnostic fields. One entry per
        # absolute path, holding the (mtime_ns, size) it answers for: an edit replaces it
        # rather than adding one (BACK-2093; it grew by one entry per edit).
        self._mem_cache: Dict[str, Tuple[int, int, ImportExtraction]] = {}
        # A long-lived host (MCP) starts every request with this layer empty; the disk
        # layer still serves unchanged files (BACK-2083).
        register_request_cache(f'{__name__}.{namespace}', self.clear)

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
        self, file_path: Path, compute: Callable[[], List[ImportStatement]],
        *, owner: 'LanguageExtractor',
    ) -> List[ImportStatement]:
        """Cache the complete analysis artifact; callers receive an isolated copy.

        Legacy tuple entries are misses, never assumed to have clean diagnostics.
        Input freshness belongs in the key; request path spelling is applied on read.
        A failure the file's content did not cause (``ImportExtraction.cacheable``) is
        returned but stored in neither layer, so the next call reads the file again (BACK-2083).
        """
        path_str = os.path.abspath(str(file_path))
        try:
            stat = os.stat(path_str)
        except OSError:
            owner.analysis = ImportExtraction()
            owner.analysis.imports = compute()
            return owner.analysis.imports
        stamp = (stat.st_mtime_ns, stat.st_size)
        fingerprint = self.fingerprint(path_str, stat.st_mtime_ns)
        entry = self._mem_cache.get(path_str)
        cached = entry[2] if entry is not None and entry[:2] == stamp else None
        if cached is None and fingerprint is not None:
            candidate = disk_cache.get(self.namespace, fingerprint)
            if isinstance(candidate, ImportExtraction):
                cached = candidate
                self._mem_cache[path_str] = (*stamp, candidate)
        if cached is not None:
            owner.analysis = deepcopy(cached)
            owner.analysis.imports = restamp_file_path(owner.analysis.imports, file_path)
            return owner.analysis.imports
        owner.analysis = ImportExtraction()
        owner.analysis.imports = compute()
        if not owner.analysis.cacheable:
            return owner.analysis.imports
        self._mem_cache[path_str] = (*stamp, deepcopy(owner.analysis))
        if fingerprint is not None:
            disk_cache.put(self.namespace, fingerprint, owner.analysis, max_entries=self.max_files())
        return owner.analysis.imports

    def clear(self) -> None:
        """Drop the in-process layer (each host request, and tests; disk entries are untouched)."""
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


def extension_detects_unused(ext: str) -> bool:
    """True when the extractor for `ext` judges unused imports (BACK-1398)."""
    extractor_cls = _EXTRACTOR_REGISTRY.get(ext)
    return bool(extractor_cls and extractor_cls.detects_unused)


def scanned_rule_traits(files: Iterable[Path]) -> Tuple[bool, List[str]]:
    """Which language-specific counting-rule clauses hold for ``files`` (BACK-2494).

    Returns whether any file's extractor excludes TYPE_CHECKING imports, and the sorted package
    marker names of the extractors the files reach.
    """
    classes = {_EXTRACTOR_REGISTRY[suffix] for suffix in {Path(f).suffix for f in files}
               if suffix in _EXTRACTOR_REGISTRY}
    return (any(cls.excludes_type_checking for cls in classes),
            sorted({cls.package_marker for cls in classes if cls.package_marker}))


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


def nearest_marker_dir(start: Path, marker: str) -> Optional[Path]:
    """The nearest directory at or above *start* holding *marker* (``go.mod``,
    ``Cargo.toml``, ``Gemfile.lock``), for resolving one language's imports.

    Climbs through the shared ``search_parents_within_ceiling``, so it stops at a
    filesystem boundary, ``$HOME``, the temp dir or a system dir instead of reaching
    an unrelated ancestor's marker. Go, Rust and Ruby each had their own unbounded
    copy of this loop (BACK-1054 note 3); a stray ``~/go.mod`` became every Go
    file's module root. Not ``resolve_project_root``: that finds the project, and
    this needs the nearest marker of one language inside it.
    """
    return search_parents_within_ceiling(start.resolve(), lambda d: (d / marker).exists())


def marker_ancestry(start: Path, marker: str) -> List[Path]:
    """Every directory at or above *start* holding *marker*, nearest first, under the same
    ceiling as :func:`nearest_marker_dir` (a Cargo workspace root sits above its members)."""
    found: List[Path] = []
    directory = nearest_marker_dir(start, marker)
    while directory is not None:
        found.append(directory)
        directory = nearest_marker_dir(directory.parent, marker) if directory.parent != directory else None
    return found


def get_package_manifests() -> Set[str]:
    """Every manifest file name a registered language reads its package model from (BACK-2559)."""
    return {name for cls in _EXTRACTOR_REGISTRY.values() for name in cls.package_manifests}


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
    # False when extract_symbols() is not implemented and every import is
    # skip_unused: an empty unused list then means "not checked", never "clean".
    detects_unused: ClassVar[bool] = True
    # Counting-rule clauses only this language's files make true (BACK-2494): whether imports
    # under `if TYPE_CHECKING:` are left out of the graph, and the file name that marks a
    # package (an entry-point filter skips it). The rule text names them only when a scanned
    # file's extractor sets them.
    excludes_type_checking: ClassVar[bool] = False
    package_marker: ClassVar[Optional[str]] = None
    # The manifest file names this language's package units are read from (``package_units``, BACK-2559).
    # Empty: the language has no package model, and ``packages`` reaches its resolution as unused.
    package_manifests: ClassVar[Tuple[str, ...]] = ()

    def __init__(self) -> None:
        # Set by _get_tree_analyzer() when a file this extractor claims to
        # support (matching extension) fails to parse — as opposed to genuinely
        # having no imports/symbols. Callers (I001/I002, the imports:// adapter)
        # check this after calling extract_imports()/extract_symbols() to tell
        # "confirmed empty" apart from "analysis could not run", instead of
        # treating both as a clean/empty result (BACK-982).
        self.analysis = ImportExtraction()

    @property
    def parse_failed(self) -> bool:
        """Compatibility view of the diagnostic carried by the complete artifact."""
        return self.analysis.parse_failed

    @parse_failed.setter
    def parse_failed(self, value: bool) -> None:
        self.analysis.parse_failed = value

    def _get_tree_analyzer(self, file_path):
        """Get a tree-sitter analyzer instance for *file_path*, or None.

        Returns None in two distinct situations, only one of which is an
        error: no analyzer is registered for this file (not an error --
        extract_imports/extract_symbols degrade to empty as documented), or
        an analyzer was found but the file failed to parse TOTALLY (sets
        ``self.parse_failed`` and logs a warning, since a silent empty result
        here is indistinguishable from "genuinely no imports" to callers).

        A PARTIAL parse (tree exists, has ERROR nodes) also sets
        ``self.parse_failed`` and warns, but still returns the analyzer so the
        imports/symbols outside the ERROR region are kept (BACK-1460).
        """
        path_str = str(file_path)
        # Where a failure comes from decides whether it is the file's answer (BACK-2136). The
        # analyzer lookup and the tree build are reveal's machinery: tree-sitter's error-tolerant
        # parser returns a tree for any content, so a missing one with a parse_error means the
        # grammar could not be loaded. Both can succeed next time with the file unchanged.
        # Constructing the analyzer reads the content, whose own failures (too large) stay.
        content_stage = False
        try:
            analyzer_class = get_analyzer(path_str)
            if not analyzer_class:
                return None
            content_stage = True
            analyzer = analyzer_class(path_str)
            content_stage = False
            if not analyzer.tree:
                self.parse_failed = True
                load_error = getattr(analyzer, 'parse_error', None)
                reason = 'tree-sitter returned no tree'
                if load_error:
                    reason = f'{reason}: {load_error}'
                    self.analysis.transient_error = reason
                self.analysis.diagnostics['parse'] = {'status': 'unavailable', 'reason': reason}
                logger.debug(
                    "Parse failed for %s -- tree-sitter returned no tree; "
                    "imports/symbols for this file are incomplete, not confirmed empty",
                    path_str,
                )
                return None
            # BACK-1082: tree-sitter's error-tolerant parser still returns a
            # non-None tree for a file with a plain syntax error (recovered
            # with ERROR nodes), so the `not analyzer.tree` check above only
            # catches TOTAL parse failure. Without this, I001 (unused-import)
            # would confidently suggest deleting an import that merely wasn't
            # seen because its usage sat inside the ERROR-recovered region --
            # worse than a silent miss, since acting on it deletes real code.
            #
            # BACK-1460: flag it, but KEEP the analyzer. Returning None here
            # discarded every import and symbol in the file, not just the
            # ones inside the ERROR region, so every import-graph consumer
            # (depends://, imports://, I002, architecture) lost all edges
            # from any partially-parsed file (macro-heavy C/C++, Zig, ...).
            # Consumers that must not act on an incomplete parse (I001, I002,
            # I008, ...) already skip on ``parse_failed``; the rest get the
            # imports tree-sitter did recover.
            #
            # BACK-2497: the same recovery test as get_structure()'s ``_has_errors``
            # (check's "did not parse cleanly"), not ERROR nodes alone. ``def f(:``
            # and ``const x = (1;`` recover with a MISSING token and no ERROR node;
            # an ERROR-only test took them as complete, so I002 beside one exited 0
            # while check counted the same file as degraded. The benign end-of-file
            # MISSING quirk is filtered by the shared predicate.
            if hasattr(analyzer, '_has_recovery_artifacts') and analyzer._has_recovery_artifacts():
                self.parse_failed = True
                shape = 'ERROR nodes' if analyzer.has_parse_errors() else 'MISSING tokens'
                self.analysis.diagnostics['parse'] = {'status': 'partial', 'reason': f'tree-sitter recovered with {shape}'}
                # BACK-1598: debug, not warning. parse_failed is the disclosure;
                # each command that builds a graph states the failed set once
                # (adapters/imports.parse_failure_warning, deps, I002). A warning
                # here printed one stderr line per file per extraction pass
                # (364 on a cold `reveal overview` of Redis src/) and none on a
                # warm run, where extraction is cached.
                logger.debug(
                    "Partial parse for %s -- tree-sitter recovered with %s; "
                    "imports/symbols for this file may be incomplete, "
                    "not confirmed complete",
                    path_str, shape,
                )
            return analyzer
        except Exception as e:  # boundary-ok: broad-except -- one file's analyzer (tree-sitter load, file read, grammar) must not end the graph build; parse_failed + diagnostics['parse'] disclose it to every consumer
            self.parse_failed = True
            self.analysis.diagnostics['parse'] = {'status': 'unavailable', 'reason': str(e)}
            if isinstance(e, OSError):
                # Unreadable now, not unparseable: never cached as the file's answer (BACK-2083).
                self.analysis.read_error = type(e).__name__
            elif not content_stage:
                self.analysis.transient_error = f'{type(e).__name__}: {e}'
            logger.debug(
                "Parse failed for %s: %s -- imports/symbols for this file "
                "are incomplete, not confirmed empty",
                path_str, e,
            )
            return None

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

    def is_structural_edge(self, from_file: Path, to_file: Path) -> bool:
        """True when the edge ``from_file`` -> ``to_file`` is the language's own module
        layout rather than a dependency choice (BACK-2129).

        Cycle search leaves these edges out; every other view still counts them. The
        default is False: Python's ``__init__`` importing a submodule that imports the
        package is a real import-order cycle, and so is a JS barrel and its children.
        """
        return False

    def package_units(self, manifests: List[Path], files: List[Path],
                      on_error: Callable[[OSError], None]) -> List[PackageUnit]:
        """The package units ``manifests`` declare (each named in ``package_manifests``, resolved, sorted),
        for the scan whose source files of this language are ``files``. A manifest that cannot be read is
        handed to ``on_error`` and declares nothing; one that does not say something leaves it unknown."""
        return []

    def resolve_import_targets(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        packages: Optional[PackageModel] = None,
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
        edges. ``packages`` is the scan's package model (BACK-2559); a language
        with ``package_manifests`` reads it, every other ignores it.
        """
        primary = self.resolve_import(stmt, base_path, search_paths=search_paths)
        return [primary] if primary is not None else []

    def package_wildcard_prefix(self, stmt: ImportStatement) -> Optional[str]:
        """The package a wildcard import names (``a.b`` for Java/Kotlin ``import a.b.*``, Scala
        ``import a.b._``), or None when ``stmt`` is not that shape. Whether the package is in the
        tree is the caller's question (BACK-2506). A language whose wildcard is an edge to one module
        (Python ``from m import *``, a Rust glob) keeps this default.
        """
        return None

    def is_intra_project_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        project_namespaces: Optional[Set[str]] = None,
        packages: Optional[PackageModel] = None,
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

        ``packages`` (optional): the scan's package model (BACK-2559), the same one
        resolution searched; manifest languages (Go, Rust) answer from its units.

        Only consulted for statements that did not resolve; a resolved import is
        by definition intra-project and never reaches here. The resolution pass
        asks once per such statement, from the importing file's directory, and
        records the answer on ``stmt.intra_verdict`` (BACK-2550).
        """
        return None
