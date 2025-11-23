"""
Tests for Python analyzer.

Tests AST-based analysis of Python source files.
"""

import unittest
from reveal.analyzers.python_analyzer import PythonAnalyzer


class TestPythonAnalyzerStructure(unittest.TestCase):
    """Test Python structure analysis."""

    def test_extract_imports(self):
        """Should extract import statements."""
        code = """import os
import sys
from pathlib import Path
from typing import List, Dict
"""
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        imports = structure['imports']
        self.assertIn('os', imports)
        self.assertIn('sys', imports)
        self.assertIn('pathlib.Path', imports)
        self.assertIn('typing.List', imports)
        self.assertIn('typing.Dict', imports)

    def test_extract_classes(self):
        """Should extract class definitions with line numbers."""
        code = """class User:
    pass

class Product:
    def __init__(self):
        pass

class Manager(User):
    pass
"""
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        classes = structure['classes']
        self.assertEqual(len(classes), 3)

        # Check class names
        class_names = [c['name'] for c in classes]
        self.assertIn('User', class_names)
        self.assertIn('Product', class_names)
        self.assertIn('Manager', class_names)

        # Check line numbers
        class_dict = {c['name']: c['line'] for c in classes}
        self.assertEqual(class_dict['User'], 1)
        self.assertEqual(class_dict['Product'], 4)
        self.assertEqual(class_dict['Manager'], 8)

    def test_extract_functions(self):
        """Should extract top-level function definitions."""
        code = """def hello():
    print('hello')

def calculate(x, y):
    return x + y

async def async_fetch():
    pass
"""
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        functions = structure['functions']
        self.assertEqual(len(functions), 3)

        func_names = [f['name'] for f in functions]
        self.assertIn('hello', func_names)
        self.assertIn('calculate', func_names)
        self.assertIn('async_fetch', func_names)

        func_dict = {f['name']: f['line'] for f in functions}
        self.assertEqual(func_dict['hello'], 1)
        self.assertEqual(func_dict['calculate'], 4)
        self.assertEqual(func_dict['async_fetch'], 7)

    def test_extract_assignments(self):
        """Should extract top-level variable assignments."""
        code = """VERSION = "1.0.0"
DEBUG = True
CONFIG = {"key": "value"}
"""
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assignments = structure['assignments']
        self.assertEqual(len(assignments), 3)

        assign_names = [a['name'] for a in assignments]
        self.assertIn('VERSION', assign_names)
        self.assertIn('DEBUG', assign_names)
        self.assertIn('CONFIG', assign_names)

    def test_ignore_nested_functions(self):
        """Should only extract top-level functions, not nested ones."""
        code = """def outer():
    def inner():
        pass
    return inner

def top_level():
    pass
"""
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        functions = structure['functions']
        func_names = [f['name'] for f in functions]

        # Should only include top-level functions
        self.assertIn('outer', func_names)
        self.assertIn('top_level', func_names)
        self.assertNotIn('inner', func_names)

    def test_complex_imports(self):
        """Should handle complex import patterns."""
        code = """import os.path
from collections import defaultdict, Counter
from . import module
from ..parent import something
"""
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        imports = structure['imports']
        self.assertIn('os.path', imports)
        self.assertIn('collections.defaultdict', imports)
        self.assertIn('collections.Counter', imports)

    def test_empty_file(self):
        """Should handle empty Python files."""
        lines = []
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        self.assertEqual(structure['imports'], [])
        self.assertEqual(structure['classes'], [])
        self.assertEqual(structure['functions'], [])
        self.assertEqual(structure['assignments'], [])

    def test_syntax_error_handling(self):
        """Should gracefully handle syntax errors."""
        code = """def broken(
    # Missing closing parenthesis
"""
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        # Should have error field
        self.assertIn('error', structure)
        self.assertIsNotNone(structure['error'])

        # Should return empty lists
        self.assertEqual(structure['imports'], [])
        self.assertEqual(structure['classes'], [])
        self.assertEqual(structure['functions'], [])


class TestPythonAnalyzerPreview(unittest.TestCase):
    """Test Python preview generation."""

    def test_preview_with_module_docstring(self):
        """Should include module docstring in preview."""
        code = '''"""This is a module docstring.

It has multiple lines.
"""

def function():
    pass
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        preview = analyzer.generate_preview()

        # Should include docstring lines
        preview_lines = [line for _, line in preview]
        self.assertTrue(any('module docstring' in line for line in preview_lines))

    def test_preview_with_class_docstring(self):
        """Should include class definitions and docstrings."""
        code = '''class User:
    """User class docstring."""

    def method(self):
        pass
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        preview = analyzer.generate_preview()

        # Should include class definition
        preview_lines = [line for _, line in preview]
        self.assertTrue(any('class User' in line for line in preview_lines))

    def test_preview_with_function_docstring(self):
        """Should include function signatures and docstrings."""
        code = '''def calculate(x, y):
    """Calculate something."""
    return x + y

def another():
    """Another function."""
    pass
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        preview = analyzer.generate_preview()

        preview_lines = [line for _, line in preview]
        self.assertTrue(any('def calculate' in line for line in preview_lines))
        self.assertTrue(any('def another' in line for line in preview_lines))

    def test_preview_line_numbers(self):
        """Preview should return tuples with line numbers."""
        code = '''class Example:
    pass

