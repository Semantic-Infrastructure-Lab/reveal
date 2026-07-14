"""Go import extraction using tree-sitter.

Previous implementation: 172 lines with tree-sitter + 2 regex patterns
Current implementation: 178 lines using pure tree-sitter AST extraction

Benefits:
- Eliminates all regex patterns (package path, alias)
- Uses tree-sitter node types (package_identifier, dot, blank_identifier)
- More robust handling of Go import syntax variations
"""

import logging
import re
from pathlib import Path
from typing import List, Set, Optional
from ...core import node_children as _children

# Go modules' semantic-import-versioning convention: a major version >= 2
# suffixes the import path (`k8s.io/klog/v2`, `gopkg.in/yaml.v3`-style
# module paths use `/v2`, `/v3`, ...), but the package's actual declared
# name (`package klog`) is the segment BEFORE the suffix, not the suffix
# itself. Deriving the local name from the raw last path segment reads
# `k8s.io/klog/v2` as package "v2" — which never matches real usage
# (`klog.FromContext(...)`), so every unaliased v2+ import falsely reports
# as unused (BACK-431 feature-breadth pass, found via real Kubernetes
# source using `k8s.io/klog/v2` throughout).
_GO_MAJOR_VERSION_SUFFIX = re.compile(r'^v[0-9]+$')

logger = logging.getLogger(__name__)


def _line_text(analyzer, line_number: int) -> str:
    """Full source line for a 1-indexed line number, or "" if out of range.

    BACK-432: I005/I001's noqa detection read ImportStatement.source_line,
    which every non-Python extractor left at its default "" — silently
    blind to duplicate-import detection and source-line-based suppression
    comments for Go/Rust/JS despite advertising support for them.
    """
    idx = line_number - 1
    if 0 <= idx < len(analyzer.lines):
        return analyzer.lines[idx].rstrip()
    return ""

from .types import ImportStatement
from .base import ImportsDiskCache, LanguageExtractor, register_extractor
from ...registry import get_analyzer

# Cross-invocation disk cache (BACK-626, extending BACK-625 to Go): same
# independent-reparse gap as PythonExtractor had -- extract_imports() does not
# share TreeSitterAnalyzer.get_structure()'s structure cache (BACK-535).
_IMPORTS_CACHE = ImportsDiskCache("go_imports")


