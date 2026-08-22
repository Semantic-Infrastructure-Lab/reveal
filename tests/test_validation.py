"""Tests for reveal.utils.validation module."""
import pytest
from reveal.utils.validation import (
    require_path_exists,
    require_directory,
)

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


class TestRequirePathExists:
    """Tests for require_path_exists() function."""

    def test_existing_path(self, tmp_path):
        """Existing path returns the path."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        result = require_path_exists(test_file)
        assert result == test_file

    def test_nonexistent_path_raises(self, tmp_path):
        """Nonexistent path raises FileNotFoundError."""
        nonexistent = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="Path not found"):
            require_path_exists(nonexistent)

    def test_custom_error_message(self, tmp_path):
        """Custom path type appears in error message."""
        nonexistent = tmp_path / "config.yaml"
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            require_path_exists(nonexistent, "Configuration file")

    def test_directory_path(self, tmp_path):
        """Directory path works."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        result = require_path_exists(test_dir)
        assert result == test_dir


class TestRequireDirectory:
    """Tests for require_directory() function."""

    def test_existing_directory(self, tmp_path):
        """Existing directory returns the path."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        result = require_directory(test_dir)
        assert result == test_dir

    def test_nonexistent_directory_raises(self, tmp_path):
        """Nonexistent directory raises FileNotFoundError."""
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError, match="Directory not found"):
            require_directory(nonexistent)

    def test_file_raises(self, tmp_path):
        """File raises ValueError."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        with pytest.raises(ValueError, match="Directory is not a directory"):
            require_directory(test_file)

    def test_custom_error_message(self, tmp_path):
        """Custom directory type appears in error message."""
        test_file = tmp_path / "config.yaml"
        test_file.touch()
        with pytest.raises(ValueError, match="Source directory is not a directory"):
            require_directory(test_file, "Source directory")
