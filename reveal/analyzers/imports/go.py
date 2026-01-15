"""Go import extraction using tree-sitter.

Previous implementation: 172 lines with tree-sitter + 2 regex patterns
Current implementation: 178 lines using pure tree-sitter AST extraction

Benefits:
- Eliminates all regex patterns (package path, alias)
- Uses tree-sitter node types (package_identifier, dot, blank_identifier)
- More robust handling of Go import syntax variations
"""

from pathlib import Path
from typing import List, Set, Optional

from . import ImportStatement
from .base import LanguageExtractor, register_extractor
from ...registry import get_analyzer


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

        Args:
            file_path: Path to .go file

        Returns:
            List of ImportStatement objects
        """
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return []

            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return []

        except Exception:
            # Can't parse - return empty
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

        except Exception:
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
            if node.parent and node.parent.type == 'selector_expression':
                root = self._get_root_identifier(node.parent, analyzer)
                if root:
                    symbols.add(root)

        return symbols

    def _parse_import_spec(self, spec_node, file_path: Path, analyzer) -> ImportStatement:
        """Parse a Go import_spec node using tree-sitter AST.

        Tree-sitter provides structured nodes:
            "fmt"                           # interpreted_string_literal
            alias "github.com/user/pkg"     # package_identifier + interpreted_string_literal
            . "fmt"                         # dot + interpreted_string_literal
            _ "database/sql/driver"         # blank_identifier + interpreted_string_literal
        """
        line_number = spec_node.start_point[0] + 1

        # Extract components from AST
        package_path = None
        alias = None

        for child in spec_node.children:
            if child.type == 'interpreted_string_literal':
                # Extract package path (strip quotes)
                package_path = analyzer._get_node_text(child).strip('"')
            elif child.type == 'package_identifier':
                # Aliased import: f "io"
                alias = analyzer._get_node_text(child)
            elif child.type == 'dot':
                # Dot import: . "strings"
                alias = '.'
            elif child.type == 'blank_identifier':
                # Blank import: _ "database/sql/driver"
                alias = '_'

        if not package_path:
            return None

        return self._create_import(file_path, line_number, package_path, alias)

    @staticmethod
    def _create_import(
        file_path: Path,
        line_number: int,
        package_path: str,
        alias: str = None
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

        # Extract package name from path for imported_names
        # e.g., "github.com/user/pkg" → "pkg"
        package_name = package_path.split('/')[-1]
        imported_names = [package_name] if not alias == '_' else []

        return ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=package_path,
            imported_names=imported_names,
            is_relative=is_relative,
            import_type=import_type,
            alias=alias
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
        if not node.parent:
            return True

        # Walk up to check if inside import
        current = node
        while current:
            if current.type in ('import_declaration', 'import_spec'):
                return False
            current = current.parent

        parent_type = node.parent.type

        # Skip definition contexts
        if parent_type in ('function_declaration', 'method_declaration',
                          'type_declaration', 'type_spec',
                          'parameter_declaration', 'parameter_list',
                          'field_declaration', 'field_identifier'):
            return False

        # For short variable declarations (x := 5), check if left side
        if parent_type == 'short_var_declaration':
            # First child (or part of expression_list) is being declared
            if node.parent.children and node.parent.children[0] == node:
                return False

        # For var declarations
        if parent_type == 'var_spec':
            # Name is first child
            if node.parent.children and node.parent.children[0] == node:
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
        while current and current.type == 'selector_expression':
            if current.children:
                current = current.children[0]  # Get operand (left side)
            else:
                break

        # Should now be an identifier
        if current and current.type == 'identifier':
            return analyzer._get_node_text(current)

        return None

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path
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
            content = go_mod.read_text()
            # Parse "module name" from first line
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('module '):
                    return line.split()[1]
        except Exception:
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
