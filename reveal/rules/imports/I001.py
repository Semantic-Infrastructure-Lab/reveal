"""I001: Unused imports detector.

Detects imports that are never used in the code.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports.python import extract_python_imports, extract_python_symbols

logger = logging.getLogger(__name__)


class I001(BaseRule):
    """Detect unused imports in Python code."""

    code = "I001"
    message = "Unused import detected"
    category = RulePrefix.I
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    version = "1.0.0"

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
            # Extract imports and symbols used
            imports = extract_python_imports(path)
            symbols_used = extract_python_symbols(path)
        except Exception as e:
            logger.debug(f"Failed to analyze {file_path}: {e}")
            return detections

        # Check each import for usage
        for stmt in imports:
            # Skip star imports (can't reliably detect usage)
            if stmt.import_type == 'star_import':
                continue

            unused_names = []

            if stmt.imported_names:
                # from X import Y, Z - check if Y or Z are used
                for name in stmt.imported_names:
                    actual_name = name.split(' as ')[-1] if ' as ' in name else name
                    if actual_name not in symbols_used:
                        unused_names.append(name)  # Keep original name with alias

                # Create detection if ALL imported names are unused
                if len(unused_names) == len(stmt.imported_names):
                    import_str = f"from {stmt.module_name} import {', '.join(stmt.imported_names)}"
                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=stmt.line_number,
                        column=1,
                        suggestion=f"Remove unused import: {import_str}",
                        context=import_str
                    ))
            else:
                # import X or import X as Y - check if used
                check_name = stmt.alias or stmt.module_name.split('.')[0]
                if check_name not in symbols_used:
                    import_str = f"import {stmt.module_name}"
                    if stmt.alias:
                        import_str += f" as {stmt.alias}"

                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=stmt.line_number,
                        column=1,
                        suggestion=f"Remove unused import: {import_str}",
                        context=import_str
                    ))

        return detections
