"""MySQL database adapter (mysql://)."""

import os
import subprocess
from typing import Dict, Any, Optional
from .base import ResourceAdapter, register_adapter

try:
    import pymysql
    import pymysql.cursors
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


@register_adapter('mysql')
class MySQLAdapter(ResourceAdapter):
    """Adapter for inspecting MySQL databases via mysql:// URIs.

    Progressive disclosure pattern for DBA-friendly database health inspection.

    Usage:
        reveal mysql://localhost                  # Health overview
        reveal mysql://localhost/connections      # Connection details
        reveal mysql://localhost/innodb           # InnoDB status
        reveal mysql://localhost --check          # Health checks
    """

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for mysql:// adapter."""
        return {
            'name': 'mysql',
            'description': 'MySQL database inspection - progressive disclosure of health, connections, InnoDB, replication',
            'syntax': 'mysql://[user:password@]host[:port][/element]',
            'examples': [
                {
                    'uri': 'mysql://localhost',
                    'description': 'Health overview (connections, InnoDB, replication, storage)'
                },
                {
                    'uri': 'mysql://localhost/connections',
                    'description': 'Detailed connection info and processlist'
                },
                {
                    'uri': 'mysql://localhost/innodb',
                    'description': 'InnoDB buffer pool, locks, pending I/O'
                },
                {
                    'uri': 'mysql://localhost/replication',
                    'description': 'Replication status and lag'
                },
                {
                    'uri': 'mysql://localhost/storage',
                    'description': 'Storage usage by database'
                },
                {
                    'uri': 'mysql://localhost --check',
                    'description': 'Run health checks with thresholds'
                },
            ],
            'elements': {
                'connections': 'Connection details and processlist',
                'performance': 'Query performance metrics',
                'innodb': 'InnoDB engine status',
                'replication': 'Replication status and lag',
                'storage': 'Storage usage by database',
                'storage/<db>': 'Specific database tables',
                'errors': 'Error indicators',
                'variables': 'Server configuration',
                'health': 'Comprehensive health check',
                'databases': 'Database list',
            },
            'features': [
                'DBA health snapshot (~100 tokens vs 5000+ for raw SQL)',
                'Progressive disclosure (structure → element → detail)',
                'Industry-standard tuning ratios (table scans, thread cache, temp tables, etc.)',
                'Time context accuracy (uses MySQL clock, not local machine)',
                'Index usage analysis (most used, unused)',
                'Health checks with pass/warn/fail thresholds',
                'Credential resolution (TIA secrets, env vars, ~/.my.cnf)',
                'Token-efficient for AI agent consumption',
            ],
            'try_now': [
                "reveal mysql://localhost",
                "reveal mysql://localhost/connections",
                "reveal mysql://localhost --check",
            ],
            'workflows': [
                {
                    'name': 'Quick Health Check',
                    'scenario': 'Need to quickly assess database health',
                    'steps': [
                        "reveal mysql://localhost              # Overview",
                        "reveal mysql://localhost --check      # Health checks",
                        "reveal mysql://localhost/replication  # If issues found",
                    ],
                },
                {
                    'name': 'Debug Slow Performance',
                    'scenario': 'Database is slow, need to find bottleneck',
                    'steps': [
                        "reveal mysql://localhost/performance  # Check slow queries",
                        "reveal mysql://localhost/innodb       # Buffer pool hit rate",
                        "reveal mysql://localhost/connections  # Check for blocking",
                    ],
                },
            ],
            'anti_patterns': [
                {
                    'bad': "mysql -e 'SHOW STATUS' | grep -i innodb",
                    'good': "reveal mysql://localhost/innodb",
                    'why': "50x fewer tokens, structured output, DBA-relevant signals only",
                },
                {
                    'bad': "mysql -e 'SHOW PROCESSLIST\\G'",
                    'good': "reveal mysql://localhost/connections",
                    'why': "Categorized by state, highlights long-running queries",
                },
            ],
            'notes': [
                'Requires pymysql: pip install reveal-cli[database]',
                'Credentials: URI > TIA secrets > env vars > ~/.my.cnf',
                'Env vars: MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE',
                'Health thresholds: connections <80%, buffer pool >99%, replication lag <60s',
                'DBA tuning ratios: table scans <25%, thread cache miss <10%, temp tables on disk <25%',
                'All metrics show "since server start" with accurate MySQL timestamps',
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal help://env - Environment variables',
                'reveal help://python - Python runtime inspection',
            ]
        }

    def __init__(self, connection_string: str = ""):
        """Initialize MySQL adapter with connection details.

        Args:
            connection_string: mysql://[user:pass@]host[:port][/element]
        """
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
        if self.host:
            try:
                result = subprocess.run(
                    ['tia', 'secrets', 'get', f'mysql:{self.host}'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and result.stdout:
                    # Expected format: user:password
                    secret = result.stdout.strip()
                    if ':' in secret:
                        self.user, self.password = secret.split(':', 1)
                        return
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Try environment variables
        self.host = self.host or os.environ.get('MYSQL_HOST', 'localhost')
        self.user = self.user or os.environ.get('MYSQL_USER')
        self.password = self.password or os.environ.get('MYSQL_PASSWORD')
        self.database = self.database or os.environ.get('MYSQL_DATABASE')

        # ~/.my.cnf is handled by pymysql automatically

    def _get_connection(self):
        """Get MySQL connection (lazy initialization).

        Returns:
            pymysql connection object

        Raises:
            ImportError: If pymysql not installed
            Exception: Connection errors
        """
        if self._connection:
            return self._connection

        if not PYMYSQL_AVAILABLE:
            raise ImportError(
                "pymysql is required for mysql:// adapter.\n"
                "Install with: pip install reveal-cli[database]\n"
                "Or: pip install pymysql"
            )

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
                f"Error: {e}\n\n"
                "Troubleshooting:\n"
                "  1. Check credentials (tia secrets get mysql:<host>)\n"
                "  2. Check environment: MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD\n"
                "  3. Check ~/.my.cnf configuration\n"
                "  4. Verify MySQL is running and accessible"
            )

    def _convert_decimals(self, obj):
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
            return {k: self._convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_decimals(item) for item in obj]
        return obj

    def _execute_query(self, query: str) -> list:
        """Execute a SQL query and return results.

        Args:
            query: SQL query to execute

        Returns:
            List of result rows (as dicts)
        """
        conn = self._get_connection()
        cursor_class = pymysql.cursors.DictCursor if PYMYSQL_AVAILABLE else None
        with conn.cursor(cursor_class) as cursor:
            cursor.execute(query)
            results = cursor.fetchall()
            return self._convert_decimals(results)

    def _execute_single(self, query: str) -> Optional[Dict[str, Any]]:
        """Execute query and return first row.

        Args:
            query: SQL query

        Returns:
            First row as dict, or None
        """
        results = self._execute_query(query)
        return results[0] if results else None

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get MySQL health overview (DBA snapshot).

        Returns:
            Dict containing health signals (~100 tokens)
        """
        from datetime import datetime, timezone

        # Get server version and uptime
        version_info = self._execute_single("SELECT VERSION() as version")
        status_vars = {row['Variable_name']: row['Value']
                      for row in self._execute_query("SHOW GLOBAL STATUS")}

        uptime_seconds = int(status_vars.get('Uptime', 0))
        uptime_days = uptime_seconds // 86400
        uptime_hours = (uptime_seconds % 86400) // 3600
        uptime_mins = (uptime_seconds % 3600) // 60

        # Calculate server start time using MySQL's clock (not local machine clock)
        mysql_time = self._execute_single("SELECT UNIX_TIMESTAMP() as timestamp")
        mysql_timestamp = int(mysql_time['timestamp'])
        server_start_timestamp = mysql_timestamp - uptime_seconds
        server_start_time = datetime.fromtimestamp(server_start_timestamp, timezone.utc)

        # Connection health
        max_connections = int(self._execute_single(
            "SHOW VARIABLES LIKE 'max_connections'"
        )['Value'])
        current_connections = int(status_vars.get('Threads_connected', 0))
        max_used_connections = int(status_vars.get('Max_used_connections', 0))

        connection_pct = (current_connections / max_connections * 100) if max_connections else 0
        max_used_pct = (max_used_connections / max_connections * 100) if max_connections else 0

        connection_status = '✅' if connection_pct < 80 else '⚠️' if connection_pct < 95 else '❌'
        max_used_status = '⚠️' if max_used_pct >= 100 else '✅'

        # Performance (counters are cumulative since server start)
        questions = int(status_vars.get('Questions', 0))
        slow_queries = int(status_vars.get('Slow_queries', 0))
        qps = questions / uptime_seconds if uptime_seconds else 0
        slow_pct = (slow_queries / questions * 100) if questions else 0
        threads_running = int(status_vars.get('Threads_running', 0))

        # InnoDB health (counters are cumulative since server start)
        innodb_buffer_pool_reads = int(status_vars.get('Innodb_buffer_pool_reads', 0))
        innodb_buffer_pool_read_requests = int(status_vars.get('Innodb_buffer_pool_read_requests', 1))
        buffer_hit_rate = 100 * (1 - innodb_buffer_pool_reads / innodb_buffer_pool_read_requests) if innodb_buffer_pool_read_requests else 0
        buffer_status = '✅' if buffer_hit_rate > 99 else '⚠️' if buffer_hit_rate > 95 else '❌'

        row_lock_waits = int(status_vars.get('Innodb_row_lock_waits', 0))
        deadlocks = int(status_vars.get('Innodb_deadlocks', 0))

        # Resource limits
        open_files = int(status_vars.get('Open_files', 0))
        open_files_limit = int(self._execute_single(
            "SHOW VARIABLES LIKE 'open_files_limit'"
        )['Value'])
        open_files_pct = (open_files / open_files_limit * 100) if open_files_limit > 0 else 0

        open_files_status = '✅' if open_files_pct < 75 else '⚠️' if open_files_pct < 90 else '❌'

        # Replication (check if slave)
        try:
            slave_status = self._execute_single("SHOW SLAVE STATUS")
            if slave_status:
                replication_role = "Slave"
                lag = slave_status.get('Seconds_Behind_Master', 'Unknown')
                io_running = slave_status.get('Slave_IO_Running', 'No') == 'Yes'
                sql_running = slave_status.get('Slave_SQL_Running', 'No') == 'Yes'
                replication_info = {
                    'role': replication_role,
                    'lag': lag,
                    'io_running': io_running,
                    'sql_running': sql_running,
                }
            else:
                # Check if master
                slave_hosts = self._execute_query("SHOW SLAVE HOSTS")
                if slave_hosts:
                    replication_info = {
                        'role': 'Master',
                        'slaves': len(slave_hosts),
                    }
                else:
                    replication_info = {'role': 'Standalone'}
        except Exception as e:
            replication_info = {'role': 'Unknown', 'error': str(e)}

        # Storage
        db_sizes = self._execute_query("""
            SELECT
                table_schema as db_name,
                ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) as size_gb
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            GROUP BY table_schema
            ORDER BY size_gb DESC
        """)

        total_size_gb = sum(row['size_gb'] for row in db_sizes)
        largest_db = db_sizes[0] if db_sizes else None

        # Overall health
        health_issues = []
        if connection_pct > 80:
            health_issues.append(f"High connection usage ({connection_pct:.1f}%)")
        if buffer_hit_rate < 99:
            health_issues.append(f"Low buffer pool hit rate ({buffer_hit_rate:.2f}%)")
        if replication_info.get('role') == 'Slave' and replication_info.get('lag', 0) and replication_info['lag'] != 'Unknown':
            if int(replication_info['lag']) > 60:
                health_issues.append(f"Replication lag ({replication_info['lag']}s)")

        health_status = '✅ HEALTHY' if not health_issues else '⚠️ WARNING' if len(health_issues) < 3 else '❌ CRITICAL'

        return {
            'type': 'mysql_server',
            'server': f"{self.host}:{self.port}",
            'version': version_info['version'],
            'uptime': f"{uptime_days}d {uptime_hours}h {uptime_mins}m",
            'server_start_time': server_start_time.isoformat(),
            'connection_health': {
                'current': current_connections,
                'max': max_connections,
                'percentage': f"{connection_pct:.1f}%",
                'max_used_ever': max_used_connections,
                'max_used_pct': f"{max_used_pct:.1f}%",
                'max_used_status': max_used_status,
                'status': connection_status,
                'note': 'If max_used_pct was 100%, connections were rejected (since server start)'
            },
            'performance': {
                'qps': f"{qps:.1f}",
                'slow_queries': f"{slow_queries} total ({slow_pct:.2f}% of all queries since server start)",
                'threads_running': threads_running,
            },
            'innodb_health': {
                'buffer_pool_hit_rate': f"{buffer_hit_rate:.2f}% (since server start)",
                'status': buffer_status,
                'row_lock_waits': f"{row_lock_waits} (since server start)",
                'deadlocks': f"{deadlocks} (since server start)",
            },
            'replication': replication_info,
            'storage': {
                'total_size_gb': total_size_gb,
                'database_count': len(db_sizes),
                'largest_db': f"{largest_db['db_name']} ({largest_db['size_gb']} GB)" if largest_db else 'N/A',
            },
            'resource_limits': {
                'open_files': {
                    'current': open_files,
                    'limit': open_files_limit,
                    'percentage': f'{open_files_pct:.1f}%',
                    'status': open_files_status,
                    'note': 'Approaching limit (>75%) can cause "too many open files" errors'
                }
            },
            'health_status': health_status,
            'health_issues': health_issues if health_issues else ['No issues detected'],
            'next_steps': [
                f"reveal mysql://{self.host}/connections       # Connection details",
                f"reveal mysql://{self.host}/performance       # Query performance",
                f"reveal mysql://{self.host}/innodb            # InnoDB details",
                f"reveal mysql://{self.host} --check           # Run health checks",
            ]
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get details about a specific element.

        Args:
            element_name: Element type (connections, innodb, replication, etc.)

        Returns:
            Dict with element details
        """
        handlers = {
            'connections': self._get_connections,
            'performance': self._get_performance,
            'innodb': self._get_innodb,
            'replication': self._get_replication,
            'storage': self._get_storage,
            'errors': self._get_errors,
            'variables': self._get_variables,
            'health': self._get_health,
            'databases': self._get_databases,
            'indexes': self._get_indexes,
            'slow-queries': self._get_slow_queries,
        }

        # Handle storage/<db_name> pattern
        if element_name.startswith('storage/'):
            db_name = element_name.split('/', 1)[1]
            return self._get_database_storage(db_name)

        handler = handlers.get(element_name)
        if handler:
            return handler()
        return None

    def _get_connections(self) -> Dict[str, Any]:
        """Get connection details and processlist."""
        processlist = self._execute_query("SHOW FULL PROCESSLIST")

        # Group by state
        by_state = {}
        long_running = []

        for proc in processlist:
            state = proc.get('State') or 'None'
            by_state[state] = by_state.get(state, 0) + 1

            # Flag long-running queries (>5s)
            time_val = proc.get('Time', 0)
            if time_val and int(time_val) > 5:
                info = proc.get('Info') or ''
                long_running.append({
                    'id': proc.get('Id'),
                    'user': proc.get('User'),
                    'db': proc.get('db'),
                    'time': proc.get('Time'),
                    'state': proc.get('State'),
                    'info': info[:100] if info else '',  # Truncate query
                })

        return {
            'type': 'connections',
            'total_connections': len(processlist),
            'by_state': by_state,
            'long_running_queries': long_running,
        }

    def _get_performance(self) -> Dict[str, Any]:
        """Get query performance metrics."""
        from datetime import datetime, timezone

        status_vars = {row['Variable_name']: row['Value']
                      for row in self._execute_query("SHOW GLOBAL STATUS")}

        uptime_seconds = int(status_vars.get('Uptime', 1))
        uptime_days = uptime_seconds // 86400
        uptime_hours = (uptime_seconds % 86400) // 3600

        # Calculate server start time using MySQL's clock
        mysql_time = self._execute_single("SELECT UNIX_TIMESTAMP() as timestamp")
        mysql_timestamp = int(mysql_time['timestamp'])
        server_start_timestamp = mysql_timestamp - uptime_seconds
        server_start_time = datetime.fromtimestamp(server_start_timestamp, timezone.utc)

        # Full table scan detection
        select_scan = int(status_vars.get('Select_scan', 0))
        select_range = int(status_vars.get('Select_range', 0))
        select_total = select_scan + select_range
        scan_ratio = (select_scan / select_total * 100) if select_total > 0 else 0
        handler_rnd = int(status_vars.get('Handler_read_rnd_next', 0))

        scan_status = '✅' if scan_ratio < 10 else '⚠️' if scan_ratio < 25 else '❌'

        # Thread cache efficiency
        threads_created = int(status_vars.get('Threads_created', 0))
        connections = int(status_vars.get('Connections', 1))
        thread_cache_miss_rate = (threads_created / connections * 100) if connections > 0 else 0

        thread_status = '✅' if thread_cache_miss_rate < 10 else '⚠️' if thread_cache_miss_rate < 25 else '❌'

        # Temp tables on disk ratio
        tmp_disk = int(status_vars.get('Created_tmp_disk_tables', 0))
        tmp_total = int(status_vars.get('Created_tmp_tables', 1))
        tmp_disk_ratio = (tmp_disk / tmp_total * 100) if tmp_total > 0 else 0

        tmp_status = '✅' if tmp_disk_ratio < 25 else '⚠️' if tmp_disk_ratio < 50 else '❌'

        return {
            'type': 'performance',
            'measurement_window': f'{uptime_days}d {uptime_hours}h (since server start)',
            'server_start_time': server_start_time.isoformat(),
            'uptime_seconds': uptime_seconds,
            'queries_per_second': float(status_vars.get('Questions', 0)) / float(uptime_seconds),
            'slow_queries_total': f"{status_vars.get('Slow_queries', 0)} (since server start)",
            'full_table_scans': {
                'select_scan_ratio': f'{scan_ratio:.2f}%',
                'status': scan_status,
                'select_scan': f'{select_scan} (since server start)',
                'select_range': f'{select_range} (since server start)',
                'handler_read_rnd_next': f'{handler_rnd} (since server start)',
                'note': 'High scan ratio (>25%) or Handler_read_rnd_next indicates missing indexes'
            },
            'thread_cache_efficiency': {
                'miss_rate': f'{thread_cache_miss_rate:.2f}%',
                'status': thread_status,
                'threads_created': f'{threads_created} (since server start)',
                'connections': f'{connections} (since server start)',
                'note': 'Miss rate >10% suggests increasing thread_cache_size'
            },
            'temp_tables': {
                'disk_ratio': f'{tmp_disk_ratio:.2f}%',
                'status': tmp_status,
                'on_disk': f'{tmp_disk} (since server start)',
                'total': f'{tmp_total} (since server start)',
                'note': 'Ratio >25% suggests increasing tmp_table_size or max_heap_table_size'
            },
            'sort_merge_passes': f"{status_vars.get('Sort_merge_passes', 0)} (since server start)",
        }

    def _get_innodb(self) -> Dict[str, Any]:
        """Get InnoDB engine status."""
        from datetime import datetime, timezone

        status_vars = {row['Variable_name']: row['Value']
                      for row in self._execute_query("SHOW GLOBAL STATUS")}

        uptime_seconds = int(status_vars.get('Uptime', 1))
        uptime_days = uptime_seconds // 86400
        uptime_hours = (uptime_seconds % 86400) // 3600

        # Calculate server start time using MySQL's clock
        mysql_time = self._execute_single("SELECT UNIX_TIMESTAMP() as timestamp")
        mysql_timestamp = int(mysql_time['timestamp'])
        server_start_timestamp = mysql_timestamp - uptime_seconds
        server_start_time = datetime.fromtimestamp(server_start_timestamp, timezone.utc)

        buffer_reads = int(status_vars.get('Innodb_buffer_pool_reads', 0))
        buffer_requests = int(status_vars.get('Innodb_buffer_pool_read_requests', 1))
        hit_rate = 100 * (1 - buffer_reads / buffer_requests) if buffer_requests else 0

        return {
            'type': 'innodb',
            'measurement_window': f'{uptime_days}d {uptime_hours}h (since server start)',
            'server_start_time': server_start_time.isoformat(),
            'uptime_seconds': uptime_seconds,
            'buffer_pool_hit_rate': f"{hit_rate:.2f}%",
            'buffer_pool_reads': f"{buffer_reads} (since server start)",
            'buffer_pool_read_requests': f"{buffer_requests} (since server start)",
            'row_lock_waits': f"{status_vars.get('Innodb_row_lock_waits', 0)} (since server start)",
            'row_lock_time_avg': f"{status_vars.get('Innodb_row_lock_time_avg', 0)} ms",
            'deadlocks': f"{status_vars.get('Innodb_deadlocks', 0)} (since server start)",
        }

    def _get_replication(self) -> Dict[str, Any]:
        """Get replication status."""
        slave_status = self._execute_single("SHOW SLAVE STATUS")
        if slave_status:
            return {
                'type': 'replication',
                'role': 'Slave',
                'master_host': slave_status.get('Master_Host'),
                'master_port': slave_status.get('Master_Port'),
                'io_running': slave_status.get('Slave_IO_Running'),
                'sql_running': slave_status.get('Slave_SQL_Running'),
                'seconds_behind_master': slave_status.get('Seconds_Behind_Master'),
                'last_error': slave_status.get('Last_Error') or 'None',
            }

        slave_hosts = self._execute_query("SHOW SLAVE HOSTS")
        if slave_hosts:
            return {
                'type': 'replication',
                'role': 'Master',
                'slaves': [{'server_id': s.get('Server_id'), 'host': s.get('Host')} for s in slave_hosts],
            }

        return {
            'type': 'replication',
            'role': 'Standalone',
            'message': 'No replication configured',
        }

    def _get_storage(self) -> Dict[str, Any]:
        """Get storage usage by database."""
        db_sizes = self._execute_query("""
            SELECT
                table_schema as db_name,
                COUNT(*) as table_count,
                ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) as size_gb,
                ROUND(SUM(data_length) / 1024 / 1024 / 1024, 2) as data_gb,
                ROUND(SUM(index_length) / 1024 / 1024 / 1024, 2) as index_gb
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            GROUP BY table_schema
            ORDER BY size_gb DESC
        """)

        return {
            'type': 'storage',
            'databases': db_sizes,
        }

    def _get_database_storage(self, db_name: str) -> Dict[str, Any]:
        """Get storage for specific database."""
        tables = self._execute_query(f"""
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
            'database': db_name,
            'tables': tables,
        }

    def _get_errors(self) -> Dict[str, Any]:
        """Get error indicators."""
        from datetime import datetime, timezone

        status_vars = {row['Variable_name']: row['Value']
                      for row in self._execute_query("SHOW GLOBAL STATUS")}

        uptime_seconds = int(status_vars.get('Uptime', 1))
        uptime_days = uptime_seconds // 86400
        uptime_hours = (uptime_seconds % 86400) // 3600

        # Calculate server start time using MySQL's clock
        mysql_time = self._execute_single("SELECT UNIX_TIMESTAMP() as timestamp")
        mysql_timestamp = int(mysql_time['timestamp'])
        server_start_timestamp = mysql_timestamp - uptime_seconds
        server_start_time = datetime.fromtimestamp(server_start_timestamp, timezone.utc)

        return {
            'type': 'errors',
            'measurement_window': f'{uptime_days}d {uptime_hours}h (since server start)',
            'server_start_time': server_start_time.isoformat(),
            'uptime_seconds': uptime_seconds,
            'aborted_clients': f"{status_vars.get('Aborted_clients', 0)} (since server start)",
            'aborted_connects': f"{status_vars.get('Aborted_connects', 0)} (since server start)",
            'connection_errors_internal': f"{status_vars.get('Connection_errors_internal', 0)} (since server start)",
            'connection_errors_max_connections': f"{status_vars.get('Connection_errors_max_connections', 0)} (since server start)",
        }

    def _get_variables(self) -> Dict[str, Any]:
        """Get key server variables."""
        variables = self._execute_query("""
            SHOW VARIABLES WHERE Variable_name IN (
                'max_connections', 'innodb_buffer_pool_size',
                'query_cache_size', 'tmp_table_size', 'max_heap_table_size'
            )
        """)

        return {
            'type': 'variables',
            'variables': {row['Variable_name']: row['Value'] for row in variables},
        }

    def _get_health(self) -> Dict[str, Any]:
        """Comprehensive health check."""
        # Reuse get_structure for now
        return self.get_structure()

    def _get_databases(self) -> Dict[str, Any]:
        """Get database list."""
        databases = self._execute_query("SHOW DATABASES")

        return {
            'type': 'databases',
            'databases': [db['Database'] for db in databases],
        }

    def _get_indexes(self) -> Dict[str, Any]:
        """Get index usage statistics from performance_schema."""
        from datetime import datetime, timezone

        # Get uptime for measurement window context
        status_vars = {row['Variable_name']: row['Value']
                      for row in self._execute_query("SHOW GLOBAL STATUS WHERE Variable_name = 'Uptime'")}
        uptime_seconds = int(status_vars.get('Uptime', 1))
        uptime_days = uptime_seconds // 86400
        uptime_hours = (uptime_seconds % 86400) // 3600

        # Calculate server start time using MySQL's clock
        mysql_time = self._execute_single("SELECT UNIX_TIMESTAMP() as timestamp")
        mysql_timestamp = int(mysql_time['timestamp'])
        server_start_timestamp = mysql_timestamp - uptime_seconds
        server_start_time = datetime.fromtimestamp(server_start_timestamp, timezone.utc)

        # Most used indexes
        most_used = self._execute_query("""
            SELECT
                object_schema,
                object_name,
                index_name,
                count_star as total_accesses,
                count_read as read_accesses,
                count_write as write_accesses,
                ROUND(count_read / NULLIF(count_star, 0) * 100, 2) as read_pct
            FROM performance_schema.table_io_waits_summary_by_index_usage
            WHERE object_schema NOT IN ('mysql', 'performance_schema', 'information_schema', 'sys')
              AND index_name IS NOT NULL
              AND count_star > 0
            ORDER BY count_star DESC
            LIMIT 20
        """)

        # Unused indexes
        unused = self._execute_query("""
            SELECT
                object_schema,
                object_name,
                index_name
            FROM performance_schema.table_io_waits_summary_by_index_usage
            WHERE object_schema NOT IN ('mysql', 'performance_schema', 'information_schema', 'sys')
              AND index_name IS NOT NULL
              AND count_star = 0
            LIMIT 50
        """)

        return {
            'type': 'indexes',
            'measurement_window': f'{uptime_days}d {uptime_hours}h (since server start or performance_schema enable)',
            'server_start_time': server_start_time.isoformat(),
            'uptime_seconds': uptime_seconds,
            'note': 'Counters are cumulative since server start or last performance_schema reset',
            'most_used': most_used,
            'unused': unused,
            'unused_count': len(unused),
        }

    def _get_slow_queries(self) -> Dict[str, Any]:
        """Get slow query analysis from mysql.slow_log."""
        # Check if slow_log table exists and has data
        try:
            # Recent slow queries (last 24 hours)
            slow_queries = self._execute_query("""
                SELECT
                    start_time,
                    user_host,
                    TIME_TO_SEC(query_time) as query_time_seconds,
                    TIME_TO_SEC(lock_time) as lock_time_seconds,
                    rows_sent,
                    rows_examined,
                    LEFT(sql_text, 500) as query_preview
                FROM mysql.slow_log
                WHERE start_time >= NOW() - INTERVAL 24 HOUR
                ORDER BY query_time DESC
                LIMIT 20
            """)

            # Summary stats
            summary = self._execute_single("""
                SELECT
                    COUNT(*) as total_slow_queries,
                    MIN(TIME_TO_SEC(query_time)) as min_time,
                    MAX(TIME_TO_SEC(query_time)) as max_time,
                    AVG(TIME_TO_SEC(query_time)) as avg_time,
                    SUM(rows_examined) as total_rows_examined
                FROM mysql.slow_log
                WHERE start_time >= NOW() - INTERVAL 24 HOUR
            """)

            return {
                'type': 'slow_queries',
                'period': '24 hours',
                'summary': summary,
                'top_queries': slow_queries,
            }
        except Exception as e:
            return {
                'type': 'slow_queries',
                'error': str(e),
                'message': 'Slow query log may not be enabled or accessible',
            }

    def check(self, **kwargs) -> Dict[str, Any]:
        """Run health checks with pass/warn/fail thresholds.

        Returns:
            {
                'status': 'pass' | 'warning' | 'failure',
                'exit_code': 0 | 1 | 2,
                'checks': [
                    {
                        'name': 'Table Scan Ratio',
                        'status': 'pass',
                        'value': '12.5%',
                        'threshold': '<25%',
                        'severity': 'warning'
                    },
                    ...
                ],
                'summary': {
                    'total': 10,
                    'passed': 8,
                    'warnings': 1,
                    'failures': 1
                }
            }
        """
        # Get performance metrics needed for health checks
        performance = self._get_performance()

        # Get status variables for additional checks
        status_vars = {row['Variable_name']: row['Value']
                      for row in self._execute_query("SHOW GLOBAL STATUS")}

        # Get configuration variables
        vars_result = self._execute_query("SHOW VARIABLES")
        variables = {row['Variable_name']: row['Value'] for row in vars_result}

        # Parse values from performance data
        tuning_ratios = performance.get('tuning_ratios', {})

        # Extract numeric values
        def parse_percentage(value_str):
            """Parse percentage string like '12.5%' to float."""
            if isinstance(value_str, (int, float)):
                return float(value_str)
            if isinstance(value_str, str) and '%' in value_str:
                return float(value_str.replace('%', ''))
            return 0.0

        # Calculate metrics
        table_scan_ratio = parse_percentage(tuning_ratios.get('table_scan_ratio', '0%'))
        thread_cache_miss_rate = parse_percentage(tuning_ratios.get('thread_cache_miss_rate', '0%'))
        temp_disk_ratio = parse_percentage(tuning_ratios.get('temp_tables_to_disk_ratio', '0%'))

        # Connection metrics
        max_connections = int(variables.get('max_connections', 100))
        current_connections = int(status_vars.get('Threads_connected', 0))
        max_used_connections = int(status_vars.get('Max_used_connections', 0))
        connection_pct = (current_connections / max_connections * 100) if max_connections else 0
        max_used_pct = (max_used_connections / max_connections * 100) if max_connections else 0

        # Open files
        open_files_limit = int(variables.get('open_files_limit', 1))
        open_files = int(status_vars.get('Open_files', 0))
        open_files_pct = (open_files / open_files_limit * 100) if open_files_limit else 0

        # Buffer hit rate (from performance data)
        innodb_buffer_pool_reads = int(status_vars.get('Innodb_buffer_pool_reads', 0))
        innodb_buffer_pool_read_requests = int(status_vars.get('Innodb_buffer_pool_read_requests', 1))
        buffer_hit_rate = 100 * (1 - innodb_buffer_pool_reads / innodb_buffer_pool_read_requests) if innodb_buffer_pool_read_requests else 100

        # Define health checks with thresholds
        checks = []

        # Helper function to evaluate check
        def add_check(name, value, pass_threshold, warn_threshold, severity, operator='<'):
            """Add a health check result."""
            if operator == '<':
                if value < pass_threshold:
                    status = 'pass'
                elif value < warn_threshold:
                    status = 'warning'
                else:
                    status = 'failure'
            else:  # operator == '>'
                if value > pass_threshold:
                    status = 'pass'
                elif value > warn_threshold:
                    status = 'warning'
                else:
                    status = 'failure'

            checks.append({
                'name': name,
                'status': status,
                'value': f'{value:.2f}%' if 'rate' in name.lower() or 'ratio' in name.lower() or 'pct' in name.lower() else str(value),
                'threshold': f'{operator}{pass_threshold}%' if operator == '<' else f'{operator}{pass_threshold}%',
                'severity': severity
            })

        # Run all checks (based on audit spec lines 316-359)
        add_check('Table Scan Ratio', table_scan_ratio, 10, 25, 'high', '<')
        add_check('Thread Cache Miss Rate', thread_cache_miss_rate, 10, 25, 'medium', '<')
        add_check('Temp Disk Ratio', temp_disk_ratio, 25, 50, 'medium', '<')
        add_check('Max Used Connections %', max_used_pct, 80, 100, 'critical', '<')
        add_check('Open Files %', open_files_pct, 75, 90, 'critical', '<')
        add_check('Current Connection %', connection_pct, 80, 95, 'high', '<')
        add_check('Buffer Hit Rate', buffer_hit_rate, 99, 95, 'high', '>')

        # Calculate summary
        total = len(checks)
        passed = sum(1 for c in checks if c['status'] == 'pass')
        warnings = sum(1 for c in checks if c['status'] == 'warning')
        failures = sum(1 for c in checks if c['status'] == 'failure')

        # Determine overall status and exit code
        if failures > 0:
            overall_status = 'failure'
            exit_code = 2
        elif warnings > 0:
            overall_status = 'warning'
            exit_code = 1
        else:
            overall_status = 'pass'
            exit_code = 0

        return {
            'status': overall_status,
            'exit_code': exit_code,
            'checks': checks,
            'summary': {
                'total': total,
                'passed': passed,
                'warnings': warnings,
                'failures': failures
            }
        }

    def __del__(self):
        """Close connection on cleanup."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
