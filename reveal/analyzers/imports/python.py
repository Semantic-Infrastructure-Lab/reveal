"""Python import extraction using AST.

Extracts import statements and symbol usage from Python source files.
"""

import ast
from pathlib import Path
from typing import List, Set

from . import ImportStatement


def extract_python_imports(file_path: Path) -> List[ImportStatement]:
    """Extract all import statements from Python file.

    Args:
        file_path: Path to Python source file

    Returns:
        List of ImportStatement objects

    Handles:
        - import os, sys
        - from x import y, z
        - from . import relative
        - from x import *
        - import numpy as np
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


def extract_python_symbols(file_path: Path) -> Set[str]:
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
            root = _get_root_name(node)
            if root:
                symbols.add(root)

    return symbols


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


__all__ = [
    'extract_python_imports',
    'extract_python_symbols',
]
