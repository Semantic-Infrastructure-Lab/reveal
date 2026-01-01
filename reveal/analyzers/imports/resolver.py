"""Import resolution - map module names to file paths.

Handles Python's import resolution logic:
- Relative imports (./utils, ../models)
- Absolute imports (mypackage.utils)
- Package imports (mypackage.__init__)
- Namespace packages (PEP 420)
"""

from pathlib import Path
from typing import List, Optional

from . import ImportStatement


def resolve_python_import(
    import_stmt: ImportStatement,
    base_path: Path,
    search_paths: Optional[List[Path]] = None
) -> Optional[Path]:
    """Resolve import statement to actual file path.

    Args:
        import_stmt: Import to resolve
        base_path: Directory containing the importing file
        search_paths: Additional paths to search (like sys.path)

    Returns:
        Resolved file path, or None if not found
    """
    if import_stmt.is_relative:
        return _resolve_relative(import_stmt, base_path)
    else:
        return _resolve_absolute(import_stmt, base_path, search_paths or [])


def _resolve_relative(import_stmt: ImportStatement, base_path: Path) -> Optional[Path]:
    """Resolve relative import (from . import X, from .. import Y).

    Python relative imports:
        from . import utils       -> ./utils.py
        from .. import models     -> ../models.py
        from ..models import User -> ../models.py or ../models/__init__.py
    """
    # Count levels (dots): '.' = 1, '..' = 2, etc.
    # In ImportFrom node, level=1 means '.', level=2 means '..'
    # Since we stored is_relative=True, we need to infer level from context
    # For now, assume single-level relative imports (from . import X)
    # TODO: Track level explicitly in ImportStatement

    parts = import_stmt.module_name.split('.')
    target_path = base_path

    # Try module.py
    module_file = target_path / f"{parts[0]}.py"
    if module_file.exists():
        return module_file

    # Try module/__init__.py
    package_init = target_path / parts[0] / "__init__.py"
    if package_init.exists():
        return package_init

    # Try module/ directory (namespace package)
    package_dir = target_path / parts[0]
    if package_dir.is_dir():
        return package_dir

    return None


def _resolve_absolute(
    import_stmt: ImportStatement,
    base_path: Path,
    search_paths: List[Path]
) -> Optional[Path]:
    """Resolve absolute import (import os, from mypackage import utils).

    Search order:
    1. Current directory (for local packages)
    2. Additional search paths (project root, etc.)
    3. Return None for stdlib/external packages (we don't track those)
    """
    module_parts = import_stmt.module_name.split('.')

    # Build search paths: current dir + provided paths
    all_paths = [base_path] + search_paths

    for search_path in all_paths:
        # Try to resolve as module file or package
        resolved = _try_resolve_module(search_path, module_parts)
        if resolved:
            return resolved

    # Not found in any search path - likely stdlib or external package
    return None


def _try_resolve_module(base: Path, parts: List[str]) -> Optional[Path]:
    """Try to resolve module parts to a file under base path.

    Examples:
        ['mypackage', 'utils'] ->
            1. mypackage/utils.py
            2. mypackage/utils/__init__.py
            3. mypackage/utils/ (namespace package)
    """
    if not parts:
        return None

    # Single module: 'utils' -> utils.py or utils/__init__.py
    if len(parts) == 1:
        module_file = base / f"{parts[0]}.py"
        if module_file.exists():
            return module_file

        package_init = base / parts[0] / "__init__.py"
        if package_init.exists():
            return package_init

        package_dir = base / parts[0]
        if package_dir.is_dir():
            return package_dir

        return None

    # Nested module: 'mypackage.utils' -> mypackage/utils.py
    first = parts[0]
    rest = parts[1:]

    # Check if first part is a package directory
    package_dir = base / first
    if not package_dir.is_dir():
        return None

    # Recursively resolve remaining parts
    return _try_resolve_module(package_dir, rest)


__all__ = [
    'resolve_python_import',
]
