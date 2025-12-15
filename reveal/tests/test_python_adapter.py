"""
Tests for reveal/adapters/python/adapter.py

Tests the PythonAdapter class methods that remain on the adapter.
Submodule functions (modules.py, doctor.py, packages.py, bytecode.py)
are tested via integration through the adapter's public interface.
"""

import unittest
import sys
from pathlib import Path
from reveal.adapters.python import PythonAdapter


class TestPythonAdapter(unittest.TestCase):
    """Test the PythonAdapter class."""

    def setUp(self):
        """Set up test fixtures."""
        self.adapter = PythonAdapter()

    def test_get_structure(self):
        """Test getting Python environment structure."""
        result = self.adapter.get_structure()

        # Check basic structure
        self.assertIn("version", result)
        self.assertIn("executable", result)
        self.assertIn("platform", result)
        self.assertIn("virtual_env", result)
        self.assertIn("packages_count", result)
        self.assertIn("modules_loaded", result)

        # Check version info
        self.assertIsInstance(result["version"], str)
        self.assertIn(".", result["version"])  # Version has dots

        # Check virtual_env info is dict
        self.assertIsInstance(result["virtual_env"], dict)
        self.assertIn("active", result["virtual_env"])

    def test_get_version(self):
        """Test _get_version returns version info."""
        result = self.adapter._get_version()

        self.assertIn("version", result)
        self.assertIn("version_info", result)
        self.assertIn("implementation", result)
        self.assertIn("executable", result)

        # Check version_info structure
        version_info = result["version_info"]
        self.assertIn("major", version_info)
        self.assertIn("minor", version_info)
        self.assertIn("micro", version_info)

        # Verify types
        self.assertIsInstance(version_info["major"], int)
        self.assertIsInstance(version_info["minor"], int)
        self.assertEqual(version_info["major"], sys.version_info.major)
        self.assertEqual(version_info["minor"], sys.version_info.minor)

    def test_detect_venv(self):
        """Test _detect_venv detects virtual environment status."""
        result = self.adapter._detect_venv()

        self.assertIn("active", result)
        self.assertIsInstance(result["active"], bool)

        if result["active"]:
            self.assertIn("path", result)
            self.assertIn("type", result)

    def test_get_env(self):
        """Test _get_env returns environment configuration."""
        result = self.adapter._get_env()

        self.assertIn("virtual_env", result)
        self.assertIn("sys_path", result)
        self.assertIn("sys_path_count", result)
        self.assertIn("encoding", result)

        # Check sys_path is a list
        self.assertIsInstance(result["sys_path"], list)
        self.assertGreater(len(result["sys_path"]), 0)
        self.assertEqual(result["sys_path_count"], len(result["sys_path"]))

    def test_get_packages_list(self):
        """Test get_packages_list returns installed packages."""
        from reveal.adapters.python.packages import get_packages_list
        result = get_packages_list()

        self.assertIn("packages", result)
        self.assertIn("count", result)

        # Check count matches list length
        self.assertEqual(result["count"], len(result["packages"]))
        self.assertGreater(result["count"], 0)  # At least some packages

        # Check package structure
        if result["packages"]:
            pkg = result["packages"][0]
            self.assertIn("name", pkg)
            self.assertIn("version", pkg)

    def test_get_imports(self):
        """Test _get_imports returns loaded modules."""
        result = self.adapter._get_imports()

        self.assertIn("loaded", result)
        self.assertIn("count", result)

        # Check basic modules are loaded
        module_names = [m["name"] for m in result["loaded"]]
        self.assertIn("sys", module_names)

    def test_handle_debug_bytecode(self):
        """Test _handle_debug handles bytecode debug type."""
        result = self.adapter._handle_debug("bytecode")

        self.assertIn("status", result)
        # Status should be "clean" or "issues_found"
        self.assertIn(result["status"], ["clean", "issues_found"])


class TestPycToSource(unittest.TestCase):
    """Test .pyc to source file conversion."""

    def test_pyc_to_source_pep3147(self):
        """Test PEP 3147 style __pycache__/module.cpython-310.pyc -> module.py."""
        from reveal.adapters.python import PythonAdapter

        pyc_path = Path("/some/path/__pycache__/module.cpython-310.pyc")
        source_path = PythonAdapter._pyc_to_source(pyc_path)

        self.assertEqual(source_path, Path("/some/path/module.py"))

    def test_pyc_to_source_old_style(self):
        """Test old style module.pyc -> module.py."""
        from reveal.adapters.python import PythonAdapter

        pyc_path = Path("/some/path/module.pyc")
        source_path = PythonAdapter._pyc_to_source(pyc_path)

        self.assertEqual(source_path, Path("/some/path/module.py"))


if __name__ == "__main__":
    unittest.main()