def function():
    pass
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        preview = analyzer.generate_preview()

        # All preview items should be (line_num, line_content) tuples
        for item in preview:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)
            line_num, line_content = item
            self.assertIsInstance(line_num, int)
            self.assertIsInstance(line_content, str)

    def test_preview_sorted_by_line_number(self):
        """Preview should be sorted by line number."""
        code = '''def last():
    pass

class Middle:
    pass

def first():
    pass
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        preview = analyzer.generate_preview()

        line_numbers = [line_num for line_num, _ in preview]
        # Should be in ascending order
        self.assertEqual(line_numbers, sorted(line_numbers))

    def test_preview_limits_lines(self):
        """Preview should limit number of lines shown."""
        # Create large file with many functions
        code = '\n'.join([f'def func{i}():\n    pass\n' for i in range(50)])
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        preview = analyzer.generate_preview()

        # Should be limited (max 30 lines)
        self.assertLessEqual(len(preview), 30)

    def test_preview_with_syntax_error(self):
        """Preview should work even with syntax errors."""
        code = '''def broken(
    # syntax error
this is broken
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        preview = analyzer.generate_preview()

        # Should fall back to showing first 20 lines
        self.assertGreater(len(preview), 0)
        preview_lines = [line for _, line in preview]
        self.assertTrue(any('broken' in line for line in preview_lines))


class TestPythonAnalyzerWithFilePath(unittest.TestCase):
    """Test Python analyzer with file_path parameter."""

    def test_analyzer_stores_file_path(self):
        """Should store file_path when provided."""
        code = "def hello():\n    pass"
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines, file_path='example.py')

        self.assertEqual(analyzer.file_path, 'example.py')

    def test_format_location_with_file_path(self):
        """Should format location with file_path."""
        code = "def hello():\n    pass"
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines, file_path='test.py')

        loc = analyzer.format_location(5)
        self.assertEqual(loc, 'test.py:5')

    def test_format_location_without_file_path(self):
        """Should use L0000 format without file_path."""
        code = "def hello():\n    pass"
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)

        loc = analyzer.format_location(5)
        self.assertEqual(loc, 'L0005')


class TestPythonAnalyzerRealWorld(unittest.TestCase):
    """Test Python analyzer with real-world code patterns."""

    def test_analyze_class_with_methods(self):
        """Should analyze class with methods correctly."""
        code = '''class Calculator:
    """A simple calculator."""

    def __init__(self):
        self.result = 0

    def add(self, x, y):
        """Add two numbers."""
        return x + y

    def subtract(self, x, y):
        """Subtract two numbers."""
        return x - y
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        # Should extract the class
        classes = structure['classes']
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0]['name'], 'Calculator')

        # Methods are nested, so not in top-level functions
        functions = structure['functions']
        func_names = [f['name'] for f in functions]
        self.assertNotIn('add', func_names)
        self.assertNotIn('subtract', func_names)

    def test_analyze_decorator_usage(self):
        """Should handle decorators correctly."""
        code = '''@property
def value(self):
    return self._value

@staticmethod
def helper():
    pass

@classmethod
def create(cls):
    return cls()
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        functions = structure['functions']
        func_names = [f['name'] for f in functions]
        self.assertIn('value', func_names)
        self.assertIn('helper', func_names)
        self.assertIn('create', func_names)

    def test_analyze_type_hints(self):
        """Should handle type hints correctly."""
        code = '''from typing import List, Dict, Optional

def process(data: List[str]) -> Dict[str, int]:
    pass

def fetch(url: str) -> Optional[str]:
    pass
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        # Should extract functions
        functions = structure['functions']
        self.assertEqual(len(functions), 2)

        # Should extract imports
        imports = structure['imports']
        self.assertIn('typing.List', imports)
        self.assertIn('typing.Dict', imports)
        self.assertIn('typing.Optional', imports)

    def test_analyze_dataclass(self):
        """Should analyze dataclasses."""
        code = '''from dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int
    email: str = ""
'''
        lines = code.split('\n')
        analyzer = PythonAnalyzer(lines)
        structure = analyzer.analyze_structure()

        classes = structure['classes']
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0]['name'], 'User')


if __name__ == '__main__':
    unittest.main()
