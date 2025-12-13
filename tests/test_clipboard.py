"""
Tests for clipboard functionality (--copy / -c flag).

Tests the copy_to_clipboard function and CLI integration.
Cross-platform: Linux (xclip/xsel/wl-copy), macOS (pbcopy), Windows (clip).
"""

import unittest
import subprocess
import sys
import os
import tempfile
from unittest.mock import patch, MagicMock


class TestCopyToClipboard(unittest.TestCase):
    """Unit tests for copy_to_clipboard function."""

    def setUp(self):
        """Import the function for testing."""
        from reveal.utils import copy_to_clipboard
        self.copy_to_clipboard = copy_to_clipboard

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_xclip_success(self, mock_popen, mock_which):
        """Should use xclip on Linux X11."""
        mock_which.side_effect = lambda cmd: '/usr/bin/xclip' if cmd == 'xclip' else None
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        result = self.copy_to_clipboard("test text")

        self.assertTrue(result)
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        self.assertEqual(call_args[0][0], ['xclip', '-selection', 'clipboard'])

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_xsel_fallback(self, mock_popen, mock_which):
        """Should fall back to xsel if xclip unavailable."""
        mock_which.side_effect = lambda cmd: '/usr/bin/xsel' if cmd == 'xsel' else None
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        result = self.copy_to_clipboard("test text")

        self.assertTrue(result)
        call_args = mock_popen.call_args
        self.assertEqual(call_args[0][0], ['xsel', '--clipboard', '--input'])

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_wl_copy_wayland(self, mock_popen, mock_which):
        """Should use wl-copy on Wayland."""
        def which_side_effect(cmd):
            return '/usr/bin/wl-copy' if cmd == 'wl-copy' else None
        mock_which.side_effect = which_side_effect
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        result = self.copy_to_clipboard("test text")

        self.assertTrue(result)
        call_args = mock_popen.call_args
        self.assertEqual(call_args[0][0], ['wl-copy'])

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_pbcopy_macos(self, mock_popen, mock_which):
        """Should use pbcopy on macOS."""
        mock_which.side_effect = lambda cmd: '/usr/bin/pbcopy' if cmd == 'pbcopy' else None
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        result = self.copy_to_clipboard("test text")

        self.assertTrue(result)
        call_args = mock_popen.call_args
        self.assertEqual(call_args[0][0], ['pbcopy'])

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_clip_windows(self, mock_popen, mock_which):
        """Should use clip.exe on Windows."""
        mock_which.side_effect = lambda cmd: 'C:\\Windows\\System32\\clip.exe' if cmd == 'clip' else None
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        result = self.copy_to_clipboard("test text")

        self.assertTrue(result)
        call_args = mock_popen.call_args
        self.assertEqual(call_args[0][0], ['clip'])

    @patch('shutil.which')
    def test_no_clipboard_utility(self, mock_which):
        """Should return False when no clipboard utility available."""
        mock_which.return_value = None

        result = self.copy_to_clipboard("test text")

        self.assertFalse(result)

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_clipboard_failure(self, mock_popen, mock_which):
        """Should return False when clipboard command fails."""
        mock_which.return_value = '/usr/bin/xclip'
        mock_process = MagicMock()
        mock_process.returncode = 1  # Non-zero = failure
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        result = self.copy_to_clipboard("test text")

        self.assertFalse(result)

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_subprocess_exception(self, mock_popen, mock_which):
        """Should handle subprocess exceptions gracefully."""
        mock_which.return_value = '/usr/bin/xclip'
        mock_popen.side_effect = subprocess.SubprocessError("Failed")

        result = self.copy_to_clipboard("test text")

        self.assertFalse(result)

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_utf8_encoding(self, mock_popen, mock_which):
        """Should handle UTF-8 text including emoji."""
        mock_which.return_value = '/usr/bin/xclip'
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        result = self.copy_to_clipboard("Hello 世界 🎉")

        self.assertTrue(result)
        # Verify the text was encoded as UTF-8
        call_args = mock_popen.return_value.communicate.call_args
        self.assertEqual(call_args[1]['input'], "Hello 世界 🎉".encode('utf-8'))

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_empty_string(self, mock_popen, mock_which):
        """Should handle empty string."""
        mock_which.return_value = '/usr/bin/xclip'
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        result = self.copy_to_clipboard("")

        self.assertTrue(result)

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_large_text(self, mock_popen, mock_which):
        """Should handle large text blocks."""
        mock_which.return_value = '/usr/bin/xclip'
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        large_text = "x" * 100000  # 100KB
        result = self.copy_to_clipboard(large_text)

        self.assertTrue(result)

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_fallback_chain(self, mock_popen, mock_which):
        """Should try utilities in order until one works."""
        # First utility fails, second succeeds
        call_count = [0]
        def popen_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock = MagicMock()
            if call_count[0] == 1:
                mock.returncode = 1  # First fails
            else:
                mock.returncode = 0  # Second succeeds
            mock.communicate.return_value = (b'', b'')
            return mock

        mock_which.side_effect = lambda cmd: f'/usr/bin/{cmd}' if cmd in ['xclip', 'xsel'] else None
        mock_popen.side_effect = popen_side_effect

        result = self.copy_to_clipboard("test")

        self.assertTrue(result)
        self.assertEqual(call_count[0], 2)  # Tried 2 utilities


