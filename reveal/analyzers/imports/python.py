"""Python import extraction using tree-sitter.

Previous implementation: Tree-sitter + 2 regex patterns for parsing
Current implementation: Pure tree-sitter AST extraction

Benefits:
- Eliminates regex patterns (from-import parsing, __all__ string extraction)
- Uses tree-sitter node types (relative_import, import_prefix, string nodes)
- More robust handling of edge cases

Extracts import statements and symbol usage from Python source files.
Uses tree-sitter for consistent parsing across all language analyzers.
"""

import hashlib
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import FrozenSet, List, Set, Optional, Dict, Tuple
from ...core import disk_cache, node_children as _children, node_prev_sibling as _prev_sibling
from ...core.treesitter_compat import _zero_arg

logger = logging.getLogger(__name__)

from .types import ImportStatement, restamp_file_path
from .base import LanguageExtractor, register_extractor
from .resolver import resolve_python_import, resolve_python_from_import_submodules
from ...rules.imports import STDLIB_MODULES
from ...utils.path_utils import resolve_project_root

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore  # Python < 3.11 fallback

# Module-level cache for extract_imports results keyed by (file_path_str, mtime_ns).
# I002 builds an import graph by calling extract_imports on every file in a directory,
# often visiting the same files multiple times across different graph builds.
# I001 also calls extract_imports for each checked file independently.
# Caching avoids redundant parses + file reads across both rules and repeated builds.
_extract_imports_cache: Dict[Tuple[str, int], List[ImportStatement]] = {}

# Cross-invocation disk cache (BACK-625): extract_imports parses+walks the
# tree independently of TreeSitterAnalyzer.get_structure()'s own structure
# cache (BACK-535) -- a warm structure cache does NOT make this free, so
# `calls://`'s build_symbol_map (used by overview/hotspots' complex-functions
# pass) re-pays a full parse per file on every fresh CLI invocation. Found
# profiling BACK-618 on a real 9,474-file Python corpus: 32.6s of a 401s
# `overview` run was extract_imports's independent parse, unrelated to
# StatsAdapter's already-cached path. Per-file entry, same shape as BACK-535's
# structure cache, so it needs the same large prune-cap override.
_IMPORTS_CACHE_NAMESPACE = "python_imports"
_DEFAULT_IMPORTS_CACHE_MAX_FILES = 100_000


def _imports_cache_max_files() -> int:
    """Read the imports-cache entry cap, honoring REVEAL_IMPORTS_CACHE_MAX_FILES."""
    raw = os.environ.get('REVEAL_IMPORTS_CACHE_MAX_FILES')
    if raw is None:
        return _DEFAULT_IMPORTS_CACHE_MAX_FILES
    try:
        return int(raw)
    except ValueError:
        logger.debug("Invalid REVEAL_IMPORTS_CACHE_MAX_FILES=%r, using default", raw)
        return _DEFAULT_IMPORTS_CACHE_MAX_FILES


def _imports_fingerprint(path_str: str, mtime_ns: int) -> Optional[str]:
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


