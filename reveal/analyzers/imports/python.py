"""Python import extraction using AST.

Extracts import statements and symbol usage from Python source files.
"""

import ast
from pathlib import Path
from typing import List, Set, Optional

from . import ImportStatement
from .base import LanguageExtractor, register_extractor
from .resolver import resolve_python_import


@register_extractor
class PythonExtractor(LanguageExtractor):
    """Python import extractor using AST parsing.

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
        """Extract all import statements from Python file using AST.

        Args:
            file_path: Path to Python source file

        Returns:
            List of ImportStatement objects
        """
        try:
            content = file_path.read_text()
            tree = ast.parse(content)
        except (SyntaxError, UnicodeDecodeError):
            # Can't parse - return empty
            return []

        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # import os, sys
                for alias in node.names:
                    imports.append(ImportStatement(
                        file_path=file_path,
                        line_number=node.lineno,
                        module_name=alias.name,
                        imported_names=[],
                        is_relative=False,
                        import_type='import',
                        alias=alias.asname
                    ))

            elif isinstance(node, ast.ImportFrom):
                # from os import path, environ
                # from . import utils
                module_name = node.module or ''
                is_relative = node.level > 0
                imported_names = [a.name for a in node.names]
                import_type = 'star_import' if imported_names == ['*'] else 'from_import'

                imports.append(ImportStatement(
                    file_path=file_path,
                    line_number=node.lineno,
                    module_name=module_name,
                    imported_names=imported_names,
                    is_relative=is_relative,
                    import_type=import_type,
                    alias=None  # from imports don't have module-level aliases
                ))

        return imports

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
            content = file_path.read_text()
            tree = ast.parse(content)
        except (SyntaxError, UnicodeDecodeError):
            return set()

        symbols = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                # Direct name usage: os, sys, MyClass
                symbols.add(node.id)

            elif isinstance(node, ast.Attribute):
                # Attribute access: os.path.join
                # Extract root name ('os' from 'os.path.join')
                root = self._get_root_name(node)
                if root:
                    symbols.add(root)

        return symbols

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

    @staticmethod
    def _get_root_name(node: ast.Attribute) -> str:
        """Extract root name from attribute chain.

        Examples:
            os.path.join -> 'os'
            sys.argv -> 'sys'
            obj.method() -> 'obj'
        """
        while isinstance(node.value, ast.Attribute):
            node = node.value

        if isinstance(node.value, ast.Name):
            return node.value.id

        return ''


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
