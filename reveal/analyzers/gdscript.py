"""GDScript file analyzer - for Godot game engine scripts."""

import re
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer, register


@register('.gd', name='GDScript', icon='')
class GDScriptAnalyzer(FileAnalyzer):
    """GDScript file analyzer for Godot Engine.

    Extracts classes, functions, signals, and variables.
    """

    def _parse_class_line(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a class definition line."""
        class_match = re.match(r'^\s*class\s+(\w+)\s*:', line)
        if class_match:
            return {
                'line': line_num,
                'name': class_match.group(1),
            }
        return None

    def _parse_function_line(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a function definition line."""
        func_match = re.match(r'^\s*func\s+(\w+)\s*\((.*?)\)\s*(?:->\s*(.+?))?\s*:', line)
        if func_match:
            name = func_match.group(1)
            params = func_match.group(2).strip()
            return_type = func_match.group(3).strip() if func_match.group(3) else None

            signature = f"({params})"
            if return_type:
                signature += f" -> {return_type}"

            return {
                'line': line_num,
                'name': name,
                'signature': signature,
            }
        return None

    def _parse_signal_line(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a signal definition line."""
        signal_match = re.match(r'^\s*signal\s+(\w+)(?:\((.*?)\))?\s*$', line)
        if signal_match:
            name = signal_match.group(1)
            params = signal_match.group(2) if signal_match.group(2) else ''

            return {
                'line': line_num,
                'name': name,
                'signature': f"({params})" if params else "()",
            }
        return None

    def _parse_variable_line(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a variable definition line."""
        var_match = re.match(r'^\s*(?:(export|onready)\s+)?(?:(var|const)\s+)?(\w+)(?:\s*:\s*(\w+))?(?:\s*=\s*(.+?))?\s*(?:#.*)?$', line)
        if var_match and var_match.group(2) in ('var', 'const'):
            modifier = var_match.group(1) or ''
            var_type = var_match.group(2)
            name = var_match.group(3)
            type_hint = var_match.group(4) or ''

            # Skip if this looks like a function call or other syntax
            if name and not name.startswith('_'):
                var_kind = f"{modifier} {var_type}".strip()

                return {
                    'line': line_num,
                    'name': name,
                    'kind': var_kind,
                    'type': type_hint or 'Variant',
                }
        return None

    def _build_result(self, classes: List, functions: List, signals: List, variables: List) -> Dict[str, List[Dict[str, Any]]]:
        """Build result dictionary from parsed elements."""
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

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract GDScript structure."""
        classes = []
        functions = []
        signals = []
        variables = []

        for i, line in enumerate(self.lines, 1):
            # Try parsing each element type
            if (class_def := self._parse_class_line(line, i)):
                classes.append(class_def)
            elif (func_def := self._parse_function_line(line, i)):
                functions.append(func_def)
            elif (signal_def := self._parse_signal_line(line, i)):
                signals.append(signal_def)
            elif (var_def := self._parse_variable_line(line, i)):
                variables.append(var_def)

        return self._build_result(classes, functions, signals, variables)

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
