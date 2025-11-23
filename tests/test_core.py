"""
Tests for core module functionality.

Tests file reading, summary creation, and error handling.
"""

import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from reveal.core import (
    FileSummary,
    read_file_safe,
    compute_sha256,
    create_file_summary
)


class TestReadFileSafe(unittest.TestCase):
    """Test safe file reading with encoding detection."""

    def test_read_utf8_file(self):
        """Should successfully read UTF-8 encoded files."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
            f.write("Hello World\nLine 2\nLine 3")
            temp_path = Path(f.name)

        try:
            success, error, lines = read_file_safe(temp_path)
            self.assertTrue(success)
            self.assertEqual(error, "")
            self.assertEqual(len(lines), 3)
            self.assertEqual(lines[0], "Hello World")
        finally:
            temp_path.unlink()

    def test_read_utf8_bom_file(self):
        """Should handle UTF-8 files with BOM."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt') as f:
            # UTF-8 BOM
            f.write(b'\xef\xbb\xbfHello BOM')
            temp_path = Path(f.name)

        try:
            success, error, lines = read_file_safe(temp_path)
            self.assertTrue(success)
            self.assertEqual(error, "")
            self.assertIn("Hello BOM", lines[0])
        finally:
            temp_path.unlink()

    def test_read_cp1252_file(self):
        """Should handle Windows CP1252 encoded files."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt') as f:
            # CP1252 specific character - use actual smart quotes
            # \x93 and \x94 are "smart quotes" in CP1252
            # But we need to write them as bytes directly
            f.write(b"Hello \x93Windows\x94")
            temp_path = Path(f.name)

        try:
            success, error, lines = read_file_safe(temp_path)
            self.assertTrue(success)
            self.assertEqual(error, "")
            self.assertGreater(len(lines), 0)
        finally:
            temp_path.unlink()

    def test_read_nonexistent_file(self):
        """Should fail gracefully for nonexistent files."""
        temp_path = Path("/tmp/nonexistent_file_12345.txt")
        success, error, lines = read_file_safe(temp_path)

        self.assertFalse(success)
        self.assertIn("not found", error.lower())
        self.assertEqual(lines, [])

    def test_read_large_file_without_force(self):
        """Should reject large files without force flag."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt') as f:
            # Write 3MB of data
            f.write(b'x' * (3 * 1024 * 1024))
            temp_path = Path(f.name)

        try:
            success, error, lines = read_file_safe(temp_path, max_bytes=2 * 1024 * 1024, force=False)
            self.assertFalse(success)
            self.assertIn("too large", error.lower())
            self.assertEqual(lines, [])
        finally:
            temp_path.unlink()

    def test_read_large_file_with_force(self):
        """Should read large files when force flag is set."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
            # Write 3MB of data
            f.write('x' * (3 * 1024 * 1024))
            temp_path = Path(f.name)

        try:
            success, error, lines = read_file_safe(temp_path, max_bytes=2 * 1024 * 1024, force=True)
            self.assertTrue(success)
            self.assertEqual(error, "")
        finally:
            temp_path.unlink()

    def test_read_binary_file(self):
        """Should handle binary files with fallback encoding."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
            # Write pure binary data
            f.write(bytes(range(256)))
            temp_path = Path(f.name)

        try:
            success, error, lines = read_file_safe(temp_path)
            # iso-8859-1 fallback accepts all bytes, so this will succeed
            # This is the expected behavior - it provides a fallback reading
            self.assertTrue(success)
            self.assertEqual(error, "")
            # Should have read the file (though content may be garbled)
            self.assertGreater(len(lines), 0)
        finally:
            temp_path.unlink()

    def test_read_empty_file(self):
        """Should handle empty files."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
            temp_path = Path(f.name)

        try:
            success, error, lines = read_file_safe(temp_path)
            self.assertTrue(success)
            self.assertEqual(error, "")
            self.assertEqual(lines, [])
        finally:
            temp_path.unlink()


class TestComputeSha256(unittest.TestCase):
    """Test SHA256 hash computation."""

    def test_compute_hash_simple_file(self):
        """Should compute correct SHA256 hash."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(b"Hello World")
            temp_path = Path(f.name)

        try:
            hash_value = compute_sha256(temp_path)
            # Known SHA256 of "Hello World"
            expected = "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"
            self.assertEqual(hash_value, expected)
        finally:
            temp_path.unlink()

    def test_compute_hash_empty_file(self):
        """Should compute hash for empty files."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            temp_path = Path(f.name)

        try:
            hash_value = compute_sha256(temp_path)
            # Known SHA256 of empty file
            expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            self.assertEqual(hash_value, expected)
        finally:
            temp_path.unlink()

    def test_compute_hash_nonexistent_file(self):
        """Should return ERROR for nonexistent files."""
        temp_path = Path("/tmp/nonexistent_12345.txt")
        hash_value = compute_sha256(temp_path)
        self.assertEqual(hash_value, "ERROR")


class TestFileSummary(unittest.TestCase):
    """Test FileSummary dataclass."""

    def test_create_file_summary_basic(self):
        """Should create basic file summary."""
        summary = FileSummary(
            path=Path("/tmp/test.txt"),
            type="text",
            size=100,
            modified=datetime.now(),
            linecount=10,
            sha256="abc123"
        )

        self.assertEqual(summary.path, Path("/tmp/test.txt"))
        self.assertEqual(summary.type, "text")
        self.assertEqual(summary.size, 100)
        self.assertEqual(summary.linecount, 10)
        self.assertFalse(summary.is_binary)
        self.assertIsNone(summary.parse_error)

    def test_file_summary_with_metadata(self):
        """Should store metadata in file summary."""
        summary = FileSummary(
            path=Path("/tmp/test.py"),
            type="python",
            size=200,
            modified=datetime.now(),
            linecount=20,
            sha256="def456",
            metadata={"imports": 5, "classes": 2}
        )

        self.assertEqual(summary.metadata["imports"], 5)
        self.assertEqual(summary.metadata["classes"], 2)

    def test_file_summary_binary_flag(self):
        """Should mark binary files."""
        summary = FileSummary(
            path=Path("/tmp/test.bin"),
            type="unknown",
            size=1024,
            modified=datetime.now(),
            linecount=0,
            sha256="789abc",
            is_binary=True
        )

        self.assertTrue(summary.is_binary)

    def test_file_summary_parse_error(self):
        """Should store parse errors."""
        summary = FileSummary(
            path=Path("/tmp/bad.json"),
            type="json",
            size=50,
            modified=datetime.now(),
            linecount=5,
            sha256="error123",
            parse_error="Invalid JSON syntax"
        )

        self.assertIsNotNone(summary.parse_error)
        self.assertIn("Invalid JSON", summary.parse_error)


class TestCreateFileSummary(unittest.TestCase):
    """Test create_file_summary function."""

    def test_create_summary_for_text_file(self):
        """Should create summary for text files."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
            f.write("Line 1\nLine 2\nLine 3")
            temp_path = Path(f.name)

        try:
            summary = create_file_summary(temp_path)

            self.assertEqual(summary.path, temp_path)
            self.assertEqual(summary.type, "text")
            self.assertEqual(summary.linecount, 3)
            self.assertFalse(summary.is_binary)
            self.assertIsNone(summary.parse_error)
            self.assertNotEqual(summary.sha256, "ERROR")
        finally:
            temp_path.unlink()

    def test_create_summary_for_python_file(self):
        """Should detect Python file type."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.py') as f:
            f.write("def hello():\n    print('world')")
            temp_path = Path(f.name)

        try:
            summary = create_file_summary(temp_path)

            self.assertEqual(summary.type, "python")
            self.assertEqual(summary.linecount, 2)
        finally:
            temp_path.unlink()

    def test_create_summary_for_yaml_file(self):
        """Should detect YAML file type."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.yaml') as f:
            f.write("key: value\nlist:\n  - item1")
            temp_path = Path(f.name)

        try:
            summary = create_file_summary(temp_path)

            self.assertEqual(summary.type, "yaml")
            self.assertEqual(summary.linecount, 3)
        finally:
            temp_path.unlink()

    def test_create_summary_for_binary_file(self):
        """Should handle binary files with fallback encoding."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
            f.write(bytes(range(256)))
            temp_path = Path(f.name)

        try:
            summary = create_file_summary(temp_path)

            # With iso-8859-1 fallback, binary files are read successfully
            # They won't be marked as binary, but content may be garbled
            # This is expected behavior - the fallback allows reading anything
            self.assertFalse(summary.is_binary)
            self.assertIsNone(summary.parse_error)
            # Should have detected file type based on extension
            self.assertEqual(summary.type, "text")
        finally:
            temp_path.unlink()

    def test_create_summary_nonexistent_file(self):
        """Should raise FileNotFoundError for missing files."""
        temp_path = Path("/tmp/nonexistent_file_99999.txt")

        with self.assertRaises(FileNotFoundError):
            create_file_summary(temp_path)

    def test_create_summary_with_force_flag(self):
        """Should use force flag for large files."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
            # Write large content
            f.write('x\n' * 100000)
            temp_path = Path(f.name)

        try:
            summary = create_file_summary(temp_path, force=True)

            self.assertFalse(summary.is_binary)
            self.assertGreater(summary.linecount, 0)
        finally:
            temp_path.unlink()


if __name__ == '__main__':
    unittest.main()
