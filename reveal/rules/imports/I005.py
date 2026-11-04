"""I005: Duplicate imports detector.

Detects when the same import statement appears multiple times in a file.
Common in test files where imports are repeated inside test methods.
"""

import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

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

        Two imports are duplicates when they bind the same thing (same kind, module,
        names, alias and relative level), compared case-sensitively, on different lines.
        A grouped import (Rust ``use std::{a, b}``) yields one statement per name on one
        line; the line is never its own duplicate (BACK-2490).
        """
        occurrences = self._occurrences_from_extractor(file_path)
        if occurrences is None:
            occurrences = self._occurrences_from_structure(structure)
        return self._duplicates(occurrences, file_path)

    def _occurrences_from_extractor(self, file_path: str) -> Optional[Dict[Any, List[Tuple[int, str]]]]:
        """Import occurrences keyed by binding, from the language's import extractor.

        None when there is no extractor or it failed (the caller falls back to the
        structure). TYPE_CHECKING imports are skipped: they never run, so they must not
        be the canonical first occurrence of a function-body import.
        """
        path = Path(file_path)
        if not path.exists():
            return None
        extractor = get_extractor(path)
        if not extractor:
            return None
        try:
            statements = [s for s in extractor.extract_imports(path) if not s.is_type_checking]
        except Exception as e:  # boundary-ok: broad-except -- the extractor walks tree-sitter nodes of arbitrary user source (native binding, no enumerable error set); one file must not end the run, the fallback below still checks it from the structure, and the degraded path is recorded as this rule's unavailable outcome
            # A real extractor crash must not look identical to "no extractor for this
            # language". Nothing from the failed pass is kept (the fallback would count
            # the same import twice).
            logger.warning(f"I005: import extractor failed for {file_path}: {e}")
            self.unavailable(
                f"import extractor failed ({type(e).__name__}: {e}); "
                f"checked from the structure's import list instead", file_path)
            return None
        per_line = Counter(s.line_number for s in statements)
        occurrences: Dict[Any, List[Tuple[int, str]]] = defaultdict(list)
        for stmt in statements:
            key = (stmt.import_type, stmt.module_name, tuple(sorted(stmt.imported_names)),
                   stmt.alias, stmt.level)
            source = (stmt.source_line or '').strip()
            # A line holding several statements (a grouped import) is named by the
            # binding; its first source line ('use std::{') says nothing on its own.
            display = source if per_line[stmt.line_number] == 1 and source else stmt.module_name
            occurrences[key].append((stmt.line_number, display))
        return occurrences

    def _occurrences_from_structure(self, structure: Optional[Dict[str, Any]]) -> Dict[Any, List[Tuple[int, str]]]:
        """Import occurrences keyed by normalized statement, from the structure's import list."""
        occurrences: Dict[Any, List[Tuple[int, str]]] = defaultdict(list)
        for imp in (structure or {}).get('imports', None) or []:
            statement = self._normalize_import(imp)
            if not statement:
                continue
            line = imp.get('line') or imp.get('line_start', 0)
            display = imp.get('content', '') or imp.get('statement', '') or statement
            occurrences[statement].append((line, display))
        return occurrences

    def _duplicates(self, occurrences: Dict[Any, List[Tuple[int, str]]], file_path: str) -> List[Detection]:
        """One detection per later line that repeats an earlier line's import."""
        detections: List[Detection] = []
        for found in occurrences.values():
            lines: Dict[int, str] = {}
            for line, display in sorted(found, key=lambda x: x[0]):
                lines.setdefault(line, display)
            if len(lines) <= 1:
                continue
            (first_line, original_statement), *later = lines.items()
            for line, dup_statement in later:
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

        Collapses whitespace so that 'from foo import bar' matches
        '  from foo import  bar'. Case is kept: every supported language's import
        names are case-sensitive (Kotlin 'Dp' and 'dp' are two imports, BACK-2490).

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

        return ' '.join(statement.split())


# Rule instance for registry
rule = I005()
