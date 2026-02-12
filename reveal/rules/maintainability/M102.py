"""M102: Orphan file detector.

Detects Python files that are not imported anywhere in the package.
These are often dead code left behind after refactoring.
"""

import ast
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


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
                        f"This file may be dead code. If intentional (entry point, plugin), "
                        f"add to __all__ in __init__.py or rename to indicate purpose. "
                        f"Otherwise, consider removing this orphaned module."
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
        """Find the root of the Python package."""
        current = path.parent

        # Walk up looking for package markers
        for _ in range(10):  # Max 10 levels up
            if (current / 'pyproject.toml').exists():
                return current
            if (current / 'setup.py').exists():
                return current
            if (current / '__init__.py').exists():
                # Keep going up while we're in a package
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
        """Collect all imports from all Python files in the package."""
        imports = set()

        for py_file in package_root.rglob('*.py'):
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.add(alias.name)
                            # Add parent modules
                            parts = alias.name.split('.')
                            for i in range(len(parts)):
                                imports.add('.'.join(parts[:i+1]))

                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.add(node.module)
                            # Add parent modules
                            parts = node.module.split('.')
                            for i in range(len(parts)):
                                imports.add('.'.join(parts[:i+1]))

            except (SyntaxError, UnicodeDecodeError, OSError):
                continue

        return imports

    def _is_imported(self, module_name: str, all_imports: Set[str],
                     path: Path, package_root: Path) -> bool:
        """Check if module is imported anywhere."""
        # Direct import check
        if module_name in all_imports:
            return True

        # Check partial matches (e.g., 'reveal.types' when looking for 'reveal.types.python')
        for imp in all_imports:
            if imp.startswith(module_name + '.') or module_name.startswith(imp + '.'):
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
