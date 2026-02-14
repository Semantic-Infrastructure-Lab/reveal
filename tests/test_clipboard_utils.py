"""Tests for reveal/utils/clipboard.py - clipboard utilities."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from reveal.utils.clipboard import copy_to_clipboard


class TestCopyToClipboard:
    """Test copy_to_clipboard() for cross-platform clipboard support."""

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_xclip_success(self, mock_popen, mock_which):
        """Copy using xclip (Linux X11)."""
        # Mock xclip available
        mock_which.side_effect = lambda cmd: '/usr/bin/xclip' if cmd == 'xclip' else None

        # Mock successful copy
        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        result = copy_to_clipboard("test text")

        assert result is True
        mock_popen.assert_called_once()
        # Verify xclip command format
        args, kwargs = mock_popen.call_args
        assert args[0] == ['xclip', '-selection', 'clipboard']
        assert kwargs['stdin'] == __import__('subprocess').PIPE

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_xsel_fallback(self, mock_popen, mock_which):
        """Fall back to xsel when xclip unavailable."""
        # Mock xclip not available, xsel available
        def which_side_effect(cmd):
            if cmd == 'xclip':
                return None
            elif cmd == 'xsel':
                return '/usr/bin/xsel'
            return None

        mock_which.side_effect = which_side_effect

        # Mock successful xsel
        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        result = copy_to_clipboard("test")

        assert result is True
        args, _ = mock_popen.call_args
        assert args[0] == ['xsel', '--clipboard', '--input']

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_wl_copy_wayland(self, mock_popen, mock_which):
        """Use wl-copy on Wayland."""
        # Mock only wl-copy available
        def which_side_effect(cmd):
            return '/usr/bin/wl-copy' if cmd == 'wl-copy' else None

        mock_which.side_effect = which_side_effect

        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        result = copy_to_clipboard("wayland test")

        assert result is True
        args, _ = mock_popen.call_args
        assert args[0] == ['wl-copy']

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_pbcopy_macos(self, mock_popen, mock_which):
        """Use pbcopy on macOS."""
        # Mock only pbcopy available
        def which_side_effect(cmd):
            return '/usr/bin/pbcopy' if cmd == 'pbcopy' else None

        mock_which.side_effect = which_side_effect

        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        result = copy_to_clipboard("macos test")

        assert result is True
        args, _ = mock_popen.call_args
        assert args[0] == ['pbcopy']

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_clip_windows(self, mock_popen, mock_which):
        """Use clip on Windows."""
        # Mock only clip available
        def which_side_effect(cmd):
            return 'C:\\Windows\\System32\\clip.exe' if cmd == 'clip' else None

        mock_which.side_effect = which_side_effect

        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        result = copy_to_clipboard("windows test")

        assert result is True
        args, _ = mock_popen.call_args
        assert args[0] == ['clip']

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_utf8_encoding(self, mock_popen, mock_which):
        """Encode text as UTF-8 for clipboard."""
        mock_which.return_value = '/usr/bin/xclip'

        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        # Text with unicode characters
        copy_to_clipboard("Hello 世界 🚀")

        # Verify UTF-8 encoding
        mock_process.communicate.assert_called_once()
        _, kwargs = mock_process.communicate.call_args
        assert kwargs['input'] == "Hello 世界 🚀".encode('utf-8')

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_process_error_continues(self, mock_popen, mock_which):
        """Continue trying other tools on subprocess error."""
        # Both xclip and xsel available
        mock_which.side_effect = lambda cmd: f'/usr/bin/{cmd}' if cmd in ['xclip', 'xsel'] else None

        # xclip fails, xsel succeeds
        mock_fail = Mock()
        mock_fail.communicate.side_effect = __import__('subprocess').SubprocessError("Failed")

        mock_success = Mock()
        mock_success.communicate.return_value = (None, None)
        mock_success.returncode = 0

        mock_popen.side_effect = [mock_fail, mock_success]

        result = copy_to_clipboard("test")

        assert result is True
        assert mock_popen.call_count == 2

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_nonzero_returncode_continues(self, mock_popen, mock_which):
        """Continue trying other tools on non-zero return code."""
        # Both tools available
        mock_which.side_effect = lambda cmd: f'/usr/bin/{cmd}' if cmd in ['xclip', 'xsel'] else None

        # xclip returns non-zero, xsel succeeds
        mock_fail = Mock()
        mock_fail.communicate.return_value = (None, None)
        mock_fail.returncode = 1

        mock_success = Mock()
        mock_success.communicate.return_value = (None, None)
        mock_success.returncode = 0

        mock_popen.side_effect = [mock_fail, mock_success]

        result = copy_to_clipboard("test")

        assert result is True

    @patch('reveal.utils.clipboard.shutil.which')
    def test_no_clipboard_tool_available(self, mock_which):
        """Return False when no clipboard tool available."""
        # No tools available
        mock_which.return_value = None

        result = copy_to_clipboard("test")

        assert result is False

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_all_tools_fail(self, mock_popen, mock_which):
        """Return False when all available tools fail."""
        # All tools available but all fail
        mock_which.return_value = '/usr/bin/tool'

        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        result = copy_to_clipboard("test")

        assert result is False

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_oserror_handled(self, mock_popen, mock_which):
        """Handle OSError gracefully and try next tool."""
        mock_which.side_effect = lambda cmd: f'/usr/bin/{cmd}' if cmd in ['xclip', 'xsel'] else None

        # xclip raises OSError, xsel succeeds
        mock_popen.side_effect = [
            OSError("Permission denied"),
            Mock(communicate=Mock(return_value=(None, None)), returncode=0)
        ]

        result = copy_to_clipboard("test")

        assert result is True

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_empty_text(self, mock_popen, mock_which):
        """Handle empty text string."""
        mock_which.return_value = '/usr/bin/xclip'

        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        result = copy_to_clipboard("")

        assert result is True
        _, kwargs = mock_process.communicate.call_args
        assert kwargs['input'] == b""

    @patch('reveal.utils.clipboard.shutil.which')
    @patch('reveal.utils.clipboard.subprocess.Popen')
    def test_large_text(self, mock_popen, mock_which):
        """Handle large text strings."""
        mock_which.return_value = '/usr/bin/xclip'

        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        large_text = "A" * 100000
        result = copy_to_clipboard(large_text)

        assert result is True
        _, kwargs = mock_process.communicate.call_args
        assert len(kwargs['input']) == 100000
