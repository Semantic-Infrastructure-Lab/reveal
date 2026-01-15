"""
Tests for reveal/cli/scheme_handlers/sqlite.py

Tests the SQLite scheme handler functionality including:
- Rendering database overview results
- Rendering table detail results
- Handling various URI patterns
- Error handling for missing databases, tables, and other failures
"""

import unittest
import sys
from io import StringIO
from argparse import Namespace
from unittest.mock import Mock, patch, MagicMock

from reveal.cli.scheme_handlers.sqlite import _render_sqlite_result, handle_sqlite


class TestRenderSQLiteResultDatabase(unittest.TestCase):
    """Test _render_sqlite_result() with database overview data."""

    def setUp(self):
        """Set up test fixtures."""
        self.database_result = {
            'type': 'sqlite_database',
            'path': '/tmp/test.db',
            'sqlite_version': '3.31.1',
            'size': '1.2 MB',
            'configuration': {
                'page_size': 4096,
                'page_count': 256,
                'journal_mode': 'WAL',
                'encoding': 'UTF-8',
                'foreign_keys_enabled': True
            },
            'statistics': {
                'tables': 5,
                'views': 2,
                'total_rows': 10000,
                'foreign_keys': 8
            },
            'tables': [
                {
                    'name': 'users',
                    'type': 'table',
                    'rows': 1000,
                    'columns': 5,
                    'indexes': 3
                },
                {
                    'name': 'posts',
                    'type': 'table',
                    'rows': 5000,
                    'columns': 7,
                    'indexes': 2
                },
                {
                    'name': 'user_stats',
                    'type': 'view',
                    'columns': 4,
                    'rows': 0,
                    'indexes': 0
                }
            ],
            'next_steps': [
                'reveal sqlite:///tmp/test.db/users',
                'reveal sqlite:///tmp/test.db/posts'
            ]
        }

    def test_render_database_text_format(self):
        """Test rendering database overview in text format."""
        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.database_result, format='text')
            result = output.getvalue()

            # Check key sections are present
            self.assertIn('SQLite Database:', result)
            self.assertIn('/tmp/test.db', result)
            self.assertIn('3.31.1', result)
            self.assertIn('Configuration:', result)
            self.assertIn('Page Size: 4096', result)
            self.assertIn('Journal Mode: WAL', result)
            self.assertIn('Foreign Keys: Enabled', result)
            self.assertIn('Statistics:', result)
            self.assertIn('Tables: 5', result)
            self.assertIn('Total Rows: 10,000', result)
            self.assertIn('users', result)
            self.assertIn('posts', result)
            self.assertIn('Next Steps:', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_database_json_format(self):
        """Test rendering database overview in JSON format."""
        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.database_result, format='json')
            result = output.getvalue()

            # Should be valid JSON containing the data
            self.assertIn('"type": "sqlite_database"', result)
            self.assertIn('"/tmp/test.db"', result)
            self.assertIn('"sqlite_version"', result)
            self.assertIn('"configuration"', result)
            self.assertIn('"statistics"', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_database_with_view(self):
        """Test rendering database that includes views."""
        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.database_result, format='text')
            result = output.getvalue()

            # Check view is rendered differently than table
            self.assertIn('user_stats', result)
            self.assertIn('view', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_database_foreign_keys_disabled(self):
        """Test rendering database with foreign keys disabled."""
        self.database_result['configuration']['foreign_keys_enabled'] = False

        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.database_result, format='text')
            result = output.getvalue()

            self.assertIn('Foreign Keys: Disabled', result)
        finally:
            sys.stdout = sys.__stdout__


