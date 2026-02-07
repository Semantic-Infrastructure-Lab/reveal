"""Tests for diff:// adapter."""

import unittest
import tempfile
import os
import sys
import shutil
import subprocess
from pathlib import Path
from reveal.adapters.diff import DiffAdapter


class TestDiffAdapter(unittest.TestCase):
    """Test diff:// adapter functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        # Restore original working directory
        os.chdir(self.original_cwd)
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
        self.assertEqual(result['type'], 'diff_comparison')
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

    def test_element_search_in_class_methods(self):
        """Test element search finds methods in classes."""
        v1 = """
class MyClass:
    def method_one(self):
        pass
"""
        v2 = """
class MyClass:
    def method_one(self, x):
        return x * 2
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_element('method_one')

        # Verify found and modified
        self.assertEqual(result['type'], 'modified')
        self.assertEqual(result['name'], 'method_one')
        self.assertIn('signature', result['changes'])


class TestDiffURIParsing(unittest.TestCase):
    """Test URI parsing for diff:// adapter."""

    def test_simple_file_paths(self):
        """Test parsing simple file paths."""
        left, right = DiffAdapter._parse_diff_uris("app.py:backup/app.py")
        self.assertEqual(left, "app.py")
        self.assertEqual(right, "backup/app.py")

    def test_explicit_file_scheme(self):
        """Test parsing with explicit file:// scheme."""
        left, right = DiffAdapter._parse_diff_uris("file://app.py:file://backup/app.py")
        self.assertEqual(left, "file://app.py")
        self.assertEqual(right, "file://backup/app.py")

    def test_env_scheme(self):
        """Test parsing env:// URIs."""
        left, right = DiffAdapter._parse_diff_uris("env://:env://production")
        self.assertEqual(left, "env://")
        self.assertEqual(right, "env://production")

    def test_mixed_schemes(self):
        """Test parsing mixed schemes."""
        left, right = DiffAdapter._parse_diff_uris("app.py:env://production")
        self.assertEqual(left, "app.py")
        self.assertEqual(right, "env://production")

    def test_mysql_scheme(self):
        """Test parsing mysql:// URIs."""
        left, right = DiffAdapter._parse_diff_uris("mysql://localhost/db:mysql://staging/db")
        self.assertEqual(left, "mysql://localhost/db")
        self.assertEqual(right, "mysql://staging/db")

    def test_invalid_format(self):
        """Test error handling for invalid format."""
        with self.assertRaises(ValueError):
            DiffAdapter._parse_diff_uris("nocolon")


class TestDirectoryDiff(unittest.TestCase):
    """Test directory comparison functionality."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        # Restore original working directory
        os.chdir(self.original_cwd)
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

        self.assertEqual(result['type'], 'diff_comparison')
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

    def test_directory_with_imports(self):
        """Test directory diff includes import changes."""
        left_dir = Path(self.temp_dir) / "left"
        right_dir = Path(self.temp_dir) / "right"
        left_dir.mkdir()
        right_dir.mkdir()

        # Create files with different imports
        (left_dir / "module.py").write_text("import os\nimport sys\ndef foo(): pass")
        (right_dir / "module.py").write_text("import os\nimport json\ndef foo(): pass")

        adapter = DiffAdapter(str(left_dir), str(right_dir))
        result = adapter.get_structure()

        # Should detect import changes
        self.assertEqual(result['summary']['imports']['added'], 1)
        self.assertEqual(result['summary']['imports']['removed'], 1)

        # Verify file metadata is preserved in imports
        if result['diff']['imports']:
            import_elem = result['diff']['imports'][0]
            if 'left' in import_elem and import_elem['left']:
                self.assertEqual(import_elem['left']['file'], 'module.py')

    def test_directory_not_found_error(self):
        """Test error when directory doesn't exist."""
        adapter = DiffAdapter("/nonexistent/path", str(self.temp_dir))
        with self.assertRaises(ValueError) as ctx:
            adapter.get_structure()
        # When directory doesn't exist, it's treated as a file with no analyzer
        self.assertIn("No analyzer found", str(ctx.exception))


