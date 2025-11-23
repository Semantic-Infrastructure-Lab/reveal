"""
Tests for CLI module.

Tests command-line interface utilities and parsing.
"""

import unittest
from reveal.cli import parse_file_location


class TestParseFileLocation(unittest.TestCase):
    """Test file location parsing with line numbers."""

    def test_parse_simple_file_path(self):
        """Should parse simple file path without line numbers."""
        file_path, start, end = parse_file_location("script.py")

        self.assertEqual(file_path, "script.py")
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_parse_file_with_single_line_number(self):
        """Should parse file path with single line number."""
        file_path, start, end = parse_file_location("script.py:42")

        self.assertEqual(file_path, "script.py")
        self.assertEqual(start, 42)
        self.assertEqual(end, 42)

    def test_parse_file_with_line_range(self):
        """Should parse file path with line range."""
        file_path, start, end = parse_file_location("script.py:10-50")

        self.assertEqual(file_path, "script.py")
        self.assertEqual(start, 10)
        self.assertEqual(end, 50)

    def test_parse_file_with_open_ended_range(self):
        """Should parse file path with open-ended range."""
        file_path, start, end = parse_file_location("script.py:10-")

        self.assertEqual(file_path, "script.py")
        self.assertEqual(start, 10)
        self.assertIsNone(end)

    def test_parse_file_with_range_from_start(self):
        """Should parse file path with range from start."""
        file_path, start, end = parse_file_location("script.py:-50")

        self.assertEqual(file_path, "script.py")
        self.assertEqual(start, 1)
        self.assertEqual(end, 50)

    def test_parse_absolute_path_unix(self):
        """Should handle absolute Unix paths."""
        file_path, start, end = parse_file_location("/home/user/script.py:100")

        self.assertEqual(file_path, "/home/user/script.py")
        self.assertEqual(start, 100)
        self.assertEqual(end, 100)

    def test_parse_relative_path_with_dots(self):
        """Should handle relative paths with .."""
        file_path, start, end = parse_file_location("../../src/module.py:25")

        self.assertEqual(file_path, "../../src/module.py")
        self.assertEqual(start, 25)
        self.assertEqual(end, 25)

    def test_parse_file_with_multiple_dots(self):
        """Should handle filenames with multiple dots."""
        file_path, start, end = parse_file_location("config.prod.yaml:15")

        self.assertEqual(file_path, "config.prod.yaml")
        self.assertEqual(start, 15)
        self.assertEqual(end, 15)

    def test_parse_invalid_line_number(self):
        """Should treat invalid line numbers as part of filename."""
        file_path, start, end = parse_file_location("file:notanumber")

        self.assertEqual(file_path, "file:notanumber")
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_parse_file_with_colon_in_path(self):
        """Should handle Windows paths with drive letters."""
        # Windows path - last colon should be used for line number
        file_path, start, end = parse_file_location("C:\\Users\\file.txt:42")

        self.assertEqual(file_path, "C:\\Users\\file.txt")
        self.assertEqual(start, 42)
        self.assertEqual(end, 42)

    def test_parse_zero_line_number(self):
        """Should handle zero line number."""
        file_path, start, end = parse_file_location("file.py:0")

        self.assertEqual(file_path, "file.py")
        self.assertEqual(start, 0)
        self.assertEqual(end, 0)

    def test_parse_large_line_numbers(self):
        """Should handle large line numbers."""
        file_path, start, end = parse_file_location("file.py:10000-99999")

        self.assertEqual(file_path, "file.py")
        self.assertEqual(start, 10000)
        self.assertEqual(end, 99999)

    def test_parse_file_with_no_extension(self):
        """Should handle files without extensions."""
        file_path, start, end = parse_file_location("Makefile:5")

        self.assertEqual(file_path, "Makefile")
        self.assertEqual(start, 5)
        self.assertEqual(end, 5)

    def test_parse_file_path_with_spaces(self):
        """Should handle file paths with spaces."""
        file_path, start, end = parse_file_location("my file.py:10")

        self.assertEqual(file_path, "my file.py")
        self.assertEqual(start, 10)
        self.assertEqual(end, 10)

    def test_parse_complex_path(self):
        """Should handle complex real-world paths."""
        file_path, start, end = parse_file_location(
            "/home/user/projects/myapp/src/utils/helper.py:42-100"
        )

        self.assertEqual(file_path, "/home/user/projects/myapp/src/utils/helper.py")
        self.assertEqual(start, 42)
        self.assertEqual(end, 100)

    def test_parse_hidden_file(self):
        """Should handle hidden files (starting with dot)."""
        file_path, start, end = parse_file_location(".gitignore:5")

        self.assertEqual(file_path, ".gitignore")
        self.assertEqual(start, 5)
        self.assertEqual(end, 5)

    def test_parse_file_with_multiple_colons(self):
        """Should use rightmost colon for line number."""
        file_path, start, end = parse_file_location("C:\\path\\to\\file.py:100")

        self.assertEqual(file_path, "C:\\path\\to\\file.py")
        self.assertEqual(start, 100)
        self.assertEqual(end, 100)

    def test_parse_negative_line_numbers(self):
        """Should handle negative line numbers gracefully."""
        # Negative numbers in range might be parsed oddly
        # This tests the actual behavior
        file_path, start, end = parse_file_location("file.py:-5")

        # Should parse as range from start to line 5
        self.assertEqual(file_path, "file.py")

    def test_parse_empty_string(self):
        """Should handle empty string."""
        file_path, start, end = parse_file_location("")

        self.assertEqual(file_path, "")
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_parse_just_colon(self):
        """Should handle edge case of just a colon."""
        file_path, start, end = parse_file_location(":")

        # Should treat as invalid and return as-is
        self.assertEqual(file_path, ":")
        self.assertIsNone(start)
        self.assertIsNone(end)


if __name__ == '__main__':
    unittest.main()
