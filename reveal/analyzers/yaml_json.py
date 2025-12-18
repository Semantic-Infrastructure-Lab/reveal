"""YAML and JSON file analyzers."""

import json
import re
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer, register


@register('.yaml', '.yml', name='YAML', icon='')
class YamlAnalyzer(FileAnalyzer):
    """YAML file analyzer.

    Extracts top-level keys.
    """

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract YAML top-level keys."""
        keys = []

        for i, line in enumerate(self.lines, 1):
            # Match top-level key (no indentation)
            match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:', line)
            if match:
                key_name = match.group(1)
                keys.append({
                    'line': i,
                    'name': key_name,
                })

        return {'keys': keys}

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a YAML key and its value.

        Args:
            element_type: 'key'
            name: Key name to find

        Returns:
            Dict with key content
        """
        # Find the key
        start_line = None

        for i, line in enumerate(self.lines, 1):
            match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:', line)
            if match and match.group(1) == name:
                start_line = i
                break

        if not start_line:
            return super().extract_element(element_type, name)

        # Find end of this key (next top-level key or end of file)
        end_line = len(self.lines)
        for i in range(start_line, len(self.lines)):
            line = self.lines[i]
            # Next top-level key?
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_-]*\s*:', line):
                end_line = i
                break

        source = '\n'.join(self.lines[start_line-1:end_line])

        return {
            'name': name,
            'line_start': start_line,
            'line_end': end_line,
            'source': source,
        }


@register('.json', name='JSON', icon='')
class JsonAnalyzer(FileAnalyzer):
    """JSON file analyzer.

    Extracts top-level keys.
    """

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract JSON top-level keys."""
        try:
            data = json.loads(self.content)

            if not isinstance(data, dict):
                return {}

            keys = []
            for key in data.keys():
                # Find line number by searching
                line_num = self._find_key_line(key)
                keys.append({
                    'line': line_num,
                    'name': key,
                })

            return {'keys': keys}

        except json.JSONDecodeError:
            return {}

    def _find_key_line(self, key: str) -> int:
        """Find line number where key is defined."""
        pattern = rf'"{re.escape(key)}"\s*:'

        for i, line in enumerate(self.lines, 1):
            if re.search(pattern, line):
                return i

        return 1  # Default to line 1
