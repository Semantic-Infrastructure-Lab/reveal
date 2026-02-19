"""M105: CLI handler not wired to main.py.

Detects handler functions in reveal/cli/handlers_*.py that are not imported
or called in reveal/main.py. This prevents orphaned handlers that are
implemented but never accessible via CLI.

Example of violation:
    # reveal/cli/handlers_stats.py
    def handle_stats_overview():  # Implemented
        pass

    # reveal/main.py
    # Missing import and call!

This rule helps maintain the "pit of success" for CLI integration by catching
handlers that won't work because they're not wired into the CLI entry point.

See: reveal/docs/CLI_INTEGRATION_GUIDE.md
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class M105(BaseRule):
    """Detect CLI handlers not wired to main.py."""

    code = "M105"
    message = "CLI handler function not wired to main.py"
    category = RulePrefix.M
    severity = Severity.HIGH
    file_patterns = ['reveal/cli/handlers_*.py']
    version = "1.0.0"

    # Match handler function definitions
    HANDLER_PATTERN = re.compile(
        r'^def\s+(handle_[a-z_]+)\s*\(',
        re.MULTILINE
    )

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for handlers not wired to main.py.

        Args:
            file_path: Path to handlers file (e.g., reveal/cli/handlers_scaffold.py)
            structure: Parsed structure (not used)
            content: Raw file content

        Returns:
            List of detections for orphaned handlers
        """
        detections: List[Detection] = []

        # Only check handler files
        if not file_path.endswith('.py') or '/handlers_' not in file_path:
            return detections

        # Find all handler functions
        handlers = set(self.HANDLER_PATTERN.findall(content))
        if not handlers:
            return detections

        # Read main.py to check imports and calls
        main_py_path = self._find_main_py(file_path)
        if not main_py_path or not Path(main_py_path).exists():
            # Can't verify without main.py - skip check
            return detections

        try:
            main_content = Path(main_py_path).read_text()
        except Exception as e:
            logger.warning(f"Could not read main.py: {e}")
            return detections

        # Check each handler
        for handler in handlers:
            # Check if imported
            if not self._is_imported(handler, main_content):
                line = self._find_handler_line(handler, content)
                detections.append(Detection(
                    rule_code=self.code,
                    message=f"Handler '{handler}' not imported in main.py",
                    file_path=file_path,
                    line=line,
                    column=1,
                    severity=self.severity,
                    context={
                        'handler': handler,
                        'issue': 'not_imported',
                        'fix': f"Add to main.py imports: from .cli import {handler}",
                        'guide': 'reveal/docs/CLI_INTEGRATION_GUIDE.md'
                    }
                ))

            # Check if called (only if imported)
            elif not self._is_called(handler, main_content):
                line = self._find_handler_line(handler, content)
                detections.append(Detection(
                    rule_code=self.code,
                    message=f"Handler '{handler}' imported but never called in main.py",
                    file_path=file_path,
                    line=line,
                    column=1,
                    severity=self.severity,
                    context={
                        'handler': handler,
                        'issue': 'not_called',
                        'fix': f"Call in main.py or remove import",
                        'guide': 'reveal/docs/CLI_INTEGRATION_GUIDE.md'
                    }
                ))

        return detections

    def _find_main_py(self, file_path: str) -> Optional[str]:
        """Find main.py relative to handler file.

        Args:
            file_path: Path to handler file

        Returns:
            Path to main.py or None
        """
        # Handler is at reveal/cli/handlers_*.py
        # Main is at reveal/main.py
        path = Path(file_path)
        if 'reveal' in path.parts:
            reveal_idx = path.parts.index('reveal')
            reveal_root = Path(*path.parts[:reveal_idx + 1])
            main_py = reveal_root / 'main.py'
            return str(main_py)
        return None

    def _is_imported(self, handler: str, main_content: str) -> bool:
        """Check if handler is imported in main.py.

        Args:
            handler: Handler function name
            main_content: Content of main.py

        Returns:
            True if imported
        """
        # Check for direct import
        if f'import {handler}' in main_content:
            return True

        # Check for from .cli import ... handler ...
        import_pattern = re.compile(
            r'from\s+\.cli\s+import\s+\([^)]*?' + re.escape(handler) + r'[^)]*?\)',
            re.DOTALL
        )
        if import_pattern.search(main_content):
            return True

        # Check for single-line from import
        single_import = re.compile(
            r'from\s+\.cli\s+import\s+.*?' + re.escape(handler)
        )
        if single_import.search(main_content):
            return True

        return False

    def _is_called(self, handler: str, main_content: str) -> bool:
        """Check if handler is called in main.py.

        Args:
            handler: Handler function name
            main_content: Content of main.py

        Returns:
            True if called
        """
        # Check for direct call
        call_pattern = re.compile(r'\b' + re.escape(handler) + r'\s*\(')
        return bool(call_pattern.search(main_content))

    def _find_handler_line(self, handler: str, content: str) -> int:
        """Find line number where handler is defined.

        Args:
            handler: Handler function name
            content: File content

        Returns:
            Line number (1-indexed)
        """
        pattern = re.compile(r'^def\s+' + re.escape(handler) + r'\s*\(', re.MULTILINE)
        match = pattern.search(content)
        if match:
            return content[:match.start()].count('\n') + 1
        return 1