@register_extractor
class PythonExtractor(LanguageExtractor):
    """Python import extractor using tree-sitter parsing.

    Supports:
    - import os, sys
    - from x import y, z
    - from . import relative
    - from x import *
    - import numpy as np
    """

    extensions = {'.py', '.pyi'}
    language_name = 'Python'

    def extract_imports(self, file_path: Path) -> List[ImportStatement]:
        """Extract all import statements from Python file using tree-sitter.

        Results are cached in-process by (file_path, mtime_ns) so I002's graph
        builder and I001's per-file check share results without re-parsing
        within one CLI invocation, and cross-invocation on disk (BACK-625) so
        a 2nd+ `reveal` command on an unchanged file skips the parse entirely
        -- this independently re-parses every file (does not share
        TreeSitterAnalyzer's own structure cache, BACK-535).

        Args:
            file_path: Path to Python source file

        Returns:
            List of ImportStatement objects
        """
        path_str = os.path.abspath(str(file_path))
        try:
            mtime_ns = os.stat(path_str).st_mtime_ns
        except OSError:
            mtime_ns = 0
        cache_key = (path_str, mtime_ns)
        if cache_key in _extract_imports_cache:
            return restamp_file_path(_extract_imports_cache[cache_key], file_path)

        fingerprint = _imports_fingerprint(path_str, mtime_ns)
        if fingerprint is not None:
            cached = disk_cache.get(_IMPORTS_CACHE_NAMESPACE, fingerprint)
            if cached is not None:
                _extract_imports_cache[cache_key] = cached
                return restamp_file_path(cached, file_path)

        analyzer = self._get_tree_analyzer(path_str)
        if not analyzer:
            _extract_imports_cache[cache_key] = []
            return []

        # Read source lines for noqa comment detection
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()
        except Exception:  # noqa: BLE001
            source_lines = []

        imports = []
        for node in analyzer._find_nodes_by_type('import_statement'):
            imports.extend(self._parse_import_statement(node, file_path, analyzer, source_lines))
        for node in analyzer._find_nodes_by_type('import_from_statement'):
            imports.extend(self._parse_from_import(node, file_path, analyzer, source_lines))

        _extract_imports_cache[cache_key] = imports
        if fingerprint is not None:
            disk_cache.put(_IMPORTS_CACHE_NAMESPACE, fingerprint, imports,
                            max_entries=_imports_cache_max_files())
        return imports

    def _is_inside_type_checking(self, node, analyzer=None) -> bool:
        """Check if import node is inside a TYPE_CHECKING conditional block.

        Walks up the AST to detect patterns like:
            if TYPE_CHECKING:
                from typing import SomeType

        Returns:
            True if import is inside TYPE_CHECKING block
        """
        current = _zero_arg(node, 'parent')
        while current:
            is_if = _zero_arg(current, 'kind') == 'if_statement'
            if is_if and _zero_arg(current, 'child_count') > 1:
                condition_text = self._get_node_text_from_tree(current.child(1), analyzer)
                if 'TYPE_CHECKING' in condition_text:
                    return True
            current = _zero_arg(current, 'parent')
        return False

    def _is_inside_function(self, node) -> bool:
        """Check if import node is inside a function or method body."""
        current = _zero_arg(node, 'parent')
        while current:
            if _zero_arg(current, 'kind') in ('function_definition', 'decorated_definition'):
                return True
            current = _zero_arg(current, 'parent')
        return False

    def _get_node_text_from_tree(self, node, analyzer_or_tree) -> str:
        """Helper to get node text when we have a tree reference."""
        if hasattr(analyzer_or_tree, '_get_node_text'):
            return str(analyzer_or_tree._get_node_text(node))
        return ""

    def _parse_import_statement(self, node, file_path: Path, analyzer, source_lines: List[str]) -> List[ImportStatement]:
        """Parse 'import x, y as z' statements."""
        imports = []

        # Detect TYPE_CHECKING context and function body
        is_type_checking = self._is_inside_type_checking(node, analyzer)
        is_in_function = self._is_inside_function(node)

        # Get source line (0-indexed -> 1-indexed)
        start_row = _zero_arg(node, 'start_position').row
        line_number = start_row + 1
        source_line = source_lines[start_row].rstrip() if start_row < len(source_lines) else ""

        # Get full import text for parsing
        import_text = analyzer._get_node_text(node)

        # Extract module names and aliases
        # Pattern: import os, sys as s, pathlib
        # Remove 'import ' prefix
        modules_text = import_text[7:].strip() if import_text.startswith('import ') else import_text

        # Split by comma, handle aliases
        for module_part in modules_text.split(','):
            module_part = module_part.strip()
            if not module_part:
                continue

            # Check for alias (import numpy as np)
            if ' as ' in module_part:
                module_name, alias = module_part.split(' as ', 1)
                module_name = module_name.strip()
                alias = alias.strip()
            else:
                module_name = module_part
                alias = None

            imports.append(ImportStatement(
                file_path=file_path,
                line_number=line_number,
                module_name=module_name,
                imported_names=[],
                is_relative=False,
                import_type='import',
                alias=alias,
                is_type_checking=is_type_checking,
                is_in_function=is_in_function,
                source_line=source_line
            ))

        return imports

    def _extract_from_module_name(self, node, analyzer) -> tuple:
        """Extract module name and relative flag from 'from' import node.

        Returns:
            Tuple of (module_name, is_relative)
        """
        is_relative = False
        module_name = ''
        level = 0

        for child in _children(node):
            if _zero_arg(child, 'kind') == 'relative_import':
                is_relative = True
                module_name, level = self._parse_relative_import(child, analyzer)
            elif (_zero_arg(child, 'kind') == 'dotted_name' and _prev_sibling(child) and
                  analyzer._get_node_text(_prev_sibling(child)) == 'from'):
                module_name = analyzer._get_node_text(child)
                break

        return module_name, is_relative, level

    def _parse_relative_import(self, rel_node, analyzer) -> tuple:
        """Extract module name and dot-level from a relative_import node."""
        level = 0
        module_name = ''
        for subchild in _children(rel_node):
            if _zero_arg(subchild, 'kind') == '.':
                level += 1
            elif _zero_arg(subchild, 'kind') == 'import_prefix':
                # tree-sitter-python wraps dots in import_prefix node
                level += sum(1 for c in _children(subchild) if _zero_arg(c, 'kind') == '.')
            elif _zero_arg(subchild, 'kind') == 'dotted_name':
                module_name = analyzer._get_node_text(subchild)
        return module_name, level

    def _parse_imported_names(self, node, analyzer) -> tuple:
        """Parse imported names and determine import type.

        Returns:
            Tuple of (imported_names, import_type)
        """
        imported_names = []
        import_type = 'from_import'
        seen_import_keyword = False

        for child in _children(node):
            # Wait until we see the 'import' keyword
            if _zero_arg(child, 'kind') == 'import':
                seen_import_keyword = True
                continue

            if not seen_import_keyword:
                continue

            # Skip commas and parentheses
            if _zero_arg(child, 'kind') in [',', '(', ')']:
                continue

            # Wildcard import: from x import *
            if (_zero_arg(child, 'kind') == 'wildcard_import' or
                    analyzer._get_node_text(child) == '*'):
                return ['*'], 'star_import'

            # Regular imports: from x import Name or from x import Name as Alias
            if _zero_arg(child, 'kind') == 'dotted_name':
                imported_names.append(analyzer._get_node_text(child))
            elif _zero_arg(child, 'kind') == 'aliased_import':
                imported_names.append(analyzer._get_node_text(child))

        return imported_names, import_type

    def _parse_from_import(self, node, file_path: Path, analyzer, source_lines: List[str]) -> List[ImportStatement]:
        """Parse 'from x import y' statements."""
        # Detect TYPE_CHECKING context and function body
        is_type_checking = self._is_inside_type_checking(node, analyzer)
        is_in_function = self._is_inside_function(node)

        # Get source line (0-indexed -> 1-indexed)
        start_row = _zero_arg(node, 'start_position').row
        line_number = start_row + 1
        source_line = source_lines[start_row].rstrip() if start_row < len(source_lines) else ""

        # Extract module name and imported names
        module_name, is_relative, level = self._extract_from_module_name(node, analyzer)
        imported_names, import_type = self._parse_imported_names(node, analyzer)

        return [ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=module_name,
            imported_names=imported_names,
            is_relative=is_relative,
            import_type=import_type,
            alias=None,  # from imports don't have module-level aliases
            is_type_checking=is_type_checking,
            is_in_function=is_in_function,
            source_line=source_line,
            level=level,
        )]

    def extract_symbols(self, file_path: Path) -> Set[str]:
        """Extract all symbol references (names used in code).

        Args:
            file_path: Path to Python source file

        Returns:
            Set of symbol names referenced in the file

        Used for detecting unused imports by comparing imported names
        with actually-used symbols.
        """
        analyzer = self._get_tree_analyzer(str(file_path))
        if not analyzer:
            return set()

        symbols = set()

        # Find identifier nodes (tree-sitter node type for names)
        identifier_nodes = analyzer._find_nodes_by_type('identifier')

        for node in identifier_nodes:
            # Extract the identifier text
            name = analyzer._get_node_text(node)

            # Filter out identifiers in assignment/definition contexts
            # We want to track usage, not definitions
            if self._is_usage_context(node):
                symbols.add(name)

            # Also handle attribute access (os.path -> track 'os')
            parent = _zero_arg(node, 'parent')
            if parent and _zero_arg(parent, 'kind') == 'attribute':
                # Get root of attribute chain
                root = self._get_root_identifier(parent, analyzer)
                if root:
                    symbols.add(root)

        return symbols

    def _is_usage_context(self, node) -> bool:
        """Check if identifier node is in a usage context (not definition).

        Filters out:
        - Function/class definitions
        - Parameter names
        - Assignment targets
        - Import names
        """
        if not _zero_arg(node, 'parent'):
            return True

        parent_type = _zero_arg(_zero_arg(node, 'parent'), 'kind')

        # Fast path: common definition/import contexts at immediate parent level.
        # import_from_name covers `from x import NAME` identifiers;
        # dotted_name covers module path identifiers; aliased_import covers aliases.
        if parent_type in ('function_definition', 'class_definition', 'parameters',
                           'dotted_name', 'aliased_import', 'import_from_name'):
            return False

        # Check for import statement ancestor. Import identifiers are at most
        # 2-3 levels below their containing import_statement, so bound the walk.
        current = _zero_arg(node, 'parent')
        for _ in range(3):
            if _zero_arg(current, 'kind') in ('import_statement', 'import_from_statement'):
                return False
            current = _zero_arg(current, 'parent')
            if current is None:
                break

        # For assignments and keyword args, only filter the target/key (left side),
        # not the value (right side) which is a genuine usage context.
        if parent_type in ('assignment', 'keyword_argument'):
            _p = _zero_arg(node, 'parent')
            if (_p and _zero_arg(_p, 'child_count') > 0 and
                    _zero_arg(_p.child(0), 'start_byte') == _zero_arg(node, 'start_byte')):
                return False

        return True

    def _get_root_identifier(self, attribute_node, analyzer) -> Optional[str]:
        """Extract root identifier from attribute chain.

        Examples:
            os.path.join -> 'os'
            sys.argv -> 'sys'
        """
        # Walk up the attribute chain to find the root
        current = attribute_node
        while current and _zero_arg(current, 'kind') == 'attribute':
            # Attribute nodes have structure: object.attribute
            if _children(current):
                current = current.child(0)
            else:
                break

        # Current should now be an identifier
        if current and _zero_arg(current, 'kind') == 'identifier':
            result = analyzer._get_node_text(current)
            return str(result) if result is not None else None

        return None

    def extract_exports(self, file_path: Path) -> Set[str]:
        """Extract names from __all__ declaration.

        Args:
            file_path: Path to Python source file

        Returns:
            Set of names declared in __all__ (empty if no __all__ found)

        Used to detect re-exports - imports that appear in __all__
        are intentionally exposed and should not be flagged as unused.
        """
        analyzer = self._get_tree_analyzer(str(file_path))
        if not analyzer:
            return set()

        exports: Set[str] = set()

        # Find __all__ = [...] and __all__ += [...] assignments
        for node in analyzer._find_nodes_by_type('assignment'):
            if analyzer._get_node_text(node).strip().startswith('__all__'):
                exports.update(self._extract_string_literals(node, analyzer))

        # Also find __all__.append('X') and __all__.extend([...]) call patterns
        for node in analyzer._find_nodes_by_type('call'):
            call_text = analyzer._get_node_text(node)
            if call_text.startswith('__all__.append(') or call_text.startswith('__all__.extend('):
                exports.update(self._extract_string_literals(node, analyzer))

        return exports

    def _extract_string_literals(self, node, analyzer) -> List[str]:
        """Recursively extract string content from AST nodes."""
        strings = []
        if _zero_arg(node, 'kind') == 'string':
            text = analyzer._get_node_text(node).strip('"\'')
            strings.append(text)
        for child in _children(node):
            strings.extend(self._extract_string_literals(child, analyzer))
        return strings

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
    ) -> Optional[Path]:
        """Resolve Python import statement to file path.

        Args:
            stmt: Import statement to resolve
            base_path: Directory of the file containing the import
            search_paths: Additional directories to search for absolute imports
                (e.g., the project root so that ``from pkg.mod import X`` resolves
                even when the file is in a sub-package directory)

        Returns:
            Absolute path to the imported file, or None if not resolvable
        """
        return resolve_python_import(stmt, base_path, search_paths=search_paths or [])

    def resolve_import_targets(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
    ) -> List[Path]:
        """All files a Python import statement depends on (BACK-542).

        Extends the single primary resolution with the submodule files pulled
        in by ``from pkg import submodule`` — one of the most common Python
        import idioms, which the primary resolution (resolving only the
        ``pkg`` part → ``pkg/__init__.py``) silently misses.
        """
        paths = search_paths or []
        targets: List[Path] = []
        primary = resolve_python_import(stmt, base_path, search_paths=paths)
        if primary is not None:
            targets.append(primary)
        for sub in resolve_python_from_import_submodules(stmt, base_path, search_paths=paths):
            if sub not in targets:
                targets.append(sub)
        return targets

    def is_intra_project_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        project_namespaces: Optional[Set[str]] = None,
    ) -> Optional[bool]:
        """A *relative* Python import (`from . import x`, `from ..pkg import y`)
        is unambiguously intra-project — if it didn't resolve, that's a real
        miss. An *absolute* import (`import os`, `from django.db import
        models`) could be stdlib, a third-party dependency, or an in-tree
        package.

        BACK-1189: upgrades the prior unconditional ``None`` for absolute
        imports into a real verdict wherever it can be told cheaply and
        safely, honest-decline (``None``) otherwise:

          1. A known stdlib top-level name (``STDLIB_MODULES``, the same list
             ``resolver.py`` already uses to stop a same-named local package
             from shadowing it) is always ``False`` — no manifest needed.
          2. Otherwise, resolve the project root (``pyproject.toml``/
             ``setup.py``/``setup.cfg``/a contiguous ``__init__.py`` chain)
             and build its package inventory: ``True`` if the top-level name
             is a real in-tree top-level package/module (root or ``src/``
             layout), ``False`` if it matches a dependency the project's own
             ``pyproject.toml``/``requirements.txt`` declares.
          3. Anything else (an unlisted or transitively-pulled dependency,
             a name whose PyPI distribution name doesn't match its import
             name — ``Pillow``/``PIL``, ``PyYAML``/``yaml``) stays ``None``:
             under-classifying is honest, a wrong verdict here is not.
        """
        if stmt.is_relative or stmt.level > 0:
            return True
        top_level = stmt.module_name.split('.')[0]
        if not top_level:
            return None
        if top_level in STDLIB_MODULES:
            return False
        project_root = resolve_project_root(base_path, python_init_chain=True)
        if project_root is None:
            return None
        local_names, external_names = _python_project_inventory(project_root)
        if top_level in local_names:
            return True
        if _normalize_dist_name(top_level) in external_names:
            return False
        return None


