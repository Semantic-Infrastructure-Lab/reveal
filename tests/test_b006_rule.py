"""Tests for B006: Silent broad exception handler detector."""

import unittest
import tempfile
import os
from reveal.rules.bugs.B006 import B006
from reveal.rules.base import Severity


class TestB006SilentBroadException(unittest.TestCase):
    """Test B006: Silent broad exception handler detector."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.rule = B006()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, name: str = "test.py") -> str:
        """Helper: Create temp file with given content."""
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    # ==================== Tests for detection ====================

    def test_detect_silent_exception_pass(self):
        """Test detection of except Exception: pass with no comment."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')
        self.assertEqual(detections[0].severity, Severity.MEDIUM)
        self.assertIn('specific exception types', detections[0].suggestion)

    def test_detect_silent_exception_as_e_pass(self):
        """Test detection of except Exception as e: pass with no comment."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception as e:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')

    def test_detect_base_exception_pass(self):
        """Test detection of except BaseException: pass."""
        content = """
def foo():
    try:
        risky_operation()
    except BaseException:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')

    def test_detect_tuple_with_exception(self):
        """Test detection when Exception is in tuple of exceptions."""
        content = """
def foo():
    try:
        risky_operation()
    except (ValueError, Exception):
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')

    def test_multiple_silent_exceptions(self):
        """Test detection of multiple silent exception handlers in same file."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        pass

def bar():
    try:
        another_risky()
    except Exception:
        pass

class Baz:
    def method(self):
        try:
            risky()
        except Exception:
            pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 3)

    # ==================== Tests for allowed patterns (no detection) ====================

    def test_allow_specific_exception(self):
        """Test that specific exceptions with pass are allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except ValueError:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_multiple_specific_exceptions(self):
        """Test that tuple of specific exceptions is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except (ValueError, KeyError, TypeError):
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_bare_except(self):
        """Test that bare except is not flagged (handled by B001)."""
        content = """
def foo():
    try:
        risky_operation()
    except:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # B006 should not flag bare except (that's B001's job)
        self.assertEqual(len(detections), 0)

    def test_allow_exception_with_logging(self):
        """Test that exception with logging is allowed (not just pass)."""
        content = """
import logging
logger = logging.getLogger(__name__)

def foo():
    try:
        risky_operation()
    except Exception as e:
        logger.debug(f"Ignoring error: {e}")
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_exception_with_other_action(self):
        """Test that exception with other actions besides pass is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        return None
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_exception_with_inline_comment(self):
        """Test that exception with inline comment on except line is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:  # Intentional: best-effort operation
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_exception_with_comment_on_pass(self):
        """Test that exception with comment on pass line is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        pass  # Intentional: cleanup operation, errors don't matter
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_exception_with_comment_between_except_and_pass(self):
        """Test that exception with comment between except and pass is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        # If operation fails, return empty
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_exception_with_multiline_body(self):
        """Test that exception with multiple statements is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        pass
        pass  # Two pass statements (weird but not our concern)
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Not just a single pass, so shouldn't flag
        self.assertEqual(len(detections), 0)

    # ==================== Tests for edge cases ====================

    def test_nested_try_except(self):
        """Test detection in nested try-except blocks."""
        content = """
def foo():
    try:
        try:
            inner_risky()
        except Exception:
            pass
    except ValueError:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should only flag the inner Exception handler
        self.assertEqual(len(detections), 1)

    def test_syntax_error_handling(self):
        """Test that syntax errors are handled gracefully."""
        content = """
def foo()  # Missing colon
    try:
        risky()
    except Exception:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should return empty list on syntax error, not crash
        self.assertEqual(len(detections), 0)

    def test_empty_file(self):
        """Test that empty file doesn't cause errors."""
        content = ""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_rule_metadata(self):
        """Test that rule has correct metadata."""
        self.assertEqual(self.rule.code, 'B006')
        self.assertEqual(self.rule.severity, Severity.MEDIUM)
        self.assertIn('.py', self.rule.file_patterns)
        self.assertIn('Broad exception', self.rule.message)

    def test_detection_message_helpful(self):
        """Test that detection message includes helpful suggestions."""
        content = """
def foo():
    try:
        risky()
    except Exception:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        suggestion = detections[0].suggestion
        # Check for key suggestions
        self.assertIn('specific exception types', suggestion)
        self.assertIn('logging', suggestion)
        self.assertIn('comment', suggestion)
        self.assertIn('Re-raise', suggestion)

    # ==================== Real-world patterns ====================

    def test_real_world_file_reading_pattern(self):
        """Test common pattern in file reading with silent failure."""
        content = """
def read_config(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        pass
    return None
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should flag this - better to catch FileNotFoundError, IOError
        self.assertEqual(len(detections), 1)

    def test_real_world_import_pattern_with_comment(self):
        """Test common pattern in optional imports with comment."""
        content = """
try:
    import optional_dependency
except Exception:
    optional_dependency = None  # Not just pass, has assignment
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should not flag - has action beyond pass
        self.assertEqual(len(detections), 0)

    def test_real_world_cleanup_pattern_commented(self):
        """Test cleanup pattern with explanatory comment."""
        content = """
def cleanup():
    try:
        os.remove(temp_file)
    except Exception:
        pass  # Best effort cleanup, errors don't matter
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should not flag - has explanatory comment
        self.assertEqual(len(detections), 0)


if __name__ == '__main__':
    unittest.main()