class TestGitDiff(unittest.TestCase):
    """Test git integration for diffing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.git_dir = Path(self.temp_dir) / "git_repo"
        self.git_dir.mkdir()
        self.original_cwd = os.getcwd()

        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'],
                      cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'],
                      cwd=self.git_dir, check=True, capture_output=True)

    def tearDown(self):
        # Restore original working directory
        os.chdir(self.original_cwd)
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

    def test_git_directory_diff(self):
        """Test diffing directories across git commits."""
        # Create directory structure in first commit
        (self.git_dir / "src").mkdir()
        (self.git_dir / "src" / "a.py").write_text("def foo(): pass")
        (self.git_dir / "src" / "b.py").write_text("def bar(): pass")
        subprocess.run(['git', 'add', '.'], cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial'],
                      cwd=self.git_dir, check=True, capture_output=True)

        # Modify directory in second commit
        (self.git_dir / "src" / "a.py").write_text("def foo(): pass\ndef new_foo(): pass")
        (self.git_dir / "src" / "c.py").write_text("def baz(): pass")
        subprocess.run(['git', 'add', '.'], cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Add functions'],
                      cwd=self.git_dir, check=True, capture_output=True)

        # Test directory diff
        os.chdir(self.git_dir)
        adapter = DiffAdapter('git://HEAD~1/src/', 'git://HEAD/src/')
        result = adapter.get_structure()

        # Should detect added functions (new_foo in a.py, baz in c.py)
        self.assertGreaterEqual(result['summary']['functions']['added'], 2)

    def test_git_not_in_repo_error(self):
        """Test error when not in git repository."""
        # Create temp directory outside git
        temp_not_git = Path(tempfile.mkdtemp())
        (temp_not_git / "test.py").write_text("def foo(): pass")

        try:
            os.chdir(temp_not_git)
            adapter = DiffAdapter('git://HEAD/test.py', 'test.py')
            with self.assertRaises(ValueError) as ctx:
                adapter.get_structure()
            self.assertIn("Not in a git repository", str(ctx.exception))
        finally:
            shutil.rmtree(temp_not_git)

    def test_git_file_not_found_error(self):
        """Test error when file not found in git ref."""
        # Create repo with one file
        (self.git_dir / "exists.py").write_text("def foo(): pass")
        subprocess.run(['git', 'add', '.'], cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial'],
                      cwd=self.git_dir, check=True, capture_output=True)

        os.chdir(self.git_dir)
        adapter = DiffAdapter('git://HEAD/nonexistent.py', 'exists.py')
        with self.assertRaises(ValueError) as ctx:
            adapter.get_structure()
        self.assertIn("Path not found", str(ctx.exception))

    def test_git_invalid_uri_format(self):
        """Test error for invalid git URI format."""
        (self.git_dir / "test.py").write_text("def foo(): pass")
        subprocess.run(['git', 'add', '.'], cwd=self.git_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial'],
                      cwd=self.git_dir, check=True, capture_output=True)

        os.chdir(self.git_dir)
        adapter = DiffAdapter('git://HEAD', 'test.py')  # Missing path
        with self.assertRaises(ValueError) as ctx:
            adapter.get_structure()
        self.assertIn("Git URI must be in format", str(ctx.exception))


class TestDiffAdapterInit(unittest.TestCase):
    """Test diff adapter initialization with various URI formats."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        os.chdir(self.original_cwd)
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

    def test_init_with_file_paths(self):
        """Should initialize with two file paths."""
        v1 = "def foo(): pass"
        v2 = "def bar(): pass"
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        self.assertEqual(adapter.left_uri, path1)
        self.assertEqual(adapter.right_uri, path2)

    def test_init_with_combined_uri(self):
        """Should parse combined 'left:right' format."""
        v1 = "def foo(): pass"
        v2 = "def bar(): pass"
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(f"{path1}:{path2}")
        self.assertEqual(adapter.left_uri, path1)
        self.assertEqual(adapter.right_uri, path2)

    def test_init_with_explicit_right_uri(self):
        """Should accept left URI as resource and right_uri parameter."""
        v1 = "def foo(): pass"
        v2 = "def bar(): pass"
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, right_uri=path2)
        self.assertEqual(adapter.left_uri, path1)
        self.assertEqual(adapter.right_uri, path2)

    def test_init_with_file_scheme(self):
        """Should handle file:// scheme in URIs."""
        v1 = "def foo(): pass"
        v2 = "def bar(): pass"
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(f"file://{path1}:file://{path2}")
        self.assertEqual(adapter.left_uri, f"file://{path1}")
        self.assertEqual(adapter.right_uri, f"file://{path2}")

    def test_init_missing_right_uri(self):
        """Should raise error if right URI not provided."""
        path1 = self.create_file("def foo(): pass", "v1.py")

        with self.assertRaises(ValueError) as ctx:
            DiffAdapter(path1)
        self.assertIn("requires 'left:right' format", str(ctx.exception))

    def test_init_with_directories(self):
        """Should accept directory paths."""
        dir1 = os.path.join(self.temp_dir, "dir1")
        dir2 = os.path.join(self.temp_dir, "dir2")
        os.makedirs(dir1)
        os.makedirs(dir2)

        adapter = DiffAdapter(dir1, dir2)
        self.assertEqual(adapter.left_uri, dir1)
        self.assertEqual(adapter.right_uri, dir2)


