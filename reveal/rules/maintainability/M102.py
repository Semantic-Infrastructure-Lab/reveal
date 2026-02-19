"""M102: Orphan file detector.

Detects Python files that are not imported anywhere in the package.
These are often dead code left behind after refactoring.
"""

import ast
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)

# Module-level cache: package_root → set of imported names.
# Built once per package per process; safe because files don't change mid-run.
_import_cache: Dict[Path, Set[str]] = {}

# Compiled regexes for fast import extraction (replaces ast.parse + ast.walk in scan)
# Handles both `import X` (including `import X, Y`) and `from X import Y, Z`.
# Leading whitespace is allowed to catch imports inside functions/blocks.
_RE_IMPORT = re.compile(r'^\s*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)', re.MULTILINE)
_RE_FROM = re.compile(r'^\s*from\s+([\w.]+)\s+import\s+([^\n(#]+)', re.MULTILINE)
# Multi-line: `from X import (\n    Y, Z\n)` — captures everything inside the parens
_RE_FROM_PAREN = re.compile(r'^\s*from\s+([\w.]+)\s+import\s*\(([^)]+)\)', re.MULTILINE | re.DOTALL)


def _resolve_relative_import(
        module: str, file_path: Path, package_root: Path) -> Optional[str]:
    """Convert a relative import like '.analysis' or '..base' to its absolute name.

    Args:
        module: Raw module string from source, e.g. '.analysis', '..base', '.'
        file_path: Absolute path of the file containing the import
        package_root: Root of the package (directory containing pyproject.toml etc.)

    Returns:
        Absolute dotted module name, or None if it can't be resolved
    """
    dots = len(module) - len(module.lstrip('.'))
    rest = module.lstrip('.')

    try:
        rel = file_path.relative_to(package_root)
        pkg_parts = list(rel.parts[:-1])  # directories only — strip filename
        # Each extra dot beyond the first goes up one level
        go_up = dots - 1
        if go_up > len(pkg_parts):
            return None
        if go_up > 0:
            pkg_parts = pkg_parts[:len(pkg_parts) - go_up]
        if rest:
            pkg_parts.append(rest)
        return '.'.join(pkg_parts) if pkg_parts else None
    except ValueError:
        return None


def _add_module_and_parents(imports: Set[str], module: str) -> None:
    """Add a module name and all its parent packages to the imports set."""
    imports.add(module)
    parts = module.split('.')
    for i in range(1, len(parts)):
        imports.add('.'.join(parts[:i]))


def _resolve_import_module(
        module: str,
        file_path: Optional[Path],
        package_root: Optional[Path]) -> Optional[str]:
    """Resolve a raw module string to an absolute name, or None to skip."""
    if module.startswith('.'):
        if file_path and package_root:
            return _resolve_relative_import(module, file_path, package_root)
        return None  # relative but no context — skip
    return module


def _add_named_imports(imports: Set[str], module: str, names_str: str, strip_backslash: bool = False) -> None:
    """Add 'module.name' entries for each name in a comma-separated names string."""
    for name in names_str.split(','):
        name = name.strip()
        if strip_backslash:
            name = name.rstrip('\\').strip()
        name = name.split()[0] if name else ''
        if name and name != '*':
            imports.add(module + '.' + name)


def _extract_imports_regex(
        content: str,
        imports: Set[str],
        file_path: Optional[Path] = None,
        package_root: Optional[Path] = None) -> None:
    """Extract all import names from Python source using regex.

    Much faster than ast.parse + ast.walk for bulk import scanning
    (used by _collect_all_imports to scan 700+ files in the package).
    Handles: `import X`, `import X, Y`, `from X import Y, Z`,
    `from X import (\\n    Y, Z\\n)` (multi-line parenthesized imports),
    and relative imports (`from .foo import bar`, `from . import baz`).

    When file_path and package_root are provided, relative imports are
    resolved to their absolute module names.
    """
    # `import X` and `import X, Y`
    for m in _RE_IMPORT.finditer(content):
        for name in m.group(1).split(','):
            name = name.strip()
            if name:
                _add_module_and_parents(imports, name)

    # `from X import (Y, Z)` — multi-line; process first to avoid overlap
    for m in _RE_FROM_PAREN.finditer(content):
        module = _resolve_import_module(m.group(1).strip(), file_path, package_root)
        if module is None:
            continue
        _add_module_and_parents(imports, module)
        _add_named_imports(imports, module, m.group(2), strip_backslash=True)

    # `from X import Y, Z` — single-line (skip if already covered by paren form)
    for m in _RE_FROM.finditer(content):
        module = _resolve_import_module(m.group(1).strip(), file_path, package_root)
        if module is None:
            continue
        _add_module_and_parents(imports, module)
        # Record 'X.Y' for each name so `from pkg import mod` is not a false orphan
        _add_named_imports(imports, module, m.group(2).strip())