class TestCopyFlagCLI(unittest.TestCase):
    """CLI integration tests for --copy flag."""

    def run_reveal(self, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        return result

    def test_copy_flag_recognized(self):
        """--copy flag should be recognized."""
        result = self.run_reveal("--help")
        self.assertIn("--copy", result.stdout)
        self.assertIn("-c", result.stdout)

    def test_copy_shows_feedback_on_stderr(self):
        """Should show clipboard feedback on stderr."""
        # Create a simple test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello(): pass\n")
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--copy")
            # Either succeeds with "Copied" or fails with "Could not copy"
            self.assertTrue(
                "Copied" in result.stderr or "Could not copy" in result.stderr,
                f"Expected clipboard feedback in stderr, got: {result.stderr}"
            )
        finally:
            os.unlink(temp_file)

    def test_copy_output_still_displays(self):
        """Output should still display when using --copy (tee behavior)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test_function(): pass\n")
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--copy")
            # Main output should still go to stdout
            self.assertIn("test_function", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_short_flag_c(self):
        """-c should work as shorthand for --copy."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def short_test(): pass\n")
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "-c")
            self.assertIn("short_test", result.stdout)
            self.assertTrue(
                "Copied" in result.stderr or "Could not copy" in result.stderr
            )
        finally:
            os.unlink(temp_file)

    def test_copy_with_element_extraction(self):
        """--copy should work with element extraction."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def foo(): pass\ndef bar(): return 42\n")
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "bar", "--copy")
            self.assertIn("bar", result.stdout)
            self.assertIn("42", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_copy_with_outline(self):
        """--copy should work with --outline flag."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("class MyClass:\n    def method(self): pass\n")
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline", "--copy")
            self.assertIn("MyClass", result.stdout)
        finally:
            os.unlink(temp_file)


class TestWindowsClipboardCompat(unittest.TestCase):
    """Windows-specific clipboard compatibility tests."""

    @patch('sys.platform', 'win32')
    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_windows_clip_priority(self, mock_popen, mock_which):
        """On Windows, clip should be found and used."""
        from reveal.main import copy_to_clipboard

        # Only clip available (Windows scenario)
        mock_which.side_effect = lambda cmd: 'C:\\Windows\\System32\\clip.exe' if cmd == 'clip' else None
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        result = copy_to_clipboard("Windows test")

        self.assertTrue(result)
        call_args = mock_popen.call_args
        self.assertEqual(call_args[0][0], ['clip'])

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_windows_utf8_handling(self, mock_popen, mock_which):
        """Windows clip should receive UTF-8 encoded text."""
        from reveal.main import copy_to_clipboard

        mock_which.side_effect = lambda cmd: 'clip.exe' if cmd == 'clip' else None
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'', b'')
        mock_popen.return_value = mock_process

        # Text with unicode that might cause Windows issues
        result = copy_to_clipboard("→ arrow • bullet 中文")

        self.assertTrue(result)
        call_args = mock_popen.return_value.communicate.call_args
        expected_bytes = "→ arrow • bullet 中文".encode('utf-8')
        self.assertEqual(call_args[1]['input'], expected_bytes)


if __name__ == '__main__':
    unittest.main()
