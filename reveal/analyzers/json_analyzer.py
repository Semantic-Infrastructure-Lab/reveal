"""JSON file analyzer."""

import json
from typing import Dict, Any, List
from .base import BaseAnalyzer


class JSONAnalyzer(BaseAnalyzer):
    """Analyzer for JSON files."""

    def __init__(self, lines: List[str]):
        super().__init__(lines)
        self.parse_error = None
        self.parsed_data = None

        try:
            content = '\n'.join(lines)
            self.parsed_data = json.loads(content)
        except Exception as e:
            self.parse_error = str(e)

    def analyze_structure(self) -> Dict[str, Any]:
        """Analyze JSON structure."""
        if self.parse_error:
            return {
                'error': self.parse_error,
                'top_level_keys': [],
                'object_count': 0,
                'array_count': 0,
                'max_depth': 0,
                'value_types': {}
            }

        # Get top-level keys
        top_level_keys = []
        if isinstance(self.parsed_data, dict):
            top_level_keys = list(self.parsed_data.keys())

        # Count objects and arrays
        object_count, array_count = self._count_structures(self.parsed_data)

        # Calculate max depth
        max_depth = self._calculate_depth(self.parsed_data)

        # Count value types
        value_types = self._count_value_types(self.parsed_data)

        return {
            'top_level_keys': top_level_keys,
            'object_count': object_count,
            'array_count': array_count,
            'max_depth': max_depth,
            'value_types': value_types
        }

    def _count_structures(self, obj: Any) -> tuple[int, int]:
        """Count objects and arrays recursively."""
        object_count = 0
        array_count = 0

        if isinstance(obj, dict):
            object_count += 1
            for value in obj.values():
                obj_c, arr_c = self._count_structures(value)
                object_count += obj_c
                array_count += arr_c
        elif isinstance(obj, list):
            array_count += 1
            for item in obj:
                obj_c, arr_c = self._count_structures(item)
                object_count += obj_c
                array_count += arr_c

        return object_count, array_count

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

    def _count_value_types(self, obj: Any) -> Dict[str, int]:
        """Count value types in JSON."""
        types = {}

        def count_type(value):
            type_name = type(value).__name__
            if type_name == 'NoneType':
                type_name = 'null'
            elif type_name == 'bool':
                type_name = 'boolean'
            elif type_name == 'int' or type_name == 'float':
                type_name = 'number'
            types[type_name] = types.get(type_name, 0) + 1

        def traverse(item):
            if isinstance(item, dict):
                for value in item.values():
                    traverse(value)
            elif isinstance(item, list):
                for element in item:
                    traverse(element)
            else:
                count_type(item)

        traverse(obj)
        return types

    def generate_preview(self) -> List[tuple[int, str]]:
        """Generate JSON preview (first 10 key/value pairs or 20 lines)."""
        preview = []

        if self.parse_error:
            # Fallback to first 20 lines
            for i, line in enumerate(self.lines[:20], 1):
                preview.append((i, line))
            return preview

        # Show first 20 lines
        for i, line in enumerate(self.lines[:20], 1):
            preview.append((i, line))

        return preview
