"""V002: Analyzer registration validation.

Validates that all analyzer files are properly registered with @register decorator.
Unregistered analyzers won't be used even if they exist in the codebase.

Example violation:
    - File: reveal/analyzers/newanalyzer.py exists
    - Missing: @register('.ext', name='...') decorator
    - Result: File type won't be recognized
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import re

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V002(BaseRule):
    """Validate that all analyzer files are properly registered."""

    code = "V002"
    message = "Analyzer file exists but may not be registered"
    category = RulePrefix.V
    severity = Severity.HIGH  # Unregistered analyzers silently don't work
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for unregistered analyzers."""
        detections: List[Detection] = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections

        # Get all analyzer files
        analyzers_dir = reveal_root / 'analyzers'
        if not analyzers_dir.exists():
            return detections

        for analyzer_file in analyzers_dir.glob('*.py'):
            # Skip special files
            if analyzer_file.stem.startswith('_'):
                continue

            # Check this analyzer file
            detection = self._check_analyzer_registration(analyzer_file, reveal_root)
            if detection:
                detections.append(detection)

        return detections

    def _check_analyzer_registration(
        self, analyzer_file: Path, reveal_root: Path
    ) -> Optional[Detection]:
        """Check if analyzer file is properly registered.

        Returns Detection if unregistered, None otherwise.
        """
        try:
            content = analyzer_file.read_text(encoding='utf-8')
        except Exception:
            # Skip files we can't read
            return None

        # Check if file has @register decorator
        if self._has_register_decorator(content):
            return None

        # Count classes to see if it looks like an analyzer
        class_count = len(re.findall(r'^class\s+\w+', content, re.MULTILINE))
        if class_count == 0:
            return None

        # Has classes but no @register - create detection
        return self.create_detection(
            file_path=str(analyzer_file.relative_to(reveal_root)),
            line=1,
            message=f"Analyzer '{analyzer_file.stem}' has {class_count} class(es) but no @register decorator",
            suggestion="Add @register decorator to the analyzer class(es)",
            context="File contains classes but may not be registered"
        )

    def _has_register_decorator(self, content: str) -> bool:
        """Check if file contains @register decorator.

        Args:
            content: File content

        Returns:
            True if @register found
        """
        # Check for @register decorator (from base.py)
        register_patterns = [
            r'@register\(',       # @register('.py', ...)
            r'from.*base.*import.*register',  # from ..base import register
        ]

        for pattern in register_patterns:
            if re.search(pattern, content):
                return True

        return False
