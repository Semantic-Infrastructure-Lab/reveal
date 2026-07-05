"""B005: Dead import detector.

Detects import statements that reference modules that don't exist or can't be
resolved. This catches orphaned imports left behind after refactoring.

BACK-465: detection is deliberately limited to what is provable from the
filesystem alone — relative imports, and absolute imports of the analyzed
project's *own* packages (resolved against the project root). An absolute
import of a third-party module is NEVER flagged just because it isn't
importable in reveal's own environment: `find_spec` against the analyzer's
venv is not evidence the module doesn't exist for the analyzed project (it
would flag every uninstalled dependency of every external repo). Such imports
are treated as 'unknown' and left alone.
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
                                file_dir: Path,
                                project_root: Path) -> List[Detection]:
        """Check 'import X' statement for dead imports.

        Args:
            node: AST Import node
            file_path: Path to the file being checked
            file_dir: Directory containing the file
            project_root: Resolved project root for same-project resolution

        Returns:
            List of detections for dead imports
        """
        detections: List[Detection] = []
        for alias in node.names:
            module_name = alias.name.split('.')[0]
            if self._absolute_import_status(alias.name, file_dir, project_root) == 'dead':
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"Import '{alias.name}' references a missing project module",
                    suggestion=f"Remove the orphaned import or fix the path '{module_name}'",
                    context=f"import {alias.name}"
                ))
        return detections

    def _check_from_import_statement(self,
                                     node: ast.ImportFrom,
                                     file_path: str,
                                     file_dir: Path,
                                     project_root: Path) -> List[Detection]:
        """Check 'from X import Y' statement for dead imports.

        Args:
            node: AST ImportFrom node
            file_path: Path to the file being checked
            file_dir: Directory containing the file
            project_root: Resolved project root for same-project resolution

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
            if self._absolute_import_status(node.module, file_dir, project_root) == 'dead':
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"Import from '{node.module}' references a missing project module",
                    suggestion=f"Remove the orphaned import or fix the path '{module_name}'",
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
        project_root = self._find_project_root(file_dir)
        for node in self._ast_walk(tree):
            if getattr(node, 'lineno', None) in optional_lines:
                continue
            if isinstance(node, ast.Import):
                detections.extend(self._check_import_statement(
                    node, file_path, file_dir, project_root))
            elif isinstance(node, ast.ImportFrom):
                detections.extend(self._check_from_import_statement(
                    node, file_path, file_dir, project_root))

        return detections

    def _find_project_root(self, file_dir: Path) -> Path:
        """Return the project root: the parent of the topmost package directory.

        Walks up while each directory is a package (has __init__.py). If the
        file isn't inside a package, its own directory is the root. This is
        what lets an absolute import of the project's own package
        (`from homeassistant.core import ...` inside
        homeassistant/components/mqtt/) resolve against the tree on disk
        instead of being flagged (BACK-465).
        """
        current = file_dir
        root = file_dir
        while (current / "__init__.py").exists():
            parent = current.parent
            if parent == current:
                break
            root = parent
            current = parent
        return root

    def _same_project_module(self, dotted: str, project_root: Path) -> Optional[bool]:
        """Resolve an absolute dotted module path against the project root.

        Returns:
            True  — the module resolves on disk under the project root.
            False — the top-level package is part of this project but the full
                    dotted path does not exist (a genuine dead import).
            None  — the top-level package is not part of this project
                    (third-party / unknown; absence cannot be proven).
        """
        parts = dotted.split('.')
        top = parts[0]
        top_is_local = (
            (project_root / top / "__init__.py").exists()
            or (project_root / f"{top}.py").exists()
        )
        if not top_is_local:
            return None

        target = project_root
        for i, part in enumerate(parts):
            pkg_dir = target / part
            if pkg_dir.is_dir() and (pkg_dir / "__init__.py").exists():
                target = pkg_dir  # descend into sub-package
            elif pkg_dir.is_dir():
                target = pkg_dir  # namespace package (no __init__.py) — accept
            elif i == len(parts) - 1 and (target / f"{part}.py").exists():
                return True  # final component is a module file
            else:
                return False  # component missing → same-project dead import
        return True

    def _absolute_import_status(self, dotted: str, file_dir: Path, project_root: Path) -> str:
        """Classify an absolute import as 'exists', 'dead', or 'unknown'.

        'dead' is returned only when absence is provable from the filesystem
        (a same-project module path that doesn't exist). Third-party modules
        not installed in reveal's environment are 'unknown', never 'dead'.
        """
        top = dotted.split('.')[0]
        if top in STDLIB_MODULES:
            return 'exists'

        resolved = self._same_project_module(dotted, project_root)
        if resolved is True:
            return 'exists'
        if resolved is False:
            return 'dead'

        # Not part of this project. A positive find_spec proves existence; a
        # miss proves nothing (dependency may simply be uninstalled here).
        try:
            if find_spec(top) is not None:
                return 'exists'
        except (ModuleNotFoundError, ValueError, ImportError):
            pass
        return 'unknown'

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
