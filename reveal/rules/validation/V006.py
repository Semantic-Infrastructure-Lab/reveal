"""V006: Output format support validation.

Validates that analyzers properly support different output formats (text, JSON, grep).
Inconsistent format handling can lead to runtime errors or poor UX.

Example violation:
    - Analyzer: Returns dict with unexpected structure
    - Missing: Proper JSON serialization support
    - Result: --format=json crashes or produces invalid JSON
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import re

from ..base import BaseRule, Detection, RulePrefix, Severity


class V006(BaseRule):
    """Validate that analyzers support standard output formats."""

    code = "V006"
    message = "Analyzer may not properly support all output formats"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = ['*']

    # Required method for analyzers
    REQUIRED_METHOD = 'get_structure'

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for output format support."""
        detections: List[Detection] = []

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
            if analyzer_file.stem.startswith('_') or analyzer_file.stem == 'base':
                continue

            try:
                content = analyzer_file.read_text(encoding='utf-8')

                # Check for get_structure method
                # Can be either direct implementation OR inherited from base classes
                has_get_structure = (
                    'def get_structure' in content or
                    'TreeSitterAnalyzer' in content or
                    'FileAnalyzer' in content
                )

                if not has_get_structure:
                    # Check if it's actually an analyzer (has @register)
                    if '@register' in content:
                        detections.append(self.create_detection(
                            file_path=str(analyzer_file.relative_to(reveal_root)),
                            line=1,
                            message=f"Analyzer '{analyzer_file.stem}' missing get_structure() method",
                            suggestion="Implement get_structure() -> Dict[str, Any] method or inherit from FileAnalyzer/TreeSitterAnalyzer",
                            context="get_structure() is required for proper output format support"
                        ))
                        continue

                # Check return type hints (only if method is defined locally, not inherited)
                has_local_method = 'def get_structure' in content
                has_dict_return = self._check_return_type(content)

                if has_local_method and not has_dict_return:
                    line_num = self._find_method_line(content, 'get_structure')
                    detections.append(self.create_detection(
                        file_path=str(analyzer_file.relative_to(reveal_root)),
                        line=line_num,
                        message=f"get_structure() in '{analyzer_file.stem}' missing Dict return type hint",
                        suggestion="Add return type: -> Dict[str, Any]",
                        context="Type hints help ensure consistent output format (inherited methods are OK)"
                    ))

            except Exception:
                # Skip files we can't read
                continue

        return detections

    def _check_return_type(self, content: str) -> bool:
        """Check if get_structure has proper return type hint.

        Args:
            content: File content

        Returns:
            True if return type hint found
        """
        # Look for -> Dict pattern in get_structure signature
        patterns = [
            r'def get_structure\([^)]*\)\s*->\s*Dict',
            r'def get_structure\([^)]*\)\s*->\s*dict',
        ]

        for pattern in patterns:
            if re.search(pattern, content):
                return True

        return False

    def _find_method_line(self, content: str, method_name: str) -> int:
        """Find line number of method definition.

        Args:
            content: File content
            method_name: Method name to find

        Returns:
            Line number (1-indexed) or 1 if not found
        """
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if f'def {method_name}' in line:
                return i
        return 1

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
