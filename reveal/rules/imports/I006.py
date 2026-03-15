"""I006: Import inside function body detector.

Detects imports placed inside function or method bodies when they could
be at the module top level. The motivating case was ssl/adapter.py, where
NginxAnalyzer was imported three times inside separate methods.

Example:
    # Bad
    def process():
        import json  # I006 - should be at module top
        return json.dumps({})

    # OK - circular import avoidance is legitimate, but prefer a comment
    def _fetch():
        from .heavy_module import Widget  # intentional lazy load
"""

import logging
from typing import List, Dict, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class I006(BaseRule):
    """Detect imports placed inside function or method bodies.

    Imports inside functions are occasionally necessary (circular import
    avoidance, optional heavy dependencies), but most of the time they
    are accidental and belong at the module top level.

    Exceptions — skipped without flagging:
    - ``from __future__ import`` (must be at module top; parser handles it)
    - Import line contains ``# noqa`` or ``# noqa: I006``
    - The enclosing function name contains 'lazy' or 'import' (signals
      intentional lazy-loading, e.g. ``_lazy_import``, ``_get_module``)
    - The import content contains ``TYPE_CHECKING`` (type-hint-only guard)
    - The enclosing function name contains ``type_checking``

    Example (Python):
        # Bad
        def process():
            import json  # I006 - should be at module top
            return json.dumps({})

        # OK - intentional lazy load
        def _lazy_import_heavy():
            from .heavy_module import Widget
            return Widget()
    """

    code = "I006"
    message = "Import inside function body"
    category = RulePrefix.I
    severity = Severity.LOW
    file_patterns = ['.py']  # Python-only: other languages rarely have this pattern
    version = "1.0.0"

    # Suggestion shown alongside every detection
    _SUGGESTION = "Move to module top unless needed for circular import avoidance"

    def _build_function_ranges(self, functions: List[Dict[str, Any]]) -> List[Tuple[int, int, str]]:
        """Build a list of (start_line, end_line, function_name) tuples.

        Args:
            functions: List of function dicts from structure, each with
                       'line' (start), 'line_end' (end), and 'name' keys.

        Returns:
            List of (start, end, name) tuples for range membership tests.
        """
        ranges: List[Tuple[int, int, str]] = []
        for func in functions:
            start = func.get('line', 0)
            end = func.get('line_end', 0)
            name = func.get('name', '') or ''
            if start and end and start <= end:
                ranges.append((start, end, name))
        return ranges

    def _find_enclosing_function(
        self,
        import_line: int,
        ranges: List[Tuple[int, int, str]],
    ) -> Optional[Tuple[int, int, str]]:
        """Return the innermost function range that contains import_line.

        If nested functions exist the innermost (smallest span) wins,
        which is the most accurate scope.

        Args:
            import_line: 1-based line number of the import statement.
            ranges: List of (start, end, name) tuples from _build_function_ranges.

        Returns:
            (start, end, name) of the enclosing function, or None.
        """
        best: Optional[Tuple[int, int, str]] = None
        best_span = float('inf')
        for start, end, name in ranges:
            if start <= import_line <= end:
                span = end - start
                if span < best_span:
                    best_span = span
                    best = (start, end, name)
        return best

    def _is_exception(self, import_content: str, func_name: str) -> bool:
        """Return True if this inline import should be silently skipped.

        Args:
            import_content: Raw import line text (may include comments).
            func_name: Name of the enclosing function.

        Returns:
            True if the import qualifies for an exception.
        """
        content_lower = import_content.lower()
        func_lower = func_name.lower()

        # from __future__ import — must stay at top; parser places it correctly
        if '__future__' in content_lower:
            return True

        # noqa suppression
        if '# noqa' in import_content:
            return True

        # TYPE_CHECKING guard in the import line itself
        if 'type_checking' in content_lower:
            return True

        # Function is a known lazy-loading helper
        if 'lazy' in func_lower or 'import' in func_lower:
            return True

        # Function name signals a TYPE_CHECKING scope
        if 'type_checking' in func_lower:
            return True

        return False

    def check(
        self,
        file_path: str,
        structure: Optional[Dict[str, Any]],
        content: str,
    ) -> List[Detection]:
        """Check for imports placed inside function bodies.

        Args:
            file_path: Path to the Python file being analyzed.
            structure: Parsed file structure from the analyzer. Expected keys:
                       'imports' — list of dicts with 'line' and 'content'.
                       'functions' — list of dicts with 'line', 'line_end', 'name'.
            content: Raw file content (unused; structure carries what we need).

        Returns:
            List of Detection objects, one per flagged inline import.
        """
        detections: List[Detection] = []

        if not structure:
            return detections

        imports = structure.get('imports', [])
        functions = structure.get('functions', [])

        if not imports or not functions:
            # No imports or no functions → nothing can be inside a function
            return detections

        # Build function ranges once; reused for every import
        ranges = self._build_function_ranges(functions)
        if not ranges:
            return detections

        for imp in imports:
            import_line: int = imp.get('line', 0)
            if not import_line:
                continue

            import_content: str = imp.get('content', '') or ''

            # Check if this import falls inside any function body
            enclosing = self._find_enclosing_function(import_line, ranges)
            if enclosing is None:
                continue  # Top-level import — fine

            _start, _end, func_name = enclosing

            # Apply exception rules before flagging
            if self._is_exception(import_content, func_name):
                continue

            detections.append(Detection(
                file_path=file_path,
                line=import_line,
                rule_code=self.code,
                message=f"{self.message} (inside '{func_name}')",
                severity=self.severity,
                category=self.category,
                suggestion=self._SUGGESTION,
                context=import_content.strip(),
            ))

        return detections


# Rule instance for registry
rule = I006()
