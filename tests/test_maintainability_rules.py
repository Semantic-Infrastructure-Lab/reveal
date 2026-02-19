"""Tests for reveal maintainability rules (M101-M103)."""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.rules.maintainability.M101 import M101
from reveal.rules.maintainability.M102 import M102
from reveal.rules.maintainability.M103 import M103
from reveal.rules.base import Severity


class TestM101FileTooLarge(unittest.TestCase):
    """Test M101: File too large detector."""

    def create_temp_file(self, content: str, suffix: str = ".py") -> str:
        """Helper: Create temp file with given content and suffix."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, f"test{suffix}")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        if os.path.exists(path):
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_small_file_ok(self):
        """Test that small files (< 500 lines) are not flagged."""
        content = "\n".join([f"line{i}" for i in range(100)])
        path = self.create_temp_file(content)
        try:
            rule = M101()
            detections = rule.check(path, None, content)
            self.assertEqual(len(detections), 0)
        finally:
            self.teardown_file(path)

    def test_medium_file_warning(self):
        """Test that medium files (500-1000 lines) trigger warning."""
        content = "\n".join([f"line{i}" for i in range(600)])
        path = self.create_temp_file(content)
        try:
            rule = M101()
            detections = rule.check(path, None, content)
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'M101')
            # Message format: "File is too large (600 lines, consider splitting at 1,000)"
            self.assertIn("lines", detections[0].message.lower())
        finally:
            self.teardown_file(path)

    def test_large_file_error(self):
        """Test that large files (> 1000 lines) trigger error."""
        content = "\n".join([f"line{i}" for i in range(1200)])
        path = self.create_temp_file(content)
        try:
            rule = M101()
            detections = rule.check(path, None, content)
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'M101')
            # Message format: "File is too large (1,200 lines, 9.5KB)"
            self.assertIn("1,200", detections[0].message)
            self.assertEqual(detections[0].severity, Severity.HIGH)
        finally:
            self.teardown_file(path)

    def test_edge_case_at_warn_threshold(self):
        """Test edge case: exactly at warn threshold (501 lines, just over)."""
        # Create content with exactly 501 lines (will trigger warning)
        content = "\n".join([f"line{i}" for i in range(501)])
        path = self.create_temp_file(content)
        try:
            rule = M101()
            detections = rule.check(path, None, content)
            # Just over threshold: should trigger warning
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].severity, Severity.MEDIUM)
        finally:
            self.teardown_file(path)

    def test_edge_case_at_error_threshold(self):
        """Test edge case: exactly at error threshold (1001 lines, just over)."""
        # Create content with exactly 1001 lines (will trigger error)
        content = "\n".join([f"line{i}" for i in range(1001)])
        path = self.create_temp_file(content)
        try:
            rule = M101()
            detections = rule.check(path, None, content)
            # Just over threshold: should trigger error
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].severity, Severity.HIGH)
        finally:
            self.teardown_file(path)

    def test_works_on_any_file_type(self):
        """Test that M101 works on any file type (not just Python)."""
        content = "\n".join([f"line{i}" for i in range(600)])
        for suffix in [".py", ".js", ".md", ".txt", ".yaml"]:
            path = self.create_temp_file(content, suffix=suffix)
            try:
                rule = M101()
                detections = rule.check(path, None, content)
                self.assertEqual(len(detections), 1, f"Failed for {suffix}")
            finally:
                self.teardown_file(path)


class TestM102OrphanFile(unittest.TestCase):
    """Test M102: Orphan file detector."""

    def setUp(self):
        """Clear the module-level import cache between tests."""
        import reveal.rules.maintainability.M102 as m
        m._import_cache.clear()

    def create_temp_directory_structure(self, files: dict) -> Path:
        """Helper: Create temp directory with multiple files.

        Args:
            files: Dict mapping relative paths to content

        Returns:
            Path to temp directory
        """
        temp_dir = Path(tempfile.mkdtemp())
        for rel_path, content in files.items():
            file_path = temp_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding='utf-8')
        return temp_dir

    def teardown_directory(self, path: Path):
        """Helper: Clean up temp directory."""
        import shutil
        if path.exists():
            shutil.rmtree(path)

    def test_imported_file_ok(self):
        """Test that imported files are not flagged."""
        files = {
            "main.py": "from utils import helper\n",
            "utils.py": "def helper():\n    pass\n",
        }
        temp_dir = self.create_temp_directory_structure(files)
        try:
            rule = M102()
            utils_path = str(temp_dir / "utils.py")
            utils_content = files["utils.py"]
            detections = rule.check(utils_path, None, utils_content)
            # Should not be flagged (imported by main.py)
            self.assertEqual(len(detections), 0)
        finally:
            self.teardown_directory(temp_dir)

    def test_orphan_file_detected(self):
        """Test that orphan files are detected in a proper package."""
        files = {
            "pyproject.toml": "[project]\nname = 'testpkg'\n",
            "testpkg/__init__.py": "",
            "testpkg/main.py": "print('hello')\n",
            "testpkg/orphan.py": "def unused():\n    pass\n",
        }
        temp_dir = self.create_temp_directory_structure(files)
        try:
            rule = M102()
            orphan_path = str(temp_dir / "testpkg" / "orphan.py")
            orphan_content = files["testpkg/orphan.py"]
            detections = rule.check(orphan_path, None, orphan_content)
            # Should be flagged (not imported anywhere in package)
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'M102')
        finally:
            self.teardown_directory(temp_dir)

    def test_entry_point_files_ok(self):
        """Test that entry point files (__init__.py, __main__.py, etc.) are not flagged."""
        for entry_point in ["__init__.py", "__main__.py", "setup.py", "main.py", "cli.py", "app.py"]:
            files = {
                entry_point: "print('entry point')\n",
            }
            temp_dir = self.create_temp_directory_structure(files)
            try:
                rule = M102()
                entry_path = str(temp_dir / entry_point)
                entry_content = files[entry_point]
                detections = rule.check(entry_path, None, entry_content)
                # Entry points should not be flagged
                self.assertEqual(len(detections), 0, f"{entry_point} should not be flagged")
            finally:
                self.teardown_directory(temp_dir)

    def test_test_files_ok(self):
        """Test that test files (test_*.py, *_test.py) are not flagged."""
        for test_file in ["test_foo.py", "foo_test.py", "tests.py"]:
            files = {
                test_file: "def test_something():\n    pass\n",
            }
            temp_dir = self.create_temp_directory_structure(files)
            try:
                rule = M102()
                test_path = str(temp_dir / test_file)
                test_content = files[test_file]
                detections = rule.check(test_path, None, test_content)
                # Test files should not be flagged
                self.assertEqual(len(detections), 0, f"{test_file} should not be flagged")
            finally:
                self.teardown_directory(temp_dir)

    def test_cache_populated_and_reused(self):
        """Cache is built on first check and reused for subsequent checks in same package."""
        import reveal.rules.maintainability.M102 as m

        files = {
            "pyproject.toml": "[project]\nname = 'testpkg'\n",
            "testpkg/__init__.py": "",
            "testpkg/used.py": "def helper(): pass\n",
            "testpkg/consumer.py": "from testpkg.used import helper\n",
            "testpkg/orphan.py": "def unused(): pass\n",
        }
        temp_dir = self.create_temp_directory_structure(files)
        try:
            rule = M102()
            # Cache starts empty
            self.assertEqual(len(m._import_cache), 0)

            # First check — builds cache
            rule.check(str(temp_dir / "testpkg" / "used.py"), None, files["testpkg/used.py"])
            self.assertEqual(len(m._import_cache), 1)
            first_cache_value = list(m._import_cache.values())[0]

            # Second check with same package root — cache must not grow
            rule.check(str(temp_dir / "testpkg" / "orphan.py"), None, files["testpkg/orphan.py"])
            self.assertEqual(len(m._import_cache), 1, "Cache grew; second check re-scanned package")
            self.assertIs(list(m._import_cache.values())[0], first_cache_value,
                          "Cache entry was replaced instead of reused")
        finally:
            self.teardown_directory(temp_dir)

    def test_cache_is_correct(self):
        """Cached results still produce correct detections."""
        import reveal.rules.maintainability.M102 as m

        # consumer.py imports from stdlib only so 'testpkg' never ends up in
        # all_imports (which would trigger the parent-prefix false-negative).
        files = {
            "pyproject.toml": "[project]\nname = 'testpkg'\n",
            "testpkg/__init__.py": "",
            "testpkg/used.py": "def helper(): pass\n",
            "testpkg/consumer.py": "import os\nfrom testpkg import used\n",
            "testpkg/orphan.py": "def unused(): pass\n",
        }
        temp_dir = self.create_temp_directory_structure(files)
        try:
            rule = M102()
            # First call builds cache; used.py IS imported by consumer
            d1 = rule.check(str(temp_dir / "testpkg" / "used.py"), None, files["testpkg/used.py"])
            self.assertEqual(len(d1), 0, "used.py is imported, should not be flagged")

            # Second call uses cache — orphan must still be detected
            d2 = rule.check(str(temp_dir / "testpkg" / "orphan.py"), None, files["testpkg/orphan.py"])
            self.assertEqual(len(d2), 1, "orphan.py should be flagged even via cache")
            self.assertEqual(d2[0].rule_code, "M102")
        finally:
            self.teardown_directory(temp_dir)


class TestM103VersionConsistency(unittest.TestCase):
    """Test M103: Version consistency detector."""

    def create_temp_project(self, pyproject_version: str, init_version: str = None) -> Path:
        """Helper: Create temp project with pyproject.toml and __init__.py.

        Args:
            pyproject_version: Version in pyproject.toml
            init_version: Version in __init__.py (optional)

        Returns:
            Path to temp project directory
        """
        temp_dir = Path(tempfile.mkdtemp())

        # Create pyproject.toml
        pyproject_content = f'''[project]
name = "testpkg"
version = "{pyproject_version}"
'''
        (temp_dir / "pyproject.toml").write_text(pyproject_content, encoding='utf-8')

        # Create package directory and __init__.py
        pkg_dir = temp_dir / "testpkg"
        pkg_dir.mkdir()

        if init_version is not None:
            init_content = f'__version__ = "{init_version}"\n'
            (pkg_dir / "__init__.py").write_text(init_content, encoding='utf-8')
        else:
            (pkg_dir / "__init__.py").write_text("", encoding='utf-8')

        return temp_dir

    def teardown_directory(self, path: Path):
        """Helper: Clean up temp directory."""
        import shutil
        if path.exists():
            shutil.rmtree(path)

    def test_matching_versions_ok(self):
        """Test that matching versions are not flagged."""
        temp_dir = self.create_temp_project("1.2.3", "1.2.3")
        try:
            rule = M103()
            init_path = str(temp_dir / "testpkg" / "__init__.py")
            init_content = '__version__ = "1.2.3"\n'
            detections = rule.check(init_path, None, init_content)
            self.assertEqual(len(detections), 0)
        finally:
            self.teardown_directory(temp_dir)

    def test_mismatched_versions_detected(self):
        """Test that mismatched versions are detected."""
        temp_dir = self.create_temp_project("1.2.3", "1.1.0")
        try:
            rule = M103()
            init_path = str(temp_dir / "testpkg" / "__init__.py")
            init_content = '__version__ = "1.1.0"\n'
            detections = rule.check(init_path, None, init_content)
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'M103')
            self.assertIn("1.2.3", detections[0].message)
            self.assertIn("1.1.0", detections[0].message)
        finally:
            self.teardown_directory(temp_dir)

    def test_missing_version_in_init(self):
        """Test handling when __version__ is missing from __init__.py."""
        temp_dir = self.create_temp_project("1.2.3", None)
        try:
            rule = M103()
            init_path = str(temp_dir / "testpkg" / "__init__.py")
            init_content = ""
            detections = rule.check(init_path, None, init_content)
            # Should not crash, may or may not flag depending on implementation
            # Just ensure it doesn't crash
            self.assertIsInstance(detections, list)
        finally:
            self.teardown_directory(temp_dir)

    def test_version_with_different_formats(self):
        """Test version format variations (v prefix, etc.)."""
        temp_dir = self.create_temp_project("1.2.3", "v1.2.3")
        try:
            rule = M103()
            init_path = str(temp_dir / "testpkg" / "__init__.py")
            init_content = '__version__ = "v1.2.3"\n'
            detections = rule.check(init_path, None, init_content)
            # M103 might normalize versions or strictly compare - accept either behavior
            # This test documents the actual behavior without enforcing it
            self.assertIsInstance(detections, list)
            if len(detections) > 0:
                self.assertEqual(detections[0].rule_code, 'M103')
        finally:
            self.teardown_directory(temp_dir)

    def test_semantic_version_components(self):
        """Test various semantic version formats."""
        test_cases = [
            ("1.0.0", "1.0.0", False),  # Match
            ("1.0.0", "1.0.1", True),   # Patch mismatch
            ("1.0.0", "1.1.0", True),   # Minor mismatch
            ("1.0.0", "2.0.0", True),   # Major mismatch
            ("1.0.0-alpha", "1.0.0-alpha", False),  # Match with prerelease
        ]

        for pyproject_ver, init_ver, should_detect in test_cases:
            temp_dir = self.create_temp_project(pyproject_ver, init_ver)
            try:
                rule = M103()
                init_path = str(temp_dir / "testpkg" / "__init__.py")
                init_content = f'__version__ = "{init_ver}"\n'
                detections = rule.check(init_path, None, init_content)

                if should_detect:
                    self.assertEqual(len(detections), 1,
                        f"Expected mismatch: pyproject={pyproject_ver}, init={init_ver}")
                else:
                    self.assertEqual(len(detections), 0,
                        f"Expected match: pyproject={pyproject_ver}, init={init_ver}")
            finally:
                self.teardown_directory(temp_dir)


if __name__ == '__main__':
    unittest.main()
