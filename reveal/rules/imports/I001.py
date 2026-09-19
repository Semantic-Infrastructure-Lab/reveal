"""I001: Unused imports detector.

Detects imports that are never used in the code.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports.base import get_extractor, get_all_extensions
from ...analyzers.imports.unused import bound_name, is_named_import, unused_entries

logger = logging.getLogger(__name__)


# Initialize file patterns from all registered extractors at module load time
def _initialize_file_patterns():
    """Get all supported file extensions from registered extractors."""
    try:
        return list(get_all_extensions())
    except Exception:
        # Fallback to common extensions if registry not yet initialized
        return ['.py', '.js', '.go', '.rs']


class I001(BaseRule):
    """Detect unused imports in supported languages (Python, JavaScript, Go, Rust)."""

    code = "I001"
    message = "Unused import detected"
    category = RulePrefix.I
    severity = Severity.MEDIUM
    file_patterns = _initialize_file_patterns()  # Populated at module load time
    version = "2.0.0"

    def _detections_for(self, stmt, symbols_used: set, exports: set, file_path: str) -> List[Detection]:
        """One detection per unused name (matches Ruff F401); the decision itself
        lives in analyzers/imports/unused.py, shared with imports://?unused."""
        detections: List[Detection] = []
        for entry in unused_entries(stmt, symbols_used, frozenset(exports)):
            if is_named_import(stmt):
                context = f"from {stmt.module_name} import {entry}"
                suggestion = f"Remove unused import: `{bound_name(entry)}`"
            else:
                context = f"import {stmt.module_name}"
                if stmt.alias:
                    context += f" as {stmt.alias}"
                suggestion = f"Remove unused import: {context}"
            detections.append(self.create_detection(
                file_path=file_path,
                line=stmt.line_number,
                column=1,
                suggestion=suggestion,
                context=context,
            ))
        return detections

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for unused imports in supported languages.

        Args:
            file_path: Path to source file (Python, JavaScript, Go, Rust)
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections for unused imports
        """
        detections: List[Detection] = []
        path = Path(file_path)

        # __init__.py imports are public API / side-effect registrations — skip
        if path.name == '__init__.py':
            return detections

        # Get language-specific extractor
        extractor = get_extractor(path)
        if not extractor:
            logger.debug(f"No extractor found for {file_path}")
            return detections

        try:
            # Extract imports and symbols used (common to all languages)
            imports = extractor.extract_imports(path)
            symbols_used = extractor.extract_symbols(path)

            # Extract exports (__all__ for Python, not applicable to other languages yet)
            exports = set()
            if hasattr(extractor, 'extract_exports'):
                exports = extractor.extract_exports(path)
        except Exception as e:
            logger.warning(f"I001: failed to analyze {file_path}: {e}")
            return detections

        # BACK-982: a parse failure makes extract_symbols() return an empty
        # set indistinguishable from "genuinely uses nothing" -- comparing
        # imports against that would flag every import in the file as unused
        # (a false positive, not a missing result). Skip rather than report.
        if extractor.parse_failed:
            logger.warning(
                "I001: %s failed to parse -- skipping unused-import check "
                "(result would be unreliable, not confirmed clean)",
                file_path,
            )
            return detections

        for stmt in imports:
            detections.extend(self._detections_for(stmt, symbols_used, exports, file_path))

        return detections
