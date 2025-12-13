"""
Tests for reveal/adapters/python.py

Comprehensive test coverage for the Python runtime adapter,
including module analysis, doctor diagnostics, and helper functions.
"""

import unittest
import sys
import tempfile
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
        """Test _get_packages_list returns installed packages."""
        result = self.adapter._get_packages_list()

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


class TestModuleAnalysis(unittest.TestCase):
    """Test module analysis functions (Phase 4 refactoring)."""

    def setUp(self):
        """Set up test fixtures."""
        self.adapter = PythonAdapter()

    def test_find_module_import_location_existing(self):
        """Test finding import location for existing module (sys)."""
        result = self.adapter._find_module_import_location("sys")

        self.assertIn("import_location", result)
        self.assertIn("status", result)
        self.assertEqual(result["status"], "importable")
        self.assertIn("is_package", result)

    def test_find_module_import_location_nonexistent(self):
        """Test finding import location for nonexistent module."""
        result = self.adapter._find_module_import_location("nonexistent_module_xyz123")

        self.assertIn("import_location", result)
        self.assertIn("status", result)
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["import_location"])

    def test_get_pip_package_metadata_existing(self):
        """Test getting pip metadata for existing package."""
        # Try to find any installed package (pip itself should be there)
        result = self.adapter._get_pip_package_metadata("pip")

        if result is not None:  # pip might not have metadata
            self.assertIn("name", result)
            self.assertIn("version", result)
            self.assertIn("location", result)
            self.assertIn("install_type", result)

    def test_get_pip_package_metadata_nonexistent(self):
        """Test getting pip metadata for nonexistent package."""
        result = self.adapter._get_pip_package_metadata("nonexistent_package_xyz123")

        self.assertIsNone(result)

    def test_detect_pip_import_conflicts_no_conflict(self):
        """Test conflict detection with no conflicts."""
        # No pip package or import path -> no conflicts
        result = self.adapter._detect_pip_import_conflicts(None, None)
        self.assertEqual(result, [])

        result = self.adapter._detect_pip_import_conflicts(
            {"name": "test", "version": "1.0", "location": "/tmp/test"}, None
        )
        self.assertEqual(result, [])

    def test_detect_cwd_shadowing_no_shadowing(self):
        """Test CWD shadowing detection when no shadowing occurs."""
        # Test with None import path
        conflicts, recommendations = self.adapter._detect_cwd_shadowing(None)
        self.assertEqual(conflicts, [])
        self.assertEqual(recommendations, [])

        # Test with import path that's not CWD
        conflicts, recommendations = self.adapter._detect_cwd_shadowing("/usr/lib/python3")
        # May or may not shadow depending on CWD, but should return lists
        self.assertIsInstance(conflicts, list)
        self.assertIsInstance(recommendations, list)

    def test_find_module_syspath_index_none(self):
        """Test finding sys.path index with no import path."""
        result = self.adapter._find_module_syspath_index(None)
        self.assertEqual(result, {})

    def test_find_module_syspath_index_existing(self):
        """Test finding sys.path index for existing path."""
        # Use first sys.path entry
        if sys.path and sys.path[0]:
            result = self.adapter._find_module_syspath_index(sys.path[0])
            # Should find it at index 0
            if result:  # Might be empty if path doesn't match
                self.assertIn("syspath_index", result)
                self.assertIn("syspath_entry", result)

    def test_get_module_analysis_builtin(self):
        """Test full module analysis for builtin module."""
        result = self.adapter._get_module_analysis("sys")

        self.assertIn("module", result)
        self.assertEqual(result["module"], "sys")
        self.assertIn("status", result)
        self.assertEqual(result["status"], "importable")
        self.assertIn("conflicts", result)
        self.assertIn("recommendations", result)
        self.assertIsInstance(result["conflicts"], list)
        self.assertIsInstance(result["recommendations"], list)

    def test_get_module_analysis_nonexistent(self):
        """Test full module analysis for nonexistent module."""
        result = self.adapter._get_module_analysis("nonexistent_module_xyz123")

        self.assertIn("module", result)
        self.assertIn("status", result)
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["pip_package"])


