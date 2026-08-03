"""SQLite database adapter (sqlite://)."""

import os
import sqlite3
from typing import Dict, Any, List, Optional
from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from ...utils.results import ResultBuilder
from .renderer import SqliteRenderer

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'sqlite_database',
        'description': 'Database overview with tables, indices, and size info',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'sqlite_database'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string', 'const': 'database'},
                'db_path': {'type': 'string'},
                'size_bytes': {'type': 'integer'},
                'tables': {'type': 'array'},
                'indices': {'type': 'array'},
                'version': {'type': 'string'}
            }
        },
        'example': {
            'contract_version': '1.1',
            'type': 'sqlite_database',
            'source': '/path/to/app.db',
            'source_type': 'database',
            'db_path': '/path/to/app.db',
            'size_bytes': 524288,
            'tables': ['users', 'posts', 'comments'],
            'indices': ['idx_users_email', 'idx_posts_created'],
            'version': '3.35.5'
        }
    },
    {
        'type': 'sqlite_table',
        'description': 'Table schema with columns, types, and indices',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'sqlite_table'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string', 'const': 'table'},
                'table_name': {'type': 'string'},
                'columns': {'type': 'array'},
                'indices': {'type': 'array'},
                'row_count': {'type': 'integer'}
            }
        }
    },
    {
        'type': 'sqlite_health',
        'description': 'Database health check results',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'sqlite_health'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string', 'const': 'database'},
                'integrity': {'type': 'boolean'},
                'corruption': {'type': 'boolean'},
                'detections': {'type': 'array'}
            }
        }
    }
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'sqlite:///path/to/app.db',
        'description': 'Database overview with tables and indices',
        'output_type': 'sqlite_database'
    },
    {
        'uri': 'sqlite:///path/to/app.db/users',
        'description': 'Table schema for users table',
        'element': 'users',
        'output_type': 'sqlite_table'
    },
    {
        'uri': 'sqlite:///path/to/app.db --check',
        'description': 'Run integrity checks on database',
        'cli_flag': '--check',
        'output_type': 'sqlite_health'
    },
    {
        'uri': 'sqlite://./relative/path/data.db',
        'description': 'Relative path to database',
        'output_type': 'sqlite_database'
    }
]

_SCHEMA_NOTES = [
    'Opens databases in read-only mode for safety',
    'Supports both absolute (///) and relative (//) paths',
    'Health checks include integrity verification',
    'Built-in SQLite module, no external dependencies'
]


