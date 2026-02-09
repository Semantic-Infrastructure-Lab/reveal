"""MySQL storage analysis."""

from typing import Dict, Any


class StorageAnalyzer:
    """Analyzes MySQL storage usage.

    Provides database and table-level storage metrics including data size,
    index size, and row counts.
    """

    def __init__(self, connection):
        """Initialize with MySQL connection.

        Args:
            connection: MySQLConnection instance
        """
        self.conn = connection

    def get_storage(self) -> Dict[str, Any]:
        """Get storage usage by database.

        Returns:
            Dict with database sizes, table counts, data/index breakdown,
            plus snapshot timing context for tracking growth trends
        """
        timing = self.conn.get_snapshot_context()

        db_sizes = self.conn.execute_query("""
            SELECT
                table_schema as db_name,
                COUNT(*) as table_count,
                ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2)
                    as size_gb,
                ROUND(SUM(data_length) / 1024 / 1024 / 1024, 2) as data_gb,
                ROUND(SUM(index_length) / 1024 / 1024 / 1024, 2) as index_gb
            FROM information_schema.tables
            WHERE table_schema NOT IN
                ('information_schema', 'mysql', 'performance_schema', 'sys')
            GROUP BY table_schema
            ORDER BY size_gb DESC
        """)

        return {
            'type': 'storage',
            **timing,
            'databases': db_sizes,
        }

    def get_database_storage(self, db_name: str) -> Dict[str, Any]:
        """Get storage for specific database.

        Args:
            db_name: Database name

        Returns:
            Dict with table-level storage breakdown plus snapshot timing context
        """
        timing = self.conn.get_snapshot_context()

        tables = self.conn.execute_query(f"""
            SELECT
                table_name,
                engine,
                table_rows,
                ROUND((data_length + index_length) / 1024 / 1024, 2) as size_mb
            FROM information_schema.tables
            WHERE table_schema = '{db_name}'
            ORDER BY (data_length + index_length) DESC
        """)

        return {
            'type': 'database_storage',
            **timing,
            'database': db_name,
            'tables': tables,
        }
