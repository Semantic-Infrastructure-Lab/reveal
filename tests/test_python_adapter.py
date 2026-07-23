"""
Tests for reveal/adapters/python/adapter.py

Tests the PythonAdapter class methods that remain on the adapter.
Submodule functions (modules.py, doctor.py, packages.py, bytecode.py)
are tested via integration through the adapter's public interface.
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
        # Scan an isolated empty dir, not the live repo cwd: scanning the repo
        # tree races with other test processes' concurrent __pycache__ writes
        # (esp. under pytest-xdist), which can trip the scan's except-clause
        # and return status "error" instead of "clean"/"issues_found".
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = self.adapter._handle_debug("bytecode", root_path=tmp_dir)

        self.assertIn("status", result)
        # Status should be "clean" or "issues_found"
        self.assertIn(result["status"], ["clean", "issues_found"])


class TestPackageDirShadowing(unittest.TestCase):
    """BACK-419: package-directory shadowing with version mismatch."""

    def test_clean_env_has_no_false_positives(self):
        """A normal env must not flag shadowing (guards against noisy mismaps
        like a stdlib `test` dir mapping to an unrelated distribution)."""
        from reveal.adapters.python.doctor import check_package_dir_shadowing

        issues, _recs = check_package_dir_shadowing()
        self.assertEqual(issues, [], f"unexpected shadowing issues: {issues}")

    def test_detects_version_mismatch(self):
        """A source package dir with a literal __version__ that differs from an
        installed distribution of the same import name, on an earlier sys.path
        entry, is flagged high-severity."""
        import importlib.metadata as im
        import tempfile
        from reveal.adapters.python.doctor import check_package_dir_shadowing

        # Find an installed distribution whose top-level import package we can
        # shadow with a bogus version.
        pkg_to_dist = im.packages_distributions()
        target = None
        for import_name, dists in pkg_to_dist.items():
            try:
                if im.version(dists[0]):
                    target = (import_name, dists[0])
                    break
            except Exception:
                continue
        if target is None:
            self.skipTest("no importable installed distribution available")
        import_name, dist = target

        tmp = Path(tempfile.mkdtemp())
        pkg = tmp / import_name
        pkg.mkdir()
        (pkg / "__init__.py").write_text('__version__ = "0.0.0-shadow-test"\n')
        sys.path.insert(0, str(tmp))
        try:
            issues, recs = check_package_dir_shadowing()
        finally:
            sys.path.remove(str(tmp))

        mine = [i for i in issues if import_name in i["message"]]
        self.assertEqual(len(mine), 1, f"expected one shadowing issue, got {issues}")
        self.assertEqual(mine[0]["severity"], "high")
        self.assertEqual(mine[0]["category"], "import_shadowing")
        self.assertTrue(recs, "a resolution recommendation should accompany the issue")

    def test_matching_version_not_flagged(self):
        """When the local __version__ matches the installed version, it is not a
        problem (this is what a correct editable checkout looks like)."""
        import importlib.metadata as im
        import tempfile
        from reveal.adapters.python.doctor import check_package_dir_shadowing

        pkg_to_dist = im.packages_distributions()
        target = None
        for import_name, dists in pkg_to_dist.items():
            try:
                v = im.version(dists[0])
                if v:
                    target = (import_name, v)
                    break
            except Exception:
                continue
        if target is None:
            self.skipTest("no importable installed distribution available")
        import_name, real_ver = target

        tmp = Path(tempfile.mkdtemp())
        pkg = tmp / import_name
        pkg.mkdir()
        (pkg / "__init__.py").write_text(f'__version__ = "{real_ver}"\n')
        sys.path.insert(0, str(tmp))
        try:
            issues, _recs = check_package_dir_shadowing()
        finally:
            sys.path.remove(str(tmp))

        mine = [i for i in issues if import_name in i["message"]]
        self.assertEqual(mine, [], f"matching version must not be flagged: {mine}")


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
