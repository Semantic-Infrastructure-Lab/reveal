"""I005: Duplicate imports detector.

Detects when the same import statement appears multiple times in a file.
Common in test files where imports are repeated inside test methods.
"""

import logging
from collections import defaultdict
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports.base import get_all_extensions

logger = logging.getLogger(__name__)


def _initialize_file_patterns():
    """Get all supported file extensions from registered extractors."""
    try:
        return list(get_all_extensions())
    except Exception:
        # Fallback to common extensions if registry not yet initialized
        return ['.py', '.js', '.go', '.rs', '.ts', '.tsx']


class I005(BaseRule):
    """Detect duplicate import statements in supported languages.

    Identifies when the same import appears multiple times at the top level
    of a file.

    Note: Currently only detects duplicate top-level imports. Does not detect
    imports inside functions/methods (requires deeper AST analysis).

    Example (Python):
        # Bad - same import twice at top level
        from module import Class  # First import
        from other import Thing
        from module import Class  # I005 (duplicate)

        # Good - import once
        from module import Class
        from other import Thing

    Future enhancement: Detect imports inside functions (requires AST traversal)
    """

    code = "I005"
    message = "Duplicate import statement"
    category = RulePrefix.I
    severity = Severity.LOW  # Low severity - cosmetic issue
    file_patterns = _initialize_file_patterns()
    version = "1.0.0"

    def check(self, file_path: str, structure: Dict[str, Any], content: List[str]) -> List[Detection]:
        """Check for duplicate imports in the file.

        Args:
            file_path: Path to the file being analyzed
            structure: File structure from analyzer
            content: File content lines (unused for this rule)

        Returns:
            List of detections for duplicate imports
        """
        detections: List[Detection] = []

        # Get imports from structure
        imports = structure.get('imports', [])
        if not imports:
            return detections

        # Track import statements and their locations
        # Key: normalized import statement, Value: list of (line, statement)
        import_occurrences = defaultdict(list)

        for imp in imports:
            # Normalize the import statement for comparison
            statement = self._normalize_import(imp)
            if not statement:
                continue

            line = imp.get('line') or imp.get('line_start', 0)
            import_occurrences[statement].append((line, imp.get('statement', statement)))

        # Find duplicates (imports that appear more than once)
        for statement, occurrences in import_occurrences.items():
            if len(occurrences) <= 1:
                continue

            # Sort by line number
            occurrences.sort(key=lambda x: x[0])

            # First occurrence is OK, subsequent ones are duplicates
            first_line = occurrences[0][0]
            original_statement = occurrences[0][1]

            for line, dup_statement in occurrences[1:]:
                detections.append(Detection(
                    file_path=file_path,
                    line=line,
                    rule_code=self.code,
                    message=f"Duplicate import: '{original_statement}' (first imported at line {first_line})",
                    severity=self.severity,
                    category=self.category,
                    suggestion=f'Remove duplicate. Already imported at line {first_line}',
                    context=dup_statement
                ))

        return detections

    def _normalize_import(self, imp: Dict[str, Any]) -> Optional[str]:
        """Normalize an import for comparison.

        Strips whitespace and standardizes format so that:
        - 'from foo import bar' matches '  from foo import bar'
        - 'import foo' matches 'import    foo'

        Args:
            imp: Import dict from structure

        Returns:
            Normalized import statement or None
        """
        # Get the import statement
        statement = imp.get('statement') or imp.get('source', '')
        if not statement:
            # Try to reconstruct from module/symbol
            module = imp.get('module', '')
            symbol = imp.get('symbol', '')
            if module and symbol:
                statement = f"from {module} import {symbol}"
            elif module:
                statement = f"import {module}"
            else:
                return None

        # Normalize whitespace
        # Convert multiple spaces to single space
        normalized = ' '.join(statement.split())

        return normalized.lower()  # Case-insensitive comparison


# Rule instance for registry
rule = I005()
