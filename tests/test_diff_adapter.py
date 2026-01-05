"""Tests for diff:// adapter."""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.adapters.diff import DiffAdapter
from reveal.cli.scheme_handlers.diff import parse_diff_uris


class TestDiffAdapter(unittest.TestCase):
    """Test diff:// adapter functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def create_file(self, content: str, filename: str) -> str:
        """Create a temporary file with given content.

        Args:
            content: File content
            filename: Filename

        Returns:
            Full path to created file
        """
        path = os.path.join(self.temp_dir, filename)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_simple_file_diff_no_changes(self):
        """Test diffing two identical Python files."""
        content = """
def foo():
    return 42

def bar():
    return "hello"
"""
        path1 = self.create_file(content, "v1.py")
        path2 = self.create_file(content, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Verify no changes
        self.assertEqual(result['type'], 'diff')
        self.assertEqual(result['summary']['functions']['added'], 0)
        self.assertEqual(result['summary']['functions']['removed'], 0)
        self.assertEqual(result['summary']['functions']['modified'], 0)

    def test_function_added(self):
        """Test detecting added functions."""
        v1 = """
def foo():
    return 42
"""
        v2 = """
def foo():
    return 42

def bar():
    return "hello"
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Verify function added
        self.assertEqual(result['summary']['functions']['added'], 1)
        self.assertEqual(result['summary']['functions']['removed'], 0)
        self.assertEqual(result['summary']['functions']['modified'], 0)

        # Check details
        func_details = result['diff']['functions']
        added_funcs = [f for f in func_details if f['type'] == 'added']
        self.assertEqual(len(added_funcs), 1)
        self.assertEqual(added_funcs[0]['name'], 'bar')

    def test_function_removed(self):
        """Test detecting removed functions."""
        v1 = """
def foo():
    return 42

def bar():
    return "hello"
"""
        v2 = """
def foo():
    return 42
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Verify function removed
        self.assertEqual(result['summary']['functions']['added'], 0)
        self.assertEqual(result['summary']['functions']['removed'], 1)
        self.assertEqual(result['summary']['functions']['modified'], 0)

        # Check details
        func_details = result['diff']['functions']
        removed_funcs = [f for f in func_details if f['type'] == 'removed']
        self.assertEqual(len(removed_funcs), 1)
        self.assertEqual(removed_funcs[0]['name'], 'bar')

    def test_function_signature_changed(self):
        """Test detecting function signature changes."""
        v1 = """
def foo(x):
    return x * 2
"""
        v2 = """
def foo(x, y):
    return x * y
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Verify function modified
        self.assertEqual(result['summary']['functions']['added'], 0)
        self.assertEqual(result['summary']['functions']['removed'], 0)
        self.assertEqual(result['summary']['functions']['modified'], 1)

        # Check details
        func_details = result['diff']['functions']
        modified_funcs = [f for f in func_details if f['type'] == 'modified']
        self.assertEqual(len(modified_funcs), 1)
        self.assertEqual(modified_funcs[0]['name'], 'foo')
        self.assertIn('signature', modified_funcs[0]['changes'])

    def test_function_complexity_changed(self):
        """Test detecting function complexity changes."""
        v1 = """
def process(x):
    return x
"""
        v2 = """
def process(x):
    if x > 0:
        if x > 10:
            if x > 20:
                return x * 3
            return x * 2
        return x * 1
    return 0
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Verify complexity increase detected
        self.assertEqual(result['summary']['functions']['modified'], 1)

        # Check complexity delta
        func_details = result['diff']['functions']
        modified_funcs = [f for f in func_details if f['type'] == 'modified']
        self.assertEqual(len(modified_funcs), 1)
        changes = modified_funcs[0]['changes']
        self.assertIn('complexity', changes)
        self.assertGreater(changes['complexity']['new'], changes['complexity']['old'])

    def test_class_added(self):
        """Test detecting added classes."""
        v1 = """
def foo():
    pass
"""
        v2 = """
def foo():
    pass

