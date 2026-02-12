"""Windows Batch file analyzer.

Handles .bat and .cmd files for Windows automation scripts.
"""

import re
import logging
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer
from ..registry import register

logger = logging.getLogger(__name__)


@register('.bat', name='Batch', icon='🪟')
@register('.cmd', name='Command', icon='🪟')
class BatchAnalyzer(FileAnalyzer):
    """Windows Batch file analyzer.

    Analyzes Windows batch scripts (.bat, .cmd) for:
    - Labels/subroutines (:label)
    - Environment variables (%VAR%, !VAR!)
    - Key commands (set, call, goto, if, for)

    Common uses: Windows automation, build scripts, deployment.

    Structure view shows:
    - Labels (subroutines/jump targets)
    - Variable assignments
    - External calls
    - Script statistics

    Extract by label name to view subroutine contents.
    """

    # Regex patterns for batch file parsing
    LABEL_PATTERN = re.compile(r'^:(\w+)', re.MULTILINE)
    SET_PATTERN = re.compile(r'^\s*set\s+["\']*(\w+)\s*=', re.MULTILINE | re.IGNORECASE)
    CALL_PATTERN = re.compile(r'\bcall\s+:(\w+)', re.IGNORECASE)
    CALL_EXTERNAL_PATTERN = re.compile(r'\bcall\s+([^\s:][^\s]*)', re.IGNORECASE)
    GOTO_PATTERN = re.compile(r'\bgoto\s+:?(\w+)', re.IGNORECASE)
    ECHO_OFF_PATTERN = re.compile(r'^\s*@?echo\s+off', re.IGNORECASE)
    SETLOCAL_PATTERN = re.compile(r'\bsetlocal\b', re.IGNORECASE)
    REM_PATTERN = re.compile(r'^\s*(?:rem\s|::)', re.IGNORECASE)

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract batch file structure.

        Args:
            head: Show first N labels
            tail: Show last N labels
            range: Show labels in range (start, end) - 1-indexed
            **kwargs: Additional parameters (unused)

        Returns:
            Dict with labels, variables, calls, and statistics
        """
        # Extract labels with their line numbers and content
        labels = self._extract_labels()
        variables = self._extract_variables()
        internal_calls = self._extract_internal_calls()
        external_calls = self._extract_external_calls()

        # Apply filtering if requested
        if head is not None:
            labels = labels[:head]
        elif tail is not None:
            labels = labels[-tail:]
        elif range is not None:
            start, end = range
            labels = labels[start-1:end]

        # Calculate statistics
        stats = self._calculate_stats()

        return {
            'functions': labels,  # Labels are the "functions" in batch
            'variables': variables,
            'internal_calls': internal_calls,
            'external_calls': external_calls,
            'stats': stats,  # Named 'stats' to be skipped by _render_text_categories
        }

    def _extract_labels(self) -> List[Dict[str, Any]]:
        """Extract all labels from batch file.

        Returns:
            List of label dictionaries with name, line, and end_line
        """
        labels = []
        lines = self.content.split('\n')

        for i, line in enumerate(lines, start=1):
            match = self.LABEL_PATTERN.match(line.strip())
            if match:
                label_name = match.group(1).lower()
                # Skip special labels
                if label_name in ('eof',):
                    continue

                # Find end of label (next label or end of file)
                end_line = len(lines)
                for j in range(i, len(lines)):
                    next_line = lines[j].strip()
                    if j > i - 1 and self.LABEL_PATTERN.match(next_line):
                        end_line = j
                        break

                labels.append({
                    'name': label_name,
                    'line': i,
                    'line_end': end_line,
                    'line_count': end_line - i,
                })

        return labels

    def _extract_variables(self) -> List[Dict[str, Any]]:
        """Extract variable assignments.

        Returns:
            List of variable dictionaries with name and line
        """
        variables = []
        seen_vars = set()

        for match in self.SET_PATTERN.finditer(self.content):
            var_name = match.group(1)
            if var_name.upper() not in seen_vars:
                seen_vars.add(var_name.upper())
                # Calculate line number
                line_num = self.content[:match.start()].count('\n') + 1
                variables.append({
                    'name': var_name,
                    'line': line_num,
                })

        return variables

    def _extract_internal_calls(self) -> List[Dict[str, Any]]:
        """Extract internal subroutine calls (call :label).

        Returns:
            List of call dictionaries with name and line
        """
        calls = []
        seen_calls = set()

        for match in self.CALL_PATTERN.finditer(self.content):
            target = match.group(1).lower()
            if target not in seen_calls:
                seen_calls.add(target)
                line_num = self.content[:match.start()].count('\n') + 1
                calls.append({
                    'name': f':{target}',  # Use 'name' for consistency with formatter
                    'line': line_num,
                })

        return calls

    def _extract_external_calls(self) -> List[Dict[str, Any]]:
        """Extract external script/program calls.

        Returns:
            List of call dictionaries with name and line
        """
        calls = []
        seen_calls = set()

        for match in self.CALL_EXTERNAL_PATTERN.finditer(self.content):
            target = match.group(1).strip('"\'')
            # Skip internal calls (already captured)
            if target.startswith(':'):
                continue
            # Skip obvious variables
            if target.startswith('%') or target.startswith('!'):
                continue

            if target.lower() not in seen_calls:
                seen_calls.add(target.lower())
                line_num = self.content[:match.start()].count('\n') + 1
                calls.append({
                    'name': target,  # Use 'name' for consistency with formatter
                    'line': line_num,
                })

        return calls

    def _calculate_stats(self) -> Dict[str, Any]:
        """Calculate batch file statistics.

        Returns:
            Dict with various statistics
        """
        lines = self.content.split('\n')
        comment_lines = sum(1 for line in lines if self.REM_PATTERN.match(line))
        blank_lines = sum(1 for line in lines if not line.strip())
        has_echo_off = bool(self.ECHO_OFF_PATTERN.search(self.content))
        has_setlocal = bool(self.SETLOCAL_PATTERN.search(self.content))

        return {
            'total_lines': len(lines),
            'code_lines': len(lines) - comment_lines - blank_lines,
            'comment_lines': comment_lines,
            'blank_lines': blank_lines,
            'has_echo_off': has_echo_off,
            'has_setlocal': has_setlocal,
        }

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a specific label's content.

        Args:
            element_type: Type of element (ignored, all are labels)
            name: Label name (case-insensitive)

        Returns:
            Dict with label content or None if not found
        """
        labels = self._extract_labels()
        target = name.lower().lstrip(':')

        for label in labels:
            if label['name'] == target:
                # Extract the label's content
                lines = self.content.split('\n')
                start = label['line'] - 1
                end = label['line_end']
                source = '\n'.join(lines[start:end])

                return {
                    'name': label['name'],
                    'line_start': label['line'],
                    'line_end': label['line_end'],
                    'source': source,
                }

        return None
