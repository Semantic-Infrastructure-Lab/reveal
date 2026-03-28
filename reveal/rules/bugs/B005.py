"""B005: Dead import detector.

Detects import statements that reference modules that don't exist or can't be resolved.
This catches orphaned imports left behind after refactoring.
"""

import ast
from pathlib import Path
from typing import List, Dict, Any, Optional
from importlib.util import find_spec

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin
from ..imports import STDLIB_MODULES


class B005(BaseRule, ASTParsingMixin):
    """Detect imports referencing non-existent modules."""

    code = "B005"
    message = "Import references non-existent or unresolvable module"
    category = RulePrefix.B
    severity = Severity.HIGH
    file_patterns = ['.py']
    version = "1.0.0"

    def _check_import_statement(self,
                                node: ast.Import,
                                file_path: str,
                                file_dir: Path) -> List[Detection]:
        """Check 'import X' statement for dead imports.

        Args:
            node: AST Import node
            file_path: Path to the file being checked
            file_dir: Directory containing the file

        Returns:
            List of detections for dead imports
        """
        detections: List[Detection] = []
        for alias in node.names:
            module_name = alias.name.split('.')[0]
            if not self._module_exists(module_name, file_dir):
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"Import '{alias.name}' references non-existent module",
                    suggestion=f"Remove unused import or install missing package '{module_name}'",
                    context=f"import {alias.name}"
                ))
        return detections

    def _check_from_import_statement(self,
                                     node: ast.ImportFrom,
                                     file_path: str,
                                     file_dir: Path) -> List[Detection]:
        """Check 'from X import Y' statement for dead imports.

        Args:
            node: AST ImportFrom node
            file_path: Path to the file being checked
            file_dir: Directory containing the file

        Returns:
            List of detections for dead imports
        """
        detections: List[Detection] = []

        if not node.module:
            return detections

        # Handle relative imports
        if node.level > 0:
            if not self._relative_import_exists(node, file_path):
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"Relative import '{'.' * node.level}{node.module or ''}' cannot be resolved",
                    suggestion="Check that the referenced module exists in the package",
                    context=f"from {'.' * node.level}{node.module or ''} import ..."
                ))
        else:
            # Absolute import
            module_name = node.module.split('.')[0]
            if not self._module_exists(module_name, file_dir):
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"Import from '{node.module}' references non-existent module",
                    suggestion=f"Remove unused import or install missing package '{module_name}'",
                    context=f"from {node.module} import ..."
                ))

        return detections

    def _find_optional_import_lines(self, tree: ast.AST) -> set:
        """Return line numbers of imports inside try/except ImportError blocks.

        The try/except ImportError pattern is canonical Python for optional
        dependencies. Imports in these blocks should not be flagged as broken.
        """
        optional_lines: set = set()

        def _handler_catches_import_error(handler: ast.ExceptHandler) -> bool:
            if handler.type is None:
                return True  # bare except — assume it covers ImportError
            if isinstance(handler.type, ast.Name):
                return handler.type.id in ('ImportError', 'ModuleNotFoundError')
            if isinstance(handler.type, ast.Tuple):
                return any(
                    isinstance(el, ast.Name) and el.id in ('ImportError', 'ModuleNotFoundError')
                    for el in handler.type.elts
                )
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                if any(_handler_catches_import_error(h) for h in node.handlers):
                    for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                        if isinstance(child, (ast.Import, ast.ImportFrom)):
                            optional_lines.add(child.lineno)

        return optional_lines

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """
        Check for imports that reference non-existent modules.

        Args:
            file_path: Path to Python file
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections for dead imports
        """
        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        optional_lines = self._find_optional_import_lines(tree)
        file_dir = Path(file_path).parent
        for node in self._ast_walk(tree):
            if getattr(node, 'lineno', None) in optional_lines:
                continue
            if isinstance(node, ast.Import):
                detections.extend(self._check_import_statement(node, file_path, file_dir))
            elif isinstance(node, ast.ImportFrom):
                detections.extend(self._check_from_import_statement(node, file_path, file_dir))

        return detections

    def _module_exists(self, module_name: str, file_dir: Path) -> bool:
        """Check if a module exists."""
        # Skip stdlib modules
        if module_name in STDLIB_MODULES:
            return True

        # Check if it's a local module (file in same directory or package)
        if (file_dir / f"{module_name}.py").exists():
            return True
        if (file_dir / module_name / "__init__.py").exists():
            return True

        # Try to find the module spec
        try:
            spec = find_spec(module_name)
            return spec is not None
        except (ModuleNotFoundError, ValueError, ImportError):
            return False

    def _relative_import_exists(self, node: ast.ImportFrom, file_path: str) -> bool:
        """Check if a relative import can be resolved."""
        file_dir = Path(file_path).parent

        # Go up 'level' directories
        target_dir = file_dir
        for _ in range(node.level - 1):
            target_dir = target_dir.parent

        if node.module:
            # from .foo import bar -> check for foo.py or foo/
            parts = node.module.split('.')
            for part in parts:
                if (target_dir / f"{part}.py").exists():
                    return True
                if (target_dir / part).is_dir():
                    target_dir = target_dir / part
                else:
                    return False
            return True
        else:
            # from . import foo -> check __init__.py exists
            return (target_dir / "__init__.py").exists()
