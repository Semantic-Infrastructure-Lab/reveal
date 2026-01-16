"""Tests for CLI handler functions.

These tests prevent bugs like the TypeError crash in `reveal --rules`
when rule metadata serialization encounters unexpected types.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
from io import StringIO

from reveal.cli.handlers import (
    handle_rules_list,
    handle_explain_rule,
    handle_languages,
    handle_list_schemas,
)
from reveal.rules import RuleRegistry


class TestHandleRulesList(unittest.TestCase):
    """Tests for handle_rules_list function."""

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_rules_list_doesnt_crash(self, mock_stdout, mock_exit):
        """Test --rules command doesn't crash with TypeError."""
        # This is the bug we're preventing: TypeError when file_patterns is None
        handle_rules_list(version="0.36.1")

        output = mock_stdout.getvalue()
        # Should print rule codes
        self.assertIn('B001', output)
        self.assertIn('I001', output)
        self.assertIn('Total:', output)
        mock_exit.assert_called_once_with(0)

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_rules_list_shows_categories(self, mock_stdout, mock_exit):
        """Test --rules shows rule categories."""
        handle_rules_list(version="0.36.1")

        output = mock_stdout.getvalue()
        # Should show category headers
        self.assertIn('B Rules', output)  # Bugs
        self.assertIn('I Rules', output)  # Imports
        self.assertIn('S Rules', output)  # Security
        mock_exit.assert_called_once_with(0)

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_rules_list_shows_file_patterns(self, mock_stdout, mock_exit):
        """Test --rules shows file patterns for non-universal rules."""
        handle_rules_list(version="0.36.1")

        output = mock_stdout.getvalue()
        # Rules with specific file patterns should show them
        # (e.g., V001 only applies to YAML files)
        # The exact rules may vary, but format should be present
        self.assertIn('Files:', output)
        mock_exit.assert_called_once_with(0)

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_rules_list_shows_severity(self, mock_stdout, mock_exit):
        """Test --rules shows severity icons."""
        handle_rules_list(version="0.36.1")

        output = mock_stdout.getvalue()
        # Should have severity icons
        self.assertTrue(
            any(icon in output for icon in ['❌', '⚠️', 'ℹ️', '🚨']),
            "Should show at least one severity icon"
        )
        mock_exit.assert_called_once_with(0)


class TestHandleExplainRule(unittest.TestCase):
    """Tests for handle_explain_rule function."""

    def test_explain_existing_rule(self):
        """Test explaining an existing rule."""
        # Use sys.exit exception to stop execution naturally
        with self.assertRaises(SystemExit) as cm:
            handle_explain_rule("B001")

        self.assertEqual(cm.exception.code, 0)

    def test_explain_nonexistent_rule(self):
        """Test explaining a non-existent rule."""
        # Should exit with code 1 for non-existent rule
        with self.assertRaises(SystemExit) as cm:
            handle_explain_rule("X999")

        self.assertEqual(cm.exception.code, 1)


class TestHandleLanguages(unittest.TestCase):
    """Tests for handle_languages function."""

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    def test_list_languages_doesnt_crash(self, mock_stdout, mock_exit):
        """Test --languages command works."""
        handle_languages()

        output = mock_stdout.getvalue()
        # Should list supported languages
        self.assertIn('python', output.lower())
        mock_exit.assert_called_once_with(0)


class TestHandleListSchemas(unittest.TestCase):
    """Tests for handle_list_schemas function."""

    def test_list_schemas_doesnt_crash(self):
        """Test --list-schemas command works."""
        with self.assertRaises(SystemExit) as cm:
            handle_list_schemas()

        self.assertEqual(cm.exception.code, 0)


class TestRuleMetadataIntegrity(unittest.TestCase):
    """Tests for rule metadata serialization.

    These tests ensure _rule_to_dict() handles all edge cases:
    - None values
    - Empty lists
    - String patterns
    - List patterns
    """

    def test_list_rules_returns_valid_metadata(self):
        """Test list_rules() returns valid metadata for all rules."""
        rules = RuleRegistry.list_rules()

        self.assertGreater(len(rules), 0, "Should have at least one rule")

        for rule in rules:
            # Every rule must have these keys
            self.assertIn('code', rule)
            self.assertIn('message', rule)
            self.assertIn('category', rule)
            self.assertIn('severity', rule)
            self.assertIn('file_patterns', rule)
            self.assertIn('enabled', rule)

            # Code should be non-empty string
            self.assertIsInstance(rule['code'], str)
            self.assertGreater(len(rule['code']), 0)

            # Message should be a string (may be empty - that's a separate bug)
            self.assertIsInstance(rule['message'], str)

    def test_file_patterns_are_always_iterable(self):
        """Test file_patterns are never None (prevents TypeError in join()).

        This is the specific bug we're preventing: file_patterns = None
        caused TypeError when handlers.py tried ', '.join(patterns).
        """
        rules = RuleRegistry.list_rules()

        for rule in rules:
            patterns = rule.get('file_patterns')

            # file_patterns should never be None
            self.assertIsNotNone(
                patterns,
                f"Rule {rule['code']} has file_patterns=None"
            )

            # Should be iterable (list or tuple)
            self.assertTrue(
                hasattr(patterns, '__iter__') and not isinstance(patterns, str),
                f"Rule {rule['code']} file_patterns={patterns!r} is not iterable (or is string)"
            )

            # If not universal, should be able to join without error
            if patterns and patterns != ['*']:
                try:
                    # This is what handlers.py does - it should not crash
                    if isinstance(patterns, str):
                        patterns = [patterns]
                    result = ', '.join(patterns)
                    self.assertIsInstance(result, str)
                except TypeError as e:
                    self.fail(
                        f"Rule {rule['code']} file_patterns={patterns!r} "
                        f"cannot be joined: {e}"
                    )

    def test_dynamic_rules_have_valid_patterns(self):
        """Test I001/I002 (dynamic file_patterns) are properly initialized.

        These rules populate file_patterns dynamically in __init__.
        Without proper initialization, file_patterns would be None or [].
        """
        rules = RuleRegistry.list_rules()

        # Find I001 and I002
        i001 = next((r for r in rules if r['code'] == 'I001'), None)
        i002 = next((r for r in rules if r['code'] == 'I002'), None)

        self.assertIsNotNone(i001, "I001 should be registered")
        self.assertIsNotNone(i002, "I002 should be registered")

        # Both should have non-empty file patterns
        self.assertIsInstance(i001['file_patterns'], list)
        self.assertIsInstance(i002['file_patterns'], list)

        # After initialization, they should have multiple extensions
        # (at least .py, .js, .go, .rs)
        self.assertGreater(
            len(i001['file_patterns']), 0,
            "I001 should have file patterns after initialization"
        )
        self.assertGreater(
            len(i002['file_patterns']), 0,
            "I002 should have file patterns after initialization"
        )


if __name__ == '__main__':
    unittest.main()
