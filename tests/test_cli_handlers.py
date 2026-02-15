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
    handle_list_supported,
    handle_adapters,
    handle_explain_file,
    handle_capabilities,
    handle_show_ast,
    handle_language_info,
    handle_agent_help,
    handle_agent_help_full,
    handle_schema,
    _get_schema_v1,
    _aggregate_batch_stats,
    _group_results_by_scheme,
    _filter_batch_display_results,
    _determine_batch_overall_status,
    _get_status_indicator,
    _calculate_batch_exit_code,
    _process_stdin_file,
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


class TestHandleListSupported(unittest.TestCase):
    """Tests for handle_list_supported function."""

    @patch('sys.exit')
    def test_handle_list_supported_calls_function_and_exits(self, mock_exit):
        """Test handle_list_supported calls the provided function and exits."""
        mock_func = MagicMock()
        handle_list_supported(mock_func)

        mock_func.assert_called_once()
        mock_exit.assert_called_once_with(0)


class TestHandleAdapters(unittest.TestCase):
    """Tests for handle_adapters function."""

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_adapters_shows_registry(self, mock_stdout, mock_exit):
        """Test --adapters shows registered adapters."""
        handle_adapters()

        output = mock_stdout.getvalue()
        # Should show header and some adapters
        self.assertIn('URI Adapters', output)
        self.assertIn('Registered Adapters', output)
        mock_exit.assert_called_once_with(0)

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_adapters_shows_examples(self, mock_stdout, mock_exit):
        """Test --adapters shows usage examples."""
        handle_adapters()

        output = mock_stdout.getvalue()
        # Should show usage section
        self.assertIn('Usage:', output)
        self.assertIn('help://adapters', output)
        mock_exit.assert_called_once_with(0)


class TestHandleExplainFile(unittest.TestCase):
    """Tests for handle_explain_file function."""

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('reveal.cli.introspection.explain_file')
    def test_handle_explain_file_basic(self, mock_explain, mock_stdout, mock_exit):
        """Test --explain-file with basic usage."""
        mock_explain.return_value = "File explanation"
        handle_explain_file('test.py')

        mock_explain.assert_called_once_with('test.py', verbose=False)
        output = mock_stdout.getvalue()
        self.assertIn('File explanation', output)
        mock_exit.assert_called_once_with(0)

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('reveal.cli.introspection.explain_file')
    def test_handle_explain_file_verbose(self, mock_explain, mock_stdout, mock_exit):
        """Test --explain-file with verbose flag."""
        mock_explain.return_value = "Detailed explanation"
        handle_explain_file('test.py', verbose=True)

        mock_explain.assert_called_once_with('test.py', verbose=True)
        output = mock_stdout.getvalue()
        self.assertIn('Detailed explanation', output)
        mock_exit.assert_called_once_with(0)


class TestHandleCapabilities(unittest.TestCase):
    """Tests for handle_capabilities function."""

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('reveal.cli.introspection.get_capabilities')
    def test_handle_capabilities_json_output(self, mock_caps, mock_stdout, mock_exit):
        """Test --capabilities outputs JSON."""
        mock_caps.return_value = {'analyzer': 'python', 'capabilities': ['functions']}
        handle_capabilities('test.py')

        mock_caps.assert_called_once_with('test.py')
        output = mock_stdout.getvalue()
        # Should be valid JSON
        import json
        data = json.loads(output)
        self.assertEqual(data['analyzer'], 'python')
        self.assertIn('capabilities', data)
        mock_exit.assert_called_once_with(0)


class TestHandleShowAst(unittest.TestCase):
    """Tests for handle_show_ast function."""

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('reveal.cli.introspection.show_ast')
    def test_handle_show_ast_default_depth(self, mock_show_ast, mock_stdout, mock_exit):
        """Test --show-ast with default depth."""
        mock_show_ast.return_value = "AST tree"
        handle_show_ast('test.py')

        mock_show_ast.assert_called_once_with('test.py', max_depth=10)
        output = mock_stdout.getvalue()
        self.assertIn('AST tree', output)
        mock_exit.assert_called_once_with(0)

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('reveal.cli.introspection.show_ast')
    def test_handle_show_ast_custom_depth(self, mock_show_ast, mock_stdout, mock_exit):
        """Test --show-ast with custom depth."""
        mock_show_ast.return_value = "AST tree (depth 5)"
        handle_show_ast('test.py', max_depth=5)

        mock_show_ast.assert_called_once_with('test.py', max_depth=5)
        output = mock_stdout.getvalue()
        self.assertIn('AST tree', output)
        mock_exit.assert_called_once_with(0)


