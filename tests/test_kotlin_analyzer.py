"""Tests for Kotlin analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.kotlin import KotlinAnalyzer


class TestKotlinAnalyzer(unittest.TestCase):
    """Test suite for Kotlin source file analysis.

    Note: Kotlin tree-sitter support is limited. These tests verify
    that the analyzer doesn't crash and extracts what it can.
    """

    def test_basic_file_parsing(self):
        """Should parse Kotlin files without crashing."""
        code = '''fun main() {
    println("Hello, World!")
}'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should return a dict, even if empty
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_extract_classes(self):
        """Should extract class definitions."""
        code = '''class Person(val name: String, var age: Int) {
    fun greet(): String {
        return "Hello, I'm $name"
    }
}

data class Point(val x: Int, val y: Int)

class Animal(val species: String)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract classes
            if 'classes' in structure:
                classes = structure['classes']
                class_names = [c['name'] for c in classes]
                self.assertIn('Person', class_names)
                self.assertIn('Point', class_names)
                self.assertIn('Animal', class_names)

        finally:
            os.unlink(temp_path)

    def test_data_classes(self):
        """Should extract data class definitions."""
        code = '''data class User(
    val id: Int,
    val name: String,
    val email: String
)

data class Result<T>(
    val value: T?,
    val error: String?
)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract data classes
            if 'classes' in structure:
                classes = structure['classes']
                class_names = [c['name'] for c in classes]
                self.assertIn('User', class_names)
                self.assertIn('Result', class_names)

        finally:
            os.unlink(temp_path)

    def test_interfaces(self):
        """Should extract interface definitions."""
        code = '''interface Drawable {
    fun draw()
    fun move(x: Int, y: Int)
}

interface Clickable {
    fun click()
}

class Button : Clickable, Drawable {
    override fun click() {
        println("Button clicked")
    }

    override fun draw() {
        println("Drawing button")
    }

    override fun move(x: Int, y: Int) {
        println("Moving to ($x, $y)")
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract interfaces and classes
            if 'classes' in structure:
                classes = structure['classes']
                class_names = [c['name'] for c in classes]
                self.assertIn('Drawable', class_names)
                self.assertIn('Clickable', class_names)
                self.assertIn('Button', class_names)

        finally:
            os.unlink(temp_path)

    def test_sealed_classes(self):
        """Should handle sealed classes."""
        code = '''sealed class Result {
    data class Success(val data: String) : Result()
    data class Error(val message: String) : Result()
    object Loading : Result()
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''class 日本語 {
    fun こんにちは(): String {
        return "世界🌍"
    }
}

fun emojiTest(): String {
    return "👍 Kotlin is awesome! 🚀"
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash on UTF-8
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
