"""E501: Line too long detector.

Detects lines that exceed the maximum line length (PEP 8 style).
Universal rule that works on any text file.
"""

import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class E501(BaseRule):
    """Detect lines that exceed maximum length."""

    code = "E501"
    message = "Line too long"
    category = RulePrefix.E
    severity = Severity.LOW
    file_patterns = ['*']  # Universal: works on any file
    version = "1.0.0"

    # Default maximum line length (100 is pragmatic for modern development)
    # PEP 8 = 79, Black = 88, but many codebases use 100-120
    # Can be overridden in .reveal.yaml:
    #   rules:
    #     E501:
    #       max_length: 120
    #       ignore_urls: true
    DEFAULT_MAX_LENGTH = 100

    # Default patterns to ignore (URLs, etc.)
    DEFAULT_IGNORE_PATTERNS = [
        'http://',
        'https://',
        'ftp://',
        '# noqa',  # Flake8 ignore comment
        '# type:',  # Type comments
    ]

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for lines exceeding maximum length.

        Args:
            file_path: Path to file
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections
        """
        detections = []
        lines = content.splitlines()

        # Get configuration
        max_length = self.get_threshold('max_length', self.DEFAULT_MAX_LENGTH)
        ignore_urls = self.get_threshold('ignore_urls', True)
        ignore_patterns = self.DEFAULT_IGNORE_PATTERNS if ignore_urls else []

        for i, line in enumerate(lines, start=1):
            # Skip if line contains ignore patterns
            if any(pattern in line for pattern in ignore_patterns):
                continue

            # Check length (excluding trailing whitespace)
            line_length = len(line.rstrip())

            if line_length > max_length:
                excess = line_length - max_length

                detections.append(Detection(
                    file_path=file_path,
                    line=i,
                    rule_code=self.code,
                    message=f"{self.message} ({line_length} > {max_length} characters, {excess} over)",
                    column=max_length + 1,
                    suggestion=f"Break line into multiple lines or refactor",
                    context=line[:80] + '...' if len(line) > 80 else line,
                    severity=self.severity,
                    category=self.category
                ))

        return detections
