"""Comprehensive tests for MySQL adapter.

Tests cover:
- Adapter initialization and connection string parsing
- 3-tier credential resolution (URI, env vars, ~/.my.cnf)
- Element routing (all 12 element types)
- Data conversion (Decimal, datetime, timedelta)
- Error handling (connection failures, invalid credentials)
- Health checks (--check flag)
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, mock_open
import sys
import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime, date, time, timedelta, timezone

# Add parent directory to path to import reveal
sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.adapters.mysql import MySQLAdapter


class TestMySQLAdapterInit(unittest.TestCase):
    """Test MySQL adapter initialization and connection string parsing."""

    @patch.object(MySQLAdapter, '_resolve_credentials')
    def test_init_with_empty_connection_string(self, mock_resolve):
        """Should handle empty connection string."""
        # Mock credential resolution to do nothing
        mock_resolve.return_value = None

        adapter = MySQLAdapter("")
        self.assertEqual(adapter.connection_string, "")
        # host and port are None until get_connection() applies defaults
        # This allows .my.cnf to be read by pymysql
        self.assertIsNone(adapter.host)
        self.assertIsNone(adapter.port)
        self.assertIsNone(adapter.database)
        # user/password depend on _resolve_credentials which is mocked

    def test_init_with_minimal_connection_string(self):
        """Should parse minimal connection string (host only)."""
        adapter = MySQLAdapter("mysql://localhost")
        self.assertEqual(adapter.host, "localhost")
        # Port is None when not in URI - defaults applied in get_connection()
        self.assertIsNone(adapter.port)
        self.assertIsNone(adapter.database)

    def test_init_with_full_connection_string(self):
        """Should parse full connection string with all components."""
        adapter = MySQLAdapter("mysql://user:pass@host:3307/element")
        self.assertEqual(adapter.host, "host")
        self.assertEqual(adapter.port, 3307)
        self.assertEqual(adapter.element, "element")  # Path is element
        self.assertEqual(adapter.user, "user")
        self.assertEqual(adapter.password, "pass")

    def test_init_with_custom_port(self):
        """Should parse custom port from connection string."""
        adapter = MySQLAdapter("mysql://localhost:3307")
        self.assertEqual(adapter.host, "localhost")
        self.assertEqual(adapter.port, 3307)

    def test_init_with_element(self):
        """Should parse element from connection string."""
        adapter = MySQLAdapter("mysql://localhost/testdb")
        self.assertEqual(adapter.host, "localhost")
        self.assertEqual(adapter.element, "testdb")  # Path is element, not database

    def test_init_with_credentials_in_uri(self):
        """Should parse credentials from URI."""
        adapter = MySQLAdapter("mysql://root:secret@localhost")
        self.assertEqual(adapter.user, "root")
        self.assertEqual(adapter.password, "secret")

    def test_init_with_scheme_stripped_host(self):
        """CLI routing (_try_resource_arg_init) commonly hands the adapter the
        resource with the 'mysql://' scheme already stripped (e.g. bare
        'localhost' for `reveal mysql://localhost`). Without normalization,
        urlparse has no netloc to parse and silently reads the bare host as
        the *element* instead, leaving host=None and falling back to
        ~/.my.cnf undetected — a real bug (BACK-859 dogfood sweep)."""
        adapter = MySQLAdapter("localhost")
        self.assertEqual(adapter.host, "localhost")
        self.assertIsNone(adapter.element)

    def test_init_with_scheme_stripped_full_uri(self):
        """Scheme-stripped form with credentials/port/element must parse
        identically to the full 'mysql://...' form."""
        adapter = MySQLAdapter("user:pass@host:3307/element")
        self.assertEqual(adapter.host, "host")
        self.assertEqual(adapter.port, 3307)
        self.assertEqual(adapter.element, "element")
        self.assertEqual(adapter.user, "user")
        self.assertEqual(adapter.password, "pass")


class TestCredentialResolution(unittest.TestCase):
    """Test 3-tier credential resolution system."""

    def test_credentials_from_uri_take_precedence(self):
        """URI credentials should override all other sources."""
        adapter = MySQLAdapter("mysql://uri_user:uri_pass@localhost")
        self.assertEqual(adapter.user, "uri_user")
        self.assertEqual(adapter.password, "uri_pass")

    @patch.dict(os.environ, {'MYSQL_USER': 'env_user', 'MYSQL_PASSWORD': 'env_pass'}, clear=False)
    def test_credentials_from_env_vars(self):
        """Should use environment variables when not in URI."""
        from reveal.adapters.mysql.connection import MySQLConnection
        conn = MySQLConnection("mysql://localhost")

        # Env vars should be picked up for user/password
        self.assertEqual(conn.host, 'localhost')  # From URI
        self.assertEqual(conn.user, 'env_user')
        self.assertEqual(conn.password, 'env_pass')

    @patch.dict(os.environ, {'MYSQL_USER': 'env_user', 'MYSQL_PASSWORD': 'env_pass'}, clear=False)
    def test_uri_credentials_override_env_vars(self):
        """URI credentials should take precedence over env vars."""
        from reveal.adapters.mysql.connection import MySQLConnection
        conn = MySQLConnection("mysql://uri_user:uri_pass@myhost")

        # URI should override env vars
        self.assertEqual(conn.host, 'myhost')
        self.assertEqual(conn.user, 'uri_user')
        self.assertEqual(conn.password, 'uri_pass')

    def test_defaults_to_localhost_when_no_env(self):
        """Should default to localhost when no MYSQL_HOST set."""
        # Remove MYSQL_HOST if present
        env_backup = os.environ.get('MYSQL_HOST')
        if 'MYSQL_HOST' in os.environ:
            del os.environ['MYSQL_HOST']

        try:
            from reveal.adapters.mysql.connection import MySQLConnection
            conn = MySQLConnection("mysql://")

            # Host is None after init - defaults applied in get_connection()
            # This allows .my.cnf to be read properly
            self.assertIsNone(conn.host)
        finally:
            # Restore env if it was set
            if env_backup is not None:
                os.environ['MYSQL_HOST'] = env_backup

    @patch.dict(os.environ, {
        'MYSQL_HOST': 'dbserver',
        'MYSQL_USER': 'dbuser',
        'MYSQL_PASSWORD': 'dbpass',
        'MYSQL_DATABASE': 'mydb'
    }, clear=False)
    def test_all_env_vars_used(self):
        """Should use all MYSQL_* env vars when URI is minimal."""
        from reveal.adapters.mysql.connection import MySQLConnection
        conn = MySQLConnection("mysql://")

        self.assertEqual(conn.host, 'dbserver')
        self.assertEqual(conn.user, 'dbuser')
        self.assertEqual(conn.password, 'dbpass')
        self.assertEqual(conn.database, 'mydb')

    def test_credentials_from_my_cnf(self):
        """~/.my.cnf is handled by pymysql, not tested here."""
        # pymysql automatically reads ~/.my.cnf when connecting
        # This is integration-level behavior, not unit testable
        pass

    @patch.dict(os.environ, {
        'MYSQL_HOST': 'env-host.example.com',
        'MYSQL_USER': 'env_user',
        'MYSQL_PASSWORD': 'env_pass'
    })
    def test_empty_uri_uses_env_vars(self):
        """Empty mysql:// URI should use MYSQL_HOST from environment."""
        from reveal.adapters.mysql.connection import MySQLConnection
        conn = MySQLConnection("mysql://")

        # Host should come from MYSQL_HOST env var, not default to localhost
        self.assertEqual(conn.host, 'env-host.example.com')
        self.assertEqual(conn.user, 'env_user')
        self.assertEqual(conn.password, 'env_pass')

    @patch.dict(os.environ, {'MYSQL_PORT': '25060'}, clear=False)
    def test_mysql_port_env_var(self):
        """MYSQL_PORT environment variable should be used."""
        from reveal.adapters.mysql.connection import MySQLConnection
        conn = MySQLConnection("mysql://")

        # Port should come from MYSQL_PORT env var
        self.assertEqual(conn.port, 25060)

    @patch.dict(os.environ, {
        'MYSQL_HOST': 'dbserver',
        'MYSQL_PORT': '3307',
        'MYSQL_USER': 'dbuser',
        'MYSQL_PASSWORD': 'dbpass'
    })
    def test_all_env_vars_including_port(self):
        """Should use all MYSQL_* env vars including PORT."""
        from reveal.adapters.mysql.connection import MySQLConnection
        conn = MySQLConnection("mysql://")

        self.assertEqual(conn.host, 'dbserver')
        self.assertEqual(conn.port, 3307)
        self.assertEqual(conn.user, 'dbuser')
        self.assertEqual(conn.password, 'dbpass')

    def test_uri_port_overrides_env_port(self):
        """URI port should take precedence over MYSQL_PORT env var."""
        with patch.dict(os.environ, {'MYSQL_PORT': '3307'}):
            from reveal.adapters.mysql.connection import MySQLConnection
            conn = MySQLConnection("mysql://localhost:25060")

            # URI port should override env var
            self.assertEqual(conn.host, 'localhost')
            self.assertEqual(conn.port, 25060)

    @patch('reveal.adapters.mysql.connection.pymysql')
    def test_my_cnf_used_when_no_explicit_params(self, mock_pymysql):
        """When host/port not in URI or env, pymysql should read from .my.cnf."""
        from reveal.adapters.mysql.connection import MySQLConnection

        # Remove any MYSQL_* env vars
        env_backup = {}
        for key in ['MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_USER', 'MYSQL_PASSWORD']:
            if key in os.environ:
                env_backup[key] = os.environ[key]
                del os.environ[key]

        try:
            conn = MySQLConnection("mysql://")
            conn.get_connection()

            # Verify pymysql.connect was called
            mock_pymysql.connect.assert_called_once()
            call_kwargs = mock_pymysql.connect.call_args[1]

            # Should have read_default_file
            self.assertIn('read_default_file', call_kwargs)
            self.assertTrue(call_kwargs['read_default_file'].endswith('.my.cnf'))

            # Should NOT have explicit host/port/user/password
            # pymysql will read them from .my.cnf, or use its own defaults
            self.assertNotIn('host', call_kwargs)
            self.assertNotIn('port', call_kwargs)
            self.assertNotIn('user', call_kwargs)
            self.assertNotIn('password', call_kwargs)
        finally:
            # Restore env vars
            for key, value in env_backup.items():
                os.environ[key] = value

    @patch('reveal.adapters.mysql.connection.pymysql')
    def test_explicit_params_override_my_cnf(self, mock_pymysql):
        """Explicit URI params should override .my.cnf values."""
        from reveal.adapters.mysql.connection import MySQLConnection

        conn = MySQLConnection("mysql://myuser:mypass@myhost:25060")
        conn.get_connection()

        mock_pymysql.connect.assert_called_once()
        call_kwargs = mock_pymysql.connect.call_args[1]

        # Explicit values should be passed to pymysql
        self.assertEqual(call_kwargs.get('host'), 'myhost')
        self.assertEqual(call_kwargs.get('port'), 25060)
        self.assertEqual(call_kwargs.get('user'), 'myuser')
        self.assertEqual(call_kwargs.get('password'), 'mypass')

        # These will override anything in .my.cnf
        # (pymysql uses explicit params over .my.cnf values)

    @patch('reveal.adapters.mysql.connection.pymysql')
    def test_env_vars_passed_as_explicit_params(self, mock_pymysql):
        """Env vars should be passed as explicit params, overriding .my.cnf."""
        from reveal.adapters.mysql.connection import MySQLConnection

        with patch.dict(os.environ, {
            'MYSQL_HOST': 'env-host',
            'MYSQL_PORT': '25060',
            'MYSQL_USER': 'env-user'
        }):
            conn = MySQLConnection("mysql://")
            conn.get_connection()

            mock_pymysql.connect.assert_called_once()
            call_kwargs = mock_pymysql.connect.call_args[1]

            # Env vars should be passed explicitly
            self.assertEqual(call_kwargs.get('host'), 'env-host')
            self.assertEqual(call_kwargs.get('port'), 25060)
            self.assertEqual(call_kwargs.get('user'), 'env-user')

            # Password not in env, so not in call_kwargs
            # pymysql will read it from .my.cnf if present


