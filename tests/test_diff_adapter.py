"""Tests for diff:// adapter."""

import unittest
import tempfile
import os
import shutil
import subprocess
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


class TestDirectoryDiff(unittest.TestCase):
    """Test directory comparison functionality."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_directory_diff_basic(self):
        """Test basic directory diff with files in both directories."""
        left_dir = Path(self.temp_dir) / "left"
        right_dir = Path(self.temp_dir) / "right"
        left_dir.mkdir()
        right_dir.mkdir()

        # Create same file with different content
        (left_dir / "module.py").write_text("def foo(): pass")
        (right_dir / "module.py").write_text("def foo(): pass\ndef bar(): pass")

        adapter = DiffAdapter(str(left_dir), str(right_dir))
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'diff')
        self.assertEqual(result['left']['type'], 'directory')
        self.assertEqual(result['right']['type'], 'directory')

        # Should detect added function
        self.assertEqual(result['summary']['functions']['added'], 1)
        self.assertEqual(result['summary']['functions']['removed'], 0)

    def test_directory_with_new_file(self):
        """Test directory diff when file only exists in right."""
        left_dir = Path(self.temp_dir) / "left"
        right_dir = Path(self.temp_dir) / "right"
        left_dir.mkdir()
        right_dir.mkdir()

        # File only in right
        (right_dir / "new_module.py").write_text("def new_func(): pass")

        adapter = DiffAdapter(str(left_dir), str(right_dir))
        result = adapter.get_structure()

        # Should show function added
        self.assertEqual(result['summary']['functions']['added'], 1)

    def test_directory_with_removed_file(self):
        """Test directory diff when file only exists in left."""
        left_dir = Path(self.temp_dir) / "left"
        right_dir = Path(self.temp_dir) / "right"
        left_dir.mkdir()
        right_dir.mkdir()

        # File only in left
        (left_dir / "old_module.py").write_text("def old_func(): pass")

        adapter = DiffAdapter(str(left_dir), str(right_dir))
        result = adapter.get_structure()

        # Should show function removed
        self.assertEqual(result['summary']['functions']['removed'], 1)

    def test_directory_file_metadata(self):
        """Test that file metadata is preserved in directory diffs."""
        left_dir = Path(self.temp_dir) / "left"
        right_dir = Path(self.temp_dir) / "right"
        left_dir.mkdir()
        right_dir.mkdir()

        (left_dir / "a.py").write_text("def foo(x): pass")
        (right_dir / "a.py").write_text("def foo(x, y): pass")

        adapter = DiffAdapter(str(left_dir), str(right_dir))
        result = adapter.get_structure()

        # Find the modified function
        modified = [f for f in result['diff']['functions'] if f['type'] == 'modified'][0]

        # Should have file metadata in both left and right
        self.assertEqual(modified['left']['file'], 'a.py')
        self.assertEqual(modified['right']['file'], 'a.py')

    def test_directory_nested_structure(self):
        """Test directory diff with nested directories."""
        left_dir = Path(self.temp_dir) / "left"
        right_dir = Path(self.temp_dir) / "right"
        left_dir.mkdir()
        right_dir.mkdir()
        (left_dir / "subdir").mkdir()
        (right_dir / "subdir").mkdir()

        # Create files in subdirectories
        (left_dir / "subdir" / "module.py").write_text("def foo(): pass")
        (right_dir / "subdir" / "module.py").write_text("def foo(): pass\ndef bar(): pass")

        adapter = DiffAdapter(str(left_dir), str(right_dir))
        result = adapter.get_structure()

        # Should detect changes in nested files
        self.assertEqual(result['summary']['functions']['added'], 1)

        # Check file path includes subdirectory
        modified = result['diff']['functions'][0]
        if 'file' in modified:
            self.assertIn('subdir', modified['file'])

    def test_empty_directories(self):
        """Test diff of empty directories."""
        left_dir = Path(self.temp_dir) / "left"
        right_dir = Path(self.temp_dir) / "right"
        left_dir.mkdir()
        right_dir.mkdir()

        adapter = DiffAdapter(str(left_dir), str(right_dir))
        result = adapter.get_structure()

        # Should show no changes
        self.assertEqual(result['summary']['functions']['added'], 0)
        self.assertEqual(result['summary']['functions']['removed'], 0)


class TestGitDiff(unittest.TestCase):
    """Test git integration for diffing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.git_dir = Path(self.temp_dir) / "git_repo"
        self.git_dir.mkdir()

        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'],
                      cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'],
                      cwd=self.git_dir, check=True, capture_output=True)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_git_file_diff(self):
        """Test diffing files across git commits."""
        # Create and commit initial version
        (self.git_dir / "file.py").write_text("def foo(): pass")
        subprocess.run(['git', 'add', 'file.py'], cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial'],
                      cwd=self.git_dir, check=True, capture_output=True)

        # Create second version
        (self.git_dir / "file.py").write_text("def foo(): pass\ndef bar(): pass")
        subprocess.run(['git', 'add', 'file.py'], cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Add bar'],
                      cwd=self.git_dir, check=True, capture_output=True)

        # Test diff
        os.chdir(self.git_dir)
        adapter = DiffAdapter('git://HEAD~1/file.py', 'git://HEAD/file.py')
        result = adapter.get_structure()

        self.assertEqual(result['summary']['functions']['added'], 1)

    def test_git_working_tree_diff(self):
        """Test diffing git HEAD vs working tree."""
        # Commit a file
        (self.git_dir / "module.py").write_text("def original(): pass")
        subprocess.run(['git', 'add', 'module.py'], cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial'],
                      cwd=self.git_dir, check=True, capture_output=True)

        # Modify without committing
        (self.git_dir / "module.py").write_text("def original(): pass\ndef new_func(): pass")

        # Compare HEAD vs working tree
        os.chdir(self.git_dir)
        adapter = DiffAdapter('git://HEAD/module.py', 'module.py')
        result = adapter.get_structure()

        self.assertEqual(result['summary']['functions']['added'], 1)


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
