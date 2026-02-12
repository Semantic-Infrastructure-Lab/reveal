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

from pathlib import Path
from typing import List, Set, Optional

from . import ImportStatement
from .base import LanguageExtractor, register_extractor
from .resolver import resolve_python_import
from ...registry import get_analyzer


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

        Args:
            file_path: Path to Python source file

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

        # Read source lines for noqa comment detection
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()
        except Exception:
            source_lines = []

        imports = []

        # Find import_statement nodes (import os, sys)
        import_nodes = analyzer._find_nodes_by_type('import_statement')
        for node in import_nodes:
            imports.extend(self._parse_import_statement(node, file_path, analyzer, source_lines))

        # Find import_from_statement nodes (from x import y)
        from_nodes = analyzer._find_nodes_by_type('import_from_statement')
        for node in from_nodes:
            imports.extend(self._parse_from_import(node, file_path, analyzer, source_lines))

        return imports

    def _is_inside_type_checking(self, node) -> bool:
        """Check if import node is inside a TYPE_CHECKING conditional block.

        Walks up the AST to detect patterns like:
            if TYPE_CHECKING:
                from typing import SomeType

        Returns:
            True if import is inside TYPE_CHECKING block
        """
        current = node.parent
        while current:
            # Check if this is an 'if' statement
            if current.type == 'if_statement':
                # Get the condition node (first child after 'if')
                if current.children and len(current.children) > 1:
                    condition = current.children[1]  # Skip 'if' keyword
                    # Check if condition contains 'TYPE_CHECKING'
                    # This handles: TYPE_CHECKING, typing.TYPE_CHECKING, etc.
                    condition_text = self._get_node_text_from_tree(condition, current)
                    if 'TYPE_CHECKING' in condition_text:
                        return True
            current = current.parent
        return False

    def _get_node_text_from_tree(self, node, analyzer_or_tree) -> str:
        """Helper to get node text when we have a tree reference."""
        if hasattr(analyzer_or_tree, '_get_node_text'):
            return str(analyzer_or_tree._get_node_text(node))
        # Fallback: decode bytes
        if hasattr(node, 'text'):
            return str(node.text.decode('utf-8'))
        return ""

    def _parse_import_statement(self, node, file_path: Path, analyzer, source_lines: List[str]) -> List[ImportStatement]:
        """Parse 'import x, y as z' statements."""
        imports = []

        # Detect TYPE_CHECKING context
        is_type_checking = self._is_inside_type_checking(node)

        # Get source line (0-indexed -> 1-indexed)
        line_number = node.start_point[0] + 1
        source_line = source_lines[node.start_point[0]].rstrip() if node.start_point[0] < len(source_lines) else ""

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

        for child in node.children:
            if child.type == 'relative_import':
                # Relative import: from . import x, from ..parent import y
                is_relative = True
                for subchild in child.children:
                    if subchild.type == 'dotted_name':
                        module_name = analyzer._get_node_text(subchild)
            elif (child.type == 'dotted_name' and child.prev_sibling and
                  analyzer._get_node_text(child.prev_sibling) == 'from'):
                # Absolute import: from pathlib import Path
                module_name = analyzer._get_node_text(child)
                break

        return module_name, is_relative

    def _parse_imported_names(self, node, analyzer) -> tuple:
        """Parse imported names and determine import type.

        Returns:
            Tuple of (imported_names, import_type)
        """
        imported_names = []
        import_type = 'from_import'
        seen_import_keyword = False

        for child in node.children:
            # Wait until we see the 'import' keyword
            if child.type == 'import':
                seen_import_keyword = True
                continue

            if not seen_import_keyword:
                continue

            # Skip commas and parentheses
            if child.type in [',', '(', ')']:
                continue

            # Wildcard import: from x import *
            if child.type == 'wildcard_import' or analyzer._get_node_text(child) == '*':
                return ['*'], 'star_import'

            # Regular imports: from x import Name or from x import Name as Alias
            if child.type == 'dotted_name':
                imported_names.append(analyzer._get_node_text(child))
            elif child.type == 'aliased_import':
                imported_names.append(analyzer._get_node_text(child))

        return imported_names, import_type

    def _parse_from_import(self, node, file_path: Path, analyzer, source_lines: List[str]) -> List[ImportStatement]:
        """Parse 'from x import y' statements."""
        # Detect TYPE_CHECKING context
        is_type_checking = self._is_inside_type_checking(node)

        # Get source line (0-indexed -> 1-indexed)
        line_number = node.start_point[0] + 1
        source_line = source_lines[node.start_point[0]].rstrip() if node.start_point[0] < len(source_lines) else ""

        # Extract module name and imported names
        module_name, is_relative = self._extract_from_module_name(node, analyzer)
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
            source_line=source_line
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
            if node.parent and node.parent.type == 'attribute':
                # Get root of attribute chain
                root = self._get_root_identifier(node.parent, analyzer)
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
        if not node.parent:
            return True

        # Walk up the tree to check if we're inside an import statement
        current = node
        while current:
            if current.type in ('import_statement', 'import_from_statement'):
                return False
            current = current.parent

        parent_type = node.parent.type

        # Skip definition contexts
        if parent_type in ('function_definition', 'class_definition', 'parameters',
                          'keyword_argument', 'dotted_name', 'aliased_import'):
            return False

        # For assignments, check if this is the target (left side)
        if parent_type == 'assignment':
            # Check if this node is on the left side
            if node.parent.children and node.parent.children[0] == node:
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
        while current and current.type == 'attribute':
            # Attribute nodes have structure: object.attribute
            if current.children:
                current = current.children[0]
            else:
                break

        # Current should now be an identifier
        if current and current.type == 'identifier':
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
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return set()

            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return set()

        except Exception:
            return set()

        exports = set()

        # Find assignment nodes
        assignment_nodes = analyzer._find_nodes_by_type('assignment')

        for node in assignment_nodes:
            # Get assignment text
            assignment_text = analyzer._get_node_text(node)

            # Check if this is __all__ assignment
            if not assignment_text.strip().startswith('__all__'):
                continue

            # Extract string literals from the assignment using tree-sitter
            # Handles: __all__ = ["a", "b"] and __all__ += ["c"]
            # Find all string nodes in the assignment
            def extract_strings(node):
                """Recursively extract string content from AST nodes."""
                strings = []
                if node.type == 'string':
                    # Get string content, strip quotes
                    text = analyzer._get_node_text(node)
                    # Remove quotes (handles both " and ')
                    text = text.strip('"\'')
                    strings.append(text)
                for child in node.children:
                    strings.extend(extract_strings(child))
                return strings

            exports.update(extract_strings(node))

        return exports

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path
    ) -> Optional[Path]:
        """Resolve Python import statement to file path.

        Args:
            stmt: Import statement to resolve
            base_path: Directory of the file containing the import

        Returns:
            Absolute path to the imported file, or None if not resolvable
        """
        return resolve_python_import(stmt, base_path)


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