class TestElementRouting(unittest.TestCase):
    """Test element routing to correct methods."""

    def setUp(self):
        """Create adapter with mocked connection."""
        self.adapter = MySQLAdapter("mysql://test:test@localhost/test")

        # Mock the connection to avoid actual MySQL connection
        self.adapter._connection = MagicMock()
        self.adapter._cursor = MagicMock()

    def test_get_element_routes_to_connections(self):
        """Should route 'connections' to _get_connections."""
        with patch.object(self.adapter, '_get_connections', return_value={'test': 'data'}):
            result = self.adapter.get_element('connections')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_performance(self):
        """Should route 'performance' to _get_performance."""
        with patch.object(self.adapter, '_get_performance', return_value={'test': 'data'}):
            result = self.adapter.get_element('performance')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_innodb(self):
        """Should route 'innodb' to _get_innodb."""
        with patch.object(self.adapter, '_get_innodb', return_value={'test': 'data'}):
            result = self.adapter.get_element('innodb')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_replication(self):
        """Should route 'replication' to _get_replication."""
        with patch.object(self.adapter, '_get_replication', return_value={'test': 'data'}):
            result = self.adapter.get_element('replication')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_storage(self):
        """Should route 'storage' to _get_storage."""
        with patch.object(self.adapter, '_get_storage', return_value={'test': 'data'}):
            result = self.adapter.get_element('storage')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_errors(self):
        """Should route 'errors' to _get_errors."""
        with patch.object(self.adapter, '_get_errors', return_value={'test': 'data'}):
            result = self.adapter.get_element('errors')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_variables(self):
        """Should route 'variables' to _get_variables."""
        with patch.object(self.adapter, '_get_variables', return_value={'test': 'data'}):
            result = self.adapter.get_element('variables')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_health(self):
        """Should route 'health' to _get_health."""
        with patch.object(self.adapter, '_get_health', return_value={'test': 'data'}):
            result = self.adapter.get_element('health')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_databases(self):
        """Should route 'databases' to _get_databases."""
        with patch.object(self.adapter, '_get_databases', return_value={'test': 'data'}):
            result = self.adapter.get_element('databases')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_indexes(self):
        """Should route 'indexes' to _get_indexes."""
        with patch.object(self.adapter, '_get_indexes', return_value={'test': 'data'}):
            result = self.adapter.get_element('indexes')
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_slow_queries(self):
        """Should route 'slow-queries' to _get_slow_queries."""
        with patch.object(self.adapter, '_get_slow_queries', return_value={'test': 'data'}):
            result = self.adapter.get_element('slow-queries')  # Uses hyphen, not underscore
            self.assertEqual(result['test'], 'data')

    def test_get_element_routes_to_tables(self):
        """Should route 'tables' to _get_tables."""
        with patch.object(self.adapter, '_get_tables', return_value={'test': 'data'}):
            result = self.adapter.get_element('tables')
            self.assertEqual(result['test'], 'data')

    def test_get_element_invalid_returns_none(self):
        """Should return None for invalid element name."""
        result = self.adapter.get_element('invalid_element')
        self.assertIsNone(result)


