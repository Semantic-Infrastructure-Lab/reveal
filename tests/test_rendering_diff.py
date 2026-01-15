"""Tests for diff rendering functions."""

import unittest
import io
import sys
from contextlib import redirect_stdout

from reveal.rendering.diff import (
    render_diff,
    render_diff_text,
    render_diff_json,
    render_element_diff_text,
    _render_diff_header,
    _has_changes,
    _render_category_summary,
    _render_diff_summary,
)


def capture_stdout(func, *args, **kwargs):
    """Capture stdout from a function call."""
    f = io.StringIO()
    with redirect_stdout(f):
        func(*args, **kwargs)
    return f.getvalue()


class TestRenderDiff(unittest.TestCase):
    """Tests for main render_diff function."""

    def setUp(self):
        """Set up test data."""
        self.simple_diff = {
            'left': {'file': 'test.py', 'ref': 'HEAD~1'},
            'right': {'file': 'test.py', 'ref': 'HEAD'},
            'summary': {
                'functions': {'added': 1, 'removed': 0, 'modified': 0},
                'classes': {'added': 0, 'removed': 0, 'modified': 0},
                'imports': {'added': 0, 'removed': 0, 'modified': 0},
            },
            'diff': {
                'functions': [],
                'classes': [],
                'imports': [],
            }
        }

    def test_render_text_format(self):
        """Test rendering in text format."""
        output = capture_stdout(render_diff, self.simple_diff, format='text')
        self.assertIn('test.py', output)

    def test_render_json_format(self):
        """Test rendering in JSON format."""
        output = capture_stdout(render_diff, self.simple_diff, format='json')
        self.assertIn('{', output)  # Should be JSON
        self.assertIn('}', output)

    def test_render_element_diff(self):
        """Test rendering element-specific diff."""
        element_diff = {
            'left': {'name': 'func1', 'type': 'function'},
            'right': {'name': 'func1', 'type': 'function'},
            'changes': []
        }
        # Should not crash
        try:
            output = capture_stdout(render_diff, element_diff, format='text', is_element=True)
            # Output should contain something
            self.assertGreater(len(output), 0)
        except Exception as e:
            self.fail(f"render_diff raised {type(e).__name__} unexpectedly")


class TestRenderDiffText(unittest.TestCase):
    """Tests for render_diff_text function."""

    def test_render_with_minimal_structure(self):
        """Test rendering diff with minimal valid structure."""
        diff = {
            'left': {'file': 'old.py', 'ref': 'main'},
            'right': {'file': 'new.py', 'ref': 'feature'},
            'summary': {
                'functions': {'added': 0, 'removed': 0, 'modified': 0},
                'classes': {'added': 0, 'removed': 0, 'modified': 0},
                'imports': {'added': 0, 'removed': 0, 'modified': 0},
            },
            'diff': {
                'functions': [],
                'classes': [],
                'imports': [],
            }
        }

        output = capture_stdout(render_diff_text, diff)

        # Should show it's a diff
        self.assertIn('Diff', output)
        # Should indicate no changes
        self.assertIn('No', output)

    def test_render_handles_missing_fields(self):
        """Test rendering handles missing optional fields gracefully."""
        diff = {
            'left': {},
            'right': {},
            'summary': {},
            'diff': {}
        }

        # Should not crash
        try:
            capture_stdout(render_diff_text, diff)
        except Exception as e:
            self.fail(f"render_diff_text raised {type(e).__name__} unexpectedly")


class TestRenderDiffJson(unittest.TestCase):
    """Tests for render_diff_json function."""

    def test_valid_json_output(self):
        """Test that JSON output is valid."""
        diff = {
            'left': {'file': 'test.py'},
            'right': {'file': 'test.py'},
            'summary': {}
        }

        output = capture_stdout(render_diff_json, diff)

        # Should be valid JSON
        import json
        try:
            parsed = json.loads(output)
            self.assertIsInstance(parsed, dict)
        except json.JSONDecodeError:
            self.fail("Output is not valid JSON")

    def test_json_contains_diff_data(self):
        """Test that JSON output contains diff data."""
        diff = {
            'left': {'file': 'old.py', 'ref': 'main'},
            'right': {'file': 'new.py', 'ref': 'feature'},
            'summary': {'functions': {'added': 1}}
        }

        output = capture_stdout(render_diff_json, diff)

        import json
        parsed = json.loads(output)
        self.assertIn('left', parsed)
        self.assertIn('right', parsed)
        self.assertIn('summary', parsed)


