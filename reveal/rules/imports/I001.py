"""I001: Unused imports detector.

Detects imports that are never used in the code.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports.python import PythonExtractor

logger = logging.getLogger(__name__)


class I001(BaseRule):
    """Detect unused imports in Python code."""

    code = "I001"
    message = "Unused import detected"
    category = RulePrefix.I
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    version = "1.0.0"

    def _has_noqa_comment(self, source_line: str) -> bool:
        """Check if source line has a noqa comment.

        Detects patterns like:
        - # noqa
        - # noqa: F401
        - # noqa: I001
        - # noqa: F401, I001

        Args:
            source_line: Full source line text

        Returns:
            True if line has noqa comment (generic or specific to F401/I001)
        """
        if not source_line:
            return False

        comment_lower = source_line.lower()
        if '# noqa' not in comment_lower:
            return False

        # Generic noqa (no colon) or specific F401/I001
        return ':' not in comment_lower or 'f401' in comment_lower or 'i001' in comment_lower

    def _should_skip_import(self, stmt) -> bool:
        """Check if import should be skipped from unused detection.

        Args:
            stmt: ImportStatement to check

        Returns:
            True if import should be skipped (star import, TYPE_CHECKING, or has noqa)
        """
        # Skip star imports (can't reliably detect usage)
        if stmt.import_type == 'star_import':
            return True

        # Skip TYPE_CHECKING imports (used only in type hints)
        if stmt.is_type_checking:
            return True

        # Skip imports with # noqa comments
        if self._has_noqa_comment(stmt.source_line):
            return True

        return False

    def _check_from_import(self,
                          stmt,
                          symbols_used: set,
                          exports: set,
                          file_path: str) -> List[Detection]:
        """Check if 'from X import Y' style import has unused names.

        Args:
            stmt: ImportStatement to check
            symbols_used: Set of symbols used in the code
            exports: Set of symbols in __all__
            file_path: Path to the file being checked

        Returns:
            List of detections for each unused import name (matches Ruff F401)
        """
        detections = []

        if not stmt.imported_names:
            return detections

        # Check each imported name individually (aligned with Ruff F401)
        for name in stmt.imported_names:
            actual_name = name.split(' as ')[-1] if ' as ' in name else name
            # Check if used in code OR exported via __all__
            if actual_name not in symbols_used and actual_name not in exports:
                import_str = f"from {stmt.module_name} import {name}"
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=stmt.line_number,
                    column=1,
                    suggestion=f"Remove unused import: `{actual_name}`",
                    context=import_str
                ))

        return detections

    def _check_regular_import(self,
                             stmt,
                             symbols_used: set,
                             exports: set,
                             file_path: str) -> Optional[Detection]:
        """Check if 'import X' style import is unused.

        Args:
            stmt: ImportStatement to check
            symbols_used: Set of symbols used in the code
            exports: Set of symbols in __all__
            file_path: Path to the file being checked

        Returns:
            Detection if import is unused, None otherwise
        """
        # import X or import X as Y - check if used OR exported
        check_name = stmt.alias or stmt.module_name.split('.')[0]
        if check_name not in symbols_used and check_name not in exports:
            import_str = f"import {stmt.module_name}"
            if stmt.alias:
                import_str += f" as {stmt.alias}"

            return self.create_detection(
                file_path=file_path,
                line=stmt.line_number,
                column=1,
                suggestion=f"Remove unused import: {import_str}",
                context=import_str
            )

        return None

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for unused imports.

        Args:
            file_path: Path to Python file
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections for unused imports
        """
        detections = []
        path = Path(file_path)

        try:
            # Extract imports, symbols used, and exports (__all__)
            extractor = PythonExtractor()
            imports = extractor.extract_imports(path)
            symbols_used = extractor.extract_symbols(path)
            exports = extractor.extract_exports(path)
        except Exception as e:
            logger.debug(f"Failed to analyze {file_path}: {e}")
            return detections

        # Check each import for usage
        for stmt in imports:
            if self._should_skip_import(stmt):
                continue

            # Check import based on type (from-import vs regular import)
            if stmt.imported_names:
                # from-import returns list of detections (one per unused name)
                detections.extend(self._check_from_import(stmt, symbols_used, exports, file_path))
            else:
                detection = self._check_regular_import(stmt, symbols_used, exports, file_path)
                if detection:
                    detections.append(detection)

        return detections