@register_extractor
class GoExtractor(LanguageExtractor):
    """Go import extractor using pure tree-sitter parsing.

    Supports:
    - Single imports: import "fmt"
    - Grouped imports: import ( "fmt" "os" )
    - Aliased imports: import f "fmt"
    - Dot imports: import . "fmt"
    - Blank imports: import _ "database/sql/driver"
    """

    extensions = {'.go'}
    language_name = 'Go'

    def extract_imports(self, file_path: Path) -> List[ImportStatement]:
        """Extract all import declarations from Go file using tree-sitter.

        Cached cross-invocation on disk (BACK-626), same pattern as
        PythonExtractor (BACK-625).

        Args:
            file_path: Path to .go file

        Returns:
            List of ImportStatement objects
        """
        return _IMPORTS_CACHE.get_or_compute(file_path, lambda: self._extract_imports_uncached(file_path))

    def _extract_imports_uncached(self, file_path: Path) -> List[ImportStatement]:
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return []

            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return []

        except Exception as e:
            logger.debug("extract_imports failed for %s: %s", file_path, e)
            return []

        imports = []

        # Find all import_spec nodes (works for both single and grouped imports)
        import_specs = analyzer._find_nodes_by_type('import_spec')
        for spec_node in import_specs:
            result = self._parse_import_spec(spec_node, file_path, analyzer)
            if result:
                imports.append(result)

        return imports

    def extract_symbols(self, file_path: Path) -> Set[str]:
        """Extract symbols used in Go file.

        Args:
            file_path: Path to source file

        Returns:
            Set of symbol names referenced in the file

        Used for detecting unused imports by comparing imported package names
        with actually-used symbols.
        """
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return set()

            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return set()

        except Exception as e:
            logger.debug("extract_symbols failed for %s: %s", file_path, e)
            return set()

        symbols = set()

        # Find identifier nodes
        identifier_nodes = analyzer._find_nodes_by_type('identifier')

        for node in identifier_nodes:
            name = analyzer._get_node_text(node)

            # Filter out identifiers in definition contexts
            if self._is_usage_context(node):
                symbols.add(name)

            # Handle selector expressions (pkg.Function -> track 'pkg')
            if node.parent() and node.parent().kind() == 'selector_expression':
                root = self._get_root_identifier(node.parent(), analyzer)
                if root:
                    symbols.add(root)

        # Handle qualified types (pkg.Type in type position -> track 'pkg').
        # tree-sitter-go represents `sync.WaitGroup` as
        # qualified_type(package_identifier, type_identifier), NOT a
        # selector_expression, and the package part is a 'package_identifier'
        # node — so the identifier walk above never sees it and a package used
        # only for a type is falsely reported unused (BACK-420).
        for qt in analyzer._find_nodes_by_type('qualified_type'):
            if qt.child_count() > 0 and qt.child(0).kind() == 'package_identifier':
                symbols.add(analyzer._get_node_text(qt.child(0)))

        return symbols

    def _parse_import_spec(self, spec_node, file_path: Path, analyzer) -> ImportStatement | None:
        """Parse a Go import_spec node using tree-sitter AST.

        Tree-sitter provides structured nodes:
            "fmt"                           # interpreted_string_literal
            alias "github.com/user/pkg"     # package_identifier + interpreted_string_literal
            . "fmt"                         # dot + interpreted_string_literal
            _ "database/sql/driver"         # blank_identifier + interpreted_string_literal
        """
        line_number = spec_node.start_position().row + 1

        # Extract components from AST
        package_path = None
        alias = None

        for child in _children(spec_node):
            if child.kind() == 'interpreted_string_literal':
                # Extract package path (strip quotes)
                package_path = analyzer._get_node_text(child).strip('"')
            elif child.kind() == 'package_identifier':
                # Aliased import: f "io"
                alias = analyzer._get_node_text(child)
            elif child.kind() == 'dot':
                # Dot import: . "strings"
                alias = '.'
            elif child.kind() == 'blank_identifier':
                # Blank import: _ "database/sql/driver"
                alias = '_'

        if not package_path:
            return None

        return self._create_import(
            file_path, line_number, package_path, alias,
            source_line=_line_text(analyzer, line_number),
        )

    @staticmethod
    def _create_import(
        file_path: Path,
        line_number: int,
        package_path: str,
        alias: Optional[str] = None,
        source_line: str = "",
    ) -> ImportStatement:
        """Create ImportStatement for a Go import.

        Args:
            file_path: Path to source file
            line_number: Line number of import
            package_path: Package path (e.g., "fmt", "github.com/user/pkg")
            alias: Optional alias (identifier, '.', or '_')

        Returns:
            ImportStatement object
        """
        # Determine import type based on alias
        if alias == '.':
            import_type = 'dot_import'  # Imports into current namespace
        elif alias == '_':
            import_type = 'blank_import'  # Side-effect only
        elif alias:
            import_type = 'aliased_import'
        else:
            import_type = 'go_import'

        # Go imports are never relative (no ./ syntax)
        # Internal packages start with module name, external from domain
        is_relative = False

        # Determine the local name the package is referenced by — this is what
        # I001 compares against the used-symbol set. For an aliased import
        # (`utilruntime "k8s.io/.../runtime"`) the code uses the *alias*, not the
        # path basename, so imported_names must be the alias or the import reads
        # as falsely unused (BACK-420). Blank imports ('_') bind no name; dot
        # imports ('.') pull names into scope directly (skipped by I001 anyway).
        path_segments = package_path.split('/')
        package_name = path_segments[-1]
        if _GO_MAJOR_VERSION_SUFFIX.match(package_name) and len(path_segments) > 1:
            package_name = path_segments[-2]
        if alias == '_':
            imported_names = []
        elif alias and alias not in ('.', '_'):
            imported_names = [alias]
        else:
            imported_names = [package_name]

        return ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=package_path,
            imported_names=imported_names,
            is_relative=is_relative,
            import_type=import_type,
            alias=alias,
            source_line=source_line,
        )

    def _is_usage_context(self, node) -> bool:
        """Check if identifier is in a usage context (not definition).

        Filters out:
        - Function/method/type declarations
        - Parameter names
        - Field names in struct definitions
        - Variable declarations (left side of :=)
        - Import names
        """
        if not node.parent():
            return True

        # Walk up to check if inside import
        current = node
        while current:
            if current.kind() in ('import_declaration', 'import_spec'):
                return False
            current = current.parent()

        parent_type = node.parent().kind()

        # Skip definition contexts
        if parent_type in ('function_declaration', 'method_declaration',
                          'type_declaration', 'type_spec',
                          'parameter_declaration', 'parameter_list',
                          'field_declaration', 'field_identifier'):
            return False

        # For short variable declarations (x := 5), check if left side
        if parent_type == 'short_var_declaration':
            # First child (or part of expression_list) is being declared
            _p = node.parent()
            if _p and _p.child_count() > 0 and _p.child(0).start_byte() == node.start_byte():
                return False

        # For var declarations
        if parent_type == 'var_spec':
            # Name is first child
            _p = node.parent()
            if _p and _p.child_count() > 0 and _p.child(0).start_byte() == node.start_byte():
                return False

        return True

    def _get_root_identifier(self, selector_node, analyzer):
        """Extract root identifier from selector expression chain.

        Examples:
            fmt.Println -> 'fmt'
            os.File.Read -> 'os'
        """
        # Walk up selector expression chain to find root
        current = selector_node
        while current and current.kind() == 'selector_expression':
            if _children(current):
                current = current.child(0)  # Get operand (left side)
            else:
                break

        # Should now be an identifier
        if current and current.kind() == 'identifier':
            return analyzer._get_node_text(current)

        return None

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
    ) -> Optional[Path]:
        """Resolve Go import to file path.

        Args:
            stmt: Import statement to resolve
            base_path: Directory of the file containing the import

        Returns:
            Absolute path to package directory, or None if not resolvable

        Go module resolution:
        - All imports are absolute package paths (no relative imports)
        - Local packages: in same module (go.mod)
        - External packages: stdlib + go.mod dependencies (skip for cycles)
        - Package = directory (all .go files in dir are same package)
        """
        package_path = stmt.module_name

        # Find module root (go.mod location)
        module_root = self._find_go_module_root(base_path)
        if not module_root:
            # No go.mod found - can't resolve local packages
            return None

        # Get module name from go.mod
        module_name = self._get_module_name(module_root)
        if not module_name:
            return None

        # Check if this is a local package (starts with module name)
        if not package_path.startswith(module_name):
            # External package (stdlib or dependency) - skip
            return None

        # Map package path to directory
        # Example: 'mymodule/internal/utils' -> module_root/internal/utils
        relative_path = package_path[len(module_name):].lstrip('/')
        package_dir = module_root / relative_path

        if package_dir.exists() and package_dir.is_dir():
            # Return directory (all .go files in it are the package)
            return package_dir.resolve()

        return None

    def is_intra_project_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        project_namespaces: Optional[Set[str]] = None,
    ) -> Optional[bool]:
        """Go classification is precise: an import is intra-project iff its
        package path starts with the module name from go.mod (the same test
        resolve_import uses to decide local-vs-external). If there's no go.mod
        we can't tell (None)."""
        module_root = self._find_go_module_root(base_path)
        if not module_root:
            return None
        module_name = self._get_module_name(module_root)
        if not module_name:
            return None
        return stmt.module_name.startswith(module_name)

    def _find_go_module_root(self, start_path: Path) -> Optional[Path]:
        """Find go.mod file by walking up directory tree.

        Args:
            start_path: Directory to start search from

        Returns:
            Directory containing go.mod, or None if not found
        """
        current = start_path.resolve()

        # Walk up until we find go.mod or hit filesystem root
        while current != current.parent:
            go_mod = current / 'go.mod'
            if go_mod.exists():
                return current
            current = current.parent

        return None

    def _get_module_name(self, module_root: Path) -> Optional[str]:
        """Extract module name from go.mod file.

        Args:
            module_root: Directory containing go.mod

        Returns:
            Module name (e.g., 'github.com/user/repo'), or None if not found
        """
        go_mod = module_root / 'go.mod'
        if not go_mod.exists():
            return None

        try:
            content = go_mod.read_text(encoding='utf-8')
            # Parse "module name" from first line
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('module '):
                    return line.split()[1]
        except Exception as e:
            logger.debug("_get_module_name failed for %s: %s", module_root, e)
            return None

        return None


# Backward compatibility: Keep old function-based API
def extract_go_imports(file_path: Path) -> List[ImportStatement]:
    """Extract all import declarations from Go file.

    DEPRECATED: Use GoExtractor().extract_imports() instead.
    Kept for backward compatibility with existing code.
    """
    extractor = GoExtractor()
    return extractor.extract_imports(file_path)


__all__ = [
    'GoExtractor',
    'extract_go_imports',  # deprecated
]