class TestRenderSQLiteResultTable(unittest.TestCase):
    """Test _render_sqlite_result() with table detail data."""

    def setUp(self):
        """Set up test fixtures."""
        self.table_result = {
            'type': 'sqlite_table',
            'table': 'users',
            'database': '/tmp/test.db',
            'row_count': 1000,
            'columns': [
                {
                    'name': 'id',
                    'type': 'INTEGER',
                    'primary_key': True,
                    'nullable': False,
                    'default': None
                },
                {
                    'name': 'username',
                    'type': 'TEXT',
                    'primary_key': False,
                    'nullable': False,
                    'default': None
                },
                {
                    'name': 'email',
                    'type': 'TEXT',
                    'primary_key': False,
                    'nullable': True,
                    'default': "'user@example.com'"
                }
            ],
            'indexes': [
                {
                    'name': 'idx_username',
                    'unique': True,
                    'columns': ['username']
                },
                {
                    'name': 'idx_email',
                    'unique': False,
                    'columns': ['email']
                }
            ],
            'foreign_keys': [
                {
                    'column': 'group_id',
                    'references_table': 'groups',
                    'references_column': 'id',
                    'on_delete': 'CASCADE',
                    'on_update': 'NO ACTION'
                }
            ],
            'create_statement': 'CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL)',
            'next_steps': [
                'reveal sqlite:///tmp/test.db'
            ]
        }

    def test_render_table_text_format(self):
        """Test rendering table details in text format."""
        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.table_result, format='text')
            result = output.getvalue()

            # Check key sections are present
            self.assertIn('Table: users', result)
            self.assertIn('Row Count: 1,000', result)
            self.assertIn('Columns (3):', result)
            self.assertIn('id: INTEGER [PK] NOT NULL', result)
            self.assertIn('username: TEXT NOT NULL', result)
            self.assertIn('email: TEXT NULL DEFAULT', result)
            self.assertIn('Indexes (2):', result)
            self.assertIn('idx_username [UNIQUE]', result)
            self.assertIn('idx_email (email)', result)
            self.assertIn('Foreign Keys (1):', result)
            self.assertIn('group_id → groups.id', result)
            self.assertIn('ON DELETE CASCADE', result)
            self.assertIn('CREATE Statement:', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_table_json_format(self):
        """Test rendering table details in JSON format."""
        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.table_result, format='json')
            result = output.getvalue()

            # Should be valid JSON
            self.assertIn('"type": "sqlite_table"', result)
            self.assertIn('"table": "users"', result)
            self.assertIn('"row_count": 1000', result)
            self.assertIn('"columns"', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_table_without_indexes(self):
        """Test rendering table with no indexes."""
        self.table_result['indexes'] = []

        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.table_result, format='text')
            result = output.getvalue()

            # Should still render other sections
            self.assertIn('Table: users', result)
            self.assertIn('Columns', result)
            # Indexes section should not appear
            # (or appear but be empty)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_table_without_foreign_keys(self):
        """Test rendering table with no foreign keys."""
        self.table_result['foreign_keys'] = []

        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.table_result, format='text')
            result = output.getvalue()

            # Should still render other sections
            self.assertIn('Table: users', result)
            self.assertIn('Columns', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_table_without_create_statement(self):
        """Test rendering table without CREATE statement."""
        del self.table_result['create_statement']

        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.table_result, format='text')
            result = output.getvalue()

            # Should still render other sections
            self.assertIn('Table: users', result)
            self.assertIn('Columns', result)
        finally:
            sys.stdout = sys.__stdout__

    def test_render_table_without_next_steps(self):
        """Test rendering table without next_steps field."""
        del self.table_result['next_steps']

        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(self.table_result, format='text')
            result = output.getvalue()

            # Should still render other sections
            self.assertIn('Table: users', result)
            self.assertIn('Columns', result)
        finally:
            sys.stdout = sys.__stdout__


class TestRenderSQLiteResultUnknown(unittest.TestCase):
    """Test _render_sqlite_result() with unknown result types."""

    def test_render_unknown_type_as_json(self):
        """Test that unknown result types are rendered as JSON."""
        unknown_result = {
            'type': 'unknown_type',
            'some_data': 'value',
            'nested': {'key': 'value'}
        }

        output = StringIO()
        sys.stdout = output
        try:
            _render_sqlite_result(unknown_result, format='text')
            result = output.getvalue()

            # Should fall back to JSON rendering
            self.assertIn('"type": "unknown_type"', result)
            self.assertIn('"some_data"', result)
        finally:
            sys.stdout = sys.__stdout__


