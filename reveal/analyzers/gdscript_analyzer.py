"""GDScript file analyzer for Godot Engine."""

import re
from typing import Dict, Any, List
from .base import BaseAnalyzer
from ..registry import register


@register(['.gd'], name='GDScript', icon='🎮')
class GDScriptAnalyzer(BaseAnalyzer):
    """Analyzer for GDScript files (Godot Engine)"""

    def __init__(self, lines: List[str], **kwargs):
        super().__init__(lines, **kwargs)

    def analyze_structure(self) -> Dict[str, Any]:
        """Analyze GDScript structure."""
        extends_class = None
        class_name = None
        signals = []
        exports = []
        functions = []
        constants = []
        variables = []

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # extends declaration
            if stripped.startswith('extends '):
                extends_class = stripped[8:].strip()

            # class_name declaration
            elif stripped.startswith('class_name '):
                class_name = stripped[11:].strip()

            # signal definitions
            elif stripped.startswith('signal '):
                signal_match = re.match(r'signal\s+(\w+)', stripped)
                if signal_match:
                    signals.append({'name': signal_match.group(1), 'line': i})

            # @export variables
            elif stripped.startswith('@export'):
                # Look for variable on same line or next line
                var_match = re.search(r'var\s+(\w+)', stripped)
                if var_match:
                    exports.append({'name': var_match.group(1), 'line': i})
                elif i < len(self.lines):
                    next_line = self.lines[i].strip()
                    var_match = re.search(r'var\s+(\w+)', next_line)
                    if var_match:
                        exports.append({'name': var_match.group(1), 'line': i + 1})

            # const declarations
            elif stripped.startswith('const '):
                const_match = re.match(r'const\s+(\w+)', stripped)
                if const_match:
                    constants.append({'name': const_match.group(1), 'line': i})

            # var declarations (not exported)
            elif stripped.startswith('var ') and not any(e['line'] == i for e in exports):
                var_match = re.match(r'var\s+(\w+)', stripped)
                if var_match:
                    variables.append({'name': var_match.group(1), 'line': i})

            # function definitions
            elif stripped.startswith('func '):
                func_match = re.match(r'func\s+(\w+)', stripped)
                if func_match:
                    func_name = func_match.group(1)
                    # Mark special Godot lifecycle functions
                    is_lifecycle = func_name in ['_ready', '_process', '_physics_process',
                                                  '_input', '_unhandled_input', '_enter_tree',
                                                  '_exit_tree', '_draw', '_notification']
                    functions.append({
                        'name': func_name,
                        'line': i,
                        'lifecycle': is_lifecycle
                    })

        return {
            'extends': extends_class,
            'class_name': class_name,
            'signals': signals,
            'exports': exports,
            'constants': constants,
            'variables': variables,
            'functions': functions
        }

    def generate_preview(self) -> List[tuple[int, str]]:
        """Generate GDScript preview showing key elements."""
        preview = []

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # Include extends/class_name
            if stripped.startswith('extends ') or stripped.startswith('class_name '):
                preview.append((i, line))

            # Include comments at the top (documentation)
            elif stripped.startswith('#') and i <= 10:
                preview.append((i, line))

            # Include signal definitions
            elif stripped.startswith('signal '):
                preview.append((i, line))

            # Include @export declarations
            elif stripped.startswith('@export'):
                preview.append((i, line))
                # Include the variable line too
                if i < len(self.lines) and self.lines[i].strip().startswith('var '):
                    preview.append((i + 1, self.lines[i]))

            # Include const declarations
            elif stripped.startswith('const '):
                preview.append((i, line))

            # Include function signatures
            elif stripped.startswith('func '):
                preview.append((i, line))
                # Include function docstring if present
                if i < len(self.lines):
                    next_line = self.lines[i].strip()
                    if next_line.startswith('#'):
                        preview.append((i + 1, self.lines[i]))

        # Sort by line number and limit to first 40 lines
        preview = sorted(list(set(preview)), key=lambda x: x[0])
        return preview[:40]

    def format_structure(self, structure: Dict[str, Any]) -> List[str]:
        """Format GDScript structure output."""
        output = []

        # Class inheritance
        if structure['extends']:
            output.append(f"Extends: {structure['extends']}")
        if structure['class_name']:
            output.append(f"Class Name: {structure['class_name']}")

        if structure['extends'] or structure['class_name']:
            output.append("")

        # Signals
        if structure['signals']:
            output.append("Signals:")
            for sig in structure['signals']:
                loc = self.format_location(sig['line'])
                output.append(f"  {loc:<30}  signal {sig['name']}")
            output.append("")

        # Exported variables
        if structure['exports']:
            output.append("Exported Variables:")
            for exp in structure['exports']:
                loc = self.format_location(exp['line'])
                output.append(f"  {loc:<30}  @export var {exp['name']}")
            output.append("")

        # Constants
        if structure['constants']:
            output.append("Constants:")
            for const in structure['constants']:
                loc = self.format_location(const['line'])
                output.append(f"  {loc:<30}  const {const['name']}")
            output.append("")

        # Variables
        if structure['variables']:
            output.append("Variables:")
            for var in structure['variables'][:10]:  # Limit to first 10
                loc = self.format_location(var['line'])
                output.append(f"  {loc:<30}  var {var['name']}")
            if len(structure['variables']) > 10:
                output.append(f"  ... and {len(structure['variables']) - 10} more")
            output.append("")

        # Functions
        if structure['functions']:
            output.append("Functions:")
            lifecycle = [f for f in structure['functions'] if f.get('lifecycle')]
            regular = [f for f in structure['functions'] if not f.get('lifecycle')]

            if lifecycle:
                output.append("  Lifecycle:")
                for func in lifecycle:
                    loc = self.format_location(func['line'])
                    output.append(f"    {loc:<30}  func {func['name']}()")

            if regular:
                if lifecycle:
                    output.append("  Custom:")
                for func in regular:
                    loc = self.format_location(func['line'])
                    output.append(f"    {loc:<30}  func {func['name']}()")

        return output