class TestDiffAdapterSchema(unittest.TestCase):
    """Test schema generation for AI agent integration."""

    def test_get_schema(self):
        """Should return machine-readable schema."""
        schema = DiffAdapter.get_schema()

        self.assertIsNotNone(schema)
        self.assertEqual(schema['adapter'], 'diff')
        self.assertIn('description', schema)
        self.assertIn('uri_syntax', schema)

    def test_schema_cli_flags(self):
        """Schema should document CLI flags."""
        schema = DiffAdapter.get_schema()

        self.assertIn('cli_flags', schema)
        self.assertIsInstance(schema['cli_flags'], list)

    def test_schema_output_types(self):
        """Schema should define output types."""
        schema = DiffAdapter.get_schema()

        self.assertIn('output_types', schema)
        self.assertTrue(len(schema['output_types']) >= 1)

        # Should have diff output type
        output_types = [ot['type'] for ot in schema['output_types']]
        self.assertIn('diff', output_types)

    def test_schema_examples(self):
        """Schema should include usage examples."""
        schema = DiffAdapter.get_schema()

        self.assertIn('example_queries', schema)
        self.assertTrue(len(schema['example_queries']) >= 5)

        # Examples should have required fields
        for example in schema['example_queries']:
            self.assertIn('uri', example)
            self.assertIn('description', example)

    def test_schema_git_examples(self):
        """Schema should include git:// usage examples."""
        schema = DiffAdapter.get_schema()

        # Should have git:// examples from bug fix
        git_examples = [ex for ex in schema['example_queries'] if 'git://' in ex['uri']]
        self.assertGreaterEqual(len(git_examples), 2)


