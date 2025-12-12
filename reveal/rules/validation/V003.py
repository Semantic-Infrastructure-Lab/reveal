"""V003: Feature matrix coverage.

Validates that common features are consistently implemented across analyzers.
Helps catch missing features like --outline support for markdown.

Example violation:
    - Feature: --outline (hierarchical view)
    - Supported: Python, JavaScript, TypeScript analyzers
    - Missing: Markdown analyzer (has headings but no outline)
    - Result: Inconsistent UX across file types (Issue #3)
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import re

from ..base import BaseRule, Detection, RulePrefix, Severity


class V003(BaseRule):
    """Validate feature consistency across analyzers."""

    code = "V003"
    message = "Analyzer may be missing common feature support"
    category = RulePrefix.M  # Maintainability
    severity = Severity.MEDIUM
    file_patterns = ['*']

    # Features that should be widely supported
    # Format: (feature_name, method_or_flag, applicable_to)
    COMMON_FEATURES = {
        'structure_extraction': {
            'method': 'get_structure',
            'description': 'Extract file structure',
            'applicable': 'all'  # All analyzers should have this
        },
        'hierarchical_outline': {
            'keywords': ['outline', 'hierarchy', 'tree'],
            'description': 'Support hierarchical outline view',
            'applicable': 'structured'  # Code and document formats
        },
    }

    # Analyzer types that should support hierarchical features
    STRUCTURED_FORMATS = {
        'python', 'javascript', 'typescript', 'rust', 'go',
        'markdown', 'jupyter', 'json', 'yaml', 'toml'
    }

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for feature matrix coverage."""
        detections = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = self._find_reveal_root()
        if not reveal_root:
            return detections

        # Get all analyzers
        analyzers = self._get_analyzers_with_types(reveal_root)

        # Check each analyzer for common features
        for analyzer_name, analyzer_info in analyzers.items():
            analyzer_path = analyzer_info['path']
            is_structured = analyzer_name in self.STRUCTURED_FORMATS

            try:
                content = analyzer_path.read_text()

                # Check for get_structure (required for all)
                # Can be either direct implementation OR inherited from base classes
                has_get_structure = (
                    'def get_structure' in content or
                    'TreeSitterAnalyzer' in content or
                    'FileAnalyzer' in content
                )

                if not has_get_structure:
                    detections.append(self.create_detection(
                        file_path=str(analyzer_path.relative_to(reveal_root)),
                        line=1,
                        message=f"Analyzer '{analyzer_name}' missing get_structure() method",
                        suggestion="All analyzers should implement get_structure() or inherit from FileAnalyzer/TreeSitterAnalyzer",
                        context="This is the core method for structure extraction"
                    ))

                # Check for hierarchical support (for structured formats)
                if is_structured:
                    has_hierarchy_support = self._check_hierarchy_support(content)

                    if not has_hierarchy_support:
                        # This is informational - not all structured formats need it
                        # But we should track it for Issue #3 type situations
                        line_num = self._find_class_line(content)
                        detections.append(self.create_detection(
                            file_path=str(analyzer_path.relative_to(reveal_root)),
                            line=line_num,
                            message=f"Structured analyzer '{analyzer_name}' may not support --outline",
                            suggestion="Consider implementing hierarchical outline support (see markdown.py or python.py for examples)",
                            context="Would have caught Issue #3 (markdown missing outline)"
                        ))

            except Exception:
                # Skip files we can't read
                continue

        return detections

    def _get_analyzers_with_types(self, reveal_root: Path) -> Dict[str, Dict[str, Any]]:
        """Get all analyzers with their metadata.

        Returns:
            Dict mapping analyzer name to info dict
        """
        analyzers = {}
        analyzers_dir = reveal_root / 'analyzers'

        if not analyzers_dir.exists():
            return analyzers

        for file in analyzers_dir.glob('*.py'):
            if file.stem.startswith('_') or file.stem == 'base':
                continue

            analyzers[file.stem] = {
                'path': file,
                'name': file.stem
            }

        return analyzers

    def _check_hierarchy_support(self, content: str) -> bool:
        """Check if analyzer has any hierarchy/outline support.

        Args:
            content: File content

        Returns:
            True if hierarchy support found
        """
        # Look for keywords that suggest hierarchy support
        hierarchy_indicators = [
            'hierarchy',
            'outline',
            'tree',
            'nested',
            'parent',
            'children',
            'build.*tree',
            'build.*hierarchy',
        ]

        for indicator in hierarchy_indicators:
            if re.search(indicator, content, re.IGNORECASE):
                return True

        return False

    def _find_class_line(self, content: str) -> int:
        """Find line number of first class definition.

        Args:
            content: File content

        Returns:
            Line number (1-indexed) or 1 if not found
        """
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if re.match(r'^class\s+\w+', line):
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