# ---------------------------------------------------------------------------
# BACK-1189: manifest-informed project inventory for is_intra_project_import.
#
# Cached per project root (functools.lru_cache on the resolved path string):
# unlike Go's is_intra_project_import (a single small go.mod re-read per
# call, cheap enough uncached), Python's inventory walks the project's
# top-level directory/-ies and parses pyproject.toml/requirements.txt --
# measured hanging past 5 minutes uncached on a ~5,000-file real corpus
# (Home Assistant core) where most files share the same project root, so
# every one of many thousands of unresolved absolute imports was paying a
# full inventory rebuild. Safe within one process/invocation: reveal is a
# one-shot CLI process, so there's no long-lived-daemon staleness concern.
# ---------------------------------------------------------------------------

_DEP_NAME_RE = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)')


def _normalize_dist_name(name: str) -> str:
    """PEP 503 normalization: case-fold, collapse runs of -._ to a single '-'."""
    return re.sub(r'[-_.]+', '-', name).lower()


def _parse_requirement_names(path: Path) -> Set[str]:
    """Package names declared in a requirements.txt-shaped file (one
    requirement per line, comments/options/version-specifiers stripped)."""
    names: Set[str] = set()
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return names
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('-'):
            continue
        match = _DEP_NAME_RE.match(line)
        if match:
            names.add(match.group(1))
    return names