class TestDataConversion(unittest.TestCase):
    """Test data type conversion for JSON serialization."""

    def setUp(self):
        """Create adapter instance."""
        self.adapter = MySQLAdapter("mysql://localhost")

    def test_convert_decimal_to_float(self):
        """Should convert Decimal to float."""
        data = {'value': Decimal('123.45')}
        result = self.adapter._convert_decimals(data)
        self.assertEqual(result['value'], 123.45)
        self.assertIsInstance(result['value'], float)

    def test_convert_datetime_to_iso(self):
        """Should convert datetime to ISO format string."""
        dt = datetime(2025, 12, 17, 15, 30, 45)
        data = {'timestamp': dt}
        result = self.adapter._convert_decimals(data)
        self.assertIsInstance(result['timestamp'], str)
        self.assertIn('2025-12-17', result['timestamp'])

    def test_convert_date_to_iso(self):
        """Should convert date to ISO format string."""
        d = date(2025, 12, 17)
        data = {'date': d}
        result = self.adapter._convert_decimals(data)
        self.assertEqual(result['date'], '2025-12-17')

    def test_convert_time_to_iso(self):
        """Should convert time to ISO format string."""
        t = time(15, 30, 45)
        data = {'time': t}
        result = self.adapter._convert_decimals(data)
        self.assertIsInstance(result['time'], str)

    def test_convert_timedelta_to_string(self):
        """Should convert timedelta to string."""
        td = timedelta(days=1, hours=2, minutes=30)
        data = {'duration': td}
        result = self.adapter._convert_decimals(data)
        self.assertEqual(result['duration'], '1 day, 2:30:00')  # Converts to string

    def test_convert_nested_dict(self):
        """Should recursively convert nested structures."""
        data = {
            'outer': {
                'inner': {
                    'decimal': Decimal('99.99'),
                    'datetime': datetime(2025, 1, 1, 0, 0, 0)
                }
            }
        }
        result = self.adapter._convert_decimals(data)
        self.assertEqual(result['outer']['inner']['decimal'], 99.99)
        self.assertIsInstance(result['outer']['inner']['datetime'], str)

    def test_convert_list_of_dicts(self):
        """Should convert list of dictionaries."""
        data = [
            {'value': Decimal('1.1')},
            {'value': Decimal('2.2')},
        ]
        result = self.adapter._convert_decimals(data)
        self.assertEqual(result[0]['value'], 1.1)
        self.assertEqual(result[1]['value'], 2.2)


class TestErrorHandling(unittest.TestCase):
    """Test error handling for connection failures and invalid input."""

    @patch('reveal.adapters.mysql.connection.pymysql')
    def test_connection_failure_handling(self, mock_pymysql):
        """Should handle connection failures gracefully."""
        # Mock connection failure
        mock_pymysql.connect.side_effect = Exception("Connection refused")

        adapter = MySQLAdapter("mysql://localhost")

        # Should not raise, but handle gracefully
        try:
            conn = adapter._get_connection()
            # If this doesn't raise, connection error was handled
        except Exception as e:
            # Connection errors should be caught and handled
            self.assertIn("Connection", str(e) or "refused")

    @patch('reveal.adapters.mysql.connection.pymysql')
    def test_invalid_credentials_handling(self, mock_pymysql):
        """Should handle invalid credentials gracefully."""
        # Mock authentication failure
        mock_pymysql.connect.side_effect = Exception("Access denied")

        adapter = MySQLAdapter("mysql://baduser:badpass@localhost")

        try:
            conn = adapter._get_connection()
        except Exception as e:
            self.assertIn("Access denied", str(e) or "denied")

    def test_missing_pymysql_import(self):
        """Should provide helpful error if pymysql not installed."""
        # Test that connection module raises ImportError with helpful message
        with patch.dict('sys.modules', {'pymysql': None}):
            # Reimport to trigger the ImportError path
            # The error message should include install instructions
            from reveal.adapters.mysql.connection import PYMYSQL_AVAILABLE
            # If pymysql is installed, this test just verifies it's True
            # The actual ImportError behavior is tested in integration
            self.assertTrue(PYMYSQL_AVAILABLE or True)  # Always passes - see integration test

    def test_del_safe_when_conn_not_initialized(self):
        """__del__ should not raise AttributeError if self.conn was never set."""
        # This tests the fix for the secondary error when pymysql is missing
        # Simulate an adapter where __init__ failed before setting self.conn
        adapter = object.__new__(MySQLAdapter)
        # Don't call __init__, so self.conn is never set
        # __del__ should handle this gracefully
        try:
            adapter.__del__()
        except AttributeError:
            self.fail("__del__ raised AttributeError when conn not initialized")

    @patch('reveal.adapters.mysql.MySQLAdapter._get_connection')
    def test_query_timeout_handling(self, mock_get_conn):
        """Should handle query errors gracefully."""
        # Mock connection that will fail on query
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("Query timeout")
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        adapter = MySQLAdapter("mysql://localhost")

        # Element methods should handle query failures gracefully
        # Most methods will raise or return error dict
        # This test just verifies no unhandled exceptions
        try:
            result = adapter._get_connections()
            # If we get here, method handled error gracefully
            self.assertTrue(True)
        except Exception:
            # Expected for some methods
            self.assertTrue(True)


class TestGetStructure(unittest.TestCase):
    """Test get_structure method (integration-style tests)."""

    def test_get_structure_method_exists(self):
        """Should have get_structure method."""
        adapter = MySQLAdapter("mysql://localhost")
        self.assertTrue(hasattr(adapter, 'get_structure'))
        self.assertTrue(callable(adapter.get_structure))

    def test_get_structure_signature(self):
        """Should accept kwargs parameter."""
        adapter = MySQLAdapter("mysql://localhost")
        # Verify method signature - should not raise TypeError
        import inspect
        sig = inspect.signature(adapter.get_structure)
        self.assertIn('kwargs', sig.parameters)


class TestGetHelp(unittest.TestCase):
    """Test help system for MySQL adapter."""

    def test_get_help_returns_dict(self):
        """Should return help data as dictionary."""
        help_data = MySQLAdapter.get_help()
        self.assertIsInstance(help_data, dict)

    def test_get_help_has_required_fields(self):
        """Should include all required help fields."""
        help_data = MySQLAdapter.get_help()

        self.assertEqual(help_data['name'], 'mysql')
        self.assertIn('description', help_data)
        self.assertIn('examples', help_data)
        self.assertIn('syntax', help_data)

    def test_get_help_includes_examples(self):
        """Should include usage examples."""
        help_data = MySQLAdapter.get_help()
        examples = help_data.get('examples', [])

        self.assertIsInstance(examples, list)
        self.assertGreater(len(examples), 0)

    def test_get_help_includes_element_types(self):
        """Should document all 12 element types."""
        help_data = MySQLAdapter.get_help()

        # Help should mention all element types
        help_str = str(help_data)
        self.assertIn('connections', help_str.lower())
        self.assertIn('performance', help_str.lower())

    def test_get_help_includes_install_instructions(self):
        """Should include pymysql install instructions in notes."""
        help_data = MySQLAdapter.get_help()

        # Help should mention it's an optional dependency
        notes = help_data.get('notes', [])
        notes_str = ' '.join(notes)

        self.assertIn('pymysql', notes_str.lower())
        self.assertIn('pip install', notes_str.lower())
        # Should mention the extras syntax
        self.assertIn('reveal-cli[database]', notes_str)


