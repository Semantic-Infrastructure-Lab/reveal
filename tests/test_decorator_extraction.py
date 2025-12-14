"""
Tests for TreeSitter decorator extraction.

Verifies that Python decorators are correctly extracted from:
- Functions with single decorator
- Functions with multiple decorators
- Decorated classes
- Decorators with arguments
- Mixed decorated and undecorated definitions
"""

import unittest
import tempfile
import os
from reveal.analyzers.python import PythonAnalyzer


class TestDecoratorExtraction(unittest.TestCase):
    """Test that TreeSitter correctly extracts Python decorators."""

    def _analyze_code(self, code: str) -> dict:
        """Helper to analyze Python code and return structure."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PythonAnalyzer(temp_path)
            return analyzer.get_structure()
        finally:
            os.unlink(temp_path)

    def test_single_decorator_on_function(self):
        """Function with single decorator should have it extracted."""
        code = '''
@property
def name(self):
    return self._name
'''
        structure = self._analyze_code(code)
        functions = structure.get('functions', [])

        self.assertEqual(len(functions), 1)
        func = functions[0]
        self.assertEqual(func['name'], 'name')
        self.assertEqual(func['decorators'], ['@property'])

    def test_multiple_decorators_on_function(self):
        """Function with multiple decorators should have all extracted in order."""
        code = '''
@lru_cache(maxsize=100)
@functools.wraps(func)
def cached_func(x):
    return x * 2
'''
        structure = self._analyze_code(code)
        functions = structure.get('functions', [])

        self.assertEqual(len(functions), 1)
        func = functions[0]
        self.assertEqual(func['name'], 'cached_func')
        self.assertEqual(len(func['decorators']), 2)
        self.assertEqual(func['decorators'][0], '@lru_cache(maxsize=100)')
        self.assertEqual(func['decorators'][1], '@functools.wraps(func)')

    def test_staticmethod_decorator(self):
        """@staticmethod should be extracted."""
        code = '''
@staticmethod
def helper():
    pass
'''
        structure = self._analyze_code(code)
        functions = structure.get('functions', [])

        self.assertEqual(len(functions), 1)
        self.assertEqual(functions[0]['decorators'], ['@staticmethod'])

    def test_classmethod_decorator(self):
        """@classmethod should be extracted."""
        code = '''
@classmethod
def from_config(cls, config):
    return cls(**config)
'''
        structure = self._analyze_code(code)
        functions = structure.get('functions', [])

        self.assertEqual(len(functions), 1)
        self.assertEqual(functions[0]['decorators'], ['@classmethod'])

    def test_decorated_class(self):
        """Class with decorator should have it extracted."""
        code = '''
@dataclass
class Config:
    name: str
    value: int
'''
        structure = self._analyze_code(code)
        classes = structure.get('classes', [])

        self.assertEqual(len(classes), 1)
        cls = classes[0]
        self.assertEqual(cls['name'], 'Config')
        self.assertEqual(cls['decorators'], ['@dataclass'])

    def test_class_with_multiple_decorators(self):
        """Class with multiple decorators should have all extracted."""
        code = '''
@dataclass
@frozen
class ImmutableConfig:
    name: str
'''
        structure = self._analyze_code(code)
        classes = structure.get('classes', [])

        self.assertEqual(len(classes), 1)
        cls = classes[0]
        self.assertEqual(len(cls['decorators']), 2)
        self.assertIn('@dataclass', cls['decorators'])
        self.assertIn('@frozen', cls['decorators'])

    def test_undecorated_function_has_empty_decorators(self):
        """Function without decorators should have empty decorators list."""
        code = '''
def plain_func():
    pass
'''
        structure = self._analyze_code(code)
        functions = structure.get('functions', [])

        self.assertEqual(len(functions), 1)
        self.assertEqual(functions[0]['decorators'], [])

    def test_undecorated_class_has_empty_decorators(self):
        """Class without decorators should have empty decorators list."""
        code = '''
class PlainClass:
    pass
'''
        structure = self._analyze_code(code)
        classes = structure.get('classes', [])

        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0]['decorators'], [])

    def test_mixed_decorated_and_undecorated(self):
        """Mix of decorated and undecorated definitions."""
        code = '''
@dataclass
class DecoratedClass:
    pass

class PlainClass:
    pass

@property
def decorated_func():
    pass

def plain_func():
    pass
'''
        structure = self._analyze_code(code)

        # Classes
        classes = structure.get('classes', [])
        self.assertEqual(len(classes), 2)

        decorated_cls = next(c for c in classes if c['name'] == 'DecoratedClass')
        plain_cls = next(c for c in classes if c['name'] == 'PlainClass')

        self.assertEqual(decorated_cls['decorators'], ['@dataclass'])
        self.assertEqual(plain_cls['decorators'], [])

        # Functions
        functions = structure.get('functions', [])
        self.assertEqual(len(functions), 2)

        decorated_func = next(f for f in functions if f['name'] == 'decorated_func')
        plain_func = next(f for f in functions if f['name'] == 'plain_func')

        self.assertEqual(decorated_func['decorators'], ['@property'])
        self.assertEqual(plain_func['decorators'], [])

    def test_decorator_with_dotted_name(self):
        """Decorators with dotted names like @app.route should work."""
        code = '''
@app.route('/api/users')
def get_users():
    return []
'''
        structure = self._analyze_code(code)
        functions = structure.get('functions', [])

        self.assertEqual(len(functions), 1)
        self.assertEqual(functions[0]['decorators'], ["@app.route('/api/users')"])

    def test_decorator_line_numbers_include_decorator(self):
        """Line numbers should include the decorator, not just the def."""
        code = '''# Line 1
# Line 2
@property
def name(self):
    return self._name
'''
        structure = self._analyze_code(code)
        functions = structure.get('functions', [])

        self.assertEqual(len(functions), 1)
        # Line starts at decorator (@property is line 3)
        self.assertEqual(functions[0]['line'], 3)

    def test_no_duplicate_entries(self):
        """Each function/class should appear exactly once."""
        code = '''
@dataclass
class Config:
    name: str

@property
def prop(self):
    return self._prop

def plain():
    pass

class Plain:
    pass
'''
        structure = self._analyze_code(code)

        classes = structure.get('classes', [])
        functions = structure.get('functions', [])

        # Should have exactly 2 classes, 2 functions
        self.assertEqual(len(classes), 2)
        self.assertEqual(len(functions), 2)

        # No duplicate names
        class_names = [c['name'] for c in classes]
        func_names = [f['name'] for f in functions]

        self.assertEqual(len(class_names), len(set(class_names)))
        self.assertEqual(len(func_names), len(set(func_names)))


if __name__ == '__main__':
    unittest.main()
