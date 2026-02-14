"""Tests for reveal/utils/updates.py - update checking."""

import pytest
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
from reveal.utils.updates import check_for_updates


class TestCheckForUpdates:
    """Test check_for_updates() function."""

    @patch.dict('os.environ', {'REVEAL_NO_UPDATE_CHECK': '1'})
    def test_skips_when_disabled_via_env(self):
        """Skip update check when REVEAL_NO_UPDATE_CHECK is set."""
        # Should return immediately without any network calls
        result = check_for_updates()

        assert result is None

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    def test_successful_update_check_no_update(self, mock_urlopen, mock_get_cache):
        """Check succeeds when no update available."""
        # Mock cache path (no existing cache)
        cache_file = Mock()
        cache_file.exists.return_value = False
        cache_file.write_text = Mock()
        mock_get_cache.return_value = cache_file

        # Mock PyPI response (same version)
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.26.0'}  # Same as current
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch('reveal.version.__version__', '0.26.0'):
            check_for_updates()

        # Should update cache
        mock_get_cache.assert_called_once_with('last_update_check')
        cache_file.write_text.assert_called_once()

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('builtins.print')
    def test_prints_message_when_update_available(self, mock_print, mock_urlopen, mock_get_cache):
        """Print message when newer version available."""
        # Mock cache (no existing)
        cache_file = Mock()
        cache_file.exists.return_value = False
        cache_file.write_text = Mock()
        mock_get_cache.return_value = cache_file

        # Mock PyPI response (newer version)
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.27.0'}  # Newer
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch('reveal.version.__version__', '0.26.0'):
            check_for_updates()

        # Should print update message
        assert mock_print.call_count >= 1
        printed_text = ' '.join(str(call[0][0]) for call in mock_print.call_args_list)
        assert '0.27.0' in printed_text
        assert 'Update available' in printed_text or 'available' in printed_text.lower()

    @patch('reveal.config.get_cache_path')
    def test_skips_if_checked_recently(self, mock_get_cache):
        """Skip check if performed within last 24 hours."""
        # Mock cache with recent timestamp
        cache_file = Mock()
        cache_file.exists.return_value = True
        recent_time = datetime.now() - timedelta(hours=12)
        cache_file.read_text.return_value = recent_time.isoformat()
        mock_get_cache.return_value = cache_file

        # Should return early without network call
        with patch('urllib.request.urlopen') as mock_urlopen:
            check_for_updates()

            # Should NOT make network request
            mock_urlopen.assert_not_called()

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    def test_checks_if_cache_old(self, mock_urlopen, mock_get_cache):
        """Perform check if cache is older than 24 hours."""
        # Mock cache with old timestamp
        cache_file = Mock()
        cache_file.exists.return_value = True
        old_time = datetime.now() - timedelta(days=2)
        cache_file.read_text.return_value = old_time.isoformat()
        cache_file.write_text = Mock()
        mock_get_cache.return_value = cache_file

        # Mock PyPI response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.26.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch('reveal.version.__version__', '0.26.0'):
            check_for_updates()

        # Should make network request
        mock_urlopen.assert_called_once()

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    def test_handles_invalid_cache_file(self, mock_urlopen, mock_get_cache):
        """Continue check if cache contains invalid timestamp."""
        # Mock cache with invalid content
        cache_file = Mock()
        cache_file.exists.return_value = True
        cache_file.read_text.return_value = "not a valid timestamp"
        cache_file.write_text = Mock()
        mock_get_cache.return_value = cache_file

        # Mock PyPI response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.26.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch('reveal.version.__version__', '0.26.0'):
            check_for_updates()

        # Should proceed with check despite invalid cache
        mock_urlopen.assert_called_once()

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    def test_fails_silently_on_network_error(self, mock_urlopen, mock_get_cache):
        """Fail silently on network errors."""
        cache_file = Mock()
        cache_file.exists.return_value = False
        mock_get_cache.return_value = cache_file

        # Mock network error
        mock_urlopen.side_effect = Exception("Network error")

        # Should not raise
        check_for_updates()

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    def test_fails_silently_on_invalid_json(self, mock_urlopen, mock_get_cache):
        """Fail silently on invalid JSON response."""
        cache_file = Mock()
        cache_file.exists.return_value = False
        mock_get_cache.return_value = cache_file

        # Mock invalid JSON
        mock_response = Mock()
        mock_response.read.return_value = b"not valid json"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        # Should not raise
        check_for_updates()

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('builtins.print')
    def test_version_comparison_handles_invalid_version(self, mock_print, mock_urlopen, mock_get_cache):
        """Handle invalid version strings gracefully."""
        cache_file = Mock()
        cache_file.exists.return_value = False
        cache_file.write_text = Mock()
        mock_get_cache.return_value = cache_file

        # Mock response with non-semver version
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': 'invalid.version.string'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch('reveal.version.__version__', '0.26.0'):
            # Should not raise
            check_for_updates()

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    def test_sets_user_agent_header(self, mock_urlopen, mock_get_cache):
        """Set User-Agent header with version."""
        cache_file = Mock()
        cache_file.exists.return_value = False
        cache_file.write_text = Mock()
        mock_get_cache.return_value = cache_file

        # Mock response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.26.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch('reveal.version.__version__', '0.26.0'):
            with patch('urllib.request.Request') as mock_request:
                mock_request.return_value = Mock()
                check_for_updates()

                # Should create Request with User-Agent
                mock_request.assert_called_once()
                call_args = mock_request.call_args
                assert 'headers' in call_args[1]
                assert 'User-Agent' in call_args[1]['headers']
                assert 'reveal-cli/0.26.0' in call_args[1]['headers']['User-Agent']

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    def test_timeout_parameter(self, mock_urlopen, mock_get_cache):
        """Use 1-second timeout for network request."""
        cache_file = Mock()
        cache_file.exists.return_value = False
        cache_file.write_text = Mock()
        mock_get_cache.return_value = cache_file

        # Mock response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.26.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch('reveal.version.__version__', '0.26.0'):
            check_for_updates()

        # Verify timeout parameter
        args, kwargs = mock_urlopen.call_args
        assert kwargs.get('timeout') == 1 or (len(args) > 1 and args[1] == 1)

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('builtins.print')
    def test_no_message_when_version_same(self, mock_print, mock_urlopen, mock_get_cache):
        """Don't print message when versions match."""
        cache_file = Mock()
        cache_file.exists.return_value = False
        cache_file.write_text = Mock()
        mock_get_cache.return_value = cache_file

        # Mock response with same version
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.26.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch('reveal.version.__version__', '0.26.0'):
            check_for_updates()

        # Should NOT print anything
        mock_print.assert_not_called()

    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('builtins.print')
    def test_no_message_when_current_version_newer(self, mock_print, mock_urlopen, mock_get_cache):
        """Don't print message when running dev version newer than PyPI."""
        cache_file = Mock()
        cache_file.exists.return_value = False
        cache_file.write_text = Mock()
        mock_get_cache.return_value = cache_file

        # Mock response with older version
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.25.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch('reveal.version.__version__', '0.26.0'):
            check_for_updates()

        # Should NOT print (current version is newer)
        mock_print.assert_not_called()

    @patch('reveal.config.get_cache_path')
    def test_handles_oserror_on_cache_read(self, mock_get_cache):
        """Fail silently if cache read raises OSError."""
        cache_file = Mock()
        cache_file.exists.return_value = True
        cache_file.read_text.side_effect = OSError("Permission denied")
        mock_get_cache.return_value = cache_file

        with patch('urllib.request.urlopen') as mock_urlopen:
            # Should not raise (fails silently)
            check_for_updates()

            # OSError is caught by outer try-except, no network call made
            mock_urlopen.assert_not_called()
