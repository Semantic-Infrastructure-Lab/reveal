"""Python import extraction using tree-sitter.

Extracts import statements and symbol usage from Python source files.
Uses tree-sitter for consistent parsing across all language analyzers.
"""

from pathlib import Path
from typing import List, Set, Optional
import re

from . import ImportStatement
from .base import LanguageExtractor, register_extractor
from .resolver import resolve_python_import
from ...base import get_analyzer


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

        imports = []

        # Find import_statement nodes (import os, sys)
        import_nodes = analyzer._find_nodes_by_type('import_statement')
        for node in import_nodes:
            imports.extend(self._parse_import_statement(node, file_path, analyzer))

        # Find import_from_statement nodes (from x import y)
        from_nodes = analyzer._find_nodes_by_type('import_from_statement')
        for node in from_nodes:
            imports.extend(self._parse_from_import(node, file_path, analyzer))

        return imports

    def _parse_import_statement(self, node, file_path: Path, analyzer) -> List[ImportStatement]:
        """Parse 'import x, y as z' statements."""
        imports = []

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
                line_number=node.start_point[0] + 1,
                module_name=module_name,
                imported_names=[],
                is_relative=False,
                import_type='import',
                alias=alias
            ))

        return imports

    def _parse_from_import(self, node, file_path: Path, analyzer) -> List[ImportStatement]:
        """Parse 'from x import y' statements."""
        import_text = analyzer._get_node_text(node)

        # Parse: from <module> import <names>
        # Also handles: from . import x, from .. import y
        match = re.match(r'from\s+(\.*)(\S*)\s+import\s+(.+)', import_text, re.DOTALL)
        if not match:
            return []

        dots, module_part, names_part = match.groups()

        # Determine if relative
        is_relative = len(dots) > 0
        module_name = module_part.strip() if module_part else ''

        # Parse imported names (handle aliases, wildcards)
        imported_names = []
        names_part = names_part.strip()

        # Handle wildcard imports
        if names_part == '*':
            imported_names = ['*']
            import_type = 'star_import'
        else:
            # Handle parenthesized imports: from x import (a, b, c)
            names_part = re.sub(r'[()]', '', names_part)

            # Split by comma, handle aliases
            for name_part in names_part.split(','):
                name_part = name_part.strip()
                if not name_part:
                    continue

                # Handle 'from X import Y as Z'
                if ' as ' in name_part:
                    name, alias_name = name_part.split(' as ', 1)
                    imported_names.append(f"{name.strip()} as {alias_name.strip()}")
                else:
                    imported_names.append(name_part)

            import_type = 'from_import'

        return [ImportStatement(
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            module_name=module_name,
            imported_names=imported_names,
            is_relative=is_relative,
            import_type=import_type,
            alias=None  # from imports don't have module-level aliases
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
            return analyzer._get_node_text(current)

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

            # Extract string literals from the assignment
            # Handles: __all__ = ["a", "b"] and __all__ += ["c"]
            # Use regex to extract quoted strings
            pattern = r'["\']([^"\']+)["\']'
            matches = re.findall(pattern, assignment_text)
            exports.update(matches)

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