class TestRenderElementDiffText(unittest.TestCase):
    """Tests for render_element_diff_text function."""

    def test_render_basic_element_diff(self):
        """Test rendering element diff with basic structure."""
        element_diff = {
            'left': {
                'name': 'calculate',
                'type': 'function',
            },
            'right': {
                'name': 'calculate',
                'type': 'function',
            },
            'changes': []
        }

        # Should not crash
        try:
            output = capture_stdout(render_element_diff_text, element_diff)
            # Should produce some output
            self.assertGreater(len(output), 0)
        except Exception as e:
            self.fail(f"render_element_diff_text raised {type(e).__name__} unexpectedly")


class TestHelperFunctions(unittest.TestCase):
    """Tests for helper functions."""

    def test_has_changes_true(self):
        """Test _has_changes returns True when there are changes."""
        data = {'added': 1, 'removed': 0, 'modified': 0}
        self.assertTrue(_has_changes(data))

        data = {'added': 0, 'removed': 1, 'modified': 0}
        self.assertTrue(_has_changes(data))

        data = {'added': 0, 'removed': 0, 'modified': 1}
        self.assertTrue(_has_changes(data))

    def test_has_changes_false(self):
        """Test _has_changes returns False when no changes."""
        data = {'added': 0, 'removed': 0, 'modified': 0}
        self.assertFalse(_has_changes(data))

    def test_render_diff_header(self):
        """Test _render_diff_header produces output."""
        left = {'file': 'old.py', 'ref': 'main'}
        right = {'file': 'new.py', 'ref': 'feature'}

        # Should not crash
        try:
            output = capture_stdout(_render_diff_header, left, right)
            # Should produce some output
            self.assertGreater(len(output), 0)
        except Exception as e:
            self.fail(f"_render_diff_header raised {type(e).__name__} unexpectedly")

    def test_render_category_summary_with_changes(self):
        """Test _render_category_summary when there are changes."""
        data = {'added': 2, 'removed': 1, 'modified': 1}

        output = capture_stdout(_render_category_summary, 'Functions', data)

        self.assertIn('Functions', output)
        self.assertIn('2', output)  # Added count
        self.assertIn('1', output)  # Removed/modified count

    def test_render_category_summary_no_changes(self):
        """Test _render_category_summary when there are no changes."""
        data = {'added': 0, 'removed': 0, 'modified': 0}

        output = capture_stdout(_render_category_summary, 'Functions', data)

        # Should return empty or very short output
        self.assertTrue(len(output.strip()) == 0 or 'no changes' in output.lower())

    def test_render_diff_summary_has_changes(self):
        """Test _render_diff_summary when there are changes."""
        summary = {
            'functions': {'added': 1, 'removed': 0, 'modified': 0},
            'classes': {'added': 0, 'removed': 0, 'modified': 0},
            'imports': {'added': 0, 'removed': 0, 'modified': 0},
        }

        output = capture_stdout(_render_diff_summary, summary)

        # Should show some summary
        self.assertGreater(len(output.strip()), 0)

    def test_render_diff_summary_no_changes(self):
        """Test _render_diff_summary when there are no changes."""
        summary = {
            'functions': {'added': 0, 'removed': 0, 'modified': 0},
            'classes': {'added': 0, 'removed': 0, 'modified': 0},
            'imports': {'added': 0, 'removed': 0, 'modified': 0},
        }

        # Should not crash
        try:
            output = capture_stdout(_render_diff_summary, summary)
            # Should produce output (even if just "no changes")
            self.assertIsInstance(output, str)
        except Exception as e:
            self.fail(f"_render_diff_summary raised {type(e).__name__} unexpectedly")


if __name__ == '__main__':
    unittest.main()
