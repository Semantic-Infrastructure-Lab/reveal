"""
Tests for TreeSitter UTF-8 byte offset handling.

Regression tests for GitHub issues #6, #7, #8:
- Issue #6: Python function names truncated
- Issue #7: Python import statements garbled
- Issue #8: Python class names corrupted

Root cause: Tree-sitter uses byte offsets, but we were slicing Unicode strings.
Multi-byte UTF-8 characters caused byte/character offset mismatch.
"""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.analyzers.python import PythonAnalyzer


class TestTreeSitterUTF8Handling(unittest.TestCase):
    """Test that TreeSitter correctly handles UTF-8 byte offsets."""

    def test_function_names_with_emoji_in_docstring(self):
        """Function names should not be truncated when file has emoji/multi-byte chars."""
        # This test reproduces issue #6
        code = '''"""Test file with emoji ✨ in docstring"""

def test_function_one():
    """A function ✨"""
    pass

def test_function_two():
    """Another function 🎉"""
    pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PythonAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should have 2 functions
            self.assertEqual(len(functions), 2)

            # Function names should be complete, not truncated
            func_names = [f['name'] for f in functions]
            self.assertIn('test_function_one', func_names)
            self.assertIn('test_function_two', func_names)

            # Names should NOT be truncated (no missing prefixes)
            for name in func_names:
                self.assertFalse(name.startswith('st_function'))  # Missing "te"
                self.assertFalse(name.startswith('function'))      # Missing "test_"

        finally:
            os.unlink(temp_path)

    def test_class_names_with_multi_byte_chars(self):
        """Class names should not be corrupted when file has multi-byte characters."""
        # This test reproduces issue #8
        code = '''"""Module with ✨ emoji ✨"""

class TestFirstClass:
    """First class ⭐"""
    pass

class TestSecondClass:
    """Second class 🎯"""
    pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PythonAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('classes', structure)
            classes = structure['classes']

            # Should have 2 classes
            self.assertEqual(len(classes), 2)

            # Class names should be complete
            class_names = [c['name'] for c in classes]
            self.assertIn('TestFirstClass', class_names)
            self.assertIn('TestSecondClass', class_names)

            # Names should NOT be corrupted
            for name in class_names:
                self.assertFalse(name.startswith('stClass'))     # Missing "TestFirst"
                self.assertFalse(name.startswith('ondClass'))    # Missing "TestSec"
                self.assertFalse(name.endswith(':'))              # No colon contamination

        finally:
            os.unlink(temp_path)

    def test_imports_with_unicode_strings(self):
        """Import statements should not be garbled with multi-byte characters."""
        # This test reproduces issue #7
        code = '''"""Test file ⚡ with imports"""
import sys
import os
import numpy as np
from typing import Dict, List, Optional
from pathlib import Path
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PythonAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('imports', structure)
            imports = structure['imports']

            # Should have 5 imports
            self.assertGreaterEqual(len(imports), 5)

            # Check imports are complete, not garbled
            import_contents = [imp['content'] for imp in imports]

            # Find the numpy import
            numpy_imports = [i for i in import_contents if 'numpy' in i]
            self.assertGreater(len(numpy_imports), 0, "Should find numpy import")

            # Should be "import numpy as np", not "rt numpy as np\nimp"
            numpy_import = numpy_imports[0]
            self.assertTrue(numpy_import.startswith('import'),
                           f"Import should start with 'import', got: {numpy_import}")
            self.assertNotIn('\n', numpy_import.strip(),
                           f"Import should not have embedded newlines: {numpy_import}")

            # Check typing import
            typing_imports = [i for i in import_contents if 'typing' in i]
            self.assertGreater(len(typing_imports), 0, "Should find typing import")

            typing_import = typing_imports[0]
            self.assertTrue(typing_import.startswith('from'),
                          f"Typing import should start with 'from', got: {typing_import}")
            self.assertNotIn('\nimp', typing_import,
                           f"Should not have broken newlines: {typing_import}")

        finally:
            os.unlink(temp_path)

    def test_complex_unicode_throughout_file(self):
        """Test with extensive Unicode characters throughout the file."""
        code = '''"""
🐍 Python Test Module 🐍
Contains: ✨ emoji, 日本語, Ελληνικά, עברית
"""

import sys  # System 🔧
from typing import Dict  # 📦 Types

class UnicodeTestClass:
    """Class with 多言語 documentation"""

    def unicode_method_one(self):
        """Method with ⭐ stars ⭐"""
        pass

    def unicode_method_two(self):
        """Method with 🎉 celebration 🎉"""
        pass

def function_with_unicode():
    """Function 🚀 with rocket 🚀"""
    pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PythonAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Verify all imports found correctly
            self.assertIn('imports', structure)
            imports = structure['imports']
            import_strs = [i['content'] for i in imports]
            self.assertTrue(any('import sys' in i for i in import_strs))
            self.assertTrue(any('from typing import Dict' in i for i in import_strs))

            # Verify class name is complete
            self.assertIn('classes', structure)
            classes = structure['classes']
            class_names = [c['name'] for c in classes]
            self.assertIn('UnicodeTestClass', class_names)

            # Verify function names are complete
            self.assertIn('functions', structure)
            functions = structure['functions']
            func_names = [f['name'] for f in functions]

            # Should find all 3 functions (2 methods + 1 module function)
            # Note: Methods might or might not be extracted depending on analyzer depth
            # But at minimum, the module-level function should be found
            self.assertTrue(any('unicode' in name.lower() for name in func_names),
                          f"Should find unicode-related functions in: {func_names}")

            # Most importantly: NO truncated or corrupted names
            for name in func_names:
                # Names should start with valid Python identifier characters
                self.assertTrue(name[0].isalpha() or name[0] == '_',
                              f"Function name should start with letter/underscore: {name}")
                # Names should not contain colons or newlines
                self.assertNotIn(':', name)
                self.assertNotIn('\n', name)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
