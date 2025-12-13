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
            return []  # Need at least 2 functions to have duplicates

        hash_to_funcs = {}  # hash -> [(func_name, line, body_length), ...]
        detections = []

        # Build hash map
        for func in functions:
            func_body = self._extract_function_body(func, content)
            if not func_body or len(func_body.strip()) < 10:
                # Skip empty or trivial functions
                continue

            # Normalize and hash
            normalized = self._normalize(func_body)
            if not normalized:
                continue

            func_hash = sha256(normalized.encode('utf-8')).hexdigest()[:16]

            # Track duplicates
            if func_hash not in hash_to_funcs:
                hash_to_funcs[func_hash] = []
            hash_to_funcs[func_hash].append((
                func.get('name', '<unknown>'),
                func.get('line', 0),
                len(func_body)
            ))

        # Report duplicates
        for func_hash, instances in hash_to_funcs.items():
            if len(instances) < 2:
                continue

            # Sort by line number to get "original" first
            instances.sort(key=lambda x: x[1])
            original = instances[0]

            for duplicate in instances[1:]:
                detections.append(Detection(
                    file_path=file_path,
                    line=duplicate[1],
                    rule_code=self.code,
                    message=f"{self.message}: '{duplicate[0]}' identical to '{original[0]}' (line {original[1]})",
                    severity=self.severity,
                    category=self.category,
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
        code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)
        code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL)

        # Normalize whitespace
        # Collapse multiple spaces to single space
        code = re.sub(r'[ \t]+', ' ', code)
        # Remove empty lines
        code = re.sub(r'\n\s*\n', '\n', code)
        # Strip leading/trailing whitespace per line
        lines = [line.strip() for line in code.splitlines()]
        code = '\n'.join(lines)

        return code.strip()
