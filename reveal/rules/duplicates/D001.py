"""D001: Detect duplicate functions via normalized AST hashing.

Abusively lean approach:
- Normalize function body (strip whitespace, comments)
- Hash normalized content
- O(n) time, O(n) space where n = number of functions
- Zero new dependencies (stdlib only)

Performance:
- Single file: ~1-5ms for typical files
- Cross-file: Deferred (needs caching strategy)
"""

import logging
from typing import List, Dict, Any, Optional
from hashlib import sha256
import re

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class D001(BaseRule):
    """Detect exact duplicate functions (normalized)."""

    code = "D001"
    message = "Duplicate function detected"
    category = RulePrefix.D
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Works on any language with functions
    version = "1.0.0"

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Find duplicate functions within a single file.

        Args:
            file_path: Path to file
            structure: Parsed structure from reveal analyzer
            content: File content

        Returns:
            List of detections for duplicates
        """
        if not structure or 'functions' not in structure:
            return []
        functions = structure['functions']
        if len(functions) < 2:
            return []
        classes = structure.get('classes', [])
        scope_hashes = self._build_scope_hashes(functions, classes, content)
        return self._emit_duplicates(scope_hashes, file_path)

    def _build_scope_hashes(
        self, functions: list, classes: list, content: str
    ) -> Dict[str, Dict[str, list]]:
        """Hash each function body grouped by containing class scope."""
        from collections import defaultdict

        def class_for(line: int) -> Optional[str]:
            for cls in classes:
                if cls.get('line', 0) <= line <= cls.get('line_end', 0):
                    return str(cls.get('name')) if cls.get('name') is not None else None
            return None

        scope_hashes: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for func in functions:
            func_body = self._extract_function_body(func, content)
            if not func_body or len(func_body.strip()) < 10:
                continue
            normalized = self._normalize(func_body)
            if not normalized:
                continue
            func_hash = sha256(normalized.encode('utf-8')).hexdigest()[:16]
            scope = class_for(func.get('line', 0)) or '__module__'
            scope_hashes[scope][func_hash].append((
                func.get('name', '<unknown>'), func.get('line', 0), len(func_body)
            ))
        return scope_hashes

    def _emit_duplicates(
        self, scope_hashes: Dict[str, Dict[str, list]], file_path: str
    ) -> List[Detection]:
        """Report duplicate functions found within each scope."""
        detections: List[Detection] = []
        for _scope, hash_to_funcs in scope_hashes.items():
            for func_hash, instances in hash_to_funcs.items():
                if len(instances) < 2:
                    continue
                instances.sort(key=lambda x: x[1])
                original = instances[0]
                for duplicate in instances[1:]:
                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=duplicate[1],
                        message=f"{self.message}: '{duplicate[0]}' identical to '{original[0]}' (line {original[1]})",
                        suggestion=f"Refactor to share implementation with {original[0]}",
                        context=f"{duplicate[2]} chars, hash {func_hash}"
                    ))
        return detections

    def _extract_function_body(self, func: Dict, content: str) -> str:
        """
        Extract function body from content using line numbers.

        Skips the function definition line (def/func/function) to focus on body only.
        This allows detecting duplicates even when parameter names differ.

        Args:
            func: Function metadata from structure
            content: File content

        Returns:
            Function body as string (without signature line)
        """
        start = func.get('line', 0)
        end = func.get('line_end', start)  # Note: field is 'line_end' not 'end_line'

        if start == 0 or end == 0:
            return ""

        lines = content.splitlines()
        if start > len(lines) or end > len(lines):
            return ""

        # Extract function body, skipping the signature line
        # This makes duplicates detectable even with different parameter names
        # start+1 because line numbers are 1-indexed, and we want to skip def/func line
        body_lines = lines[start:end]  # Skip first line (signature)

        if not body_lines:
            return ""

        return '\n'.join(body_lines)

    def _normalize(self, code: str) -> str:
        """
        Normalize code to detect semantic duplicates.

        Removes:
        - Comments (all common styles)
        - Docstrings (Python triple quotes)
        - Whitespace variations
        - Empty lines

        Preserves:
        - Control flow structure
        - Operators
        - Identifiers (for now - stricter normalization can rename vars)
        - Literals

        Args:
            code: Raw function body

        Returns:
            Normalized code string
        """
        # Remove single-line comments
        # Python, Ruby, Shell: # comment
        code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        # C, JS, Rust, Go: // comment
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)

        # Remove multi-line comments
        # C, JS: /* comment */
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

        # Remove docstrings (Python)
        # Only remove standalone docstrings (at start of line), not string literals
        # in return statements, assignments, etc.
        code = re.sub(r'^\s*""".*?"""', '', code, flags=re.DOTALL | re.MULTILINE)
        code = re.sub(r"^\s*'''.*?'''", '', code, flags=re.DOTALL | re.MULTILINE)

        # Normalize whitespace
        # Collapse multiple spaces to single space
        code = re.sub(r'[ \t]+', ' ', code)
        # Remove empty lines
        code = re.sub(r'\n\s*\n', '\n', code)
        # Strip leading/trailing whitespace per line
        lines = [line.strip() for line in code.splitlines()]
        code = '\n'.join(lines)

        return code.strip()