class TestHandleSQLiteSuccess(unittest.TestCase):
    """Test handle_sqlite() successful execution paths."""

    @patch('reveal.cli.scheme_handlers.sqlite._render_sqlite_result')
    def test_handle_sqlite_database_without_element(self, mock_render):
        """Test handling sqlite:// URI without element (database overview)."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'type': 'sqlite_database'}
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', debug=False)

        # Call handler
        exit_code = handle_sqlite(mock_adapter_class, '/tmp/test.db', None, args)

        # Verify
        self.assertEqual(exit_code, 0)
        mock_adapter_class.assert_called_once_with('sqlite:///tmp/test.db')
        mock_adapter.get_structure.assert_called_once()
        mock_render.assert_called_once_with({'type': 'sqlite_database'}, format='text')

    @patch('reveal.cli.scheme_handlers.sqlite._render_sqlite_result')
    def test_handle_sqlite_table_with_element(self, mock_render):
        """Test handling sqlite:// URI with element (table details)."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'type': 'sqlite_table'}
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', debug=False)

        # Call handler
        exit_code = handle_sqlite(mock_adapter_class, '/tmp/test.db', 'users', args)

        # Verify
        self.assertEqual(exit_code, 0)
        mock_adapter_class.assert_called_once_with('sqlite:///tmp/test.db/users')
        mock_adapter.get_structure.assert_called_once()
        mock_render.assert_called_once()

    @patch('reveal.cli.scheme_handlers.sqlite._render_sqlite_result')
    def test_handle_sqlite_json_format(self, mock_render):
        """Test handling sqlite:// URI with JSON format."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'type': 'sqlite_database'}
        mock_adapter_class.return_value = mock_adapter

        # Create args with JSON format
        args = Namespace(format='json', debug=False)

        # Call handler
        exit_code = handle_sqlite(mock_adapter_class, '/tmp/test.db', None, args)

        # Verify
        self.assertEqual(exit_code, 0)
        mock_render.assert_called_once_with({'type': 'sqlite_database'}, format='json')


class TestHandleSQLiteErrors(unittest.TestCase):
    """Test handle_sqlite() error handling."""

    def test_handle_sqlite_file_not_found(self):
        """Test handling FileNotFoundError from adapter."""
        # Mock adapter class that raises FileNotFoundError
        mock_adapter_class = Mock()
        mock_adapter_class.side_effect = FileNotFoundError("Database not found")

        # Create args
        args = Namespace(format='text', debug=False)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            exit_code = handle_sqlite(mock_adapter_class, '/nonexistent.db', None, args)

            # Verify
            self.assertEqual(exit_code, 1)
            self.assertIn('Error:', output.getvalue())
        finally:
            sys.stderr = sys.__stderr__

    def test_handle_sqlite_value_error(self):
        """Test handling ValueError from adapter."""
        # Mock adapter class that raises ValueError
        mock_adapter_class = Mock()
        mock_adapter_class.side_effect = ValueError("Invalid database path")

        # Create args
        args = Namespace(format='text', debug=False)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            exit_code = handle_sqlite(mock_adapter_class, 'invalid', None, args)

            # Verify
            self.assertEqual(exit_code, 1)
            self.assertIn('Error:', output.getvalue())
        finally:
            sys.stderr = sys.__stderr__

    def test_handle_sqlite_import_error(self):
        """Test handling ImportError from adapter."""
        # Mock adapter class that raises ImportError
        mock_adapter_class = Mock()
        mock_adapter_class.side_effect = ImportError("sqlite3 module not found")

        # Create args
        args = Namespace(format='text', debug=False)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            exit_code = handle_sqlite(mock_adapter_class, '/tmp/test.db', None, args)

            # Verify
            self.assertEqual(exit_code, 1)
            stderr_output = output.getvalue()
            self.assertIn('Error:', stderr_output)
            self.assertIn('SQLite support', stderr_output)
        finally:
            sys.stderr = sys.__stderr__

    def test_handle_sqlite_generic_error(self):
        """Test handling generic exceptions from adapter."""
        # Mock adapter class that raises generic exception
        mock_adapter_class = Mock()
        mock_adapter_class.side_effect = RuntimeError("Unexpected error")

        # Create args without debug
        args = Namespace(format='text', debug=False)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            exit_code = handle_sqlite(mock_adapter_class, '/tmp/test.db', None, args)

            # Verify
            self.assertEqual(exit_code, 1)
            stderr_output = output.getvalue()
            self.assertIn('Error:', stderr_output)
            # Traceback should NOT be printed without debug
            self.assertNotIn('Traceback', stderr_output)
        finally:
            sys.stderr = sys.__stderr__

    @patch('traceback.print_exc')
    def test_handle_sqlite_error_with_debug(self, mock_print_exc):
        """Test that debug mode prints traceback on errors."""
        # Mock adapter class that raises exception
        mock_adapter_class = Mock()
        mock_adapter_class.side_effect = RuntimeError("Unexpected error")

        # Create args WITH debug
        args = Namespace(format='text', debug=True)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            exit_code = handle_sqlite(mock_adapter_class, '/tmp/test.db', None, args)

            # Verify
            self.assertEqual(exit_code, 1)
            # Traceback should be printed in debug mode
            mock_print_exc.assert_called_once()
        finally:
            sys.stderr = sys.__stderr__


if __name__ == '__main__':
    unittest.main()
