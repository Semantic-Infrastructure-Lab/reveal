"""TOML file analyzer."""

import re
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer
from ..registry import register


@register('.toml', name='TOML', icon='')
class TomlAnalyzer(FileAnalyzer):
    """TOML file analyzer.

    Extracts sections ([section]) and key-value pairs.
    """

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, outline: bool = False, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract TOML sections and top-level keys.

        Args:
            head: Show first N sections/keys
            tail: Show last N sections/keys
            range: Show sections/keys in range (start, end)
            outline: If True, add level information for hierarchical display
            **kwargs: Additional arguments (for compatibility)
        """
        sections = []
        keys = []

        current_section = None

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue

            # Section header: [section] or [[array]]
            section_match = re.match(r'^\[+([^\]]+)\]+', stripped)
            if section_match:
                section_name = section_match.group(1).strip()
                section_info = {
                    'line': i,
                    'name': section_name,
                }

                # Add level information for outline mode (similar to markdown headings)
                # Level is based on dot-notation depth: database=1, database.connection=2, etc.
                if outline:
                    section_info['level'] = section_name.count('.') + 1

                sections.append(section_info)
                current_section = section_name
                continue

            # Key-value pair
            key_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*=', stripped)
            if key_match:
                key_name = key_match.group(1)

                # Only include top-level keys (no section)
                if current_section is None:
                    keys.append({
                        'line': i,
                        'name': key_name,
                    })

        result = {}
        if sections:
            result['sections'] = sections
        if keys:
            result['keys'] = keys

        return result

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a TOML section or key.

        Args:
            element_type: 'section' or 'key'
            name: Section/key name to find

        Returns:
            Dict with section/key content
        """
        # Try to find as section first
        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # Match section header
            section_match = re.match(r'^\[+([^\]]+)\]+', stripped)
            if section_match and section_match.group(1).strip() == name:
                start_line = i

                # Find end of section (next section or EOF)
                end_line = len(self.lines) + 1
                for j in range(i, len(self.lines)):
                    if re.match(r'^\[+[^\]]+\]+', self.lines[j].strip()):
                        end_line = j + 1
                        break

                source = '\n'.join(self.lines[start_line-1:end_line-1])

                return {
                    'name': name,
                    'line_start': start_line,
                    'line_end': end_line - 1,
                    'source': source,
                }

        # Fall back to grep-based search
        return super().extract_element(element_type, name)
