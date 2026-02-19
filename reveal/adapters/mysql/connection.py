"""MySQL connection management and credential resolution."""

import os
from typing import Dict, Any, Optional, cast
from urllib.parse import urlparse, unquote

try:
    import pymysql
    import pymysql.cursors
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


class MySQLConnection:
    """Handles MySQL connection lifecycle and credential resolution.

    Manages connection URI parsing, credential resolution from multiple sources
    (environment variables, ~/.my.cnf), and query execution.
    """

    def __init__(self, connection_string: str):
        """Initialize connection with URI.

        Args:
            connection_string: mysql://[user:pass@]host[:port][/element]
                              Can be empty string for bare mysql:// (uses .my.cnf)

        Raises:
            ImportError: If pymysql is not installed
        """
        if not PYMYSQL_AVAILABLE:
            raise ImportError(
                "pymysql is required for mysql:// adapter.\n"
                "Install with: pip install reveal-cli[database]\n"
                "Or: pip install pymysql"
            )

        self.connection_string = connection_string
        self.host: Optional[str] = None
        self.port: Optional[int] = None  # Don't default to 3306 - let pymysql read from .my.cnf
        self.user: Optional[str] = None
        self.password: Optional[str] = None
        self.database: Optional[str] = None
        self.element: Optional[str] = None
        self._parse_connection_string(connection_string)
        self._resolve_credentials()
        self._connection = None

    def _parse_connection_string(self, uri: str):
        """Parse mysql:// URI into components.

        Args:
            uri: Connection URI (mysql://[user:pass@]host[:port][/element])

        Uses urlparse so passwords containing '@' or ':' are handled correctly
        when percent-encoded (e.g. mysql://user:p%40ssword@host/db).
        """
        if not uri or uri == "mysql://":
            # Don't set host here - let _resolve_credentials handle defaults
            # This allows MYSQL_HOST env var and ~/.my.cnf to take effect
            return

        parsed = urlparse(uri)

        if parsed.username:
            self.user = unquote(parsed.username)
        if parsed.password:
            self.password = unquote(parsed.password)
        if parsed.hostname:
            self.host = parsed.hostname
        if parsed.port:
            self.port = parsed.port

        # Path starts with '/', strip it to get the element (e.g. /tables → tables)
        if parsed.path and parsed.path.lstrip('/'):
            self.element = parsed.path.lstrip('/')

    def _resolve_credentials(self):
        """Resolve credentials from multiple sources.

        Priority:
        1. URI credentials (already parsed)
        2. Environment variables (MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE)
        3. ~/.my.cnf (handled automatically by pymysql when params not explicitly set)

        Note: We don't apply defaults here - that's done in get_connection() only if
        neither env vars nor .my.cnf provide values. This allows .my.cnf to work correctly.
        """
        # URI credentials take precedence (already set)
        if self.user and self.password:
            return

        # Try environment variables (but don't apply defaults yet)
        self.host = self.host or os.environ.get('MYSQL_HOST')
        port_env = os.environ.get('MYSQL_PORT')
        self.port = self.port or (int(port_env) if port_env else None)
        self.user = self.user or os.environ.get('MYSQL_USER')
        self.password = self.password or os.environ.get('MYSQL_PASSWORD')
        self.database = self.database or os.environ.get('MYSQL_DATABASE')

    def get_connection(self):
        """Get MySQL connection (lazy initialization).

        Returns:
            pymysql connection object

        Raises:
            Exception: Connection errors
        """
        if self._connection:
            return self._connection

        # Always pass read_default_file so pymysql can read ~/.my.cnf
        connection_params: Dict[str, Any] = {
            'read_default_file': os.path.expanduser('~/.my.cnf'),
        }

        # Only pass parameters that were explicitly set (URI or env vars)
        # This allows pymysql to read missing values from .my.cnf
        # If we don't pass them, pymysql reads from .my.cnf then defaults to localhost:3306
        if self.host:
            connection_params['host'] = self.host
        if self.port is not None:
            connection_params['port'] = self.port
        if self.user:
            connection_params['user'] = self.user
        if self.password:
            connection_params['password'] = self.password
        if self.database:
            connection_params['database'] = self.database

        # DON'T apply defaults here - let pymysql handle it
        # pymysql will: 1) Read from .my.cnf, 2) Default to localhost:3306 if not in file

        try:
            self._connection = pymysql.connect(**connection_params)
            return self._connection
        except Exception as e:
            host_display = self.host or 'localhost'
            port_display = self.port or 3306
            raise Exception(
                f"Failed to connect to MySQL at {host_display}:{port_display}\n"
                f"Error: {str(e)}\n"
                f"Hint: Set MYSQL_* env vars or configure ~/.my.cnf"
            )

    def convert_decimals(self, obj) -> Any:
        """Convert Decimal, datetime, and bytes objects for JSON serialization."""
        from decimal import Decimal
        from datetime import datetime, date, time, timedelta

        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, (date, time)):
            return obj.isoformat()
        elif isinstance(obj, timedelta):
            return str(obj)
        elif isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        elif isinstance(obj, dict):
            return {k: self.convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_decimals(item) for item in obj]
        return obj

    def execute_query(self, query: str) -> list[Any]:
        """Execute a SQL query and return results.

        Args:
            query: SQL query to execute

        Returns:
            List of result rows (as dicts)
        """
        conn = self.get_connection()
        cursor_class = pymysql.cursors.DictCursor if PYMYSQL_AVAILABLE else None
        with conn.cursor(cursor_class) as cursor:
            cursor.execute(query)
            results = cursor.fetchall()
            return cast(list[Any], self.convert_decimals(results))

    def execute_single(self, query: str) -> Optional[Dict[str, Any]]:
        """Execute query and return first row.

        Args:
            query: SQL query

        Returns:
            First row as dict, or None
        """
        results = self.execute_query(query)
        return results[0] if results else None

    def get_snapshot_context(self) -> Dict[str, Any]:
        """Get standardized timing context for all metrics.

        Returns timing information using MySQL's clock for accuracy.
        All timestamps in UTC ISO 8601 format.

        Returns:
            Dict with:
            - snapshot_time: When this snapshot was taken (ISO 8601)
            - server_start_time: When MySQL server started (ISO 8601)
            - uptime_seconds: Server uptime in seconds
            - measurement_window: Human-readable uptime (e.g., "23d 23h (since server start)")
        """
        from datetime import datetime, timezone

        # Get MySQL's current timestamp (not local machine time)
        mysql_time = self.execute_single("SELECT UNIX_TIMESTAMP() as timestamp")
        assert mysql_time is not None, "Failed to get MySQL timestamp"
        snapshot_timestamp = int(mysql_time['timestamp'])
        snapshot_time = datetime.fromtimestamp(snapshot_timestamp, timezone.utc)

        # Get server uptime
        status_vars = {row['Variable_name']: row['Value']
                      for row in self.execute_query("SHOW GLOBAL STATUS WHERE Variable_name = 'Uptime'")}
        uptime_seconds = int(status_vars.get('Uptime', 0))

        # Calculate server start time
        server_start_timestamp = snapshot_timestamp - uptime_seconds
        server_start_time = datetime.fromtimestamp(server_start_timestamp, timezone.utc)

        uptime_days = uptime_seconds // 86400
        uptime_hours = (uptime_seconds % 86400) // 3600

        return {
            'snapshot_time': snapshot_time.isoformat(),
            'server_start_time': server_start_time.isoformat(),
            'uptime_seconds': uptime_seconds,
            'measurement_window': f'{uptime_days}d {uptime_hours}h (since server start)',
        }

    def get_performance_schema_status(self) -> Dict[str, Any]:
        """Detect if performance_schema counters were reset recently.

        Uses heuristic: if server uptime is much longer than oldest
        performance_schema event (>1 hour gap), counters were likely reset.

        Returns:
            Dict with:
            - enabled: bool - Whether performance_schema is enabled
            - counters_reset_detected: bool - Whether reset was detected
            - likely_reset_time: Optional[str] - ISO timestamp of likely reset, or None
        """
        from datetime import datetime, timezone

        # Check if performance_schema is enabled
        try:
            ps_status = self.execute_single(
                "SELECT @@global.performance_schema as enabled"
            )
            assert ps_status is not None, "Failed to query performance_schema status"
            ps_enabled = bool(ps_status['enabled'])
        except Exception:
            # If query fails, assume disabled
            return {
                'enabled': False,
                'counters_reset_detected': False,
                'likely_reset_time': None,
            }

        if not ps_enabled:
            return {
                'enabled': False,
                'counters_reset_detected': False,
                'likely_reset_time': None,
            }

        # Get timing context
        timing = self.get_snapshot_context()
        snapshot_timestamp = int(datetime.fromisoformat(timing['snapshot_time']).timestamp())
        uptime_seconds = timing['uptime_seconds']

        # Find oldest performance_schema event
        try:
            oldest_event = self.execute_single("""
                SELECT MIN(TIMER_START) / 1000000000000 as oldest_timestamp
                FROM performance_schema.events_statements_summary_by_digest
                WHERE TIMER_START > 0
            """)
        except Exception:
            # If query fails (table doesn't exist, etc), assume no reset
            return {
                'enabled': True,
                'counters_reset_detected': False,
                'likely_reset_time': None,
            }

        if not oldest_event or not oldest_event.get('oldest_timestamp'):
            # No events recorded yet
            return {
                'enabled': True,
                'counters_reset_detected': False,
                'likely_reset_time': None,
            }

        oldest_timestamp = float(oldest_event['oldest_timestamp'])
        oldest_seconds_ago = snapshot_timestamp - oldest_timestamp

        # If oldest event is much newer than server start (>1 hour gap), reset likely
        # This means: server has been up for uptime_seconds, but oldest p_s event
        # is only oldest_seconds_ago old. Gap = uptime_seconds - oldest_seconds_ago
        gap_seconds = uptime_seconds - oldest_seconds_ago

        if gap_seconds > 3600:  # More than 1 hour gap
            reset_time = datetime.fromtimestamp(oldest_timestamp, timezone.utc)
            return {
                'enabled': True,
                'counters_reset_detected': True,
                'likely_reset_time': reset_time.isoformat(),
            }

        return {
            'enabled': True,
            'counters_reset_detected': False,
            'likely_reset_time': None,
        }

    def close(self):
        """Close MySQL connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass  # best-effort close; ignore already-closed or broken socket
            self._connection = None
