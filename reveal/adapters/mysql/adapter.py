"""MySQL database adapter (mysql://)."""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from .connection import MySQLConnection
from .health import HealthMetrics
from .performance import PerformanceAnalyzer
from .replication import ReplicationMonitor
from .storage import StorageAnalyzer
from .renderer import MySQLRenderer


@dataclass
class HealthCheckThresholds:
    """Thresholds for health check evaluation.

    Reduces parameter count in _evaluate_health_check() (R913 fix).
    """
    pass_threshold: float
    warn_threshold: float
    severity: str
    operator: str = '<'


@register_adapter('mysql')
@register_renderer(MySQLRenderer)
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
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for mysql:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'mysql',
            'description': 'MySQL database inspection with health monitoring, performance analysis, and replication status',
            'uri_syntax': 'mysql://[user:pass@]host[:port][/element]',
            'query_params': {},  # No query parameters
            'elements': {
                'connections': 'Connection pool and thread details',
                'innodb': 'InnoDB buffer pool and engine status',
                'replication': 'Replication status and lag',
                'storage': 'Database and table sizes',
                'performance': 'Query performance metrics',
                'variables': 'Server configuration variables'
            },
            'cli_flags': [
                '--check',  # Run health checks
                '--advanced',  # Include advanced metrics
                '--only-failures'  # Show only failed health checks
            ],
            'supports_batch': False,
            'supports_advanced': True,
            'output_types': [
                {
                    'type': 'mysql_health',
                    'description': 'Database health overview with connection, InnoDB, and resource metrics',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'mysql_health'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'database'},
                            'server': {'type': 'string'},
                            'version': {'type': 'string'},
                            'uptime': {'type': 'integer'},
                            'connections': {'type': 'object'},
                            'innodb': {'type': 'object'},
                            'resources': {'type': 'object'}
                        }
                    }
                },
                {
                    'type': 'mysql_replication',
                    'description': 'Replication status including lag and IO/SQL thread state',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'mysql_replication'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'database'},
                            'io_running': {'type': 'boolean'},
                            'sql_running': {'type': 'boolean'},
                            'lag_seconds': {'type': ['integer', 'null']},
                            'master_log_file': {'type': 'string'},
                            'relay_log_file': {'type': 'string'}
                        }
                    }
                },
                {
                    'type': 'mysql_storage',
                    'description': 'Database and table size information',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'mysql_storage'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'database'},
                            'databases': {'type': 'array'},
                            'total_size_mb': {'type': 'number'}
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'mysql://localhost',
                    'description': 'Database health overview',
                    'output_type': 'mysql_health'
                },
                {
                    'uri': 'mysql://localhost --check',
                    'description': 'Run health checks (connection, InnoDB, resources)',
                    'cli_flag': '--check',
                    'output_type': 'mysql_health'
                },
                {
                    'uri': 'mysql://localhost/connections',
                    'description': 'Connection pool and thread details',
                    'element': 'connections',
                    'output_type': 'mysql_health'
                },
                {
                    'uri': 'mysql://localhost/replication',
                    'description': 'Replication status and lag',
                    'element': 'replication',
                    'output_type': 'mysql_replication'
                },
                {
                    'uri': 'mysql://localhost/storage',
                    'description': 'Database and table sizes',
                    'element': 'storage',
                    'output_type': 'mysql_storage'
                },
                {
                    'uri': 'mysql://user:pass@prod.db.host:3306/innodb',
                    'description': 'InnoDB buffer pool status',
                    'element': 'innodb',
                    'output_type': 'mysql_health'
                }
            ],
            'notes': [
                'Requires pymysql package (pip install pymysql)',
                'Credentials can be provided in URI or via environment variables',
                'Read-only operations for safety',
                'Health checks include connection utilization, InnoDB buffer pool, and resource limits'
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for mysql:// adapter.

        Help data loaded from reveal/adapters/help_data/mysql.yaml
        to reduce function complexity.
        """
        return load_help_data('mysql') or {}

    def __init__(self, connection_string: str):
        """Initialize MySQL adapter with connection details.

        Args:
            connection_string: mysql://[user:pass@]host[:port][/element]
                              Required - routing layer passes full URI

        Raises:
            ImportError: If pymysql is not installed
            TypeError: If connection_string not provided (enforces URI-based init)
        """
        # Create connection manager
        self.conn = MySQLConnection(connection_string)
        self.element = self.conn.element

        # Create specialized analyzers
        self.health = HealthMetrics(self.conn)
        self.performance = PerformanceAnalyzer(self.conn)
        self.replication = ReplicationMonitor(self.conn)
        self.storage = StorageAnalyzer(self.conn)

        # For backwards compatibility
        self.connection_string = connection_string
        self.host = self.conn.host
        self.port = self.conn.port
        self.user = self.conn.user
        self.password = self.conn.password
        self.database = self.conn.database
        self.element = self.conn.element
        self._connection = self.conn._connection  # For tests that mock this

    # Delegation methods for backwards compatibility
    def _resolve_credentials(self):
        """Stub for backwards compatibility with tests. Actual resolution done by MySQLConnection."""
        pass

    def _get_server_display(self) -> str:
        """Get server hostname:port for display purposes.

        Returns actual connection info after connection, or 'localhost:3306' as fallback.
        """
        # Try to get from connection object (most accurate after connected)
        if self.conn._connection:
            try:
                conn = self.conn._connection
                host = getattr(conn, 'host', None) or self.host or 'localhost'
                port = getattr(conn, 'port', None) or self.port or 3306
                return f"{host}:{port}"
            except Exception:
                pass  # live connection attrs unavailable; fall back to config values
        # Fallback to parsed values or defaults
        host = self.host or 'localhost'
        port = self.port or 3306
        return f"{host}:{port}"

    def _execute_query(self, query: str) -> list:
        """Delegate to connection module."""
        return self.conn.execute_query(query)

    def _execute_single(self, query: str):
        """Delegate to connection module."""
        return self.conn.execute_single(query)

    def _get_connection(self):
        """Delegate to connection module."""
        return self.conn.get_connection()

    def _convert_decimals(self, obj):
        """Delegate to connection module."""
        return self.conn.convert_decimals(obj)

    def _get_server_uptime_info(self, status_vars):
        """Delegate to health module."""
        return self.health.get_server_uptime_info(status_vars)

    def _calculate_connection_health(self, status_vars):
        """Delegate to health module."""
        return self.health.calculate_connection_health(status_vars)

    def _calculate_innodb_health(self, status_vars):
        """Delegate to health module."""
        return self.health.calculate_innodb_health(status_vars)

    def _calculate_resource_limits(self, status_vars):
        """Delegate to health module."""
        return self.health.calculate_resource_limits(status_vars)

    def _get_performance(self) -> Dict[str, Any]:
        """Delegate to performance module."""
        return self.performance.get_performance()

    def _get_innodb(self) -> Dict[str, Any]:
        """Delegate to performance module."""
        return self.performance.get_innodb()

    def _get_replication(self) -> Dict[str, Any]:
        """Delegate to replication module."""
        return self.replication.get_replication()

    def _get_storage(self) -> Dict[str, Any]:
        """Delegate to storage module."""
        return self.storage.get_storage()

    def _get_database_storage(self, db_name: str) -> Dict[str, Any]:
        """Delegate to storage module."""
        return self.storage.get_database_storage(db_name)

    def __del__(self):
        """Close MySQL connection."""
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get MySQL health overview (DBA snapshot).

        If an element was specified in the URI (e.g., mysql://host/connections),
        returns that specific element instead of the overview.

        Returns:
            Dict containing health signals (~100 tokens) or element-specific data
        """
        # If element specified in URI, delegate to get_element for progressive disclosure
        if self.element:
            result = self.get_element(self.element, **kwargs)
            if result:
                return result
            # Fall through to overview if element not recognized

        # Get timing context for snapshot
        timing = self.conn.get_snapshot_context()

        # Get server version and status
        version_info = self._execute_single("SELECT VERSION() as version")
        status_vars = {row['Variable_name']: row['Value']
                      for row in self._execute_query("SHOW GLOBAL STATUS")}

        # Calculate uptime and health metrics (for detailed display)
        uptime_days, uptime_hours, uptime_mins, server_start_time = (
            self._get_server_uptime_info(status_vars)
        )
        uptime_seconds = int(status_vars.get('Uptime', 0))

        conn_health = self._calculate_connection_health(status_vars)
        innodb_health = self._calculate_innodb_health(status_vars)
        resource_limits = self._calculate_resource_limits(status_vars)

        # Build subsystem info using extracted helpers
        performance_metrics = self._build_performance_metrics(status_vars, uptime_seconds)
        replication_info = self._build_replication_info()
        storage_info = self._build_storage_info()
        health_status, health_issues = self._build_health_assessment(
            conn_health, innodb_health, replication_info
        )

        # Get server display string (handles None values from .my.cnf credentials)
        server_display = self._get_server_display()
        # Extract just hostname for next_steps (without port for cleaner URIs)
        host_display = server_display.split(':')[0]

        return {
            'contract_version': '1.0',
            'type': 'mysql_server',
            'source': server_display,
            'source_type': 'database',
            'snapshot_time': timing['snapshot_time'],
            'server': server_display,
            'version': version_info['version'],
            'uptime': f"{uptime_days}d {uptime_hours}h {uptime_mins}m",
            'server_start_time': server_start_time.isoformat(),
            'connection_health': {
                **conn_health,
                'percentage': f"{conn_health['percentage']:.1f}%",
                'max_used_pct': f"{conn_health['max_used_pct']:.1f}%",
                'note': 'If max_used_pct was 100%, connections were rejected (since server start)'
            },
            'performance': performance_metrics,
            'innodb_health': {
                'buffer_pool_hit_rate': f"{innodb_health['buffer_hit_rate']:.2f}% (since server start)",
                'status': innodb_health['status'],
                'row_lock_waits': f"{innodb_health['row_lock_waits']} (since server start)",
                'deadlocks': f"{innodb_health['deadlocks']} (since server start)",
            },
            'replication': replication_info,
            'storage': storage_info,
            'resource_limits': {
                'open_files': {
                    **resource_limits['open_files'],
                    'percentage': f"{resource_limits['open_files']['percentage']:.1f}%",
                    'note': 'Approaching limit (>75%) can cause "too many open files" errors'
                }
            },
            'health_status': health_status,
            'health_issues': health_issues,
            'next_steps': [
                f"reveal mysql://{host_display}/connections       # Connection details",
                f"reveal mysql://{host_display}/performance       # Query performance",
                f"reveal mysql://{host_display}/innodb            # InnoDB details",
                f"reveal mysql://{host_display} --check           # Run health checks",
            ]
        }

    def _build_performance_metrics(self, status_vars: Dict[str, str],
                                   uptime_seconds: int) -> Dict[str, Any]:
        """Build performance metrics from status variables.

        Args:
            status_vars: SHOW GLOBAL STATUS results
            uptime_seconds: Server uptime in seconds

        Returns:
            Dict with performance metrics
        """
        questions = int(status_vars.get('Questions', 0))
        slow_queries = int(status_vars.get('Slow_queries', 0))
        qps = questions / uptime_seconds if uptime_seconds else 0
        slow_pct = (slow_queries / questions * 100) if questions else 0
        threads_running = int(status_vars.get('Threads_running', 0))

        return {
            'qps': f"{qps:.1f}",
            'slow_queries': f"{slow_queries} total ({slow_pct:.2f}% of all queries since server start)",
            'threads_running': threads_running,
        }

    def _build_replication_info(self) -> Dict[str, Any]:
        """Build replication status information.

        Returns:
            Dict with replication role and status
        """
        try:
            slave_status = self._execute_single("SHOW SLAVE STATUS")
            if slave_status:
                # Seconds_Behind_Master can be None even when key exists
                lag = slave_status.get('Seconds_Behind_Master')
                return {
                    'role': 'Slave',
                    'lag': lag if lag is not None else 'Unknown',
                    'io_running': slave_status.get('Slave_IO_Running', 'No') == 'Yes',
                    'sql_running': slave_status.get('Slave_SQL_Running', 'No') == 'Yes',
                }

            # Check if master
            slave_hosts = self._execute_query("SHOW SLAVE HOSTS")
            if slave_hosts:
                return {
                    'role': 'Master',
                    'slaves': len(slave_hosts),
                }

            return {'role': 'Standalone'}

        except Exception as e:
            return {'role': 'Unknown', 'error': str(e)}

    def _build_storage_info(self) -> Dict[str, Any]:
        """Build storage usage information.

        Returns:
            Dict with database sizes and totals
        """
        db_sizes = self._execute_query("""
            SELECT
                table_schema as db_name,
                ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2)
                    as size_gb
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            GROUP BY table_schema
            ORDER BY size_gb DESC
        """)

        total_size_gb = sum(row['size_gb'] for row in db_sizes)
        largest_db = db_sizes[0] if db_sizes else None

        return {
            'total_size_gb': total_size_gb,
            'database_count': len(db_sizes),
            'largest_db': f"{largest_db['db_name']} ({largest_db['size_gb']} GB)" if largest_db else 'N/A',
        }

    def _build_health_assessment(self, conn_health: Dict[str, Any],
                                 innodb_health: Dict[str, Any],
                                 replication_info: Dict[str, Any]) -> tuple:
        """Build overall health assessment from subsystem metrics.

        Args:
            conn_health: Connection health metrics
            innodb_health: InnoDB health metrics
            replication_info: Replication status

        Returns:
            Tuple of (health_status, health_issues)
        """
        health_issues = []

        if conn_health['percentage'] > 80:
            health_issues.append(
                f"High connection usage ({conn_health['percentage']:.1f}%)"
            )

        if innodb_health['buffer_hit_rate'] < 99:
            health_issues.append(
                f"Low buffer pool hit rate ({innodb_health['buffer_hit_rate']:.2f}%)"
            )

        if (replication_info.get('role') == 'Slave' and
                replication_info.get('lag', 0) and
                replication_info['lag'] != 'Unknown'):
            if int(replication_info['lag']) > 60:
                health_issues.append(f"Replication lag ({replication_info['lag']}s)")

        health_status = ('✅ HEALTHY' if not health_issues else
                        '⚠️ WARNING' if len(health_issues) < 3 else
                        '❌ CRITICAL')

        return health_status, health_issues if health_issues else ['No issues detected']

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
            'tables': self._get_tables,
        }

        # Handle storage/<db_name> pattern
        if element_name.startswith('storage/'):
            db_name = element_name.split('/', 1)[1]
            return self._get_database_storage(db_name)

        handler = handlers.get(element_name)
        if handler:
            return handler()
        return None

    def get_available_elements(self) -> List[Dict[str, str]]:
        """Get list of available MySQL elements.

        Returns:
            List of available elements with descriptions
        """
        connection_string = f"mysql://{self.host}:{self.port}"
        if self.database:
            connection_string += f"/{self.database}"

        return [
            {
                'name': 'connections',
                'description': 'Active connections and processlist',
                'example': f'reveal {connection_string}/connections'
            },
            {
                'name': 'performance',
                'description': 'Query performance metrics',
                'example': f'reveal {connection_string}/performance'
            },
            {
                'name': 'innodb',
                'description': 'InnoDB engine status',
                'example': f'reveal {connection_string}/innodb'
            },
            {
                'name': 'replication',
                'description': 'Replication status (if configured)',
                'example': f'reveal {connection_string}/replication'
            },
            {
                'name': 'storage',
                'description': 'Storage usage by database',
                'example': f'reveal {connection_string}/storage'
            },
            {
                'name': 'errors',
                'description': 'Recent errors and warnings',
                'example': f'reveal {connection_string}/errors'
            },
            {
                'name': 'variables',
                'description': 'Server configuration variables',
                'example': f'reveal {connection_string}/variables'
            },
            {
                'name': 'health',
                'description': 'Health check results',
                'example': f'reveal {connection_string}/health'
            },
            {
                'name': 'databases',
                'description': 'List of databases',
                'example': f'reveal {connection_string}/databases'
            },
            {
                'name': 'indexes',
                'description': 'Index usage analysis',
                'example': f'reveal {connection_string}/indexes'
            },
            {
                'name': 'tables',
                'description': 'Table I/O statistics and hotspots',
                'example': f'reveal {connection_string}/tables'
            },
            {
                'name': 'slow-queries',
                'description': 'Slow query log analysis',
                'example': f'reveal {connection_string}/slow-queries'
            },
        ]

    def _get_connections(self) -> Dict[str, Any]:
        """Get connection details and processlist.

        Returns connection details with snapshot timing context to accurately
        interpret long_running_queries time values.
        """
        timing = self.conn.get_snapshot_context()
        processlist = self._execute_query("SHOW FULL PROCESSLIST")

        # Group by state
        by_state: Dict[str, int] = {}
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
            **timing,
            'total_connections': len(processlist),
            'by_state': by_state,
            'long_running_queries': long_running,
        }

    def _get_errors(self) -> Dict[str, Any]:
        """Get error indicators."""
        timing = self.conn.get_snapshot_context()
        status_vars = {row['Variable_name']: row['Value']
                      for row in self._execute_query("SHOW GLOBAL STATUS")}

        return {
            'type': 'errors',
            **timing,
            'aborted_clients': f"{status_vars.get('Aborted_clients', 0)} (since server start)",
            'aborted_connects': f"{status_vars.get('Aborted_connects', 0)} (since server start)",
            'connection_errors_internal': f"{status_vars.get('Connection_errors_internal', 0)} (since server start)",
            'connection_errors_max_connections': f"{status_vars.get('Connection_errors_max_connections', 0)} (since server start)",
        }

    def _get_variables(self) -> Dict[str, Any]:
        """Get key server variables with snapshot timing context."""
        timing = self.conn.get_snapshot_context()
        variables = self._execute_query("""
            SHOW VARIABLES WHERE Variable_name IN (
                'max_connections', 'innodb_buffer_pool_size',
                'query_cache_size', 'tmp_table_size', 'max_heap_table_size'
            )
        """)

        return {
            'type': 'variables',
            **timing,
            'variables': {row['Variable_name']: row['Value'] for row in variables},
        }

    def _get_health(self) -> Dict[str, Any]:
        """Comprehensive health check."""
        # Reuse get_structure for now
        return self.get_structure()

    def _get_databases(self) -> Dict[str, Any]:
        """Get database list with snapshot timing context."""
        timing = self.conn.get_snapshot_context()
        databases = self._execute_query("SHOW DATABASES")

        return {
            'type': 'databases',
            **timing,
            'databases': [db['Database'] for db in databases],
        }

    def _get_indexes(self) -> Dict[str, Any]:
        """Get index usage statistics from performance_schema."""
        timing = self.conn.get_snapshot_context()
        ps_status = self.conn.get_performance_schema_status()

        # Determine actual measurement basis
        if ps_status['counters_reset_detected']:
            measurement_basis = "since_reset"
            measurement_start_time = ps_status['likely_reset_time']
        else:
            measurement_basis = "since_server_start"
            measurement_start_time = timing['server_start_time']

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
            **timing,
            'measurement_basis': measurement_basis,
            'measurement_start_time': measurement_start_time,
            'performance_schema_status': ps_status,
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

    def _get_tables(self) -> Dict[str, Any]:
        """Get table I/O statistics from performance_schema."""
        timing = self.conn.get_snapshot_context()
        ps_status = self.conn.get_performance_schema_status()

        # Determine actual measurement basis
        if ps_status['counters_reset_detected']:
            measurement_basis = "since_reset"
            measurement_start_time = ps_status['likely_reset_time']
        else:
            measurement_basis = "since_server_start"
            measurement_start_time = timing['server_start_time']

        # Get table I/O statistics
        tables = self._execute_query("""
            SELECT
                OBJECT_NAME AS table_name,
                COUNT_READ AS reads,
                COUNT_WRITE AS writes,
                SUM_TIMER_READ AS read_time_ps,
                SUM_TIMER_WRITE AS write_time_ps,
                SUM_TIMER_WAIT AS total_time_ps
            FROM performance_schema.table_io_waits_summary_by_table
            WHERE OBJECT_SCHEMA = DATABASE()
              AND (COUNT_READ > 0 OR COUNT_WRITE > 0)
            ORDER BY COUNT_READ DESC
            LIMIT 50
        """)

        # Process tables and add calculated fields
        alerts = []
        processed_tables = []

        for table in tables:
            table_name = table['table_name']
            reads = int(table['reads'])
            writes = int(table['writes'])

            # Calculate read:write ratio
            if writes > 0:
                read_write_ratio = reads / writes
            else:
                read_write_ratio = float('inf') if reads > 0 else 0

            # Convert picoseconds to seconds/hours
            total_time_sec = int(table['total_time_ps']) / 1_000_000_000_000
            read_time_sec = int(table['read_time_ps']) / 1_000_000_000_000
            write_time_sec = int(table['write_time_ps']) / 1_000_000_000_000

            # Check for alerts
            alert_type = None
            recommendation = None

            # Check for alerts (priority order: extreme_read_ratio > high_read_volume > long_running)
            if read_write_ratio > 10_000:
                alert_type = "extreme_read_ratio"
                recommendation = "add_limit_clause"
                alerts.append({
                    'table': table_name,
                    'type': 'extreme_read_ratio',
                    'ratio': read_write_ratio,
                    'recommendation': 'Review queries for missing LIMIT clauses or excessive reads'
                })
            elif reads > 1_000_000_000:
                alert_type = "high_read_volume"
                recommendation = "optimize_queries"
                alerts.append({
                    'table': table_name,
                    'type': 'high_read_volume',
                    'reads': reads,
                    'recommendation': 'Review query patterns and consider caching'
                })
            elif total_time_sec > 3600:  # > 1 hour
                alert_type = "long_running"
                recommendation = "performance_review"
                alerts.append({
                    'table': table_name,
                    'type': 'long_running',
                    'total_hours': round(total_time_sec / 3600, 1),
                    'recommendation': 'Review table for performance bottlenecks'
                })

            processed_tables.append({
                'table_name': table_name,
                'reads': reads,
                'writes': writes,
                'read_write_ratio': round(read_write_ratio, 1) if read_write_ratio != float('inf') else None,
                'total_time_sec': round(total_time_sec, 2),
                'total_time_hours': round(total_time_sec / 3600, 2),
                'read_time_sec': round(read_time_sec, 2),
                'write_time_sec': round(write_time_sec, 2),
                'alert': alert_type,
                'recommendation': recommendation,
            })

        return {
            'type': 'tables',
            **timing,
            'measurement_basis': measurement_basis,
            'measurement_start_time': measurement_start_time,
            'performance_schema_status': ps_status,
            'tables': processed_tables,
            'table_count': len(processed_tables),
            'alerts': alerts,
            'alert_count': len(alerts),
        }

    def _load_health_check_config(self) -> Dict[str, Any]:
        """Load health check configuration from file or use defaults.

        Uses unified reveal config system with XDG-compliant paths.
        Config file locations (in order of precedence):
        1. ./.reveal/mysql-health-checks.yaml (project)
        2. ~/.config/reveal/mysql-health-checks.yaml (user)
        3. /etc/reveal/mysql-health-checks.yaml (system)
        4. Hardcoded defaults (fallback)

        Returns:
            Dict with 'checks' key containing list of check definitions
        """
        from reveal.config import load_config

        # Default configuration (fallback)
        defaults = {
            'checks': [
                {'name': 'Table Scan Ratio', 'metric': 'table_scan_ratio', 'pass_threshold': 10, 'warn_threshold': 25, 'severity': 'high', 'operator': '<'},
                {'name': 'Thread Cache Miss Rate', 'metric': 'thread_cache_miss_rate', 'pass_threshold': 10, 'warn_threshold': 25, 'severity': 'medium', 'operator': '<'},
                {'name': 'Temp Disk Ratio', 'metric': 'temp_disk_ratio', 'pass_threshold': 25, 'warn_threshold': 50, 'severity': 'medium', 'operator': '<'},
                {'name': 'Max Used Connections %', 'metric': 'max_used_connections_pct', 'pass_threshold': 80, 'warn_threshold': 100, 'severity': 'critical', 'operator': '<'},
                {'name': 'Open Files %', 'metric': 'open_files_pct', 'pass_threshold': 75, 'warn_threshold': 90, 'severity': 'critical', 'operator': '<'},
                {'name': 'Current Connection %', 'metric': 'connection_pct', 'pass_threshold': 80, 'warn_threshold': 95, 'severity': 'high', 'operator': '<'},
                {'name': 'Buffer Hit Rate', 'metric': 'buffer_hit_rate', 'pass_threshold': 99, 'warn_threshold': 95, 'severity': 'high', 'operator': '>'},
            ]
        }

        # Load from unified config system
        return load_config('mysql-health-checks.yaml', defaults)

    def _parse_percentage(self, value_str) -> float:
        """Parse percentage string like '12.5%' to float.

        Args:
            value_str: Value as string, int, or float

        Returns:
            Float value (percentage as number)
        """
        if isinstance(value_str, (int, float)):
            return float(value_str)
        if isinstance(value_str, str) and '%' in value_str:
            return float(value_str.replace('%', ''))
        return 0.0

    def _collect_health_metrics(self) -> Dict[str, float]:
        """Collect all health check metrics from MySQL.

        Returns:
            Dict mapping metric names to calculated values
        """
        # Get performance metrics
        performance = self._get_performance()
        tuning_ratios = performance.get('tuning_ratios', {})

        # Get status and configuration variables
        status_vars = {row['Variable_name']: row['Value']
                      for row in self._execute_query("SHOW GLOBAL STATUS")}
        vars_result = self._execute_query("SHOW VARIABLES")
        variables = {row['Variable_name']: row['Value'] for row in vars_result}

        # Parse ratio metrics
        table_scan_ratio = self._parse_percentage(tuning_ratios.get('table_scan_ratio', '0%'))
        thread_cache_miss_rate = self._parse_percentage(tuning_ratios.get('thread_cache_miss_rate', '0%'))
        temp_disk_ratio = self._parse_percentage(tuning_ratios.get('temp_tables_to_disk_ratio', '0%'))

        # Calculate connection metrics
        max_connections = int(variables.get('max_connections', 100))
        current_connections = int(status_vars.get('Threads_connected', 0))
        max_used_connections = int(status_vars.get('Max_used_connections', 0))
        connection_pct = (current_connections / max_connections * 100) if max_connections else 0
        max_used_pct = (max_used_connections / max_connections * 100) if max_connections else 0

        # Calculate open files metrics
        open_files_limit = int(variables.get('open_files_limit', 1))
        open_files = int(status_vars.get('Open_files', 0))
        open_files_pct = (open_files / open_files_limit * 100) if open_files_limit else 0

        # Calculate buffer hit rate
        innodb_buffer_pool_reads = int(status_vars.get('Innodb_buffer_pool_reads', 0))
        innodb_buffer_pool_read_requests = int(status_vars.get('Innodb_buffer_pool_read_requests', 1))
        buffer_hit_rate = 100 * (1 - innodb_buffer_pool_reads / innodb_buffer_pool_read_requests) if innodb_buffer_pool_read_requests else 100

        return {
            'table_scan_ratio': table_scan_ratio,
            'thread_cache_miss_rate': thread_cache_miss_rate,
            'temp_disk_ratio': temp_disk_ratio,
            'max_used_connections_pct': max_used_pct,
            'open_files_pct': open_files_pct,
            'connection_pct': connection_pct,
            'buffer_hit_rate': buffer_hit_rate,
        }

    def _evaluate_health_check(self, name: str, value: float, thresholds: HealthCheckThresholds) -> Dict[str, Any]:
        """Evaluate a single health check against thresholds.

        Args:
            name: Check name
            value: Measured value
            thresholds: HealthCheckThresholds config with pass/warn thresholds, severity, operator

        Returns:
            Check result dict with status, value, threshold, etc.
        """
        # Determine status based on operator and thresholds
        if thresholds.operator == '<':
            if value < thresholds.pass_threshold:
                status = 'pass'
            elif value < thresholds.warn_threshold:
                status = 'warning'
            else:
                status = 'failure'
        else:  # operator == '>'
            if value > thresholds.pass_threshold:
                status = 'pass'
            elif value > thresholds.warn_threshold:
                status = 'warning'
            else:
                status = 'failure'

        # Format value string
        is_percentage = 'rate' in name.lower() or 'ratio' in name.lower() or 'pct' in name.lower()
        value_str = f'{value:.2f}%' if is_percentage else str(value)

        return {
            'name': name,
            'status': status,
            'value': value_str,
            'threshold': f'{thresholds.operator}{thresholds.pass_threshold}%',
            'severity': thresholds.severity
        }

    def _calculate_check_summary(self, checks: List[Dict[str, Any]]) -> tuple:
        """Calculate summary and overall status from checks.

        Args:
            checks: List of check result dicts

        Returns:
            Tuple of (overall_status, exit_code, summary_dict)
        """
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

        summary = {
            'total': total,
            'passed': passed,
            'warnings': warnings,
            'failures': failures
        }

        return overall_status, exit_code, summary

    def check(self, **kwargs) -> Dict[str, Any]:
        """Run health checks with pass/warn/fail thresholds.

        Args:
            **kwargs: Check options (advanced, only_failures)

        Refactored to reduce complexity from 58 → ~15 by extracting helpers.

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
        only_failures = kwargs.get('only_failures', False)

        # Collect all health metrics using extracted helper
        metrics = self._collect_health_metrics()

        # Load health check configuration
        config = self._load_health_check_config()

        # Run all checks from config
        checks = []
        for check_def in config.get('checks', []):
            metric_name = check_def.get('metric')
            if metric_name in metrics:
                thresholds = HealthCheckThresholds(
                    pass_threshold=check_def['pass_threshold'],
                    warn_threshold=check_def['warn_threshold'],
                    severity=check_def['severity'],
                    operator=check_def.get('operator', '<')
                )
                check_result = self._evaluate_health_check(
                    name=check_def['name'],
                    value=metrics[metric_name],
                    thresholds=thresholds
                )
                checks.append(check_result)

        # Calculate summary and overall status using extracted helper (before filtering)
        overall_status, exit_code, summary = self._calculate_check_summary(checks)

        # Filter to only failures if requested
        filtered_checks = checks
        if only_failures:
            filtered_checks = [c for c in checks if c['status'] in ('failure', 'warning')]

        # Note: advanced parameter reserved for future enhanced checks

        return {
            'status': overall_status,
            'exit_code': exit_code,
            'checks': filtered_checks,
            'summary': summary
        }