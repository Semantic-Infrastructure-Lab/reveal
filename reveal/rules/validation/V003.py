"""V003: Feature matrix coverage.

Validates that common features are consistently implemented across analyzers.
Helps catch missing features like --outline support for markdown.

Example violation:
    - Feature: --outline (hierarchical view)
    - Supported: Python, JavaScript, TypeScript analyzers
    - Missing: Markdown analyzer (has headings but no outline)
    - Result: Inconsistent UX across file types (Issue #3)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
import re

from ..base import BaseRule, Detection, RulePrefix, Severity


@dataclass
class AnalyzerContext:
    """Context for analyzer-related detections.

    Bundles common parameters for creating detections about analyzers,
    reducing parameter repetition and enabling reusable helpers.
    """
    analyzer_name: str
    analyzer_path: Path
    reveal_root: Path

    @property
    def relative_path(self) -> str:
        """Get analyzer path relative to reveal root for detection reporting."""
        return str(self.analyzer_path.relative_to(self.reveal_root))


class V003(BaseRule):
    """Validate feature consistency across analyzers."""

    code = "V003"
    message = "Analyzer may be missing common feature support"
    category = RulePrefix.V
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

            # Create context for this analyzer
            ctx = AnalyzerContext(
                analyzer_name=analyzer_name,
                analyzer_path=analyzer_path,
                reveal_root=reveal_root
            )

            try:
                content = analyzer_path.read_text()

                # Check for get_structure (required for all)
                has_get_structure = (
                    'def get_structure' in content or
                    'TreeSitterAnalyzer' in content or
                    'FileAnalyzer' in content
                )

                if not has_get_structure:
                    detections.append(self._create_missing_structure_detection(ctx))

                # Check for hierarchical support (for structured formats)
                if is_structured:
                    has_hierarchy_support = self._check_hierarchy_support(content)

                    if not has_hierarchy_support:
                        line_num = self._find_class_line(content)
                        detections.append(
                            self._create_missing_outline_detection(ctx, line_num)
                        )

            except Exception:
                # Skip files we can't read
                continue

        return detections

    def _create_missing_structure_detection(
        self, ctx: AnalyzerContext
    ) -> Detection:
        """Create detection for missing get_structure() method.

        Args:
            ctx: Analyzer context
        """
        return self.create_detection(
            file_path=ctx.relative_path,
            line=1,
            message=f"Analyzer '{ctx.analyzer_name}' missing get_structure() method",
            suggestion="All analyzers should implement get_structure() or inherit from FileAnalyzer/TreeSitterAnalyzer",
            context="This is the core method for structure extraction"
        )

    def _create_missing_outline_detection(
        self, ctx: AnalyzerContext, line: int
    ) -> Detection:
        """Create detection for missing outline support.

        Args:
            ctx: Analyzer context
            line: Line number where the class is defined
        """
        return self.create_detection(
            file_path=ctx.relative_path,
            line=line,
            message=f"Structured analyzer '{ctx.analyzer_name}' may not support --outline",
            suggestion="Consider implementing hierarchical outline support (see markdown.py or python.py for examples)",
            context="Would have caught Issue #3 (markdown missing outline)"
        )

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
