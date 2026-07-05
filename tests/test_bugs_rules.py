"""Tests for reveal bugs rules (B005)."""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.rules.bugs.B005 import B005
from reveal.rules.base import Severity


class TestB005DeadImports(unittest.TestCase):
    """Test B005: Dead import detector."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.rule = B005()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, name: str = "test.py") -> str:
        """Helper: Create temp file with given content."""
        path = os.path.join(self.temp_dir, name)
        # Ensure directory exists for nested paths
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def create_package(self, name: str):
        """Helper: Create a package directory with __init__.py."""
        pkg_dir = os.path.join(self.temp_dir, name)
        os.makedirs(pkg_dir, exist_ok=True)
        init_file = os.path.join(pkg_dir, "__init__.py")
        with open(init_file, 'w', encoding='utf-8') as f:
            f.write("# Package init\n")
        return pkg_dir

    def create_project_file(self, top_pkg: str, rel_path: str, content: str) -> str:
        """Helper: build a project rooted at temp_dir with a top-level package,
        placing a file at temp_dir/top_pkg/rel_path (packages get __init__.py).

        This lets us exercise same-project absolute-import resolution — the
        case B005 can prove (BACK-465).
        """
        parts = os.path.join(top_pkg, rel_path).split(os.sep)
        cur = self.temp_dir
        for d in parts[:-1]:
            cur = os.path.join(cur, d)
            os.makedirs(cur, exist_ok=True)
            init = os.path.join(cur, "__init__.py")
            if not os.path.exists(init):
                with open(init, 'w') as f:
                    f.write("")
        path = os.path.join(cur, parts[-1])
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    # ==================== Tests for import statements ====================
    # BACK-465: an absolute import is 'dead' only when its top-level package is
    # part of THIS project (resolvable under the project root) but the dotted
    # path is missing. A bare unresolvable absolute import (third-party module
    # not installed in reveal's env) is 'unknown' and NOT flagged — flagging it
    # conflated "not installed here" with "does not exist" and produced a 100%
    # false-positive flood on every external repo.

    def test_unknown_absolute_import_not_flagged(self):
        """A non-stdlib, non-same-project absolute import is unknown, not dead."""
        content = "import nonexistent_module_xyz123"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_unknown_dotted_absolute_import_not_flagged(self):
        content = "import nonexistent_pkg_xyz.submodule.deep"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_third_party_from_import_not_flagged(self):
        """The home-assistant FP: a declared third-party dep not in reveal's env."""
        content = "from voluptuous_not_installed_xyz import Schema"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_same_project_dead_import_flagged(self):
        """Absolute import of the project's own package to a missing module."""
        # Project: temp_dir/proj/{__init__, real.py}, file at proj/sub/mod.py
        self.create_project_file("proj", "real.py", "X = 1")
        content = "from proj.typo_missing import thing"
        path = self.create_project_file("proj", os.path.join("sub", "mod.py"), content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B005')
        self.assertIn('proj.typo_missing', detections[0].message)

    def test_same_project_valid_absolute_import_not_flagged(self):
        """Own-package absolute import from a subdirectory resolves on disk."""
        self.create_project_file("proj", "real.py", "X = 1")
        content = "from proj.real import X"
        path = self.create_project_file("proj", os.path.join("sub", "mod.py"), content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_valid_stdlib_import_not_detected(self):
        """Test that valid stdlib imports are not flagged."""
        content = """
import os
import sys
import json
from pathlib import Path
import typing
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_mixed_imports_only_same_project_dead_flagged(self):
        """A mix: stdlib ok, third-party unknown, same-project dead flagged."""
        self.create_project_file("proj", "real.py", "X = 1")
        content = (
            "import os\n"
            "import some_uninstalled_thirdparty_xyz\n"
            "from proj.real import X\n"
            "from proj.gone_missing import Y\n"
        )
        path = self.create_project_file("proj", os.path.join("sub", "mod.py"), content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('proj.gone_missing', detections[0].message)

    # ==================== Tests for from...import statements ====================

    def test_valid_from_import_not_detected(self):
        """Test that valid 'from' imports are not flagged."""
        content = """
from os import path
from pathlib import Path
from typing import List, Dict
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    # ==================== Tests for relative imports ====================

    def test_relative_import_from_nonexistent_submodule(self):
        """Test relative import from a non-existent submodule path."""
        # Create package structure
        pkg_dir = self.create_package("pkg")

        # Try to import from nonexistent submodule
        content = "from .nonexistent.deeply.nested import something"
        path = os.path.join(pkg_dir, "test.py")
        with open(path, 'w') as f:
            f.write(content)

        detections = self.rule.check(path, None, content)
        # Should detect because .nonexistent doesn't exist
        self.assertGreaterEqual(len(detections), 1)

    def test_relative_import_existing_sibling(self):
        """Test relative import of existing sibling module."""
        # Create package structure
        pkg_dir = self.create_package("mypkg")
        sibling_path = os.path.join(pkg_dir, "sibling.py")
        with open(sibling_path, 'w') as f:
            f.write("# Sibling module\n")

        content = "from . import sibling"
        path = os.path.join(pkg_dir, "test.py")
        with open(path, 'w') as f:
            f.write(content)

        detections = self.rule.check(path, None, content)
        # Should NOT detect - sibling exists and __init__.py exists
        self.assertEqual(len(detections), 0)

    def test_relative_import_parent(self):
        """Test relative import from parent (from .. import X)."""
        # Create package structure: pkg/ and pkg/sub/
        pkg_dir = self.create_package("pkg")
        sub_dir = os.path.join(pkg_dir, "sub")
        os.makedirs(sub_dir, exist_ok=True)
        init_file = os.path.join(sub_dir, "__init__.py")
        with open(init_file, 'w') as f:
            f.write("")

        # Create parent module
        parent_module = os.path.join(pkg_dir, "parent_mod.py")
        with open(parent_module, 'w') as f:
            f.write("# Parent module\n")

        content = "from ..parent_mod import something"
        path = os.path.join(sub_dir, "test.py")
        with open(path, 'w') as f:
            f.write(content)

        detections = self.rule.check(path, None, content)
        # Should NOT detect - parent_mod.py exists
        self.assertEqual(len(detections), 0)

    def test_relative_import_nonexistent_parent(self):
        """Test relative import of non-existent parent module."""
        # Create minimal package structure
        pkg_dir = self.create_package("pkg")

        content = "from ..nonexistent import something"
        path = os.path.join(pkg_dir, "test.py")
        with open(path, 'w') as f:
            f.write(content)

        detections = self.rule.check(path, None, content)
        # Should detect - nonexistent module doesn't exist
        self.assertGreaterEqual(len(detections), 1)

    def test_relative_import_package(self):
        """Test relative import from package directory."""
        # Create package structure: pkg/subpkg/
        pkg_dir = self.create_package("pkg")
        subpkg_dir = self.create_package("pkg/subpkg")

        content = "from .subpkg import something"
        path = os.path.join(pkg_dir, "test.py")
        with open(path, 'w') as f:
            f.write(content)

        detections = self.rule.check(path, None, content)
        # Should NOT detect - subpkg exists as directory with __init__.py
        self.assertEqual(len(detections), 0)

    # ==================== Tests for local modules ====================

    def test_local_module_file_not_detected(self):
        """Test that local .py files are recognized."""
        # Create local module
        local_mod_path = os.path.join(self.temp_dir, "local_module.py")
        with open(local_mod_path, 'w') as f:
            f.write("# Local module\n")

        content = "import local_module"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should NOT detect - local_module.py exists
        self.assertEqual(len(detections), 0)

    def test_local_package_not_detected(self):
        """Test that local packages are recognized."""
        # Create local package
        self.create_package("local_pkg")

        content = "import local_pkg"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should NOT detect - local_pkg/ with __init__.py exists
        self.assertEqual(len(detections), 0)

    def test_from_local_module_not_detected(self):
        """Test 'from local_module import' is recognized."""
        # Create local module
        local_mod_path = os.path.join(self.temp_dir, "mymodule.py")
        with open(local_mod_path, 'w') as f:
            f.write("def func(): pass\n")

        content = "from mymodule import func"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should NOT detect
        self.assertEqual(len(detections), 0)

    # ==================== Tests for edge cases ====================

    def test_syntax_error_skipped(self):
        """Test that files with syntax errors are skipped gracefully."""
        content = "import this is not valid python syntax @@#$"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should return empty list, not crash
        self.assertEqual(len(detections), 0)

    def test_empty_file(self):
        """Test that empty files are handled."""
        content = ""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_no_imports_file(self):
        """Test file with no imports."""
        content = """
def foo():
    return 42

class Bar:
    pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_future_import_not_detected(self):
        """Test that __future__ imports are not flagged."""
        content = "from __future__ import annotations"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_line_and_column_accuracy(self):
        """Test that line and column numbers are accurate."""
        self.create_project_file("proj", "real.py", "X = 1")
        content = """import os
from proj.gone_missing import Y
import sys
"""
        path = self.create_project_file("proj", os.path.join("sub", "mod.py"), content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].line, 2)  # Line 2
        self.assertGreater(detections[0].column, 0)  # Has column position

    def test_multiple_dead_imports_different_lines(self):
        """Test multiple same-project dead imports on different lines."""
        self.create_project_file("proj", "real.py", "X = 1")
        content = """import os
from proj.gone_1 import a
from pathlib import Path
from proj.gone_2 import b
from proj.gone_3 import c
"""
        path = self.create_project_file("proj", os.path.join("sub", "mod.py"), content)
        detections = self.rule.check(path, None, content)
        # 3 same-project dead imports (os and pathlib stdlib; proj.real absent from these)
        self.assertEqual(len(detections), 3)
        lines = sorted([d.line for d in detections])
        self.assertEqual(lines, [2, 4, 5])

    def test_context_preservation(self):
        """Test that context is preserved in detections."""
        self.create_project_file("proj", "real.py", "X = 1")
        content = "from proj.gone_missing import thing"
        path = self.create_project_file("proj", os.path.join("sub", "mod.py"), content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn('import', detections[0].context)

    def test_severity_is_high(self):
        """Test that B005 detections have HIGH severity."""
        self.create_project_file("proj", "real.py", "X = 1")
        content = "from proj.gone_missing import thing"
        path = self.create_project_file("proj", os.path.join("sub", "mod.py"), content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].severity, Severity.HIGH)

    def test_category_is_bugs(self):
        """Test that B005 is categorized as bugs."""
        self.assertEqual(self.rule.category.value, 'B')

    def test_file_patterns_python_only(self):
        """Test that B005 only applies to .py files."""
        self.assertEqual(self.rule.file_patterns, ['.py'])


if __name__ == '__main__':
    unittest.main()
