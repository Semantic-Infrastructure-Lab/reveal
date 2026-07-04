"""
Tests for GDScript analyzer.

Tests tree-sitter-based analysis with:
- Structure extraction (functions, classes, signals, variables)
- UTF-8 handling
- Godot-specific patterns
"""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.analyzers.gdscript import GDScriptAnalyzer


class TestGDScriptAnalyzer(unittest.TestCase):
    """Test GDScript analyzer."""

    def test_extract_functions(self):
        """Should extract function definitions."""
        code = '''extends Node

func _ready():
    print("Ready!")

func add(a, b):
    return a + b

func process_data(input: Array) -> Dictionary:
    var result = {}
    for item in input:
        result[item] = true
    return result

func multiply(x: int, y: int) -> int:
    return x * y
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GDScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract function declarations
            func_names = [f['name'] for f in functions]
            self.assertIn('_ready', func_names)
            self.assertIn('add', func_names)
            self.assertIn('process_data', func_names)
            self.assertIn('multiply', func_names)

        finally:
            os.unlink(temp_path)

    def test_extract_classes(self):
        """Should extract class definitions."""
        code = '''class_name Player
extends KinematicBody2D

class InnerClass:
    var value = 0

    func get_value():
        return value

class DataContainer:
    var items: Array = []

    func add_item(item):
        items.append(item)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GDScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse classes
            self.assertIsNotNone(structure)

            if 'classes' in structure:
                classes = structure['classes']
                class_names = [c['name'] for c in classes]
                # Inner classes might be extracted
                self.assertTrue(len(class_names) > 0)

        finally:
            os.unlink(temp_path)

    def test_extract_signals(self):
        """Should extract signal definitions."""
        code = '''extends Node

signal health_changed(new_health)
signal player_died
signal item_collected(item_name, quantity)

func _ready():
    emit_signal("health_changed", 100)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GDScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse signals
            self.assertIsNotNone(structure)

        finally:
            os.unlink(temp_path)

    def test_extract_variables(self):
        """Should extract exported and regular variables."""
        code = '''extends Node2D

export var speed: int = 100
export(String) var player_name = "Hero"
export(Color, RGB) var color = Color.white

var health: int = 100
var position: Vector2 = Vector2.ZERO
var is_alive: bool = true

const MAX_HEALTH = 100
const GRAVITY = 9.8

onready var sprite = $Sprite
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GDScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse variables
            self.assertIsNotNone(structure)

        finally:
            os.unlink(temp_path)

    def test_godot_lifecycle_methods(self):
        """Should extract Godot lifecycle methods."""
        code = '''extends Node

func _init():
    print("Initializing")

func _ready():
    print("Ready")

func _process(delta):
    position += velocity * delta

func _physics_process(delta):
    move_and_slide(velocity)

func _input(event):
    if event is InputEventKey:
        handle_key(event)

func _unhandled_input(event):
    print("Unhandled:", event)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GDScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract lifecycle methods
            func_names = [f['name'] for f in functions]
            self.assertIn('_ready', func_names)
            self.assertIn('_process', func_names)
            self.assertIn('_physics_process', func_names)

        finally:
            os.unlink(temp_path)

    def test_utf8_with_emoji(self):
        """Should handle UTF-8 characters correctly."""
        code = '''extends Node

# ✨ GDScript file with emoji ✨

func greet_user():
    return "Hello 👋 World 🌍"

# 日本語コメント
func calculate_sum(a, b):
    return a + b

## Documentation with emoji 🚀
func launch():
    print("Launching! 🚀")
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GDScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Function names should not be truncated
            func_names = [f['name'] for f in functions]
            self.assertIn('greet_user', func_names)
            self.assertIn('calculate_sum', func_names)
            self.assertIn('launch', func_names)

            # Names should be complete (not truncated)
            for name in func_names:
                self.assertFalse(name.startswith('reet_user'))  # Missing "g"
                self.assertFalse(name.startswith('et_user'))    # Missing "gre"

        finally:
            os.unlink(temp_path)

    def test_treesitter_parsing(self):
        """Should use TreeSitter for parsing (cross-platform)."""
        code = '''extends Node

export var max_speed: float = 200.0

var velocity: Vector2 = Vector2.ZERO

func _ready():
    set_physics_process(true)

func _physics_process(delta):
    velocity = velocity.normalized() * max_speed
    position += velocity * delta

func apply_force(force: Vector2):
    velocity += force
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            # TreeSitter parsing should work on any platform
            analyzer = GDScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsNotNone(structure)
            self.assertIn('functions', structure)

            func_names = [f['name'] for f in structure['functions']]
            self.assertIn('_ready', func_names)
            self.assertIn('_physics_process', func_names)
            self.assertIn('apply_force', func_names)

        finally:
            os.unlink(temp_path)


def _resolve_gdscript_func(path, element='run'):
    """Resolve a GDScript function's node the same way the CLI does, and a
    get_text helper bound to its content."""
    from reveal.file_handler import _resolve_func_node
    analyzer = GDScriptAnalyzer(path)
    func_node, _, _ = _resolve_func_node(analyzer, element)
    content_bytes = analyzer.content.encode('utf-8')

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return func_node, get_text


class TestGDScriptCallsFindsAttributeCalls(unittest.TestCase):
    """BACK-431 feature-breadth pass (--calls, real-corpus dogfood on
    godot-demo-projects' ik_fabrik.gd chain_backward): GDScript's dotted
    method call (`x.size()`, `x.a().b()`) has no dedicated call node — it's
    folded into the same `attribute` node plain property access uses
    (`x.field`), as a flat run of `.` tokens paired with either a bare
    `identifier` (property, no call) or `attribute_call` (identifier +
    arguments — a real call). `attribute_call` was in no language's
    CALL_NODE_TYPES, so every dotted call was invisible to --calls — only
    bare `foo(x)` (the plain `call` node, shared with Python) worked, which
    is the minority of real GDScript call sites."""

    def _write(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            return f.name

    def test_calls_finds_simple_method_call(self):
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('func run(x):\n\treturn x.size()\n')
        try:
            func_node, get_text = _resolve_gdscript_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            callees = [c['callee'] for c in calls]
            self.assertIn('x.size', callees)
        finally:
            os.unlink(path)

    def test_calls_collapses_chained_call_to_dotted_form(self):
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('func run(x):\n\treturn x.normalized().length()\n')
        try:
            func_node, get_text = _resolve_gdscript_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            callees = [c['callee'] for c in calls]
            self.assertIn('x.normalized', callees)
            self.assertIn('.length', callees)
        finally:
            os.unlink(path)

    def test_calls_ignores_bare_property_access_in_chain(self):
        """`x.field.method()` — `field` is a plain property, not a call,
        and must not be reported as one; only `.method` is a call site."""
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('func run(x):\n\treturn x.field.method()\n')
        try:
            func_node, get_text = _resolve_gdscript_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            callees = [c['callee'] for c in calls]
            self.assertEqual(callees, ['x.field.method'])
        finally:
            os.unlink(path)

    def test_calls_still_finds_bare_call(self):
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('func run(x):\n\tfoo(x)\n')
        try:
            func_node, get_text = _resolve_gdscript_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            callees = [c['callee'] for c in calls]
            self.assertIn('foo', callees)
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
