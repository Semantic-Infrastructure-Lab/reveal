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


class V002(BaseRule):
    """Validate that all analyzer files are properly registered."""

    code = "V002"
    message = "Analyzer file exists but may not be registered"
    category = RulePrefix.M  # Maintainability
    severity = Severity.HIGH  # Unregistered analyzers silently don't work
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for unregistered analyzers."""
        detections = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = self._find_reveal_root()
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

            # Check if file has @register decorator
            try:
                content = analyzer_file.read_text()
                has_register = self._has_register_decorator(content)

                if not has_register:
                    # Count classes to see if it looks like an analyzer
                    class_count = len(re.findall(r'^class\s+\w+', content, re.MULTILINE))

                    if class_count > 0:
                        detections.append(self.create_detection(
                            file_path=str(analyzer_file.relative_to(reveal_root)),
                            line=1,
                            message=f"Analyzer '{analyzer_file.stem}' has {class_count} class(es) but no @register decorator",
                            suggestion="Add @register decorator to the analyzer class(es)",
                            context=f"File contains classes but may not be registered"
                        ))

            except Exception as e:
                # Skip files we can't read
                continue

        return detections

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

    def _find_reveal_root(self) -> Optional[Path]:
        """Find reveal's root directory."""
        current = Path(__file__).parent.parent.parent

        if (current / 'analyzers').exists() and (current / 'rules').exists():
            return current

        for _ in range(5):
            if (current / 'reveal' / 'analyzers').exists():
                return current / 'reveal'
            current = current.parent
            if current == current.parent:
                break

        return None
