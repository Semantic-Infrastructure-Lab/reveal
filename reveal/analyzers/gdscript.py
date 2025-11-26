"""GDScript file analyzer - for Godot game engine scripts."""

import re
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer, register


@register('.gd', name='GDScript', icon='')
class GDScriptAnalyzer(FileAnalyzer):
    """GDScript file analyzer for Godot Engine.

    Extracts classes, functions, signals, and variables.
    """

    def get_structure(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract GDScript structure."""
        classes = []
        functions = []
        signals = []
        variables = []

        for i, line in enumerate(self.lines, 1):
            # Match class definition: class ClassName:
            class_match = re.match(r'^\s*class\s+(\w+)\s*:', line)
            if class_match:
                classes.append({
                    'line': i,
                    'name': class_match.group(1),
                })
                continue

            # Match function definition: func function_name(...):
            func_match = re.match(r'^\s*func\s+(\w+)\s*\((.*?)\)\s*(?:->\s*(.+?))?\s*:', line)
            if func_match:
                name = func_match.group(1)
                params = func_match.group(2).strip()
                return_type = func_match.group(3).strip() if func_match.group(3) else None

                signature = f"({params})"
                if return_type:
                    signature += f" -> {return_type}"

                functions.append({
                    'line': i,
                    'name': name,
                    'signature': signature,
                })
                continue

            # Match signal: signal signal_name or signal signal_name(params)
            signal_match = re.match(r'^\s*signal\s+(\w+)(?:\((.*?)\))?\s*$', line)
            if signal_match:
                name = signal_match.group(1)
                params = signal_match.group(2) if signal_match.group(2) else ''

                signals.append({
                    'line': i,
                    'name': name,
                    'signature': f"({params})" if params else "()",
                })
                continue

            # Match variables: var/const/export
            var_match = re.match(r'^\s*(?:(export|onready)\s+)?(?:(var|const)\s+)?(\w+)(?:\s*:\s*(\w+))?(?:\s*=\s*(.+?))?\s*(?:#.*)?$', line)
            if var_match and var_match.group(2) in ('var', 'const'):
                modifier = var_match.group(1) or ''
                var_type = var_match.group(2)
                name = var_match.group(3)
                type_hint = var_match.group(4) or ''

                # Skip if this looks like a function call or other syntax
                if name and not name.startswith('_'):
                    var_kind = f"{modifier} {var_type}".strip()
                    type_info = f": {type_hint}" if type_hint else ""

                    variables.append({
                        'line': i,
                        'name': name,
                        'kind': var_kind,
                        'type': type_hint or 'Variant',
                    })

        result = {}
        if classes:
            result['classes'] = classes
        if functions:
            result['functions'] = functions
        if signals:
            result['signals'] = signals
        if variables:
            result['variables'] = variables

        return result

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a specific GDScript element.

        Args:
            element_type: 'function', 'class', 'signal', or 'variable'
            name: Name of the element

        Returns:
            Dict with element info and source
        """
        # Find the element
        for i, line in enumerate(self.lines, 1):
            # Check for function
            if element_type == 'function':
                func_match = re.match(r'^\s*func\s+(\w+)\s*\(', line)
                if func_match and func_match.group(1) == name:
                    return self._extract_function(i)

            # Check for class
            elif element_type == 'class':
                class_match = re.match(r'^\s*class\s+(\w+)\s*:', line)
                if class_match and class_match.group(1) == name:
                    return self._extract_class(i)

            # Check for signal or variable (single line)
            elif re.search(rf'\b{re.escape(name)}\b', line):
                return {
                    'name': name,
                    'line_start': i,
                    'line_end': i,
                    'source': line,
                }

        # Fallback to grep-based search
        return super().extract_element(element_type, name)

    def _extract_function(self, start_line: int) -> Dict[str, Any]:
        """Extract a complete function definition."""
        # Find the end of the function (next func/class/end of file)
        indent_level = len(self.lines[start_line - 1]) - len(self.lines[start_line - 1].lstrip())
        end_line = len(self.lines)

        for i in range(start_line, len(self.lines)):
            line = self.lines[i]
            # Check if we've hit another function/class at same or lower indent
            if line.strip() and not line.startswith('#'):
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= indent_level and (line.strip().startswith('func ') or line.strip().startswith('class ')):
                    end_line = i
                    break

        source = '\n'.join(self.lines[start_line - 1:end_line])

        return {
            'name': re.search(r'func\s+(\w+)', self.lines[start_line - 1]).group(1),
            'line_start': start_line,
            'line_end': end_line,
            'source': source,
        }

    def _extract_class(self, start_line: int) -> Dict[str, Any]:
        """Extract a complete class definition."""
        # Find the end of the class (next class at same level or end of file)
        indent_level = len(self.lines[start_line - 1]) - len(self.lines[start_line - 1].lstrip())
        end_line = len(self.lines)

        for i in range(start_line, len(self.lines)):
            line = self.lines[i]
            if line.strip() and not line.startswith('#'):
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= indent_level and line.strip().startswith('class '):
                    end_line = i
                    break

        source = '\n'.join(self.lines[start_line - 1:end_line])

        return {
            'name': re.search(r'class\s+(\w+)', self.lines[start_line - 1]).group(1),
            'line_start': start_line,
            'line_end': end_line,
            'source': source,
        }