class TestHandleLanguageInfo(unittest.TestCase):
    """Tests for handle_language_info function."""

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('reveal.cli.introspection.get_language_info_detailed')
    def test_handle_language_info(self, mock_info, mock_stdout, mock_exit):
        """Test --language-info shows language details."""
        mock_info.return_value = "Python language info"
        handle_language_info('python')

        mock_info.assert_called_once_with('python')
        output = mock_stdout.getvalue()
        self.assertIn('Python language info', output)
        mock_exit.assert_called_once_with(0)


class TestHandleAgentHelp(unittest.TestCase):
    """Tests for handle_agent_help and handle_agent_help_full functions."""

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="Agent help content")
    def test_handle_agent_help_success(self, mock_open, mock_stdout, mock_exit):
        """Test --agent-help reads and displays AGENT_HELP.md."""
        handle_agent_help()

        output = mock_stdout.getvalue()
        self.assertIn('Agent help content', output)
        mock_exit.assert_called_once_with(0)

    @patch('sys.stderr', new_callable=StringIO)
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_handle_agent_help_missing_file(self, mock_open, mock_stderr):
        """Test --agent-help handles missing AGENT_HELP.md."""
        with self.assertRaises(SystemExit) as cm:
            handle_agent_help()

        error = mock_stderr.getvalue()
        self.assertIn('AGENT_HELP.md not found', error)
        self.assertIn('bug', error.lower())
        self.assertEqual(cm.exception.code, 1)

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="Full agent help")
    def test_handle_agent_help_full_success(self, mock_open, mock_stdout, mock_exit):
        """Test --agent-help-full reads and displays AGENT_HELP_FULL.md."""
        handle_agent_help_full()

        output = mock_stdout.getvalue()
        self.assertIn('Full agent help', output)
        mock_exit.assert_called_once_with(0)

    @patch('sys.stderr', new_callable=StringIO)
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_handle_agent_help_full_missing_file(self, mock_open, mock_stderr):
        """Test --agent-help-full handles missing AGENT_HELP_FULL.md."""
        with self.assertRaises(SystemExit) as cm:
            handle_agent_help_full()

        error = mock_stderr.getvalue()
        self.assertIn('AGENT_HELP_FULL.md not found', error)
        self.assertIn('bug', error.lower())
        self.assertEqual(cm.exception.code, 1)


class TestHandleSchema(unittest.TestCase):
    """Tests for handle_schema function."""

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_schema_default_version(self, mock_stdout, mock_exit):
        """Test --schema with default version (1.0)."""
        handle_schema()

        output = mock_stdout.getvalue()
        self.assertIn('Output Contract v1.0', output)
        self.assertIn('contract_version', output)
        self.assertIn('source_type', output)
        mock_exit.assert_called_once_with(0)

    @patch('sys.exit')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_schema_explicit_v1(self, mock_stdout, mock_exit):
        """Test --schema with explicit v1.0."""
        handle_schema(version='1.0')

        output = mock_stdout.getvalue()
        self.assertIn('Output Contract v1.0', output)
        mock_exit.assert_called_once_with(0)

    @patch('sys.stderr', new_callable=StringIO)
    def test_handle_schema_unknown_version(self, mock_stderr):
        """Test --schema with unknown version."""
        with self.assertRaises(SystemExit) as cm:
            handle_schema(version='2.0')

        error = mock_stderr.getvalue()
        self.assertIn("Unknown contract version '2.0'", error)
        self.assertIn('Available versions: 1.0', error)
        self.assertEqual(cm.exception.code, 1)


