"""SQLite database adapter (sqlite://)."""

import os
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..base import ResourceAdapter, register_adapter


@register_adapter('sqlite')
class SQLiteAdapter(ResourceAdapter):
    """Adapter for inspecting SQLite databases via sqlite:// URIs.

    Progressive disclosure pattern for SQLite database exploration.

    Usage:
        reveal sqlite:///path/to/db.db           # Database overview
        reveal sqlite:///path/to/db.db/users     # Table structure
        reveal sqlite:///path/to/db.db --check   # Database health
    """

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for sqlite:// adapter."""
        return {
            'name': 'sqlite',
            'description': 'SQLite database exploration and schema inspection',
            'syntax': 'sqlite:///<path>[/table]',
            'examples': [
                {
                    'uri': 'sqlite:///app.db',
                    'description': 'Database overview with schema summary'
                },
                {
                    'uri': 'sqlite:///app.db/users',
                    'description': 'Detailed structure for users table'
                },
                {
                    'uri': 'sqlite:///data/production.db --check',
                    'description': 'Database health check with integrity validation'
                },
                {
                    'uri': 'sqlite:///./relative.db',
                    'description': 'Use relative paths with ./ prefix'
                }
            ],
            'notes': [
                'Absolute paths: sqlite:///absolute/path/to/db.db (three slashes)',
                'Relative paths: sqlite://./relative/path.db (two slashes + ./)',
                'Built-in support - no external dependencies required',
                'Read-only access by default for safety'
            ],
            'features': [
                'Schema exploration (tables, columns, indexes)',
                'Foreign key relationships',
                'Table statistics (row counts, sizes)',
                'SQLite-specific configuration',
                'Integrity checking'
            ],
            'see_also': [
                'reveal help://mysql - Similar adapter for MySQL databases',
                'https://www.sqlite.org/cli.html - Official SQLite CLI'
            ]
        }

    def __init__(self, connection_string: str = ""):
        """Initialize SQLite adapter with database path.

        Args:
            connection_string: sqlite:///path/to/db.db[/table]
        """
        self.connection_string = connection_string
        self.db_path = None
        self.table = None
        self._connection = None
        self._parse_connection_string(connection_string)

    def _parse_connection_string(self, uri: str):
        """Parse sqlite:// URI into components.

        Args:
            uri: Connection URI (sqlite:///path/to/db.db[/table])
        """
        if not uri or uri == "sqlite://":
            raise ValueError("SQLite URI requires database path: sqlite:///path/to/db.db")

        # Remove sqlite:// prefix
        if uri.startswith("sqlite://"):
            uri = uri[9:]

        # Handle absolute vs relative paths
        # sqlite:///absolute/path (three slashes = absolute)
        # sqlite://./relative/path (two slashes = relative)
        if uri.startswith('/'):
            # Absolute path
            path_part = uri
        else:
            # Relative path
            path_part = uri

        # Parse path/table
        parts = path_part.split('/')

        # Find the .db file in the path
        db_parts = []
        table_found = False
        for i, part in enumerate(parts):
            if not table_found:
                db_parts.append(part)
                # Check if this part ends with .db or is the last part
                if part.endswith('.db') or part.endswith('.sqlite') or part.endswith('.sqlite3'):
                    # Everything after this is the table name
                    if i + 1 < len(parts):
                        self.table = '/'.join(parts[i+1:])
                        table_found = True
                    break

        self.db_path = '/'.join(db_parts) if db_parts else path_part

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection.

        Returns:
            SQLite connection object
        """
        if self._connection is None:
            if not self.db_path:
                raise ValueError("No database path specified")

            if not os.path.exists(self.db_path):
                raise FileNotFoundError(f"Database file not found: {self.db_path}")

            # Open in read-only mode for safety
            uri = f"file:{self.db_path}?mode=ro"
            self._connection = sqlite3.connect(uri, uri=True)
            self._connection.row_factory = sqlite3.Row

        return self._connection

    def _execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts.

        Args:
            query: SQL query to execute

        Returns:
            List of result rows as dictionaries
        """
        conn = self._get_connection()
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def _execute_single(self, query: str) -> Optional[Dict[str, Any]]:
        """Execute a query and return single result as dict.

        Args:
            query: SQL query to execute

        Returns:
            Single result row as dictionary, or None if no results
        """
        results = self._execute_query(query)
        return results[0] if results else None

    def __del__(self):
        """Close SQLite connection."""
        if self._connection:
            self._connection.close()

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get SQLite database overview.

        Returns:
            Dict containing database structure and statistics
        """
        # If table specified, delegate to get_element
        if self.table:
            element_data = self.get_element(self.table)
            if element_data:
                return element_data
            raise ValueError(f"Table not found: {self.table}")

        # Get database file info
        db_size = os.path.getsize(self.db_path)
        db_size_mb = db_size / (1024 * 1024)

        # Get SQLite version and configuration
        version_info = self._execute_single("SELECT sqlite_version() as version")
        pragma_info = {
            'page_size': self._execute_single("PRAGMA page_size")['page_size'],
            'page_count': self._execute_single("PRAGMA page_count")['page_count'],
            'journal_mode': self._execute_single("PRAGMA journal_mode")['journal_mode'],
            'encoding': self._execute_single("PRAGMA encoding")['encoding'],
            'foreign_keys': self._execute_single("PRAGMA foreign_keys")['foreign_keys'],
        }

        # Get all tables
        tables_query = """
            SELECT name, type
            FROM sqlite_master
            WHERE type IN ('table', 'view')
            AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name
        """
        tables = self._execute_query(tables_query)

        # Get table statistics
        table_stats = []
        for table in tables:
            if table['type'] == 'table':
                # Get row count
                count_result = self._execute_single(
                    f"SELECT COUNT(*) as count FROM \"{table['name']}\""
                )
                row_count = count_result['count'] if count_result else 0

                # Get column count
                columns = self._execute_query(f"PRAGMA table_info(\"{table['name']}\")")
                col_count = len(columns)

                # Get index count
                indexes = self._execute_query(
                    f"SELECT COUNT(*) as count FROM sqlite_master "
                    f"WHERE type='index' AND tbl_name='{table['name']}' "
                    f"AND name NOT LIKE 'sqlite_autoindex_%'"
                )
                idx_count = indexes[0]['count'] if indexes else 0

                table_stats.append({
                    'name': table['name'],
                    'type': 'table',
                    'rows': row_count,
                    'columns': col_count,
                    'indexes': idx_count
                })
            else:  # view
                columns = self._execute_query(f"PRAGMA table_info(\"{table['name']}\")")
                table_stats.append({
                    'name': table['name'],
                    'type': 'view',
                    'columns': len(columns)
                })

        # Check for foreign keys
        fk_count = 0
        for table in tables:
            if table['type'] == 'table':
                fks = self._execute_query(f"PRAGMA foreign_key_list(\"{table['name']}\")")
                fk_count += len(fks)

        return {
            'type': 'sqlite_database',
            'path': self.db_path,
            'size': f"{db_size_mb:.2f} MB" if db_size_mb >= 1 else f"{db_size / 1024:.2f} KB",
            'sqlite_version': version_info['version'],
            'configuration': {
                'page_size': f"{pragma_info['page_size']} bytes",
                'page_count': pragma_info['page_count'],
                'total_pages': f"{pragma_info['page_count']} pages × {pragma_info['page_size']} bytes = {pragma_info['page_count'] * pragma_info['page_size'] / 1024 / 1024:.2f} MB",
                'journal_mode': pragma_info['journal_mode'],
                'encoding': pragma_info['encoding'],
                'foreign_keys_enabled': bool(pragma_info['foreign_keys'])
            },
            'statistics': {
                'tables': sum(1 for t in table_stats if t['type'] == 'table'),
                'views': sum(1 for t in table_stats if t['type'] == 'view'),
                'total_rows': sum(t.get('rows', 0) for t in table_stats),
                'foreign_keys': fk_count
            },
            'tables': table_stats,
            'next_steps': [
                f"reveal sqlite://{self.db_path}/<table>     # Inspect specific table",
                f"reveal sqlite://{self.db_path} --check     # Run integrity check",
            ]
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get details about a specific table.

        Args:
            element_name: Table name to inspect

        Returns:
            Dict containing table structure details
        """
        # Verify table exists
        table_check = self._execute_query(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{element_name}'"
        )
        if not table_check:
            return None

        # Get columns
        columns_raw = self._execute_query(f"PRAGMA table_info(\"{element_name}\")")
        columns = []
        for col in columns_raw:
            is_pk = bool(col['pk'])
            # PRIMARY KEY columns are implicitly NOT NULL in SQLite
            is_nullable = not col['notnull'] and not is_pk

            columns.append({
                'name': col['name'],
                'type': col['type'],
                'nullable': is_nullable,
                'default': col['dflt_value'],
                'primary_key': is_pk
            })

        # Get indexes
        indexes_raw = self._execute_query(
            f"SELECT name, sql FROM sqlite_master "
            f"WHERE type='index' AND tbl_name='{element_name}' "
            f"AND name NOT LIKE 'sqlite_autoindex_%'"
        )
        indexes = []
        for idx in indexes_raw:
            # Get index columns
            idx_info = self._execute_query(f"PRAGMA index_info(\"{idx['name']}\")")
            idx_columns = [info['name'] for info in idx_info]

            # Determine if unique
            is_unique = 'UNIQUE' in (idx['sql'] or '').upper()

            indexes.append({
                'name': idx['name'],
                'columns': idx_columns,
                'unique': is_unique
            })

        # Get foreign keys
        fks_raw = self._execute_query(f"PRAGMA foreign_key_list(\"{element_name}\")")
        foreign_keys = []
        for fk in fks_raw:
            foreign_keys.append({
                'column': fk['from'],
                'references_table': fk['table'],
                'references_column': fk['to'],
                'on_update': fk['on_update'],
                'on_delete': fk['on_delete']
            })

        # Get row count
        count_result = self._execute_single(f"SELECT COUNT(*) as count FROM \"{element_name}\"")
        row_count = count_result['count'] if count_result else 0

        # Get CREATE TABLE statement
        create_sql = self._execute_single(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{element_name}'"
        )

        return {
            'type': 'sqlite_table',
            'database': self.db_path,
            'table': element_name,
            'row_count': row_count,
            'columns': columns,
            'indexes': indexes,
            'foreign_keys': foreign_keys,
            'create_statement': create_sql['sql'] if create_sql else None,
            'next_steps': [
                f"reveal sqlite://{self.db_path}              # Back to database overview",
            ]
        }
