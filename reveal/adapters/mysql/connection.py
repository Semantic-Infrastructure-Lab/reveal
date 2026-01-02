"""MySQL connection management and credential resolution."""

import os
import subprocess
from typing import Dict, Any, Optional

try:
    import pymysql
    import pymysql.cursors
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


class MySQLConnection:
    """Handles MySQL connection lifecycle and credential resolution.

    Manages connection URI parsing, credential resolution from multiple sources
    (TIA secrets, environment variables, ~/.my.cnf), and query execution.
    """

    def __init__(self, connection_string: str = ""):
        """Initialize connection with URI.

        Args:
            connection_string: mysql://[user:pass@]host[:port][/element]

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
        self.host = None
        self.port = 3306
        self.user = None
        self.password = None
        self.database = None
        self.element = None
        self._parse_connection_string(connection_string)
        self._resolve_credentials()
        self._connection = None

    def _parse_connection_string(self, uri: str):
        """Parse mysql:// URI into components.

        Args:
            uri: Connection URI (mysql://[user:pass@]host[:port][/element])
        """
        if not uri or uri == "mysql://":
            self.host = "localhost"
            return

        # Remove mysql:// prefix
        if uri.startswith("mysql://"):
            uri = uri[8:]

        # Parse user:pass@host:port/element
        if '@' in uri:
            auth, rest = uri.split('@', 1)
            if ':' in auth:
                self.user, self.password = auth.split(':', 1)
            else:
                self.user = auth
            uri = rest

        # Parse host:port/element
        if '/' in uri:
            host_port, element = uri.split('/', 1)
            self.element = element
        else:
            host_port = uri

        # Parse host:port
        if ':' in host_port:
            self.host, port_str = host_port.split(':', 1)
            self.port = int(port_str)
        else:
            self.host = host_port or "localhost"

    def _try_tia_secrets(self) -> bool:
        """Try to load credentials from TIA secrets.

        Returns:
            True if credentials were loaded, False otherwise
        """
        if not self.host:
            return False

        try:
            result = subprocess.run(
                ['tia', 'secrets', 'get', f'mysql:{self.host}'],
                capture_output=True,
                text=True,
                timeout=5
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

        if result.returncode != 0 or not result.stdout:
            return False

        # Expected format: user:password
        secret = result.stdout.strip()
        if ':' not in secret:
            return False

        self.user, self.password = secret.split(':', 1)
        return True

    def _resolve_credentials(self):
        """Resolve credentials from multiple sources.

        Priority:
        1. URI credentials (already parsed)
        2. TIA secrets (tia secrets get mysql:<host>)
        3. Environment variables
        4. ~/.my.cnf
        """
        # URI credentials take precedence (already set)
        if self.user and self.password:
            return

        # Try TIA secrets
        if self._try_tia_secrets():
            return

        # Try environment variables
        self.host = self.host or os.environ.get('MYSQL_HOST', 'localhost')
        self.user = self.user or os.environ.get('MYSQL_USER')
        self.password = self.password or os.environ.get('MYSQL_PASSWORD')
        self.database = self.database or os.environ.get('MYSQL_DATABASE')

        # ~/.my.cnf is handled by pymysql automatically

    def get_connection(self):
        """Get MySQL connection (lazy initialization).

        Returns:
            pymysql connection object

        Raises:
            Exception: Connection errors
        """
        if self._connection:
            return self._connection

        connection_params = {
            'host': self.host or 'localhost',
            'port': self.port,
            'read_default_file': os.path.expanduser('~/.my.cnf'),
        }

        if self.user:
            connection_params['user'] = self.user
        if self.password:
            connection_params['password'] = self.password
        if self.database:
            connection_params['database'] = self.database

        try:
            self._connection = pymysql.connect(**connection_params)
            return self._connection
        except Exception as e:
            raise Exception(
                f"Failed to connect to MySQL at {self.host}:{self.port}\n"
                f"Error: {str(e)}\n"
                f"Hint: Check credentials, network, or try:\n"
                f"  tia secrets set mysql:{self.host} user:password"
            )

    def convert_decimals(self, obj):
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

    def execute_query(self, query: str) -> list:
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
            return self.convert_decimals(results)

    def execute_single(self, query: str) -> Optional[Dict[str, Any]]:
        """Execute query and return first row.

        Args:
            query: SQL query

        Returns:
            First row as dict, or None
        """
        results = self.execute_query(query)
        return results[0] if results else None

    def close(self):
        """Close MySQL connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None