class TestDoctorDiagnostics(unittest.TestCase):
    """Test doctor diagnostic functions (Phase 5 refactoring)."""

    def setUp(self):
        """Set up test fixtures."""
        self.adapter = PythonAdapter()

    def test_doctor_check_venv(self):
        """Test virtual environment check."""
        warnings, recommendations = self.adapter._doctor_check_venv()

        # Should return lists
        self.assertIsInstance(warnings, list)
        self.assertIsInstance(recommendations, list)

        # If venv not active, should have warnings
        venv = self.adapter._detect_venv()
        if not venv["active"]:
            self.assertGreater(len(warnings), 0)
            self.assertGreater(len(recommendations), 0)

            # Check structure of warning
            self.assertIn("category", warnings[0])
            self.assertEqual(warnings[0]["category"], "environment")

    def test_doctor_check_cwd_shadowing(self):
        """Test CWD shadowing check."""
        warnings, recommendations = self.adapter._doctor_check_cwd_shadowing()

        # Should return lists
        self.assertIsInstance(warnings, list)
        self.assertIsInstance(recommendations, list)

    def test_doctor_check_stale_bytecode(self):
        """Test stale bytecode check."""
        issues, recommendations = self.adapter._doctor_check_stale_bytecode()

        # Should return lists
        self.assertIsInstance(issues, list)
        self.assertIsInstance(recommendations, list)

        # If issues found, should have recommendations
        if issues:
            self.assertGreater(len(recommendations), 0)

    def test_doctor_check_python_version(self):
        """Test Python version check."""
        warnings = self.adapter._doctor_check_python_version()

        # Should return list
        self.assertIsInstance(warnings, list)

        # Current Python should be >= 3.8 (running tests)
        # So no warnings expected
        self.assertEqual(len(warnings), 0)

    def test_doctor_check_editable_installs(self):
        """Test editable installs check."""
        info = self.adapter._doctor_check_editable_installs()

        # Should return list
        self.assertIsInstance(info, list)

        # If editable packages found, check structure
        if info:
            self.assertIn("category", info[0])
            self.assertEqual(info[0]["category"], "development")

    def test_doctor_check_editable_conflicts(self):
        """Test editable conflicts check."""
        issues, warnings, recommendations = self.adapter._doctor_check_editable_conflicts()

        # Should return lists
        self.assertIsInstance(issues, list)
        self.assertIsInstance(warnings, list)
        self.assertIsInstance(recommendations, list)

    def test_calculate_doctor_health_score_perfect(self):
        """Test health score calculation with no issues."""
        score, status = self.adapter._calculate_doctor_health_score([], [])

        self.assertEqual(score, 100)
        self.assertEqual(status, "healthy")

    def test_calculate_doctor_health_score_with_issues(self):
        """Test health score calculation with issues."""
        issues = [{"category": "test", "message": "test issue"}]
        warnings = [{"category": "test", "message": "test warning"}]

        score, status = self.adapter._calculate_doctor_health_score(issues, warnings)

        # 100 - (1 issue * 20) - (1 warning * 10) = 70
        self.assertEqual(score, 70)
        self.assertEqual(status, "caution")  # 70 < 90 = caution

    def test_calculate_doctor_health_score_critical(self):
        """Test health score calculation for critical status."""
        issues = [{"test": f"issue_{i}"} for i in range(3)]  # 3 issues = 60 points off
        warnings = []

        score, status = self.adapter._calculate_doctor_health_score(issues, warnings)

        self.assertEqual(score, 40)
        self.assertEqual(status, "critical")

    def test_run_doctor_complete(self):
        """Test full doctor run."""
        result = self.adapter._run_doctor()

        # Check structure
        self.assertIn("status", result)
        self.assertIn("health_score", result)
        self.assertIn("issues", result)
        self.assertIn("warnings", result)
        self.assertIn("info", result)
        self.assertIn("recommendations", result)
        self.assertIn("summary", result)
        self.assertIn("checks_performed", result)

        # Check types
        self.assertIsInstance(result["health_score"], int)
        self.assertIsInstance(result["issues"], list)
        self.assertIsInstance(result["warnings"], list)
        self.assertIsInstance(result["info"], list)
        self.assertIsInstance(result["recommendations"], list)

        # Check summary
        self.assertEqual(result["summary"]["total_issues"], len(result["issues"]))
        self.assertEqual(result["summary"]["total_warnings"], len(result["warnings"]))

        # Check all checks performed
        self.assertEqual(len(result["checks_performed"]), 6)


class TestBytecodeChecking(unittest.TestCase):
    """Test bytecode checking functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.adapter = PythonAdapter()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_bytecode_empty_directory(self):
        """Test bytecode check on empty directory."""
        result = self.adapter._check_bytecode(self.temp_dir)

        self.assertIn("status", result)
        self.assertEqual(result["status"], "clean")
        self.assertIn("summary", result)
        self.assertEqual(result["summary"]["total"], 0)

    def test_check_bytecode_with_source(self):
        """Test bytecode check with Python source file."""
        # Create a simple Python file
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("print('hello')\n")

        result = self.adapter._check_bytecode(self.temp_dir)

        self.assertIn("status", result)
        # Should be clean (no .pyc files)
        self.assertEqual(result["status"], "clean")


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
