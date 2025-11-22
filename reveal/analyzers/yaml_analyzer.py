"""YAML file analyzer."""

import re
from typing import Dict, Any, List
from .base import BaseAnalyzer
from ..registry import register

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@register(['.yaml', '.yml'], name='YAML', icon='📋')
class YAMLAnalyzer(BaseAnalyzer):
    """Analyzer for YAML configuration files"""

    def __init__(self, lines: List[str]):
        super().__init__(lines)
        self.parse_error = None
        self.parsed_data = None

        if HAS_YAML:
            try:
                content = '\n'.join(lines)
                self.parsed_data = yaml.safe_load(content)
            except Exception as e:
                self.parse_error = str(e)

    def analyze_structure(self) -> Dict[str, Any]:
        """Analyze YAML structure."""
        if self.parse_error:
            return {
                'error': self.parse_error,
                'top_level_keys': [],
                'nesting_depth': 0,
                'anchor_count': 0,
                'alias_count': 0
            }

        if not HAS_YAML:
            return {
                'error': 'PyYAML not installed. Install with: pip install pyyaml',
                'top_level_keys': [],
                'nesting_depth': 0,
                'anchor_count': 0,
                'alias_count': 0
            }

        # Get top-level keys
        top_level_keys = []
        if isinstance(self.parsed_data, dict):
            top_level_keys = list(self.parsed_data.keys())

        # Calculate nesting depth
        nesting_depth = self._calculate_depth(self.parsed_data)

        # Count anchors and aliases
        content = '\n'.join(self.lines)
        anchor_count = len(re.findall(r'&\w+', content))
        alias_count = len(re.findall(r'\*\w+', content))

        return {
            'top_level_keys': top_level_keys,
            'nesting_depth': nesting_depth,
            'anchor_count': anchor_count,
            'alias_count': alias_count
        }

    def _calculate_depth(self, obj: Any, current_depth: int = 0) -> int:
        """Calculate maximum nesting depth."""
        if isinstance(obj, dict):
            if not obj:
                return current_depth
            return max(self._calculate_depth(v, current_depth + 1) for v in obj.values())
        elif isinstance(obj, list):
            if not obj:
                return current_depth
            return max(self._calculate_depth(item, current_depth + 1) for item in obj)
        else:
            return current_depth

    def generate_preview(self) -> List[tuple[int, str]]:
        """Generate YAML preview (first 10 key/value pairs or 20 lines)."""
        preview = []

        if self.parse_error or not HAS_YAML:
            # Fallback to first 20 lines
            for i, line in enumerate(self.lines[:20], 1):
                preview.append((i, line))
            return preview

        # Show first 10 key/value pairs or first 20 logical lines
        lines_shown = 0
        pairs_shown = 0
        max_pairs = 10
        max_lines = 20

        for i, line in enumerate(self.lines, 1):
            if lines_shown >= max_lines:
                break

            stripped = line.strip()

            # Count top-level key/value pairs
            if stripped and not stripped.startswith('#') and ':' in stripped:
                if not line.startswith((' ', '\t')):  # Top-level key
                    pairs_shown += 1
                    if pairs_shown > max_pairs:
                        break

            preview.append((i, line))
            lines_shown += 1

        return preview
