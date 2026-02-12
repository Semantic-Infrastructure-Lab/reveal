"""INI/Properties file analyzer.

Handles Windows INI files and Java properties files.
"""

import configparser
import logging
from typing import Dict, Any, Optional
from ..base import FileAnalyzer
from ..registry import register

logger = logging.getLogger(__name__)


@register('.ini', name='INI', icon='⚙️')
@register('.cfg', name='Config', icon='⚙️')
@register('.conf', name='Config', icon='⚙️')
@register('.properties', name='Properties', icon='⚙️')
class IniAnalyzer(FileAnalyzer):
    """INI/Properties file analyzer.

    Analyzes configuration files with section/key/value structure.
    Common uses: Windows configs, Java properties, Python configs, app settings.

    Structure view shows:
    - Section names and count
    - Keys per section
    - Value types (string, number, boolean, list)
    - Total key count

    Extract by section name to view all keys in that section.
    Extract by section.key to view specific value.
    """

    def _infer_type(self, value: str) -> str:
        """Infer value type from string representation.

        Args:
            value: String value

        Returns:
            Type name: 'integer', 'float', 'boolean', 'list', 'string'
        """
        if not value:
            return 'empty'

        # Try boolean
        if value.lower() in ('true', 'false', 'yes', 'no', 'on', 'off', '1', '0'):
            return 'boolean'

        # Try integer
        try:
            int(value)
            return 'integer'
        except ValueError:
            pass

        # Try float
        try:
            float(value)
            return 'float'
        except ValueError:
            pass

        # Check for list (comma-separated)
        if ',' in value:
            return 'list'

        return 'string'

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract INI file structure.

        Args:
            head: Show first N sections
            tail: Show last N sections
            range: Show sections in range (start, end) - 1-indexed
            **kwargs: Additional parameters (unused)

        Returns:
            Dict with sections, keys, and statistics
        """
        config = configparser.ConfigParser()

        try:
            # Parse INI file
            config.read_string(self.content)

            # Pre-scan for section line numbers
            section_lines = {}
            import re
            for i, line in enumerate(self.content.split('\n'), 1):
                match = re.match(r'^\s*\[([^\]]+)\]\s*$', line)
                if match:
                    section_lines[match.group(1)] = i

            sections_data = []
            all_sections = list(config.sections())

            # Handle DEFAULT section if it has keys
            if config.defaults():
                all_sections.insert(0, 'DEFAULT')

            # Apply filtering if requested
            if head is not None:
                all_sections = all_sections[:head]
            elif tail is not None:
                all_sections = all_sections[-tail:]
            elif range is not None:
                start, end = range
                all_sections = all_sections[start-1:end]

            total_keys = 0
            for section in all_sections:
                if section == 'DEFAULT':
                    items = list(config.defaults().items())
                else:
                    items = list(config.items(section))

                keys_data = []
                for key, value in items:
                    keys_data.append({
                        'name': key,
                        'value': value,
                        'type': self._infer_type(value)
                    })

                sections_data.append({
                    'name': section,
                    'line': section_lines.get(section),
                    'key_count': len(items),
                    'keys': keys_data
                })
                total_keys += len(items)

            return {
                'section_count': len(config.sections()) + (1 if config.defaults() else 0),
                'total_keys': total_keys,
                'sections': sections_data
            }

        except configparser.Error as e:
            logger.debug(f"Error parsing INI {self.path}: {e}")
            # Try to parse as simple properties file (Java-style, no sections)
            return self._parse_properties()

    def _parse_properties(self) -> Dict[str, Any]:
        """Parse as simple key=value properties file (no sections).

        Returns:
            Dict with properties data
        """
        properties = {}

        for line in self.lines:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#') or line.startswith(';'):
                continue

            # Parse key=value
            if '=' in line:
                key, value = line.split('=', 1)
                properties[key.strip()] = value.strip()

        if not properties:
            return {
                'message': 'Empty or invalid configuration file',
                'section_count': 0,
                'total_keys': 0
            }

        keys_data = [
            {
                'name': key,
                'value': value,
                'type': self._infer_type(value)
            }
            for key, value in properties.items()
        ]

        return {
            'section_count': 0,
            'total_keys': len(properties),
            'sections': [{
                'name': '(no section)',
                'key_count': len(properties),
                'keys': keys_data
            }],
            'format': 'properties'
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get a specific section or key value.

        Args:
            element_name: Section name or "section.key" format
            **kwargs: Additional parameters (unused)

        Returns:
            Dict with section data or specific value, or None if not found
        """
        config = configparser.ConfigParser()

        try:
            config.read_string(self.content)
        except configparser.Error:
            # Try properties format
            return None

        # Check if requesting specific key (section.key format)
        if '.' in element_name:
            section, key = element_name.split('.', 1)

            if section == 'DEFAULT':
                value = config.defaults().get(key)
            else:
                try:
                    value = config.get(section, key)
                except (configparser.NoSectionError, configparser.NoOptionError):
                    return None

            if value is not None:
                return {
                    'section': section,
                    'key': key,
                    'value': value,
                    'type': self._infer_type(value)
                }

            return None

        # Get entire section
        if element_name == 'DEFAULT':
            items = list(config.defaults().items())
        else:
            try:
                items = list(config.items(element_name))
            except configparser.NoSectionError:
                return None

        keys_data = [
            {
                'name': key,
                'value': value,
                'type': self._infer_type(value)
            }
            for key, value in items
        ]

        return {
            'name': element_name,
            'key_count': len(items),
            'keys': keys_data
        }