class TestGetSchemaV1(unittest.TestCase):
    """Tests for _get_schema_v1 internal function."""

    def test_get_schema_v1_content(self):
        """Test _get_schema_v1 returns v1.0 schema content."""
        schema = _get_schema_v1()

        # Should contain key sections
        self.assertIn('Output Contract v1.0', schema)
        self.assertIn('Required Fields:', schema)
        self.assertIn('contract_version', schema)
        self.assertIn('type:', schema)
        self.assertIn('source:', schema)
        self.assertIn('source_type:', schema)

    def test_get_schema_v1_source_types(self):
        """Test _get_schema_v1 documents valid source_type values."""
        schema = _get_schema_v1()

        # Should list all valid source types
        self.assertIn('file', schema)
        self.assertIn('directory', schema)
        self.assertIn('database', schema)
        self.assertIn('runtime', schema)
        self.assertIn('network', schema)

    def test_get_schema_v1_type_rules(self):
        """Test _get_schema_v1 documents type field rules."""
        schema = _get_schema_v1()

        # Should explain snake_case requirement
        self.assertIn('snake_case', schema)
        self.assertIn('Pattern:', schema)


class TestBatchHelpers(unittest.TestCase):
    """Tests for batch processing helper functions."""

    def test_aggregate_batch_stats_all_success(self):
        """Test _aggregate_batch_stats with all successful results."""
        results = [
            {'status': 'success', 'uri': 'test1'},
            {'status': 'pass', 'uri': 'test2'},
        ]
        stats = _aggregate_batch_stats(results)

        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['successful'], 2)
        self.assertEqual(stats['warnings'], 0)
        self.assertEqual(stats['failures'], 0)

    def test_aggregate_batch_stats_mixed(self):
        """Test _aggregate_batch_stats with mixed results."""
        results = [
            {'status': 'success', 'uri': 'test1'},
            {'status': 'warning', 'uri': 'test2'},
            {'status': 'failure', 'uri': 'test3'},
            {'status': 'error', 'uri': 'test4'},
        ]
        stats = _aggregate_batch_stats(results)

        self.assertEqual(stats['total'], 4)
        self.assertEqual(stats['successful'], 1)
        self.assertEqual(stats['warnings'], 1)
        self.assertEqual(stats['failures'], 2)  # failure + error

    def test_aggregate_batch_stats_empty(self):
        """Test _aggregate_batch_stats with empty results."""
        stats = _aggregate_batch_stats([])

        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['successful'], 0)
        self.assertEqual(stats['warnings'], 0)
        self.assertEqual(stats['failures'], 0)

    def test_group_results_by_scheme(self):
        """Test _group_results_by_scheme groups by scheme."""
        results = [
            {'scheme': 'ssl', 'host': 'example.com'},
            {'scheme': 'mysql', 'database': 'test'},
            {'scheme': 'ssl', 'host': 'test.com'},
        ]
        by_scheme = _group_results_by_scheme(results)

        self.assertEqual(len(by_scheme), 2)
        self.assertEqual(len(by_scheme['ssl']), 2)
        self.assertEqual(len(by_scheme['mysql']), 1)

    def test_group_results_by_scheme_unknown(self):
        """Test _group_results_by_scheme handles missing scheme."""
        results = [
            {'status': 'success'},  # No scheme
        ]
        by_scheme = _group_results_by_scheme(results)

        self.assertIn('unknown', by_scheme)
        self.assertEqual(len(by_scheme['unknown']), 1)

    def test_filter_batch_display_results_no_filter(self):
        """Test _filter_batch_display_results without filtering."""
        results = [
            {'status': 'success'},
            {'status': 'warning'},
            {'status': 'failure'},
        ]
        filtered = _filter_batch_display_results(results, only_failures=False)

        self.assertEqual(len(filtered), 3)

    def test_filter_batch_display_results_only_failures(self):
        """Test _filter_batch_display_results filters to failures."""
        results = [
            {'status': 'success'},
            {'status': 'warning'},
            {'status': 'failure'},
            {'status': 'error'},
        ]
        filtered = _filter_batch_display_results(results, only_failures=True)

        self.assertEqual(len(filtered), 3)  # warning, failure, error
        self.assertEqual(filtered[0]['status'], 'warning')
        self.assertEqual(filtered[1]['status'], 'failure')
        self.assertEqual(filtered[2]['status'], 'error')

    def test_determine_batch_overall_status_pass(self):
        """Test _determine_batch_overall_status returns pass."""
        status = _determine_batch_overall_status(failures=0, warnings=0)
        self.assertEqual(status, 'pass')

    def test_determine_batch_overall_status_warning(self):
        """Test _determine_batch_overall_status returns warning."""
        status = _determine_batch_overall_status(failures=0, warnings=2)
        self.assertEqual(status, 'warning')

    def test_determine_batch_overall_status_failure(self):
        """Test _determine_batch_overall_status returns failure."""
        status = _determine_batch_overall_status(failures=1, warnings=0)
        self.assertEqual(status, 'failure')

    def test_determine_batch_overall_status_failure_with_warnings(self):
        """Test _determine_batch_overall_status returns failure with warnings."""
        status = _determine_batch_overall_status(failures=1, warnings=2)
        self.assertEqual(status, 'failure')  # failures take precedence

    def test_get_status_indicator_success(self):
        """Test _get_status_indicator for success."""
        self.assertEqual(_get_status_indicator('success'), '✓')
        self.assertEqual(_get_status_indicator('pass'), '✓')

    def test_get_status_indicator_warning(self):
        """Test _get_status_indicator for warning."""
        self.assertEqual(_get_status_indicator('warning'), '⚠')

    def test_get_status_indicator_failure(self):
        """Test _get_status_indicator for failure."""
        self.assertEqual(_get_status_indicator('failure'), '✗')
        self.assertEqual(_get_status_indicator('error'), '✗')
        self.assertEqual(_get_status_indicator('unknown'), '✗')

    def test_calculate_batch_exit_code_success(self):
        """Test _calculate_batch_exit_code for success."""
        exit_code = _calculate_batch_exit_code(failures=0, warnings=0)
        self.assertEqual(exit_code, 0)

    def test_calculate_batch_exit_code_warning_only(self):
        """Test _calculate_batch_exit_code for warnings only (returns 0)."""
        exit_code = _calculate_batch_exit_code(failures=0, warnings=2)
        self.assertEqual(exit_code, 0)  # Warnings alone don't cause non-zero exit

    def test_calculate_batch_exit_code_failure_no_warnings(self):
        """Test _calculate_batch_exit_code for failures without warnings."""
        exit_code = _calculate_batch_exit_code(failures=1, warnings=0)
        self.assertEqual(exit_code, 2)

    def test_calculate_batch_exit_code_failure_with_warnings(self):
        """Test _calculate_batch_exit_code for failures with warnings."""
        exit_code = _calculate_batch_exit_code(failures=1, warnings=2)
        self.assertEqual(exit_code, 1)  # 1 when both failures and warnings