class MyClass:
    def method(self):
        pass
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Verify class added
        self.assertEqual(result['summary']['classes']['added'], 1)
        self.assertEqual(result['summary']['classes']['removed'], 0)

        # Check details
        class_details = result['diff']['classes']
        added_classes = [c for c in class_details if c['type'] == 'added']
        self.assertEqual(len(added_classes), 1)
        self.assertEqual(added_classes[0]['name'], 'MyClass')

    def test_import_changes(self):
        """Test detecting import changes."""
        v1 = """
import os
import sys
"""
        v2 = """
import os
import json
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Verify import changes
        self.assertEqual(result['summary']['imports']['added'], 1)
        self.assertEqual(result['summary']['imports']['removed'], 1)

    def test_element_specific_diff(self):
        """Test element-specific diff."""
        v1 = """
def foo(x):
    return x

def bar():
    return 42
"""
        v2 = """
def foo(x, y):
    return x + y

def bar():
    return 42
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_element('foo')

        # Verify element diff
        self.assertEqual(result['type'], 'modified')
        self.assertEqual(result['name'], 'foo')
        self.assertIn('signature', result['changes'])

    def test_element_not_found(self):
        """Test element-specific diff when element doesn't exist."""
        v1 = """
def foo():
    pass
"""
        v2 = """
def bar():
    pass
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_element('baz')

        # Verify not found
        self.assertEqual(result['type'], 'not_found')
        self.assertEqual(result['name'], 'baz')

    def test_element_added(self):
        """Test element-specific diff when element was added."""
        v1 = """
def foo():
    pass
"""
        v2 = """
def foo():
    pass

def bar():
    return 42
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_element('bar')

        # Verify added
        self.assertEqual(result['type'], 'added')
        self.assertEqual(result['name'], 'bar')

    def test_element_removed(self):
        """Test element-specific diff when element was removed."""
        v1 = """
def foo():
    pass

def bar():
    return 42
"""
        v2 = """
def foo():
    pass
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_element('bar')

        # Verify removed
        self.assertEqual(result['type'], 'removed')
        self.assertEqual(result['name'], 'bar')


class TestDiffURIParsing(unittest.TestCase):
    """Test URI parsing for diff:// adapter."""

    def test_simple_file_paths(self):
        """Test parsing simple file paths."""
        left, right = parse_diff_uris("app.py:backup/app.py")
        self.assertEqual(left, "app.py")
        self.assertEqual(right, "backup/app.py")

    def test_explicit_file_scheme(self):
        """Test parsing with explicit file:// scheme."""
        left, right = parse_diff_uris("file://app.py:file://backup/app.py")
        self.assertEqual(left, "file://app.py")
        self.assertEqual(right, "file://backup/app.py")

    def test_env_scheme(self):
        """Test parsing env:// URIs."""
        left, right = parse_diff_uris("env://:env://production")
        self.assertEqual(left, "env://")
        self.assertEqual(right, "env://production")

    def test_mixed_schemes(self):
        """Test parsing mixed schemes."""
        left, right = parse_diff_uris("app.py:env://production")
        self.assertEqual(left, "app.py")
        self.assertEqual(right, "env://production")

    def test_mysql_scheme(self):
        """Test parsing mysql:// URIs."""
        left, right = parse_diff_uris("mysql://localhost/db:mysql://staging/db")
        self.assertEqual(left, "mysql://localhost/db")
        self.assertEqual(right, "mysql://staging/db")

    def test_invalid_format(self):
        """Test error handling for invalid format."""
        with self.assertRaises(ValueError):
            parse_diff_uris("nocolon")


class TestDiffMetadata(unittest.TestCase):
    """Test diff adapter metadata functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def create_file(self, content: str, filename: str) -> str:
        """Create a temporary file."""
        path = os.path.join(self.temp_dir, filename)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_metadata(self):
        """Test get_metadata method."""
        v1 = "def foo(): pass"
        v2 = "def bar(): pass"
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        metadata = adapter.get_metadata()

        self.assertEqual(metadata['type'], 'diff')
        self.assertEqual(metadata['left_uri'], path1)
        self.assertEqual(metadata['right_uri'], path2)

    def test_help_documentation(self):
        """Test that help documentation is available."""
        help_doc = DiffAdapter.get_help()

        self.assertIsNotNone(help_doc)
        self.assertEqual(help_doc['name'], 'diff')
        self.assertIn('description', help_doc)
        self.assertIn('examples', help_doc)
        self.assertGreaterEqual(len(help_doc['examples']), 3)


if __name__ == '__main__':
    unittest.main()