class TestDiffRenderer(unittest.TestCase):
    """Test renderer output formatting."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        os.chdir(self.original_cwd)
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

    def test_renderer_structure_diff(self):
        """Renderer should format structure diff correctly."""
        from reveal.adapters.diff import DiffRenderer
        from io import StringIO

        v1 = "def foo(): pass"
        v2 = "def foo(): pass\ndef bar(): pass"
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        DiffRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain key sections
        self.assertIn('Structure Diff', output)
        self.assertIn('Summary', output)
        self.assertIn('Functions', output)
        self.assertIn('bar', output)  # Added function name

    def test_renderer_element_diff(self):
        """Renderer should format element diff correctly."""
        from reveal.adapters.diff import DiffRenderer
        from io import StringIO

        v1 = "def foo():\n    return 1"
        v2 = "def foo():\n    return 2\ndef bar(): pass"
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_element('foo')

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        DiffRenderer.render_element(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain element details
        self.assertIn('foo', output)
        self.assertIn('diff', output.lower())

    def test_renderer_error_handling(self):
        """Renderer should handle errors gracefully."""
        from reveal.adapters.diff import DiffRenderer
        from io import StringIO

        # Capture stderr (render_error outputs to stderr)
        old_stderr = sys.stderr
        sys.stderr = captured_output = StringIO()

        error = FileNotFoundError("File not found")
        DiffRenderer.render_error(error)

        sys.stderr = old_stderr
        output = captured_output.getvalue()

        self.assertIn('Error', output)
        self.assertIn('File not found', output)

    def test_renderer_json_format(self):
        """Renderer should support JSON output."""
        import json
        from reveal.adapters.diff import DiffRenderer
        from io import StringIO

        v1 = "def foo(): pass"
        v2 = "def bar(): pass"
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        DiffRenderer.render_structure(result, format='json')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should be valid JSON
        parsed = json.loads(output)
        self.assertEqual(parsed['type'], 'diff_comparison')


class TestDiffAdapterEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        os.chdir(self.original_cwd)
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

    def test_nonexistent_left_file(self):
        """Should handle nonexistent left file gracefully."""
        path2 = self.create_file("def foo(): pass", "v2.py")
        nonexistent = os.path.join(self.temp_dir, "nonexistent.py")

        adapter = DiffAdapter(nonexistent, path2)
        with self.assertRaises(FileNotFoundError):
            adapter.get_structure()

    def test_nonexistent_right_file(self):
        """Should handle nonexistent right file gracefully."""
        path1 = self.create_file("def foo(): pass", "v1.py")
        nonexistent = os.path.join(self.temp_dir, "nonexistent.py")

        adapter = DiffAdapter(path1, nonexistent)
        with self.assertRaises(FileNotFoundError):
            adapter.get_structure()

    def test_empty_files(self):
        """Should handle empty files."""
        path1 = self.create_file("", "empty1.py")
        path2 = self.create_file("", "empty2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Should complete without error
        self.assertEqual(result['type'], 'diff_comparison')
        self.assertEqual(result['summary']['functions']['added'], 0)

    def test_large_file_diff(self):
        """Should handle diffs between large files."""
        # Create files with many functions
        v1_content = "\n".join([f"def func_{i}():\n    return {i}" for i in range(100)])
        v2_content = "\n".join([f"def func_{i}():\n    return {i}" for i in range(100, 200)])

        path1 = self.create_file(v1_content, "large1.py")
        path2 = self.create_file(v2_content, "large2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Should detect all removals and additions
        self.assertEqual(result['summary']['functions']['removed'], 100)
        self.assertEqual(result['summary']['functions']['added'], 100)

    def test_binary_files(self):
        """Should handle binary files gracefully."""
        # Create binary files
        path1 = os.path.join(self.temp_dir, "binary1.bin")
        path2 = os.path.join(self.temp_dir, "binary2.bin")
        with open(path1, 'wb') as f:
            f.write(b'\x00\x01\x02\x03')
        with open(path2, 'wb') as f:
            f.write(b'\x04\x05\x06\x07')

        adapter = DiffAdapter(path1, path2)

        # Binary files with no analyzer should raise ValueError
        with self.assertRaises(ValueError) as ctx:
            adapter.get_structure()
        self.assertIn("No analyzer found", str(ctx.exception))

    def test_mixed_file_types(self):
        """Should handle comparing Python file with non-analyzable file."""
        path1 = self.create_file("def foo(): pass", "code.py")
        path2 = self.create_file("Hello World", "text.txt")

        adapter = DiffAdapter(path1, path2)

        # Non-Python file should raise ValueError
        with self.assertRaises(ValueError) as ctx:
            adapter.get_structure()
        self.assertIn("No analyzer found", str(ctx.exception))

    def test_identical_files_different_paths(self):
        """Should detect no changes for identical content."""
        content = "def foo():\n    return 42\n"
        path1 = self.create_file(content, "v1.py")
        path2 = self.create_file(content, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Should show no changes
        self.assertEqual(result['summary']['functions']['added'], 0)
        self.assertEqual(result['summary']['functions']['removed'], 0)
        self.assertEqual(result['summary']['functions']['modified'], 0)


class TestDiffMetadata(unittest.TestCase):
    """Test diff adapter metadata functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        # Restore original working directory
        os.chdir(self.original_cwd)
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
