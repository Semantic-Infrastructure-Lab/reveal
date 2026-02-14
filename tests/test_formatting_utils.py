"""Tests for reveal/utils/formatting.py - formatting utilities."""

import pytest
from reveal.utils.formatting import format_size


class TestFormatSize:
    """Test format_size() for human-readable file sizes."""

    def test_bytes(self):
        """Format sizes in bytes."""
        assert format_size(0) == "0.0 B"
        assert format_size(100) == "100.0 B"
        assert format_size(1023) == "1023.0 B"

    def test_kilobytes(self):
        """Format sizes in kilobytes."""
        assert format_size(1024) == "1.0 KB"
        assert format_size(2048) == "2.0 KB"
        assert format_size(1536) == "1.5 KB"
        assert format_size(10240) == "10.0 KB"

    def test_megabytes(self):
        """Format sizes in megabytes."""
        assert format_size(1048576) == "1.0 MB"  # 1024 * 1024
        assert format_size(5242880) == "5.0 MB"  # 5 * 1024 * 1024
        assert format_size(1572864) == "1.5 MB"  # 1.5 * 1024 * 1024

    def test_gigabytes(self):
        """Format sizes in gigabytes."""
        assert format_size(1073741824) == "1.0 GB"  # 1024^3
        assert format_size(3221225472) == "3.0 GB"  # 3 * 1024^3
        assert format_size(1610612736) == "1.5 GB"  # 1.5 * 1024^3

    def test_terabytes(self):
        """Format sizes in terabytes."""
        assert format_size(1099511627776) == "1.0 TB"  # 1024^4
        assert format_size(5497558138880) == "5.0 TB"  # 5 * 1024^4
        assert format_size(1649267441664) == "1.5 TB"  # 1.5 * 1024^4

    def test_boundary_values(self):
        """Test boundary values between units."""
        # Just under 1 KB
        assert "1023.0 B" == format_size(1023)

        # Exactly 1 KB
        assert "1.0 KB" == format_size(1024)

        # Just under 1 MB
        assert "1023.0 KB" == format_size(1024 * 1023)

        # Exactly 1 MB
        assert "1.0 MB" == format_size(1024 * 1024)

    def test_precision(self):
        """Test decimal precision is always 1 digit."""
        assert format_size(1234) == "1.2 KB"
        assert format_size(1234567) == "1.2 MB"
        assert format_size(1234567890) == "1.1 GB"

    def test_large_terabytes(self):
        """Format very large sizes in terabytes."""
        petabyte = 1024 ** 5
        assert format_size(petabyte) == "1024.0 TB"
        assert format_size(petabyte * 5) == "5120.0 TB"

    def test_negative_size(self):
        """Handle negative sizes (should not occur but test behavior)."""
        # Negative sizes stay in bytes (< 1024 check fails)
        result = format_size(-1024)
        assert result == "-1024.0 B"

    def test_float_input(self):
        """Accept integer inputs that may come from stat operations."""
        # Python's int() returns int, but test common patterns
        size = int(1536.7)
        assert format_size(size) == "1.5 KB"