@register_adapter('sqlite')
@register_renderer(SqliteRenderer)
class SQLiteAdapter(ResourceAdapter):
    """Adapter for inspecting SQLite databases via sqlite:// URIs.

    Progressive disclosure pattern for SQLite database exploration.

    Usage:
        reveal sqlite:///path/to/db.db           # Database overview
        reveal sqlite:///path/to/db.db/users     # Table structure
        reveal sqlite:///path/to/db.db --check   # Database health
    """

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    CANONICAL_EMPTY_RESOURCE = ''  # bare sqlite:// must stay empty, not '.'

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for sqlite:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'sqlite',
            'description': 'SQLite database inspection with schema exploration and health checks',
            'uri_syntax': 'sqlite:///path/to/db.db[/table]',
            'query_params': {},
            'elements': {},
            'cli_flags': ['--check'],
            'cli_only_flags': {
                '--check': 'Run SQLite integrity checks (PRAGMA integrity_check, foreign key violations)',
            },
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for sqlite:// adapter.

        Help data loaded from reveal/adapters/help_data/sqlite.yaml
        to reduce function complexity.
        """
        return load_help_data('sqlite') or {}

    def __init__(self, resource: str, query: Optional[str] = None):
        """Initialize SQLite adapter with database path.

        Args:
            resource: sqlite:///path/to/db.db[/table] — accepted with or
                without the sqlite:// prefix; _parse_connection_string
                strips it if present, so both direct construction
                (SQLiteAdapter("sqlite:///x.db")) and router construction
                (bare "/x.db") work unchanged.
            query: Unused — sqlite:// supports no query parameters

        Raises:
            ValueError: When no path is given or the format is invalid
        """
        connection_string = resource

        # Validate connection string is not empty (after required check)
        if not connection_string:
            raise ValueError(
                "SQLiteAdapter requires a non-empty connection string. "
                "Use SQLiteAdapter('sqlite:///path/to/db.db')"
            )

        self.connection_string = connection_string
        self.db_path: Optional[str] = None
        self.table: Optional[str] = None
        self._connection: Optional[sqlite3.Connection] = None
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
            if table_found:
                break
            db_parts.append(part)
            is_db = part.endswith('.db') or part.endswith('.sqlite') or part.endswith('.sqlite3')
            if not is_db:
                continue
            if i + 1 < len(parts):
                self.table = '/'.join(parts[i+1:])
                table_found = True
            break

        self.db_path = '/'.join(db_parts) if db_parts else path_part

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection.

        Returns:
            SQLite connection object

        Raises:
            FileNotFoundError: When database file does not exist
            PermissionError: When database file cannot be read
            IOError: When database cannot be opened (corrupt, encrypted, locked)
        """
        if self._connection is None:
            if not self.db_path:
                raise ValueError("No database path specified")

            if not os.path.exists(self.db_path):
                raise FileNotFoundError(f"Database file not found: {self.db_path}")

            if not os.access(self.db_path, os.R_OK):
                raise PermissionError(f"Database file is not readable: {self.db_path}")

            # Open in read-only mode for safety
            uri = f"file:{self.db_path}?mode=ro"
            try:
                self._connection = sqlite3.connect(uri, uri=True)
                self._connection.row_factory = sqlite3.Row
                # Verify the file is actually a valid SQLite database
                self._connection.execute("SELECT sqlite_version()")
            except sqlite3.DatabaseError as e:
                raise IOError(
                    f"Cannot open '{self.db_path}': file is not a valid SQLite database "
                    f"(corrupt or encrypted): {e}"
                ) from e
            except sqlite3.OperationalError as e:
                raise IOError(f"Cannot open database '{self.db_path}': {e}") from e

        return self._connection

    def _execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts.

        Args:
            query: SQL query to execute, with ? placeholders for any
                caller-supplied value (never interpolate values into the
                query string directly — see BACK-897)
            params: Values to bind to the query's ? placeholders

        Returns:
            List of result rows as dictionaries

        Raises:
            RuntimeError: When query execution fails
            IOError: When database becomes unreadable during execution
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.DatabaseError as e:
            raise IOError(f"Database error during query: {e}") from e
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"Query failed: {e}") from e

    def _execute_single(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute a query and return single result as dict.

        Args:
            query: SQL query to execute
            params: Values to bind to the query's ? placeholders

        Returns:
            Single result row as dictionary, or None if no results
        """
        results = self._execute_query(query, params)
        return results[0] if results else None

    @staticmethod
    def _quote_identifier(name: str) -> str:
        """Quote a SQL identifier (table/index name) for safe interpolation.

        SQL has no parameter-binding syntax for identifiers (only values),
        so table/index names can't use `?` placeholders the way WHERE-clause
        values can. Doubling embedded double-quotes is the standard SQL
        identifier-escaping rule (mirrors how a literal `"` inside a quoted
        identifier is written `""`) — defense in depth on top of the
        exact-match existence check every caller already performs before
        reaching an identifier-interpolation site (BACK-897).
        """
        return name.replace('"', '""')

    def __del__(self):
        """Close SQLite connection."""
        if hasattr(self, '_connection') and self._connection:
            self._connection.close()

    def _get_pragma_info(self) -> Dict[str, Any]:
        """Get SQLite PRAGMA information.

        Returns:
            Dict with page_size, page_count, journal_mode, encoding, foreign_keys

        Raises:
            IOError: When PRAGMA queries fail (database may be corrupt)
        """
        pragmas = {
            'page_size': self._execute_single("PRAGMA page_size"),
            'page_count': self._execute_single("PRAGMA page_count"),
            'journal_mode': self._execute_single("PRAGMA journal_mode"),
            'encoding': self._execute_single("PRAGMA encoding"),
            'foreign_keys': self._execute_single("PRAGMA foreign_keys"),
        }
        for name, result in pragmas.items():
            if result is None:
                raise IOError(
                    f"PRAGMA {name} returned no results — database may be corrupt: {self.db_path}"
                )

        return {
            'page_size': pragmas['page_size']['page_size'],
            'page_count': pragmas['page_count']['page_count'],
            'journal_mode': pragmas['journal_mode']['journal_mode'],
            'encoding': pragmas['encoding']['encoding'],
            'foreign_keys': pragmas['foreign_keys']['foreign_keys'],
        }

    def _get_table_stats(self, tables: list) -> list:
        """Get statistics for all tables and views.

        Args:
            tables: List of table/view dicts with 'name' and 'type'

        Returns:
            List of table statistics
        """
        table_stats = []
        for table in tables:
            quoted_name = self._quote_identifier(table['name'])
            if table['type'] == 'table':
                # Get row count
                count_result = self._execute_single(
                    f'SELECT COUNT(*) as count FROM "{quoted_name}"'
                )
                row_count = count_result['count'] if count_result else 0

                # Get column count
                columns = self._execute_query(f'PRAGMA table_info("{quoted_name}")')
                col_count = len(columns)

                # Get index count
                indexes = self._execute_query(
                    "SELECT COUNT(*) as count FROM sqlite_master "
                    "WHERE type='index' AND tbl_name=? "
                    "AND name NOT LIKE 'sqlite_autoindex_%'",
                    (table['name'],)
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
                columns = self._execute_query(f'PRAGMA table_info("{quoted_name}")')
                table_stats.append({
                    'name': table['name'],
                    'type': 'view',
                    'columns': len(columns)
                })
        return table_stats

    def _count_foreign_keys(self, tables: list) -> int:
        """Count foreign keys across all tables.

        Args:
            tables: List of table dicts

        Returns:
            Total count of foreign keys
        """
        fk_count = 0
        for table in tables:
            if table['type'] == 'table':
                quoted_name = self._quote_identifier(table['name'])
                fks = self._execute_query(f'PRAGMA foreign_key_list("{quoted_name}")')
                fk_count += len(fks)
        return fk_count

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

        # Validate connection first (checks file existence, permissions, and validity)
        self._get_connection()

        # db_path is guaranteed non-None after successful _parse_connection_string
        if not self.db_path:
            raise ValueError("No database path available after connection")

        # Get database file info
        db_size = os.path.getsize(self.db_path)
        db_size_mb = db_size / (1024 * 1024)

        # Get SQLite version
        version_info = self._execute_single("SELECT sqlite_version() as version")
        if version_info is None:
            raise IOError(f"Failed to read SQLite version — database may be corrupt: {self.db_path}")

        # Get PRAGMA information
        pragma_info = self._get_pragma_info()

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
        table_stats = self._get_table_stats(tables)

        # Count foreign keys
        fk_count = self._count_foreign_keys(tables)

        return ResultBuilder.create(
            result_type='sqlite_database',
            source=self.db_path,
            source_type='database',
            contract_version='1.1',
            data={
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
        )

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get details about a specific table.

        Args:
            element_name: Table name to inspect

        Returns:
            Dict containing table structure details
        """
        # Verify table exists (bound parameter — BACK-897, see _quote_identifier)
        table_check = self._execute_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (element_name,)
        )
        if not table_check:
            return None

        quoted_name = self._quote_identifier(element_name)

        # Get columns
        columns_raw = self._execute_query(f'PRAGMA table_info("{quoted_name}")')
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
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name=? "
            "AND name NOT LIKE 'sqlite_autoindex_%'",
            (element_name,)
        )
        indexes = []
        for idx in indexes_raw:
            # Get index columns (server-sourced name, still quoted as an identifier)
            quoted_idx_name = self._quote_identifier(idx['name'])
            idx_info = self._execute_query(f'PRAGMA index_info("{quoted_idx_name}")')
            idx_columns = [info['name'] for info in idx_info]

            # Determine if unique
            is_unique = 'UNIQUE' in (idx['sql'] or '').upper()

            indexes.append({
                'name': idx['name'],
                'columns': idx_columns,
                'unique': is_unique
            })

        # Get foreign keys
        fks_raw = self._execute_query(f'PRAGMA foreign_key_list("{quoted_name}")')
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
        count_result = self._execute_single(f'SELECT COUNT(*) as count FROM "{quoted_name}"')
        row_count = count_result['count'] if count_result else 0

        # Get CREATE TABLE statement
        create_sql = self._execute_single(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (element_name,)
        )

        return ResultBuilder.create(
            result_type='sqlite_table',
            source=self.db_path,
            source_type='table',
            contract_version='1.1',
            data={
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
        )
