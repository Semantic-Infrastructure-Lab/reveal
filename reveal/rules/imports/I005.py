"""I005: Duplicate imports detector.

Detects when the same import statement appears multiple times in a file.
Common in test files where imports are repeated inside test methods.
"""

import logging
from collections import defaultdict
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity, RuleScope
from ...analyzers.imports.base import get_all_extensions, get_extractor

logger = logging.getLogger(__name__)


def _initialize_file_patterns():
    """Get all supported file extensions from registered extractors."""
    return list(get_all_extensions())


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
    scope = RuleScope.FILE
    message = "Duplicate import statement"
    category = RulePrefix.I
    severity = Severity.LOW  # Low severity - cosmetic issue
    file_patterns = _initialize_file_patterns()
    version = "1.0.0"

    def check(self, file_path: str, structure: Optional[Dict[str, Any]], content: str) -> List[Detection]:
        """Check for duplicate imports in the file.

        Args:
            file_path: Path to the file being analyzed
            structure: File structure from analyzer
            content: File content lines (unused for this rule)

        Returns:
            List of detections for duplicate imports
        """
        detections: List[Detection] = []

        from pathlib import Path
        path = Path(file_path)

        # For on-disk Python files, use ImportStatement objects which carry
        # is_type_checking — TYPE_CHECKING imports must not be counted as the
        # canonical "first" occurrence when flagging function-body imports as
        # duplicates (they are never executed at runtime).
        import_occurrences: defaultdict = defaultdict(list)
        used_extractor = False
        if path.exists():
            extractor = get_extractor(path)
            if extractor:
                extracted: List[Any] = []
                try:
                    for stmt in extractor.extract_imports(path):
                        if stmt.is_type_checking:
                            continue
                        normalized = ' '.join(stmt.source_line.split()).lower() if stmt.source_line else None
                        if not normalized:
                            continue
                        extracted.append((normalized, stmt.line_number, stmt.source_line.strip()))
                    for normalized, line_number, source in extracted:
                        import_occurrences[normalized].append((line_number, source))
                    used_extractor = True
                except Exception as e:  # boundary-ok: broad-except -- the extractor walks tree-sitter nodes of arbitrary user source (native binding, no enumerable error set); one file must not end the run, the fallback below still checks it from the structure, and the degraded path is recorded as this rule's unavailable outcome
                    # A real extractor crash must not look identical to "no
                    # extractor for this language". Nothing from the failed pass is
                    # kept (the fallback would count the same import twice).
                    logger.warning(f"I005: import extractor failed for {file_path}: {e}")
                    self.unavailable(
                        f"import extractor failed ({type(e).__name__}: {e}); "
                        f"checked from the structure's import list instead", file_path)

        if not used_extractor:
            # Fallback: use structure dict (non-Python files, non-existent paths, or extractor failure)
            if not structure:
                return detections
            imports = structure.get('imports', [])
            if not imports:
                return detections
            for imp in imports:
                statement = self._normalize_import(imp)
                if not statement:
                    continue
                line = imp.get('line') or imp.get('line_start', 0)
                display = imp.get('content', '') or imp.get('statement', '') or statement
                import_occurrences[statement].append((line, display))

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
        # Get the import statement.
        # Priority: content (Python analyzer) > statement (JS/Go) > source (Rust)
        statement = imp.get('content', '') or imp.get('statement', '') or imp.get('source', '')
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