class M102(BaseRule):
    """Detect Python files not imported anywhere in the package."""

    code = "M102"
    message = "File appears to be orphaned (not imported anywhere)"
    category = RulePrefix.M
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    version = "1.0.0"

    # Files that are typically entry points, not imported
    ENTRY_POINT_PATTERNS = {
        '__init__', '__main__', 'setup', 'conftest', 'manage',
        'wsgi', 'asgi', 'app', 'main', 'cli', 'run', 'server',
    }

    # Directory patterns that contain entry points
    ENTRY_POINT_DIRS = {'bin', 'scripts', 'tools', 'migrations'}

    # Test file patterns
    TEST_PATTERNS = {'test_', '_test', 'tests'}

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """
        Check if this file is imported anywhere in the package.

        Args:
            file_path: Path to Python file
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections (0 or 1)
        """
        detections: List[Detection] = []
        path = Path(file_path)

        # Skip known entry points and special files
        if self._is_entry_point(path):
            return detections

        # Skip test files
        if self._is_test_file(path):
            return detections

        # Find the package root (directory with __init__.py or pyproject.toml)
        package_root = self._find_package_root(path)
        if not package_root:
            return detections

        # Get the module name for this file
        module_name = self._get_module_name(path, package_root)
        if not module_name:
            return detections

        # Scan all Python files in the package for imports
        all_imports = self._collect_all_imports(package_root)

        # Check if this module is imported anywhere
        if not self._is_imported(module_name, all_imports, path, package_root):
            # Double-check: is this file empty or just has comments?
            if self._has_meaningful_code(content):
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=1,
                    message=f"Module '{module_name}' is not imported anywhere in the package",
                    suggestion=(
                        "This file may be dead code. If intentional (entry point, plugin), "
                        "add to __all__ in __init__.py or rename to indicate purpose. "
                        "Otherwise, consider removing this orphaned module."
                    ),
                    context=f"Module: {module_name}"
                ))

        return detections

    def _is_entry_point(self, path: Path) -> bool:
        """Check if file is a typical entry point."""
        stem = path.stem.lower()

        # Check filename patterns
        if stem in self.ENTRY_POINT_PATTERNS:
            return True

        # Check if in entry point directory
        for parent in path.parents:
            if parent.name.lower() in self.ENTRY_POINT_DIRS:
                return True

        return False

    def _is_test_file(self, path: Path) -> bool:
        """Check if file is a test file."""
        stem = path.stem.lower()
        parts = [p.lower() for p in path.parts]

        # Check filename
        for pattern in self.TEST_PATTERNS:
            if pattern in stem:
                return True

        # Check directory
        if 'tests' in parts or 'test' in parts:
            return True

        return False

    def _find_package_root(self, path: Path) -> Optional[Path]:
        """Find the root of the Python package.

        Prefers project-level markers (pyproject.toml, setup.py) over
        __init__.py boundaries to correctly resolve module names for packages
        that live inside a project directory (e.g. httpie/ inside httpie-cli/).
        """
        current = path.parent

        # Pass 1: walk up looking for project-level markers
        sentinel = current
        for _ in range(10):
            if (current / 'pyproject.toml').exists() or (current / 'setup.py').exists():
                return current
            parent = current.parent
            if parent == current:  # filesystem root
                break
            current = parent

        # Pass 2: fall back to topmost __init__.py boundary
        current = sentinel
        for _ in range(10):
            if (current / '__init__.py').exists():
                parent = current.parent
                if not (parent / '__init__.py').exists():
                    return current
            current = current.parent

        return None

    def _get_module_name(self, path: Path, package_root: Path) -> Optional[str]:
        """Get the importable module name for a file."""
        try:
            relative = path.relative_to(package_root)
            parts = list(relative.parts)

            # Remove .py extension
            if parts[-1].endswith('.py'):
                parts[-1] = parts[-1][:-3]

            # Skip __init__ in module name
            if parts[-1] == '__init__':
                parts = parts[:-1]

            return '.'.join(parts) if parts else None
        except ValueError:
            return None

    def _collect_all_imports(self, package_root: Path) -> Set[str]:
        """Collect all imports from all Python files in the package.

        Results are cached by package_root so the O(n) AST scan runs once per
        package per process instead of once per file checked (was O(n²)).
        """
        if package_root in _import_cache:
            return _import_cache[package_root]

        imports = set()

        for py_file in package_root.rglob('*.py'):
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                _extract_imports_regex(content, imports, py_file, package_root)
            except OSError:
                continue

        _import_cache[package_root] = imports
        return imports

    def _is_imported(self, module_name: str, all_imports: Set[str],
                     path: Path, package_root: Path) -> bool:
        """Check if module is imported anywhere."""
        # Direct import check
        if module_name in all_imports:
            return True

        # If a submodule of this file is imported (e.g. 'reveal.types.python' is
        # imported while we're checking 'reveal.types'), treat the parent as used.
        # The inverse — parent imported therefore child is used — is NOT valid:
        # `import testpkg` does not make `testpkg.orphan` available.
        for imp in all_imports:
            if imp.startswith(module_name + '.'):
                return True

        # Check if referenced in __init__.py __all__
        init_file = path.parent / '__init__.py'
        if init_file.exists():
            try:
                init_content = init_file.read_text(encoding='utf-8')
                if path.stem in init_content:
                    return True
            except (OSError, UnicodeDecodeError):
                pass

        return False

    def _has_meaningful_code(self, content: str) -> bool:
        """Check if file has more than just comments and docstrings."""
        try:
            tree = ast.parse(content)
            # Check for any non-trivial content
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef, ast.Import, ast.ImportFrom,
                                     ast.Assign, ast.AugAssign)):
                    return True
            return False
        except SyntaxError:
            # If it can't parse, probably has code
            return len(content.strip()) > 100