def _parse_pyproject_dependency_names(path: Path) -> Set[str]:
    """Package names declared as dependencies in pyproject.toml -- PEP 621
    ``[project.dependencies]``/``[project.optional-dependencies]``, and
    legacy Poetry's ``[tool.poetry.dependencies]`` table (keys, not values;
    ``python`` itself is a version constraint there, not a dependency)."""
    names: Set[str] = set()
    try:
        with open(path, 'rb') as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return names
    project = data.get('project') or {}
    for dep in project.get('dependencies') or []:
        match = _DEP_NAME_RE.match(dep)
        if match:
            names.add(match.group(1))
    for group in (project.get('optional-dependencies') or {}).values():
        for dep in group or []:
            match = _DEP_NAME_RE.match(dep)
            if match:
                names.add(match.group(1))
    poetry_deps = ((data.get('tool') or {}).get('poetry') or {}).get('dependencies') or {}
    names.update(name for name in poetry_deps if name.lower() != 'python')
    return names


@lru_cache(maxsize=256)
def _python_project_inventory(project_root: Path) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """(local top-level import names, declared third-party dist names) for a
    Python project rooted at *project_root* -- the manifest/on-disk inventory
    that upgrades ``is_intra_project_import``'s honest ``None`` for absolute
    imports into a real verdict (BACK-1189). Cached per root -- see the
    module comment above this function."""
    local: Set[str] = set()
    for base in (project_root, project_root / 'src'):
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and (child / '__init__.py').exists():
                local.add(child.name)
            elif base is project_root and child.suffix == '.py' and child.stem not in (
                'setup', 'conftest'
            ):
                local.add(child.stem)

    external: Set[str] = set()
    external.update(_parse_requirement_names(project_root / 'requirements.txt'))
    external.update(_parse_pyproject_dependency_names(project_root / 'pyproject.toml'))

    return frozenset(local), frozenset(_normalize_dist_name(n) for n in external)


# Backward compatibility: Keep old function-based API
def extract_python_imports(file_path: Path) -> List[ImportStatement]:
    """Extract all import statements from Python file.

    DEPRECATED: Use PythonExtractor().extract_imports() instead.
    Kept for backward compatibility with existing code.
    """
    extractor = PythonExtractor()
    return extractor.extract_imports(file_path)


def extract_python_symbols(file_path: Path) -> Set[str]:
    """Extract all symbol references from Python file.

    DEPRECATED: Use PythonExtractor().extract_symbols() instead.
    Kept for backward compatibility with existing code.
    """
    extractor = PythonExtractor()
    return extractor.extract_symbols(file_path)


__all__ = [
    'PythonExtractor',
    'extract_python_imports',  # deprecated
    'extract_python_symbols',  # deprecated
]