"""
Tests for reveal/cli/scheme_handlers/mysql.py

Tests the MySQL scheme handler functionality including:
- Connection string building from URI
- ImportError handling for missing pymysql dependency
- Health check mode (--check flag) with exit codes
- Element retrieval (connections, performance, etc.)
- Structure retrieval (server overview)
- Rendering in text and JSON formats
- Error handling for missing elements
"""

import unittest
import sys
from io import StringIO
from argparse import Namespace
from unittest.mock import Mock, patch

from reveal.cli.scheme_handlers.mysql import (
    handle_mysql,
    _render_mysql_result,
    _render_mysql_check_result
)


class TestRenderMySQLResult(unittest.TestCase):
    """Test _render_mysql_result() with server overview data."""

    def setUp(self):
        """Set up test fixtures."""
        self.server_result = {
            'type': 'mysql_server',
            'server': 'localhost:3306',
            'version': '8.0.28',
            'uptime': '3 days, 4 hours',
            'connection_health': {
                'status': 'healthy',
                'current': 50,
                'max': 151,
                'percentage': '33%'
            },
            'performance': {
                'qps': 250,
                'slow_queries': 12,
                'threads_running': 5
            },
            'innodb_health': {
                'status': 'healthy',
                'buffer_pool_hit_rate': '99.5%',
                'row_lock_waits': 10,
                'deadlocks': 0
            },
            'replication': {
                'role': 'master',
                'slaves': 2
            },
            'storage': {
                'total_size_gb': 125.5,
                'database_count': 15,
                'largest_db': 'production_db (45.2 GB)'
            },
            'health_status': 'HEALTHY',
            'health_issues': [],
            'next_steps': [
                'reveal mysql://localhost/connections',
                'reveal mysql://localhost/performance'
            ]
        }

    def test_render_server_overview_text(self):
        """Test rendering server overview in text format."""
        output = StringIO()
        sys.stdout = output
        try:
            _render_mysql_result(self.server_result, format='text')
            result = output.getvalue()

            # Check key sections are present
            self.assertIn('MySQL Server:', result)
            self.assertIn('localhost:3306', result)
            self.assertIn('8.0.28', result)
            self.assertIn('Connection Health: healthy', result)
            self.assertIn('50 / 151 max', result)
            self.assertIn('Performance:', result)
            self.assertIn('QPS: 250', result)
            self.assertIn('InnoDB Health: healthy', result)
            self.assertIn('Buffer Pool Hit Rate: 99.5%', result)
            self.assertIn('Replication: master', result)
            self.assertIn('Slaves: 2', result)
            self.assertIn('Storage:', result)
            self.assertIn('125.50 GB', result)
            self.assertIn('15 databases', result)
            self.assertIn('Health Status: HEALTHY', result)
            self.assertIn('Next Steps:', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_server_overview_json(self):
        """Test rendering server overview in JSON format."""
        output = StringIO()
        sys.stdout = output
        try:
            _render_mysql_result(self.server_result, format='json')
            result = output.getvalue()

            # Should be valid JSON
            self.assertIn('"type": "mysql_server"', result)
            self.assertIn('"server": "localhost:3306"', result)
            self.assertIn('"version"', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_with_replication_lag(self):
        """Test rendering server with replication lag."""
        self.server_result['replication'] = {
            'role': 'slave',
            'lag': 2.5
        }

        output = StringIO()
        sys.stdout = output
        try:
            _render_mysql_result(self.server_result, format='text')
            result = output.getvalue()

            self.assertIn('Replication: slave', result)
            self.assertIn('Lag: 2.5s', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_with_health_issues(self):
        """Test rendering server with health issues."""
        self.server_result['health_status'] = 'DEGRADED'
        self.server_result['health_issues'] = [
            'High connection usage (80%)',
            'Slow query rate increasing'
        ]

        output = StringIO()
        sys.stdout = output
        try:
            _render_mysql_result(self.server_result, format='text')
            result = output.getvalue()

            self.assertIn('Health Status: DEGRADED', result)
            self.assertIn('Issues:', result)
            self.assertIn('High connection usage', result)
            self.assertIn('Slow query rate', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_unknown_type_as_json(self):
        """Test that unknown result types fall back to JSON."""
        unknown_result = {
            'type': 'mysql_table',
            'table_name': 'users',
            'rows': 10000
        }

        output = StringIO()
        sys.stdout = output
        try:
            _render_mysql_result(unknown_result, format='text')
            result = output.getvalue()

            # Should fall back to JSON rendering
            self.assertIn('"type": "mysql_table"', result)
            self.assertIn('"table_name"', result)
        finally:
            sys.stdout = sys.__stdout__


class TestRenderMySQLCheckResult(unittest.TestCase):
    """Test _render_mysql_check_result() with health check data."""

    def setUp(self):
        """Set up test fixtures."""
        self.pass_result = {
            'status': 'pass',
            'exit_code': 0,
            'summary': {
                'total': 8,
                'passed': 8,
                'warnings': 0,
                'failures': 0
            },
            'checks': [
                {
                    'name': 'Connection Usage',
                    'status': 'pass',
                    'value': '33%',
                    'threshold': '<80%',
                    'severity': 'critical'
                },
                {
                    'name': 'Buffer Pool Hit Rate',
                    'status': 'pass',
                    'value': '99.5%',
                    'threshold': '>95%',
                    'severity': 'warning'
                }
            ]
        }

    def test_render_check_all_passing(self):
        """Test rendering check results when all checks pass."""
        output = StringIO()
        sys.stdout = output
        try:
            _render_mysql_check_result(self.pass_result)
            result = output.getvalue()

            self.assertIn('✅', result)
            self.assertIn('PASS', result)
            self.assertIn('8/8 passed', result)
            self.assertIn('0 warnings', result)
            self.assertIn('0 failures', result)
            self.assertIn('All Checks Passed:', result)
            self.assertIn('Connection Usage', result)
            self.assertIn('Exit code: 0', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_check_with_warnings(self):
        """Test rendering check results with warnings."""
        warning_result = {
            'status': 'warning',
            'exit_code': 1,
            'summary': {
                'total': 5,
                'passed': 3,
                'warnings': 2,
                'failures': 0
            },
            'checks': [
                {
                    'name': 'Slow Queries',
                    'status': 'warning',
                    'value': '150',
                    'threshold': '<100',
                    'severity': 'warning'
                },
                {
                    'name': 'Connection Usage',
                    'status': 'pass',
                    'value': '50%',
                    'threshold': '<80%',
                    'severity': 'critical'
                }
            ]
        }

        output = StringIO()
        sys.stdout = output
        try:
            _render_mysql_check_result(warning_result)
            result = output.getvalue()

            self.assertIn('⚠️', result)
            self.assertIn('WARNING', result)
            self.assertIn('3/5 passed', result)
            self.assertIn('2 warnings', result)
            self.assertIn('Slow Queries', result)
            self.assertIn('Exit code: 1', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_check_with_failures(self):
        """Test rendering check results with failures."""
        failure_result = {
            'status': 'failure',
            'exit_code': 2,
            'summary': {
                'total': 5,
                'passed': 2,
                'warnings': 1,
                'failures': 2
            },
            'checks': [
                {
                    'name': 'Connection Usage',
                    'status': 'failure',
                    'value': '95%',
                    'threshold': '<80%',
                    'severity': 'critical'
                },
                {
                    'name': 'Deadlocks',
                    'status': 'failure',
                    'value': '50',
                    'threshold': '<10',
                    'severity': 'critical'
                },
                {
                    'name': 'Slow Queries',
                    'status': 'warning',
                    'value': '150',
                    'threshold': '<100',
                    'severity': 'warning'
                }
            ]
        }

        output = StringIO()
        sys.stdout = output
        try:
            _render_mysql_check_result(failure_result)
            result = output.getvalue()

            self.assertIn('❌', result)
            self.assertIn('FAILURE', result)
            self.assertIn('2/5 passed', result)
            self.assertIn('2 failures', result)
            self.assertIn('Failures:', result)
            self.assertIn('Connection Usage', result)
            self.assertIn('Deadlocks', result)
            self.assertIn('Warnings:', result)
            self.assertIn('Exit code: 2', result)
        finally:
            sys.stdout = sys.__stdout__


class TestHandleMySQLImportError(unittest.TestCase):
    """Test handle_mysql() ImportError handling."""

    def test_import_error_shows_install_instructions(self):
        """Test that ImportError shows clear install instructions."""
        # Mock adapter class that raises ImportError
        mock_adapter_class = Mock()
        mock_adapter_class.side_effect = ImportError("No module named 'pymysql'")

        # Create args
        args = Namespace(format='text', check=False)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            # Call handler and expect sys.exit
            with self.assertRaises(SystemExit) as cm:
                handle_mysql(mock_adapter_class, 'localhost/testdb', None, args)

            # Verify exit code
            self.assertEqual(cm.exception.code, 1)

            # Verify error message
            stderr_output = output.getvalue()
            self.assertIn('Error: mysql:// adapter requires pymysql', stderr_output)
            self.assertIn('pip install reveal-cli[database]', stderr_output)
            self.assertIn('pip install pymysql', stderr_output)
        finally:
            sys.stderr = sys.__stderr__


class TestHandleMySQLCheck(unittest.TestCase):
    """Test handle_mysql() with --check flag."""

    def test_check_mode_calls_adapter_check(self):
        """Test that --check flag calls adapter.check()."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        check_result = {
            'status': 'pass',
            'exit_code': 0,
            'summary': {'total': 5, 'passed': 5, 'warnings': 0, 'failures': 0},
            'checks': []
        }
        mock_adapter.check.return_value = check_result
        mock_adapter_class.return_value = mock_adapter

        # Create args with check=True
        args = Namespace(format='text', check=True)

        # Capture output
        output = StringIO()
        sys.stdout = output
        try:
            # Call handler and expect sys.exit
            with self.assertRaises(SystemExit) as cm:
                handle_mysql(mock_adapter_class, 'localhost/testdb', None, args)

            # Verify exit code from check result
            self.assertEqual(cm.exception.code, 0)

            # Verify check was called
            mock_adapter.check.assert_called_once()
        finally:
            sys.stdout = sys.__stdout__

    def test_check_mode_json_format(self):
        """Test --check with JSON format."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        check_result = {
            'status': 'pass',
            'exit_code': 0,
            'summary': {'total': 5, 'passed': 5, 'warnings': 0, 'failures': 0},
            'checks': []
        }
        mock_adapter.check.return_value = check_result
        mock_adapter_class.return_value = mock_adapter

        # Create args with check=True and json format
        args = Namespace(format='json', check=True)

        # Capture output
        output = StringIO()
        sys.stdout = output
        try:
            # Call handler and expect sys.exit
            with self.assertRaises(SystemExit) as cm:
                handle_mysql(mock_adapter_class, 'localhost/testdb', None, args)

            # Verify JSON output
            result = output.getvalue()
            self.assertIn('"status": "pass"', result)
            self.assertIn('"exit_code": 0', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_check_mode_exits_with_failure_code(self):
        """Test that --check exits with failure code when checks fail."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        check_result = {
            'status': 'failure',
            'exit_code': 2,
            'summary': {'total': 5, 'passed': 2, 'warnings': 1, 'failures': 2},
            'checks': []
        }
        mock_adapter.check.return_value = check_result
        mock_adapter_class.return_value = mock_adapter

        # Create args with check=True
        args = Namespace(format='text', check=True)

        # Call handler and expect sys.exit with code 2
        with self.assertRaises(SystemExit) as cm:
            handle_mysql(mock_adapter_class, 'localhost/testdb', None, args)

        self.assertEqual(cm.exception.code, 2)


class TestHandleMySQLStructure(unittest.TestCase):
    """Test handle_mysql() structure retrieval."""

    @patch('reveal.cli.scheme_handlers.mysql._render_mysql_result')
    def test_get_structure_without_element(self, mock_render):
        """Test getting server structure without element."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.element = None
        structure_result = {'type': 'mysql_server', 'server': 'localhost:3306'}
        mock_adapter.get_structure.return_value = structure_result
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Call handler
        handle_mysql(mock_adapter_class, 'localhost/testdb', None, args)

        # Verify
        mock_adapter.get_structure.assert_called_once()
        mock_render.assert_called_once_with(structure_result, 'text')

    def test_get_structure_json_format(self):
        """Test getting structure with JSON format."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.element = None
        structure_result = {'type': 'mysql_server', 'server': 'localhost:3306'}
        mock_adapter.get_structure.return_value = structure_result
        mock_adapter_class.return_value = mock_adapter

        # Create args with JSON format
        args = Namespace(format='json', check=False)

        # Capture output
        output = StringIO()
        sys.stdout = output
        try:
            # Call handler
            handle_mysql(mock_adapter_class, 'localhost/testdb', None, args)

            # Verify JSON output
            result = output.getvalue()
            self.assertIn('"type": "mysql_server"', result)
            self.assertIn('"server": "localhost:3306"', result)
        finally:
            sys.stdout = sys.__stdout__


class TestHandleMySQLElement(unittest.TestCase):
    """Test handle_mysql() element retrieval."""

    @patch('reveal.cli.scheme_handlers.mysql._render_mysql_result')
    def test_get_element_when_specified(self, mock_render):
        """Test getting specific element when adapter has element."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.element = 'connections'
        element_result = {'type': 'mysql_connections', 'current': 50}
        mock_adapter.get_element.return_value = element_result
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Call handler
        handle_mysql(mock_adapter_class, 'localhost/testdb', 'connections', args)

        # Verify
        mock_adapter.get_element.assert_called_once_with('connections')
        mock_render.assert_called_once_with(element_result, 'text')

    def test_element_not_found_shows_available_elements(self):
        """Test that missing element shows list of available elements."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.element = 'invalid_element'
        mock_adapter.get_element.return_value = None  # Element not found
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            # Call handler and expect sys.exit
            with self.assertRaises(SystemExit) as cm:
                handle_mysql(mock_adapter_class, 'localhost/testdb', 'invalid_element', args)

            # Verify exit code
            self.assertEqual(cm.exception.code, 1)

            # Verify error message includes available elements
            stderr_output = output.getvalue()
            self.assertIn('Error:', stderr_output)
            self.assertIn('invalid_element', stderr_output)
            self.assertIn('not found', stderr_output)
            self.assertIn('Available elements:', stderr_output)
            self.assertIn('connections', stderr_output)
            self.assertIn('performance', stderr_output)
        finally:
            sys.stderr = sys.__stderr__


if __name__ == '__main__':
    unittest.main()
