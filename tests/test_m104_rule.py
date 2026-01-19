"""Tests for M104 rule: Hardcoded configuration detection."""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.rules.maintainability.M104 import M104


class TestM104PathDetection(unittest.TestCase):
    """Test M104 path detection logic for skipping test files."""

    def create_temp_file(self, path: str, content: str) -> str:
        """Helper: Create temp file at specific path with given content.

        Args:
            path: Relative or absolute path for the file
            content: File content

        Returns:
            Absolute path to created file
        """
        # Create parent directories
        abs_path = os.path.abspath(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        # Write content
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return abs_path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file and empty parent directories."""
        if os.path.exists(path):
            os.unlink(path)
            # Clean up empty parent directories
            parent = os.path.dirname(path)
            while parent and parent != '/' and parent != os.path.dirname(tempfile.gettempdir()):
                try:
                    if not os.listdir(parent):
                        os.rmdir(parent)
                    parent = os.path.dirname(parent)
                except (OSError, PermissionError):
                    break

    def test_path_detection_cases(self):
        """Test all path detection cases from bug fix verification table.

        Tests the fix for M104 path detection that was using substring matching
        instead of directory-specific checks.
        """
        # Content with large dict that should trigger M104 (10 items, threshold is 5)
        large_dict_content = """
config = {
    'key1': 'value1',
    'key2': 'value2',
    'key3': 'value3',
    'key4': 'value4',
    'key5': 'value5',
    'key6': 'value6',
    'key7': 'value7',
    'key8': 'value8',
    'key9': 'value9',
    'key10': 'value10',
}
"""

        test_cases = [
            # (path, should_skip, description)
            ('/tmp/my_config.py', False, 'No test pattern'),
            ('/tmp/tests/test_utils.py', True, 'In /tests/ directory'),
            ('/tmp/test/myfile.py', True, 'In /test/ directory'),
            ('/tmp/src/myfile_test.py', True, '_test.py suffix'),
            ('/tmp/src/test.py', True, '/test.py suffix'),
            ('test_something.py', True, 'test_ prefix'),
            ('test_config.py', True, 'test_ prefix (test file)'),
            ('/tmp/contest/file.py', False, 'Contains "test" substring in directory but not test file'),
            ('/tmp/latest/file.py', False, 'Contains "test" substring in directory but not test file'),
            ('/tmp/protest/config.py', False, 'Contains "test" substring in directory but not test file'),
        ]

        rule = M104()

        for path, should_skip, description in test_cases:
            # Create temp file
            abs_path = self.create_temp_file(path, large_dict_content)

            try:
                # Run M104 check
                detections = rule.check(abs_path, None, large_dict_content)

                if should_skip:
                    # Should skip: no detections expected
                    self.assertEqual(
                        len(detections), 0,
                        f"FAILED: {description}\n"
                        f"  Path: {abs_path}\n"
                        f"  Expected: SKIP (no detections)\n"
                        f"  Got: {len(detections)} detection(s)"
                    )
                else:
                    # Should not skip: detection expected
                    self.assertEqual(
                        len(detections), 1,
                        f"FAILED: {description}\n"
                        f"  Path: {abs_path}\n"
                        f"  Expected: DON'T SKIP (1 detection)\n"
                        f"  Got: {len(detections)} detection(s)"
                    )
                    # Verify it's the M104 rule
                    self.assertEqual(detections[0].rule_code, 'M104')

            finally:
                # Clean up
                self.teardown_file(abs_path)


class TestM104DetectionLogic(unittest.TestCase):
    """Test M104 detection logic for hardcoded configuration."""

    def create_temp_file(self, content: str, suffix: str = ".py") -> str:
        """Helper: Create temp file with given content."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, f"config{suffix}")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        if os.path.exists(path):
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_large_dict_detected(self):
        """Test that large dicts (≥5 pairs) are detected."""
        content = """
config = {
    'key1': 'value1',
    'key2': 'value2',
    'key3': 'value3',
    'key4': 'value4',
    'key5': 'value5',
    'key6': 'value6',
}
"""
        path = self.create_temp_file(content)
        try:
            rule = M104()
            detections = rule.check(path, None, content)
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'M104')
            self.assertIn('6 key-value pairs', detections[0].message)
        finally:
            self.teardown_file(path)

    def test_small_dict_ok(self):
        """Test that small dicts (<5 pairs) are not flagged."""
        content = """
config = {
    'key1': 'value1',
    'key2': 'value2',
    'key3': 'value3',
}
"""
        path = self.create_temp_file(content)
        try:
            rule = M104()
            detections = rule.check(path, None, content)
            self.assertEqual(len(detections), 0)
        finally:
            self.teardown_file(path)

    def test_large_string_list_detected(self):
        """Test that large lists (≥10 items, mostly strings) are detected."""
        content = """
urls = [
    'https://example1.com',
    'https://example2.com',
    'https://example3.com',
    'https://example4.com',
    'https://example5.com',
    'https://example6.com',
    'https://example7.com',
    'https://example8.com',
    'https://example9.com',
    'https://example10.com',
    'https://example11.com',
]
"""
        path = self.create_temp_file(content)
        try:
            rule = M104()
            detections = rule.check(path, None, content)
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].rule_code, 'M104')
            self.assertIn('11 items', detections[0].message)
        finally:
            self.teardown_file(path)

    def test_small_list_ok(self):
        """Test that small lists (<10 items) are not flagged."""
        content = """
urls = [
    'https://example1.com',
    'https://example2.com',
    'https://example3.com',
]
"""
        path = self.create_temp_file(content)
        try:
            rule = M104()
            detections = rule.check(path, None, content)
            self.assertEqual(len(detections), 0)
        finally:
            self.teardown_file(path)

    def test_large_number_list_not_config(self):
        """Test that large lists with numbers (not config-like) are not flagged."""
        content = """
# List of numbers - not configuration
primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
"""
        path = self.create_temp_file(content)
        try:
            rule = M104()
            detections = rule.check(path, None, content)
            # Should not detect (not >70% strings)
            self.assertEqual(len(detections), 0)
        finally:
            self.teardown_file(path)

    def test_dict_threshold_edge_case(self):
        """Test dict detection at exact threshold (5 items)."""
        # Exactly 5 items (should trigger, threshold is ≥5)
        content_at_threshold = """
config = {
    'key1': 'value1',
    'key2': 'value2',
    'key3': 'value3',
    'key4': 'value4',
    'key5': 'value5',
}
"""
        path = self.create_temp_file(content_at_threshold)
        try:
            rule = M104()
            detections = rule.check(path, None, content_at_threshold)
            self.assertEqual(len(detections), 1, "Exactly 5 items should trigger detection")
        finally:
            self.teardown_file(path)

        # Just below threshold (4 items, should not trigger)
        content_below_threshold = """
config = {
    'key1': 'value1',
    'key2': 'value2',
    'key3': 'value3',
    'key4': 'value4',
}
"""
        path = self.create_temp_file(content_below_threshold)
        try:
            rule = M104()
            detections = rule.check(path, None, content_below_threshold)
            self.assertEqual(len(detections), 0, "4 items should not trigger detection")
        finally:
            self.teardown_file(path)

    def test_list_threshold_edge_case(self):
        """Test list detection at exact threshold (10 items)."""
        # Exactly 10 string items (should trigger, threshold is ≥10)
        content_at_threshold = """
items = [
    'item1', 'item2', 'item3', 'item4', 'item5',
    'item6', 'item7', 'item8', 'item9', 'item10',
]
"""
        path = self.create_temp_file(content_at_threshold)
        try:
            rule = M104()
            detections = rule.check(path, None, content_at_threshold)
            self.assertEqual(len(detections), 1, "Exactly 10 string items should trigger detection")
        finally:
            self.teardown_file(path)

        # Just below threshold (9 items, should not trigger)
        content_below_threshold = """
items = [
    'item1', 'item2', 'item3', 'item4', 'item5',
    'item6', 'item7', 'item8', 'item9',
]
"""
        path = self.create_temp_file(content_below_threshold)
        try:
            rule = M104()
            detections = rule.check(path, None, content_below_threshold)
            self.assertEqual(len(detections), 0, "9 items should not trigger detection")
        finally:
            self.teardown_file(path)

    def test_mixed_string_list_threshold(self):
        """Test that lists need >70% strings to be considered config.

        M104 checks if >70% of list items are strings before flagging.
        """
        # 10 items, but only 6 strings (60%) - should not trigger
        content_below_string_threshold = """
mixed = [
    'string1', 'string2', 'string3', 'string4', 'string5', 'string6',
    1, 2, 3, 4,  # 4 numbers
]
"""
        path = self.create_temp_file(content_below_string_threshold)
        try:
            rule = M104()
            detections = rule.check(path, None, content_below_string_threshold)
            self.assertEqual(len(detections), 0, "60% strings should not trigger (need >70%)")
        finally:
            self.teardown_file(path)

        # 10 items, 8 strings (80%) - should trigger
        content_above_string_threshold = """
mostly_strings = [
    'string1', 'string2', 'string3', 'string4', 'string5',
    'string6', 'string7', 'string8',
    1, 2,  # Only 2 numbers
]
"""
        path = self.create_temp_file(content_above_string_threshold)
        try:
            rule = M104()
            detections = rule.check(path, None, content_above_string_threshold)
            self.assertEqual(len(detections), 1, "80% strings should trigger (>70%)")
        finally:
            self.teardown_file(path)

    def test_non_python_file_skipped(self):
        """Test that non-Python files are skipped."""
        content = """
{
  "key1": "value1",
  "key2": "value2",
  "key3": "value3",
  "key4": "value4",
  "key5": "value5"
}
"""
        path = self.create_temp_file(content, suffix=".json")
        try:
            rule = M104()
            detections = rule.check(path, None, content)
            # Should skip non-Python files
            self.assertEqual(len(detections), 0)
        finally:
            self.teardown_file(path)

    def test_syntax_error_handled(self):
        """Test that syntax errors are handled gracefully."""
        content = """
# Invalid Python syntax
config = {
    'key1': 'value1',
    'key2': 'value2'
    # Missing closing brace
"""
        path = self.create_temp_file(content)
        try:
            rule = M104()
            # Should not crash on syntax error
            detections = rule.check(path, None, content)
            # Returns empty list when can't parse
            self.assertEqual(len(detections), 0)
        finally:
            self.teardown_file(path)

    def test_multiple_detections_in_one_file(self):
        """Test that multiple config violations are detected in a single file."""
        content = """
# Large dict
config_dict = {
    'key1': 'value1',
    'key2': 'value2',
    'key3': 'value3',
    'key4': 'value4',
    'key5': 'value5',
}

# Large list
urls = [
    'url1', 'url2', 'url3', 'url4', 'url5',
    'url6', 'url7', 'url8', 'url9', 'url10',
]
"""
        path = self.create_temp_file(content)
        try:
            rule = M104()
            detections = rule.check(path, None, content)
            # Should detect both: large dict + large list
            self.assertEqual(len(detections), 2)
            self.assertTrue(all(d.rule_code == 'M104' for d in detections))
        finally:
            self.teardown_file(path)


if __name__ == '__main__':
    unittest.main()