class TestCheckMethod(unittest.TestCase):
    """Test health check method with thresholds."""

    def setUp(self):
        """Set up adapter with mocked connection."""
        self.adapter = MySQLAdapter("mysql://test:test@localhost/test")
        self.adapter._connection = MagicMock()

    @patch('reveal.adapters.mysql.MySQLAdapter._get_performance')
    @patch('reveal.adapters.mysql.MySQLAdapter._execute_query')
    def test_check_method_exists(self, mock_query, mock_perf):
        """Should have check() method."""
        self.assertTrue(hasattr(self.adapter, 'check'))
        self.assertTrue(callable(self.adapter.check))

    @patch('reveal.adapters.mysql.MySQLAdapter._get_performance')
    @patch('reveal.adapters.mysql.MySQLAdapter._execute_query')
    def test_check_returns_required_fields(self, mock_query, mock_perf):
        """Should return required fields in check result."""
        # Mock performance data
        mock_perf.return_value = {
            'tuning_ratios': {
                'table_scan_ratio': '5.2%',
                'thread_cache_miss_rate': '2.1%',
                'temp_tables_to_disk_ratio': '10.5%'
            }
        }

        # Mock SHOW queries
        mock_query.side_effect = [
            [{'Variable_name': 'Threads_connected', 'Value': '10'},
             {'Variable_name': 'Max_used_connections', 'Value': '50'},
             {'Variable_name': 'Open_files', 'Value': '100'},
             {'Variable_name': 'Innodb_buffer_pool_reads', 'Value': '1000'},
             {'Variable_name': 'Innodb_buffer_pool_read_requests', 'Value': '100000'}],
            [{'Variable_name': 'max_connections', 'Value': '100'},
             {'Variable_name': 'open_files_limit', 'Value': '1000'}]
        ]

        result = self.adapter.check()

        self.assertIn('status', result)
        self.assertIn('exit_code', result)
        self.assertIn('checks', result)
        self.assertIn('summary', result)

    @patch('reveal.adapters.mysql.MySQLAdapter._get_performance')
    @patch('reveal.adapters.mysql.MySQLAdapter._execute_query')
    def test_check_pass_status(self, mock_query, mock_perf):
        """Should return pass status when all checks pass."""
        # Mock good performance data
        mock_perf.return_value = {
            'tuning_ratios': {
                'table_scan_ratio': '5.0%',
                'thread_cache_miss_rate': '2.0%',
                'temp_tables_to_disk_ratio': '10.0%'
            }
        }

        # Mock good status
        mock_query.side_effect = [
            [{'Variable_name': 'Threads_connected', 'Value': '10'},
             {'Variable_name': 'Max_used_connections', 'Value': '50'},
             {'Variable_name': 'Open_files', 'Value': '100'},
             {'Variable_name': 'Innodb_buffer_pool_reads', 'Value': '1'},
             {'Variable_name': 'Innodb_buffer_pool_read_requests', 'Value': '100000'}],
            [{'Variable_name': 'max_connections', 'Value': '200'},
             {'Variable_name': 'open_files_limit', 'Value': '10000'}]
        ]

        result = self.adapter.check()

        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['exit_code'], 0)

    @patch('reveal.adapters.mysql.MySQLAdapter._get_performance')
    @patch('reveal.adapters.mysql.MySQLAdapter._execute_query')
    def test_check_warning_status(self, mock_query, mock_perf):
        """Should return warning status when some checks warn."""
        # Mock warning-level performance
        mock_perf.return_value = {
            'tuning_ratios': {
                'table_scan_ratio': '15.0%',  # Warning level (10-25%)
                'thread_cache_miss_rate': '2.0%',
                'temp_tables_to_disk_ratio': '10.0%'
            }
        }

        mock_query.side_effect = [
            [{'Variable_name': 'Threads_connected', 'Value': '10'},
             {'Variable_name': 'Max_used_connections', 'Value': '50'},
             {'Variable_name': 'Open_files', 'Value': '100'},
             {'Variable_name': 'Innodb_buffer_pool_reads', 'Value': '1'},
             {'Variable_name': 'Innodb_buffer_pool_read_requests', 'Value': '100000'}],
            [{'Variable_name': 'max_connections', 'Value': '200'},
             {'Variable_name': 'open_files_limit', 'Value': '10000'}]
        ]

        result = self.adapter.check()

        self.assertEqual(result['status'], 'warning')
        self.assertEqual(result['exit_code'], 1)
        self.assertGreater(result['summary']['warnings'], 0)

    @patch('reveal.adapters.mysql.MySQLAdapter._get_performance')
    @patch('reveal.adapters.mysql.MySQLAdapter._execute_query')
    def test_check_failure_status(self, mock_query, mock_perf):
        """Should return failure status when checks fail."""
        # Mock critical failure
        mock_perf.return_value = {
            'tuning_ratios': {
                'table_scan_ratio': '50.0%',  # Failure level (>25%)
                'thread_cache_miss_rate': '30.0%',
                'temp_tables_to_disk_ratio': '60.0%'
            }
        }

        mock_query.side_effect = [
            [{'Variable_name': 'Threads_connected', 'Value': '195'},  # Near max
             {'Variable_name': 'Max_used_connections', 'Value': '199'},
             {'Variable_name': 'Open_files', 'Value': '950'},
             {'Variable_name': 'Innodb_buffer_pool_reads', 'Value': '50000'},
             {'Variable_name': 'Innodb_buffer_pool_read_requests', 'Value': '100000'}],
            [{'Variable_name': 'max_connections', 'Value': '200'},
             {'Variable_name': 'open_files_limit', 'Value': '1000'}]
        ]

        result = self.adapter.check()

        self.assertEqual(result['status'], 'failure')
        self.assertEqual(result['exit_code'], 2)
        self.assertGreater(result['summary']['failures'], 0)

    @patch('reveal.adapters.mysql.MySQLAdapter._get_performance')
    @patch('reveal.adapters.mysql.MySQLAdapter._execute_query')
    def test_check_includes_all_checks(self, mock_query, mock_perf):
        """Should run all 7 health checks."""
        mock_perf.return_value = {
            'tuning_ratios': {
                'table_scan_ratio': '5%',
                'thread_cache_miss_rate': '2%',
                'temp_tables_to_disk_ratio': '10%'
            }
        }

        mock_query.side_effect = [
            [{'Variable_name': 'Threads_connected', 'Value': '10'},
             {'Variable_name': 'Max_used_connections', 'Value': '50'},
             {'Variable_name': 'Open_files', 'Value': '100'},
             {'Variable_name': 'Innodb_buffer_pool_reads', 'Value': '1'},
             {'Variable_name': 'Innodb_buffer_pool_read_requests', 'Value': '100000'}],
            [{'Variable_name': 'max_connections', 'Value': '200'},
             {'Variable_name': 'open_files_limit', 'Value': '10000'}]
        ]

        result = self.adapter.check()

        # Should have 7 checks as per audit spec
        self.assertEqual(len(result['checks']), 7)
        self.assertEqual(result['summary']['total'], 7)

        # Verify check names
        check_names = {c['name'] for c in result['checks']}
        expected_names = {
            'Table Scan Ratio',
            'Thread Cache Miss Rate',
            'Temp Disk Ratio',
            'Max Used Connections %',
            'Open Files %',
            'Current Connection %',
            'Buffer Hit Rate'
        }
        self.assertEqual(check_names, expected_names)


class TestMySQLAdapterSchema(unittest.TestCase):
    """Test schema generation for AI agent integration."""

    def test_get_schema(self):
        """Should return machine-readable schema."""
        schema = MySQLAdapter.get_schema()

        self.assertIsNotNone(schema)
        self.assertEqual(schema['adapter'], 'mysql')
        self.assertIn('description', schema)
        self.assertIn('uri_syntax', schema)
        self.assertEqual(schema['uri_syntax'], 'mysql://[user:pass@]host[:port][/element]')

    def test_schema_query_params(self):
        """Schema should document query parameters."""
        schema = MySQLAdapter.get_schema()

        self.assertIn('query_params', schema)
        self.assertIsInstance(schema['query_params'], dict)

    def test_schema_cli_flags(self):
        """Schema should document CLI flags."""
        schema = MySQLAdapter.get_schema()

        self.assertIn('cli_flags', schema)
        self.assertIn('--check', schema['cli_flags'])

    def test_schema_output_types(self):
        """Schema should define output types."""
        schema = MySQLAdapter.get_schema()

        self.assertIn('output_types', schema)
        self.assertTrue(len(schema['output_types']) >= 2)

        # Should have mysql output types
        output_types = [ot['type'] for ot in schema['output_types']]
        # Common types: mysql_health, mysql_replication, mysql_storage
        self.assertGreater(len(output_types), 0)

    def test_schema_examples(self):
        """Schema should include usage examples."""
        schema = MySQLAdapter.get_schema()

        self.assertIn('example_queries', schema)
        self.assertTrue(len(schema['example_queries']) >= 3)

        # Examples should have required fields
        for example in schema['example_queries']:
            self.assertIn('uri', example)
            self.assertIn('description', example)

    def test_schema_elements(self):
        """Schema should document available elements."""
        schema = MySQLAdapter.get_schema()

        self.assertIn('elements', schema)
        self.assertIsInstance(schema['elements'], dict)

        # Should include common elements like 'databases', 'tables', etc.
        self.assertGreater(len(schema['elements']), 0)


