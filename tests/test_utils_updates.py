"""Tests for reveal.utils.updates module."""

import json
import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from reveal.utils.updates import check_for_updates


class TestCheckForUpdates:
    """Tests for check_for_updates function."""

    @patch.dict(os.environ, {'REVEAL_NO_UPDATE_CHECK': '1'})
    @patch('reveal.config.get_cache_path')
    def test_opt_out_with_environment_variable(self, mock_cache_path):
        """Should skip check when REVEAL_NO_UPDATE_CHECK is set."""
        # Call function
        check_for_updates()

        # Should not call get_cache_path since we return early
        mock_cache_path.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    def test_proceeds_without_opt_out(self, mock_cache_path, tmp_path):
        """Should proceed with check when opt-out not set."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Create old cache file to avoid network call
        cache_file.write_text((datetime.now() - timedelta(hours=1)).isoformat())

        check_for_updates()

        # Should have called get_cache_path
        mock_cache_path.assert_called_once_with('last_update_check')

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    def test_skips_check_when_recently_checked(self, mock_cache_path, tmp_path):
        """Should skip check if checked within last 24 hours."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Write recent timestamp (1 hour ago)
        recent_time = datetime.now() - timedelta(hours=1)
        cache_file.write_text(recent_time.isoformat())

        # Mock urllib to detect if network call is made
        with patch('urllib.request.urlopen') as mock_urlopen:
            check_for_updates()

            # Should not make network call
            mock_urlopen.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.48.0')
    def test_makes_request_when_cache_old(self, mock_urlopen, mock_cache_path, tmp_path):
        """Should make network request when cache is older than 1 day."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Write old timestamp (2 days ago)
        old_time = datetime.now() - timedelta(days=2)
        cache_file.write_text(old_time.isoformat())

        # Mock PyPI response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        check_for_updates()

        # Should have made network call
        mock_urlopen.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.48.0')
    def test_makes_request_when_no_cache(self, mock_urlopen, mock_cache_path, tmp_path):
        """Should make network request when no cache file exists."""
        cache_file = tmp_path / "nonexistent_cache"
        mock_cache_path.return_value = cache_file

        # Mock PyPI response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        check_for_updates()

        # Should have made network call
        mock_urlopen.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.48.0')
    def test_handles_invalid_cache_content(self, mock_urlopen, mock_cache_path, tmp_path):
        """Should handle invalid cache content gracefully."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Write invalid timestamp
        cache_file.write_text("not a valid timestamp")

        # Mock PyPI response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        # Should not raise exception
        check_for_updates()

        # Should have made network call (invalid cache = proceed)
        mock_urlopen.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.47.0')
    def test_shows_message_when_newer_version_available(self, mock_urlopen, mock_cache_path, tmp_path, capsys):
        """Should print message when newer version is available."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock PyPI response with newer version
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}  # Newer than 0.47.0
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        check_for_updates()

        # Check output
        captured = capsys.readouterr()
        assert "Update available" in captured.out
        assert "0.48.0" in captured.out
        assert "0.47.0" in captured.out

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.48.0')
    def test_no_message_when_same_version(self, mock_urlopen, mock_cache_path, tmp_path, capsys):
        """Should not print message when on latest version."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock PyPI response with same version
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}  # Same as current
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        check_for_updates()

        # Check output - should be empty
        captured = capsys.readouterr()
        assert "Update available" not in captured.out

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.49.0')
    def test_no_message_when_current_version_newer(self, mock_urlopen, mock_cache_path, tmp_path, capsys):
        """Should not print message when current version is newer (e.g., dev version)."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock PyPI response with older version
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}  # Older than current
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        check_for_updates()

        # Check output - should be empty
        captured = capsys.readouterr()
        assert "Update available" not in captured.out

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.48.0')
    def test_updates_cache_after_successful_check(self, mock_urlopen, mock_cache_path, tmp_path):
        """Should update cache file with current timestamp after check."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock PyPI response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        before_time = datetime.now()
        check_for_updates()
        after_time = datetime.now()

        # Cache file should exist and contain recent timestamp
        assert cache_file.exists()
        cached_time = datetime.fromisoformat(cache_file.read_text(encoding='utf-8'))
        assert before_time <= cached_time <= after_time

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    def test_fails_silently_on_network_error(self, mock_urlopen, mock_cache_path, tmp_path):
        """Should fail silently when network request fails."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock network error
        mock_urlopen.side_effect = Exception("Network error")

        # Should not raise exception
        check_for_updates()

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.48.0')
    def test_fails_silently_on_json_parse_error(self, mock_urlopen, mock_cache_path, tmp_path):
        """Should fail silently when JSON response is invalid."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock invalid JSON response
        mock_response = Mock()
        mock_response.read.return_value = b"not valid json"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        # Should not raise exception
        check_for_updates()

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', 'not.a.valid.version')
    def test_handles_invalid_version_comparison(self, mock_urlopen, mock_cache_path, tmp_path, capsys):
        """Should handle invalid version strings gracefully."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock PyPI response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        # Should not raise exception
        check_for_updates()

        # Should not print update message (version comparison failed)
        captured = capsys.readouterr()
        assert "Update available" not in captured.out

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.48.0')
    def test_uses_correct_pypi_url(self, mock_urlopen, mock_cache_path, tmp_path):
        """Should make request to correct PyPI URL."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock PyPI response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        check_for_updates()

        # Verify URL and headers
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.full_url == 'https://pypi.org/pypi/reveal-cli/json'
        assert 'reveal-cli/0.48.0' in request.headers['User-agent']

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.48.0')
    def test_uses_1_second_timeout(self, mock_urlopen, mock_cache_path, tmp_path):
        """Should use 1-second timeout for network request."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock PyPI response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.48.0'}
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        check_for_updates()

        # Verify timeout
        call_args = mock_urlopen.call_args
        assert call_args[1]['timeout'] == 1

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.config.get_cache_path')
    @patch('urllib.request.urlopen')
    @patch('reveal.version.__version__', '0.10.0')
    def test_handles_multi_digit_version_numbers(self, mock_urlopen, mock_cache_path, tmp_path, capsys):
        """Should correctly compare versions with multi-digit numbers."""
        cache_file = tmp_path / "cache"
        mock_cache_path.return_value = cache_file

        # Mock PyPI response with version that has multi-digit component
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'info': {'version': '0.100.0'}  # Much newer
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        check_for_updates()

        # Should detect 0.100.0 > 0.10.0
        captured = capsys.readouterr()
        assert "Update available" in captured.out
        assert "0.100.0" in captured.out