class TestStdinProcessing(unittest.TestCase):
    """Tests for stdin processing functions."""

    @patch('sys.stderr', new_callable=StringIO)
    @patch('pathlib.Path.exists', return_value=False)
    def test_process_stdin_file_not_found(self, mock_exists, mock_stderr):
        """Test _process_stdin_file handles non-existent files."""
        args = MagicMock()
        handle_file_func = MagicMock()

        _process_stdin_file('nonexistent.py', args, handle_file_func)

        # Should print warning and not call handler
        error = mock_stderr.getvalue()
        self.assertIn('not found', error)
        self.assertIn('nonexistent.py', error)
        handle_file_func.assert_not_called()

    @patch('sys.stderr', new_callable=StringIO)
    @patch('pathlib.Path.is_dir', return_value=True)
    @patch('pathlib.Path.exists', return_value=True)
    def test_process_stdin_file_is_directory(self, mock_exists, mock_is_dir, mock_stderr):
        """Test _process_stdin_file skips directories."""
        args = MagicMock()
        handle_file_func = MagicMock()

        _process_stdin_file('somedir', args, handle_file_func)

        # Should print warning and not call handler
        error = mock_stderr.getvalue()
        self.assertIn('directory', error)
        self.assertIn('somedir', error)
        handle_file_func.assert_not_called()

    @patch('pathlib.Path.is_file', return_value=True)
    @patch('pathlib.Path.is_dir', return_value=False)
    @patch('pathlib.Path.exists', return_value=True)
    def test_process_stdin_file_success(self, mock_exists, mock_is_dir, mock_is_file):
        """Test _process_stdin_file processes valid file."""
        args = MagicMock()
        args.meta = True
        args.format = 'json'
        handle_file_func = MagicMock()

        _process_stdin_file('test.py', args, handle_file_func)

        # Should call handler with correct args
        handle_file_func.assert_called_once()
        call_args = handle_file_func.call_args
        self.assertEqual(call_args[0][0], 'test.py')
        self.assertIsNone(call_args[0][1])  # element
        self.assertTrue(call_args[0][2])    # meta
        self.assertEqual(call_args[0][3], 'json')  # format


if __name__ == '__main__':
    unittest.main()
