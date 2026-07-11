"""Tests for Windows compatibility features."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from reveal.adapters.env import EnvAdapter


class TestWindowsCompatibility(unittest.TestCase):
    """Test Windows-specific compatibility features."""

    def test_cache_dir_windows(self):
        """Test cache directory uses Windows paths on Windows."""
        # Simulate Windows platform
        with patch('sys.platform', 'win32'):
            with patch.dict(os.environ, {'LOCALAPPDATA': r'C:\Users\TestUser\AppData\Local'}):
                # This mimics the logic from reveal/main.py:331
                if sys.platform == 'win32':
                    cache_dir = Path(os.getenv('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'reveal'
                else:
                    cache_dir = Path.home() / '.config' / 'reveal'

                # On Windows, should use LOCALAPPDATA
                expected = Path(r'C:\Users\TestUser\AppData\Local') / 'reveal'
                self.assertEqual(cache_dir, expected)

    def test_cache_dir_windows_fallback(self):
        """Test cache directory fallback when LOCALAPPDATA missing."""
        with patch('sys.platform', 'win32'):
            with patch.dict(os.environ, {}, clear=True):
                with patch('pathlib.Path.home') as mock_home:
                    mock_home.return_value = Path(r'C:\Users\TestUser')

                    # Fallback logic when LOCALAPPDATA not set
                    if sys.platform == 'win32':
                        cache_dir = Path(os.getenv('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'reveal'
                    else:
                        cache_dir = Path.home() / '.config' / 'reveal'

                    # Use parts to compare (handles mixed separators on test platform)
                    self.assertTrue(str(cache_dir).endswith('AppData/Local/reveal') or
                                  str(cache_dir).endswith(r'AppData\Local\reveal'),
                                  f"Cache dir {cache_dir} should end with AppData/Local/reveal")

    def test_cache_dir_unix(self):
        """Test cache directory uses Unix paths on Unix/macOS."""
        # Simulate Unix platform
        with patch('sys.platform', 'linux'):
            with patch('pathlib.Path.home') as mock_home:
                mock_home.return_value = Path('/home/testuser')

                # This mimics the logic from reveal/main.py:331
                if sys.platform == 'win32':
                    cache_dir = Path(os.getenv('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'reveal'
                else:
                    cache_dir = Path.home() / '.config' / 'reveal'

                expected = Path('/home/testuser/.config/reveal')
                self.assertEqual(cache_dir, expected)

    def test_windows_env_vars_in_system_vars(self):
        """Test that Windows environment variables are recognized as system vars."""
        adapter = EnvAdapter()

        # Windows-specific variables that should be in SYSTEM_VARS
        windows_vars = [
            'USERPROFILE', 'USERNAME', 'COMSPEC', 'SYSTEMROOT',
            'WINDIR', 'TEMP', 'TMP', 'OS', 'PROCESSOR_ARCHITECTURE',
            'PATHEXT', 'COMPUTERNAME', 'HOMEDRIVE', 'HOMEPATH',
            'LOCALAPPDATA', 'APPDATA', 'PROGRAMFILES'
        ]

        for var in windows_vars:
            self.assertIn(var, adapter.SYSTEM_VARS,
                         f"Windows variable {var} should be in SYSTEM_VARS")

    def test_unix_env_vars_still_present(self):
        """Test that Unix environment variables are still recognized."""
        adapter = EnvAdapter()

        # Unix-specific variables that should be in SYSTEM_VARS
        unix_vars = [
            'PATH', 'HOME', 'SHELL', 'USER', 'LANG', 'PWD',
            'LOGNAME', 'TERM', 'DISPLAY', 'EDITOR', 'PAGER'
        ]

        for var in unix_vars:
            self.assertIn(var, adapter.SYSTEM_VARS,
                         f"Unix variable {var} should be in SYSTEM_VARS")

    def test_env_adapter_categorizes_windows_vars_as_system(self):
        """Test that EnvAdapter categorizes Windows variables correctly."""
        # Mock environment with Windows variables
        with patch.dict(os.environ, {
            'USERPROFILE': r'C:\Users\TestUser',
            'USERNAME': 'TestUser',
            'COMSPEC': r'C:\Windows\system32\cmd.exe',
            'CUSTOM_VAR': 'custom_value'
        }, clear=True):
            adapter = EnvAdapter()

            # Windows system variables should be categorized as 'System'
            self.assertEqual(adapter._categorize('USERPROFILE'), 'System')
            self.assertEqual(adapter._categorize('USERNAME'), 'System')
            self.assertEqual(adapter._categorize('COMSPEC'), 'System')

            # Custom variables should not be 'System'
            self.assertEqual(adapter._categorize('CUSTOM_VAR'), 'Custom')

    def test_system_vars_count(self):
        """Test that we have reasonable coverage of system variables."""
        adapter = EnvAdapter()

        # Should have at least 27 system variables (11 Unix + 16 Windows)
        self.assertGreaterEqual(len(adapter.SYSTEM_VARS), 27,
                               "Should have at least 27 system variables for cross-platform support")


class TestResourceModuleWindows(unittest.TestCase):
    """The POSIX-only `resource` module must not break Windows.

    0.107.0 added an unconditional top-level `import resource` in main.py for
    --perf RSS logging. `resource` does not exist on Windows CPython, so every
    reveal invocation (even `--version`) crashed with ModuleNotFoundError before
    argument parsing even started. Regression guard: main must import, and the
    perf logger must no-op the RSS field, when `resource` is unavailable.
    """

    def test_main_imports_without_resource_module(self):
        """reveal.main imports even when `resource` is unavailable (Windows).

        Reproduces the Windows condition hermetically: seeding
        sys.modules['resource'] = None makes `import resource` raise
        ModuleNotFoundError, exactly as on Windows. Run in a subprocess (a fresh
        interpreter) so the block doesn't perturb the test process, pinned to the
        same reveal package under test via PYTHONPATH.
        """
        import reveal
        pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(reveal.__file__)))
        code = (
            "import sys; sys.modules['resource'] = None; "
            "import reveal.main; print('IMPORT_OK')"
        )
        env = dict(os.environ)
        env['PYTHONPATH'] = pkg_parent + os.pathsep + env.get('PYTHONPATH', '')
        result = subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(
            result.returncode, 0,
            f"reveal.main failed to import without `resource`:\n{result.stderr}",
        )
        self.assertIn('IMPORT_OK', result.stdout)

    def test_log_perf_no_ops_rss_without_resource(self):
        """_log_perf records peak_rss_kb=None (not a crash) when resource is None."""
        import reveal.main as main_mod
        with tempfile.TemporaryDirectory() as d:
            log_path = Path(d) / 'perf.jsonl'
            with patch.object(main_mod, 'resource', None), \
                 patch.object(main_mod, 'PERF_LOG_PATH', log_path):
                main_mod._log_perf(time.perf_counter(), ['reveal', '--version'], 0)
            lines = log_path.read_text(encoding='utf-8').strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIsNone(json.loads(lines[0])['peak_rss_kb'])


if __name__ == '__main__':
    unittest.main()
