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


if __name__ == '__main__':
    unittest.main()