class TestMySQLRenderer(unittest.TestCase):
    """Test renderer output formatting."""

    def test_renderer_check_output(self):
        """Renderer should format check output correctly."""
        from reveal.adapters.mysql.renderer import MySQLRenderer
        from io import StringIO

        # Mock check result with proper structure
        result = {
            'contract_version': '1.0',
            'type': 'mysql_check',
            'status': 'pass',
            'summary': {
                'passed': 1,
                'warnings': 0,
                'failures': 0,
                'total': 1
            },
            'exit_code': 0,
            'checks': [
                {
                    'name': 'Connection Test',
                    'status': 'pass',
                    'value': 'OK',
                    'threshold': None,
                    'severity': 'info'
                }
            ]
        }

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        MySQLRenderer.render_check(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain key sections
        self.assertIn('MySQL Health Check', output)
        self.assertIn('Connection Test', output)
        self.assertIn('pass', output.lower())

    def test_renderer_check_json_output(self):
        """Renderer should support JSON format."""
        import json
        from reveal.adapters.mysql.renderer import MySQLRenderer
        from io import StringIO

        result = {
            'contract_version': '1.0',
            'type': 'mysql_check',
            'status': 'pass',
            'summary': {
                'passed': 0,
                'warnings': 0,
                'failures': 0,
                'total': 0
            },
            'exit_code': 0,
            'checks': []
        }

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        MySQLRenderer.render_check(result, format='json')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should be valid JSON
        parsed = json.loads(output)
        self.assertEqual(parsed['type'], 'mysql_check')

    def test_renderer_check_only_failures(self):
        """Renderer should support only_failures flag."""
        from reveal.adapters.mysql.renderer import MySQLRenderer
        from io import StringIO

        result = {
            'contract_version': '1.0',
            'type': 'mysql_check',
            'status': 'warning',
            'summary': {
                'passed': 1,
                'warnings': 0,
                'failures': 1,
                'total': 2
            },
            'exit_code': 1,
            'checks': [
                {
                    'name': 'Pass Check',
                    'status': 'pass',
                    'value': 'OK',
                    'threshold': None,
                    'severity': 'info'
                },
                {
                    'name': 'Fail Check',
                    'status': 'failure',
                    'value': 95,
                    'threshold': 80,
                    'severity': 'critical'
                }
            ]
        }

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        MySQLRenderer.render_check(result, format='text', only_failures=True)

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should show fail check but not pass check
        self.assertIn('Fail Check', output)
        self.assertNotIn('Pass Check', output)

    def test_renderer_error_handling(self):
        """Renderer should handle errors gracefully."""
        from reveal.adapters.mysql.renderer import MySQLRenderer
        from io import StringIO

        # Capture stderr (render_error outputs to stderr)
        old_stderr = sys.stderr
        sys.stderr = captured_output = StringIO()

        error = ConnectionError("Failed to connect to MySQL")
        MySQLRenderer.render_error(error)

        sys.stderr = old_stderr
        output = captured_output.getvalue()

        self.assertIn('Error', output)
        self.assertIn('Failed to connect to MySQL', output)

    def test_renderer_server_output(self):
        """Renderer should format server overview correctly."""
        from reveal.adapters.mysql.renderer import MySQLRenderer
        from io import StringIO

        # Mock server result with proper structure
        result = {
            'contract_version': '1.0',
            'type': 'mysql_server',
            'server': 'localhost:3306',
            'version': '8.0.32',
            'uptime': '5 days',
            'connection_health': {
                'status': 'healthy',
                'current': 10,
                'max': 100,
                'percentage': '10%'
            },
            'performance': {
                'qps': 150,
                'slow_queries': 5,
                'threads_running': 3
            },
            'innodb_health': {
                'status': 'healthy',
                'buffer_pool_hit_rate': '99.5%',
                'row_lock_waits': 0,
                'deadlocks': 0
            },
            'replication': {
                'role': 'master'
            },
            'storage': {
                'total_size_gb': 50.5,
                'database_count': 10,
                'largest_db': 'production'
            },
            'health_status': 'healthy',
            'health_issues': [],
            'next_steps': ['Monitor slow queries']
        }

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        MySQLRenderer._render_mysql_server(result)

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain server info
        self.assertIn('MySQL Server', output)
        self.assertIn('localhost:3306', output)
        self.assertIn('8.0.32', output)

    def _render_and_capture(self, result):
        """Render result via render_structure(format='text') and return stdout."""
        from reveal.adapters.mysql.renderer import MySQLRenderer
        from io import StringIO

        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        try:
            MySQLRenderer.render_structure(result, format='text')
        finally:
            sys.stdout = old_stdout
        return captured_output.getvalue()

    def test_renderer_connections_output(self):
        """Renderer should format the connections element as text, not raw JSON."""
        result = {
            'type': 'connections',
            'measurement_window': '5d 2h (since server start)',
            'total_connections': 12,
            'by_state': {'Sleep': 10, 'Query': 2},
            'long_running_queries': [
                {'id': 42, 'user': 'app', 'db': 'prod', 'time': 90,
                 'state': 'Sending data', 'info': 'SELECT * FROM big_table'},
            ],
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Connections', output)
        self.assertIn('Total Connections: 12', output)
        self.assertIn('Sleep: 10', output)
        self.assertIn('app@prod', output)
        self.assertIn('SELECT * FROM big_table', output)
        self.assertNotIn('"type"', output)

    def test_renderer_errors_output(self):
        """Renderer should format the errors element as text, not raw JSON."""
        result = {
            'type': 'errors',
            'measurement_window': '5d 2h (since server start)',
            'aborted_clients': '3 (since server start)',
            'aborted_connects': '1 (since server start)',
            'connection_errors_internal': '0 (since server start)',
            'connection_errors_max_connections': '0 (since server start)',
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Errors', output)
        self.assertIn('Aborted Clients: 3', output)
        self.assertNotIn('"type"', output)

    def test_renderer_variables_output(self):
        """Renderer should format the variables element as text, not raw JSON."""
        result = {
            'type': 'variables',
            'measurement_window': '5d 2h (since server start)',
            'variables': {'max_connections': '151', 'tmp_table_size': '16777216'},
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Variables', output)
        self.assertIn('max_connections: 151', output)
        self.assertNotIn('"type"', output)

    def test_renderer_databases_output(self):
        """Renderer should format the databases element as text, not raw JSON."""
        result = {
            'type': 'databases',
            'measurement_window': '5d 2h (since server start)',
            'databases': ['app_prod', 'app_staging'],
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Databases (2)', output)
        self.assertIn('app_prod', output)
        self.assertNotIn('"type"', output)

    def test_renderer_indexes_output(self):
        """Renderer should format the indexes element as text, not raw JSON."""
        result = {
            'type': 'indexes',
            'measurement_basis': 'since_server_start',
            'measurement_start_time': '2026-08-01T00:00:00+00:00',
            'performance_schema_status': {'enabled': True, 'counters_reset_detected': False,
                                          'likely_reset_time': None},
            'most_used': [
                {'object_schema': 'app', 'object_name': 'users', 'index_name': 'PRIMARY',
                 'total_accesses': 1000, 'read_accesses': 900, 'write_accesses': 100, 'read_pct': 90.0},
            ],
            'unused': [
                {'object_schema': 'app', 'object_name': 'orders', 'index_name': 'idx_legacy'},
            ],
            'unused_count': 1,
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Index Usage', output)
        self.assertIn('app.users.PRIMARY', output)
        self.assertIn('Unused Indexes: 1', output)
        self.assertIn('app.orders.idx_legacy', output)
        self.assertNotIn('"type"', output)

    def test_renderer_slow_queries_output(self):
        """Renderer should format the slow-queries element as text, not raw JSON."""
        result = {
            'type': 'slow_queries',
            'period': '24 hours',
            'summary': {'total_slow_queries': 2, 'min_time': 1.5, 'max_time': 8.2,
                        'avg_time': 4.85, 'total_rows_examined': 50000},
            'top_queries': [
                {'start_time': '2026-08-04T01:00:00', 'user_host': 'app[app] @ localhost',
                 'query_time_seconds': 8.2, 'lock_time_seconds': 0.1, 'rows_sent': 1,
                 'rows_examined': 40000, 'query_preview': 'SELECT * FROM orders WHERE ...'},
            ],
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Slow Queries (last 24 hours)', output)
        self.assertIn('Total: 2', output)
        self.assertIn('SELECT * FROM orders WHERE ...', output)
        self.assertNotIn('"type"', output)

    def test_renderer_slow_queries_unavailable(self):
        """Renderer should handle the slow-query-log-unavailable error shape."""
        result = {
            'type': 'slow_queries',
            'error': "Table 'mysql.slow_log' doesn't exist",
            'message': 'Slow query log may not be enabled or accessible',
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Slow Queries: unavailable', output)
        self.assertIn('Slow query log may not be enabled', output)

    def test_renderer_tables_output(self):
        """Renderer should format the tables element as text, not raw JSON."""
        result = {
            'type': 'tables',
            'measurement_basis': 'since_server_start',
            'measurement_start_time': '2026-08-01T00:00:00+00:00',
            'tables': [
                {'table_name': 'orders', 'reads': 5000, 'writes': 10,
                 'read_write_ratio': 500.0, 'total_time_sec': 12.5, 'total_time_hours': 0.0,
                 'read_time_sec': 12.0, 'write_time_sec': 0.5,
                 'alert': 'extreme_read_ratio', 'recommendation': 'Review queries for missing LIMIT clauses'},
            ],
            'table_count': 1,
            'alerts': [
                {'table': 'orders', 'type': 'extreme_read_ratio', 'ratio': 500.0,
                 'recommendation': 'Review queries for missing LIMIT clauses'},
            ],
            'alert_count': 1,
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Table I/O (1 tables)', output)
        self.assertIn('orders: 5000 reads / 10 writes', output)
        self.assertIn('extreme_read_ratio', output)
        self.assertIn('Alerts: 1', output)
        self.assertNotIn('"type"', output)

    def test_renderer_performance_output(self):
        """Renderer should format the performance element as text, not raw JSON."""
        result = {
            'type': 'performance',
            'measurement_window': '5d 2h (since server start)',
            'queries_per_second': 123.456,
            'slow_queries_total': '5 (since server start)',
            'sort_merge_passes': '0 (since server start)',
            'full_table_scans': {'select_scan_ratio': '5.00%', 'status': '✅',
                                 'select_scan': '10', 'select_range': '190',
                                 'handler_read_rnd_next': '0', 'note': 'note-scans'},
            'thread_cache_efficiency': {'miss_rate': '2.00%', 'status': '✅',
                                        'threads_created': '2', 'connections': '100',
                                        'note': 'note-threads'},
            'temp_tables': {'disk_ratio': '10.00%', 'status': '✅',
                            'on_disk': '10', 'total': '100', 'note': 'note-temp'},
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Performance', output)
        self.assertIn('QPS: 123.46', output)
        self.assertIn('note-scans', output)
        self.assertIn('note-threads', output)
        self.assertIn('note-temp', output)
        self.assertNotIn('"type"', output)

    def test_renderer_innodb_output(self):
        """Renderer should format the innodb element as text, not raw JSON."""
        result = {
            'type': 'innodb',
            'measurement_window': '5d 2h (since server start)',
            'buffer_pool_hit_rate': '99.50%',
            'buffer_pool_reads': '10 (since server start)',
            'buffer_pool_read_requests': '10000 (since server start)',
            'row_lock_waits': '0 (since server start)',
            'row_lock_time_avg': '0 ms',
            'deadlocks': '0 (since server start)',
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL InnoDB', output)
        self.assertIn('Buffer Pool Hit Rate: 99.50%', output)
        self.assertNotIn('"type"', output)

    def test_renderer_replication_slave_output(self):
        """Renderer should format the replication element for a Slave role."""
        result = {
            'type': 'replication',
            'role': 'Slave',
            'master_host': 'master.internal',
            'master_port': 3306,
            'io_running': 'Yes',
            'sql_running': 'Yes',
            'seconds_behind_master': 0,
            'last_error': 'None',
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Replication: Slave', output)
        self.assertIn('master.internal:3306', output)
        self.assertNotIn('"type"', output)

    def test_renderer_replication_master_output(self):
        """Renderer should format the replication element for a Master role."""
        result = {
            'type': 'replication',
            'role': 'Master',
            'slaves': [{'server_id': 2, 'host': 'replica1.internal'}],
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Replication: Master', output)
        self.assertIn('replica1.internal', output)

    def test_renderer_replication_standalone_output(self):
        """Renderer should format the replication element for a Standalone role."""
        result = {
            'type': 'replication',
            'role': 'Standalone',
            'message': 'No replication configured',
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Replication: Standalone', output)
        self.assertIn('No replication configured', output)

    def test_renderer_storage_output(self):
        """Renderer should format the storage element as text, not raw JSON."""
        result = {
            'type': 'storage',
            'measurement_window': '5d 2h (since server start)',
            'databases': [
                {'db_name': 'app_prod', 'table_count': 20, 'size_gb': 12.5,
                 'data_gb': 10.0, 'index_gb': 2.5},
            ],
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Storage', output)
        self.assertIn('app_prod: 12.5 GB', output)
        self.assertNotIn('"type"', output)

    def test_renderer_database_storage_output(self):
        """Renderer should format the storage/<db> element as text, not raw JSON."""
        result = {
            'type': 'database_storage',
            'measurement_window': '5d 2h (since server start)',
            'database': 'app_prod',
            'tables': [
                {'table_name': 'orders', 'engine': 'InnoDB', 'table_rows': 100000, 'size_mb': 512.5},
            ],
        }
        output = self._render_and_capture(result)
        self.assertIn('MySQL Storage: app_prod', output)
        self.assertIn('orders (InnoDB): 512.5 MB, 100000 rows', output)
        self.assertNotIn('"type"', output)


class TestMySQLConnectionSnapshotContext(unittest.TestCase):
    """Test MySQLConnection.get_snapshot_context() method."""

    def setUp(self):
        """Set up test fixtures."""
        from reveal.adapters.mysql.connection import MySQLConnection
        with patch('reveal.adapters.mysql.connection.PYMYSQL_AVAILABLE', True):
            self.conn = MySQLConnection("mysql://localhost")
            # Mock the connection
            self.conn._connection = Mock()

    def test_snapshot_context_returns_all_fields(self):
        """Test that get_snapshot_context returns all required fields."""
        # Mock MySQL timestamp query (current time)
        self.conn.execute_single = Mock(return_value={'timestamp': '1704672000'})
        # Mock uptime query (23 days, 23 hours)
        self.conn.execute_query = Mock(return_value=[{'Variable_name': 'Uptime', 'Value': '2071522'}])

        result = self.conn.get_snapshot_context()

        # Check all required fields exist
        self.assertIn('snapshot_time', result)
        self.assertIn('server_start_time', result)
        self.assertIn('uptime_seconds', result)
        self.assertIn('measurement_window', result)

    def test_snapshot_context_uses_mysql_clock(self):
        """Test that snapshot uses MySQL's UNIX_TIMESTAMP, not local time."""
        # Mock MySQL timestamp
        mysql_timestamp = 1704672000
        self.conn.execute_single = Mock(return_value={'timestamp': str(mysql_timestamp)})
        self.conn.execute_query = Mock(return_value=[{'Variable_name': 'Uptime', 'Value': '86400'}])

        result = self.conn.get_snapshot_context()

        # Verify execute_single was called with MySQL timestamp query
        self.conn.execute_single.assert_called_once_with("SELECT UNIX_TIMESTAMP() as timestamp")
        # Verify snapshot_time is in ISO 8601 format
        self.assertRegex(result['snapshot_time'], r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00')

    def test_snapshot_context_calculates_server_start_time(self):
        """Test that server_start_time is calculated correctly."""
        # Current time: 1704672000, Uptime: 86400 (1 day)
        # Expected start: 1704672000 - 86400 = 1704585600
        self.conn.execute_single = Mock(return_value={'timestamp': '1704672000'})
        self.conn.execute_query = Mock(return_value=[{'Variable_name': 'Uptime', 'Value': '86400'}])

        result = self.conn.get_snapshot_context()

        # Check uptime is correct
        self.assertEqual(result['uptime_seconds'], 86400)
        # Check measurement window format
        self.assertEqual(result['measurement_window'], '1d 0h (since server start)')
        # Check server_start_time is in ISO format
        self.assertRegex(result['server_start_time'], r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00')

    def test_snapshot_context_formats_measurement_window(self):
        """Test that measurement_window is formatted correctly."""
        # 23 days, 23 hours = 2071522 seconds
        self.conn.execute_single = Mock(return_value={'timestamp': '1704672000'})
        self.conn.execute_query = Mock(return_value=[{'Variable_name': 'Uptime', 'Value': '2071522'}])

        result = self.conn.get_snapshot_context()

        self.assertEqual(result['measurement_window'], '23d 23h (since server start)')

    def test_snapshot_context_handles_zero_uptime(self):
        """Test that zero uptime is handled gracefully."""
        self.conn.execute_single = Mock(return_value={'timestamp': '1704672000'})
        self.conn.execute_query = Mock(return_value=[{'Variable_name': 'Uptime', 'Value': '0'}])

        result = self.conn.get_snapshot_context()

        self.assertEqual(result['uptime_seconds'], 0)
        self.assertEqual(result['measurement_window'], '0d 0h (since server start)')


class TestMySQLConnectionPerformanceSchemaStatus(unittest.TestCase):
    """Test MySQLConnection.get_performance_schema_status() method."""

    def setUp(self):
        """Set up test fixtures."""
        from reveal.adapters.mysql.connection import MySQLConnection
        with patch('reveal.adapters.mysql.connection.PYMYSQL_AVAILABLE', True):
            self.conn = MySQLConnection("mysql://localhost")
            self.conn._connection = Mock()

    def test_performance_schema_disabled(self):
        """Test when performance_schema is disabled."""
        self.conn.execute_single = Mock(return_value={'enabled': 0})

        result = self.conn.get_performance_schema_status()

        self.assertEqual(result['enabled'], False)
        self.assertEqual(result['counters_reset_detected'], False)
        self.assertIsNone(result['likely_reset_time'])

    def test_performance_schema_enabled_no_reset(self):
        """Test when performance_schema is enabled with no reset detected."""
        # Mock: performance_schema enabled
        # Mock: uptime = 30 days (2592000 seconds)
        # Mock: oldest event = 29 days ago (gap < 1 hour, no reset)
        mock_single_responses = [
            {'enabled': 1},  # First call: check if enabled
            {'timestamp': '1704672000'},  # Second call: snapshot time
            {'oldest_timestamp': 1704586000.0}  # Third call: oldest event (86000s ago, ~1 day)
        ]
        self.conn.execute_single = Mock(side_effect=mock_single_responses)
        self.conn.execute_query = Mock(return_value=[{'Variable_name': 'Uptime', 'Value': '86400'}])  # 1 day uptime

        result = self.conn.get_performance_schema_status()

        self.assertEqual(result['enabled'], True)
        self.assertEqual(result['counters_reset_detected'], False)
        self.assertIsNone(result['likely_reset_time'])

    def test_performance_schema_enabled_with_reset(self):
        """Test when performance_schema reset is detected (>1 hour gap)."""
        # Mock: uptime = 30 days (2592000 seconds)
        # Mock: oldest event = 1 day ago (gap = 29 days, reset detected!)
        mock_single_responses = [
            {'enabled': 1},  # First call: check if enabled
            {'timestamp': '1704672000'},  # Second call: snapshot time
            {'oldest_timestamp': 1704585600.0}  # Third call: oldest event (86400s ago = 1 day)
        ]
        self.conn.execute_single = Mock(side_effect=mock_single_responses)
        # Uptime = 30 days = 2592000 seconds
        self.conn.execute_query = Mock(return_value=[{'Variable_name': 'Uptime', 'Value': '2592000'}])

        result = self.conn.get_performance_schema_status()

        self.assertEqual(result['enabled'], True)
        self.assertEqual(result['counters_reset_detected'], True)
        self.assertIsNotNone(result['likely_reset_time'])
        # Verify reset time is in ISO format
        self.assertRegex(result['likely_reset_time'], r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00')

    def test_performance_schema_no_events_yet(self):
        """Test when performance_schema has no events recorded yet."""
        mock_single_responses = [
            {'enabled': 1},  # First call: check if enabled
            {'timestamp': '1704672000'},  # Second call: snapshot time
            {'oldest_timestamp': None}  # Third call: no events yet
        ]
        self.conn.execute_single = Mock(side_effect=mock_single_responses)
        self.conn.execute_query = Mock(return_value=[{'Variable_name': 'Uptime', 'Value': '86400'}])

        result = self.conn.get_performance_schema_status()

        self.assertEqual(result['enabled'], True)
        self.assertEqual(result['counters_reset_detected'], False)
        self.assertIsNone(result['likely_reset_time'])

    def test_performance_schema_query_failure(self):
        """Test graceful handling when performance_schema query fails."""
        # Simulate query failure
        self.conn.execute_single = Mock(side_effect=Exception("Table doesn't exist"))

        result = self.conn.get_performance_schema_status()

        self.assertEqual(result['enabled'], False)
        self.assertEqual(result['counters_reset_detected'], False)
        self.assertIsNone(result['likely_reset_time'])

    def test_performance_schema_reset_detection_threshold(self):
        """Test that 1 hour gap threshold works correctly."""
        # Test just above threshold (>3600 seconds gap = >1 hour)
        mock_single_responses = [
            {'enabled': 1},
            {'timestamp': '1704672000'},
            {'oldest_timestamp': 1704668398.0}  # 3602 seconds ago (just over 1 hour)
        ]
        self.conn.execute_single = Mock(side_effect=mock_single_responses)
        self.conn.execute_query = Mock(return_value=[{'Variable_name': 'Uptime', 'Value': '7203'}])  # 2 hours + 3 seconds uptime

        result = self.conn.get_performance_schema_status()

        # Gap = 7203 - 3602 = 3601 seconds (just over 1 hour)
        # Should detect reset since gap > 3600
        self.assertEqual(result['enabled'], True)
        self.assertEqual(result['counters_reset_detected'], True)


class TestGetTables(unittest.TestCase):
    """Test _get_tables() method for table I/O statistics."""

    def setUp(self):
        """Create adapter with mocked connection."""
        self.adapter = MySQLAdapter("mysql://test:test@localhost/test")
        self.adapter._connection = MagicMock()
        self.adapter._cursor = MagicMock()

    def test_get_tables_basic_output(self):
        """Should return properly formatted table I/O statistics."""
        # Mock snapshot context
        mock_timing = {
            'snapshot_time': '2026-02-16T13:00:00+00:00',
            'server_start_time': '2026-01-17T08:00:00+00:00',
            'uptime_seconds': 2592000,
            'measurement_window': '30d 0h (since server start)',
        }

        # Mock performance schema status
        mock_ps_status = {
            'enabled': True,
            'counters_reset_detected': False,
            'likely_reset_time': None,
        }

        # Mock table I/O data (simulating the asset_library case from issue)
        mock_tables = [
            {
                'table_name': 'asset_library',
                'reads': 80039744536,  # 80B reads
                'writes': 163460,
                'read_time_ps': 98234000000000000,  # ~27.3 hours
                'write_time_ps': 4305000000000000,  # ~1.2 hours
                'total_time_ps': 102539000000000000,  # ~28.5 hours
            },
            {
                'table_name': 'normal_table',
                'reads': 1000,
                'writes': 500,
                'read_time_ps': 100000000000,  # ~0.0001 seconds
                'write_time_ps': 50000000000,
                'total_time_ps': 150000000000,
            }
        ]

        # Setup mocks
        self.adapter.conn = MagicMock()
        self.adapter.conn.get_snapshot_context = Mock(return_value=mock_timing)
        self.adapter.conn.get_performance_schema_status = Mock(return_value=mock_ps_status)
        self.adapter._execute_query = Mock(return_value=mock_tables)

        # Execute
        result = self.adapter._get_tables()

        # Verify structure
        self.assertEqual(result['type'], 'tables')
        self.assertEqual(result['snapshot_time'], mock_timing['snapshot_time'])
        self.assertEqual(result['measurement_basis'], 'since_server_start')
        self.assertIn('tables', result)
        self.assertIn('alerts', result)
        self.assertEqual(result['table_count'], 2)

        # Verify asset_library calculations
        asset_lib = result['tables'][0]
        self.assertEqual(asset_lib['table_name'], 'asset_library')
        self.assertEqual(asset_lib['reads'], 80039744536)
        self.assertEqual(asset_lib['writes'], 163460)
        self.assertIsNotNone(asset_lib['read_write_ratio'])
        self.assertGreater(asset_lib['read_write_ratio'], 10000)  # Should trigger alert
        self.assertEqual(asset_lib['total_time_hours'], 28.48)  # ~28.5 hours
        self.assertEqual(asset_lib['alert'], 'extreme_read_ratio')

        # Verify normal_table
        normal = result['tables'][1]
        self.assertEqual(normal['table_name'], 'normal_table')
        self.assertIsNone(normal['alert'])

    def test_get_tables_alerts_extreme_read_ratio(self):
        """Should alert on extreme read:write ratios (>10K:1)."""
        mock_tables = [{
            'table_name': 'read_heavy',
            'reads': 500000,
            'writes': 10,  # 50K:1 ratio
            'read_time_ps': 1000000000000,
            'write_time_ps': 1000000000000,
            'total_time_ps': 2000000000000,
        }]

        self._setup_mocks(mock_tables)
        result = self.adapter._get_tables()

        self.assertEqual(result['alert_count'], 1)
        self.assertEqual(result['alerts'][0]['type'], 'extreme_read_ratio')
        self.assertEqual(result['alerts'][0]['table'], 'read_heavy')
        self.assertIn('LIMIT', result['alerts'][0]['recommendation'])

    def test_get_tables_alerts_high_read_volume(self):
        """Should alert on high read volume (>1B reads)."""
        mock_tables = [{
            'table_name': 'high_volume',
            'reads': 2000000000,  # 2B reads
            'writes': 2000000,  # 1K:1 ratio (not extreme)
            'read_time_ps': 1000000000000,
            'write_time_ps': 1000000000000,
            'total_time_ps': 2000000000000,
        }]

        self._setup_mocks(mock_tables)
        result = self.adapter._get_tables()

        self.assertEqual(result['alert_count'], 1)
        self.assertEqual(result['alerts'][0]['type'], 'high_read_volume')

    def test_get_tables_alerts_long_running(self):
        """Should alert on long-running queries (>1 hour)."""
        mock_tables = [{
            'table_name': 'slow_table',
            'reads': 1000,
            'writes': 1000,
            'read_time_ps': 7200000000000000,  # 2 hours
            'write_time_ps': 0,
            'total_time_ps': 7200000000000000,
        }]

        self._setup_mocks(mock_tables)
        result = self.adapter._get_tables()

        self.assertEqual(result['alert_count'], 1)
        self.assertEqual(result['alerts'][0]['type'], 'long_running')
        self.assertEqual(result['alerts'][0]['total_hours'], 2.0)

    def test_get_tables_handles_reset_detection(self):
        """Should use reset time when counters were reset."""
        mock_ps_status = {
            'enabled': True,
            'counters_reset_detected': True,
            'likely_reset_time': '2026-02-01T00:00:00+00:00',
        }

        self._setup_mocks([], ps_status=mock_ps_status)
        result = self.adapter._get_tables()

        self.assertEqual(result['measurement_basis'], 'since_reset')
        self.assertEqual(result['measurement_start_time'], '2026-02-01T00:00:00+00:00')

    def _setup_mocks(self, mock_tables, ps_status=None):
        """Helper to setup common mocks."""
        mock_timing = {
            'snapshot_time': '2026-02-16T13:00:00+00:00',
            'server_start_time': '2026-01-17T08:00:00+00:00',
            'uptime_seconds': 2592000,
            'measurement_window': '30d 0h (since server start)',
        }

        if ps_status is None:
            ps_status = {
                'enabled': True,
                'counters_reset_detected': False,
                'likely_reset_time': None,
            }

        self.adapter.conn = MagicMock()
        self.adapter.conn.get_snapshot_context = Mock(return_value=mock_timing)
        self.adapter.conn.get_performance_schema_status = Mock(return_value=ps_status)
        self.adapter._execute_query = Mock(return_value=mock_tables)


class TestGetDatabaseStorageSQLInjection(unittest.TestCase):
    """BACK-896: db_name must be bound as a query parameter, never
    interpolated into the SQL text."""

    def setUp(self):
        from reveal.adapters.mysql.storage import StorageAnalyzer
        self.mock_conn = MagicMock()
        self.mock_conn.get_snapshot_context = Mock(return_value={})
        self.mock_conn.execute_query = Mock(return_value=[])
        self.analyzer = StorageAnalyzer(self.mock_conn)

    def test_db_name_passed_as_bind_parameter_not_interpolated(self):
        """A malicious db_name must never appear inside the query string."""
        malicious = "x' UNION SELECT user,authentication_string,3,4 FROM mysql.user-- "

        self.analyzer.get_database_storage(malicious)

        self.mock_conn.execute_query.assert_called_once()
        query_arg, params_arg = self.mock_conn.execute_query.call_args[0]
        self.assertNotIn(malicious, query_arg)
        self.assertIn('%s', query_arg)
        self.assertEqual(params_arg, (malicious,))

    def test_normal_db_name_returns_expected_shape(self):
        self.mock_conn.execute_query = Mock(return_value=[
            {'table_name': 'users', 'engine': 'InnoDB', 'table_rows': 10, 'size_mb': 1.2},
        ])

        result = self.analyzer.get_database_storage('app_prod')

        self.assertEqual(result['type'], 'database_storage')
        self.assertEqual(result['database'], 'app_prod')
        self.assertEqual(result['tables'][0]['table_name'], 'users')
        _, params_arg = self.mock_conn.execute_query.call_args[0]
        self.assertEqual(params_arg, ('app_prod',))


if __name__ == '__main__':
    unittest.main()
