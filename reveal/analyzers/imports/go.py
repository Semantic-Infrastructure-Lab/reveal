"""Go import extraction using tree-sitter.

Previous implementation: 172 lines with tree-sitter + 2 regex patterns
Current implementation: 178 lines using pure tree-sitter AST extraction

Benefits:
- Eliminates all regex patterns (package path, alias)
- Uses tree-sitter node types (package_identifier, dot, blank_identifier)
- More robust handling of Go import syntax variations
"""

from pathlib import Path
from typing import List, Set

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
            Set of symbol names (currently empty - TODO: Phase 5.1)

        TODO: Implement symbol extraction using tree-sitter or regex
        """
        # TODO: Phase 5.1 - Implement Go symbol extraction
        return set()

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
