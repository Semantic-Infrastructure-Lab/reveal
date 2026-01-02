"""MySQL health metrics calculation."""

from typing import Dict, Tuple
from datetime import datetime, timezone


class HealthMetrics:
    """Calculates MySQL server health metrics.

    Provides methods to assess connection health, InnoDB performance,
    and resource limit utilization.
    """

    def __init__(self, connection):
        """Initialize with MySQL connection.

        Args:
            connection: MySQLConnection instance
        """
        self.conn = connection

    def get_server_uptime_info(
        self, status_vars: Dict[str, str]
    ) -> Tuple[int, int, int, datetime]:
        """Calculate server uptime and start time.

        Args:
            status_vars: Dict from SHOW GLOBAL STATUS

        Returns:
            Tuple of (uptime_days, uptime_hours, uptime_mins, server_start_time)
        """
        uptime_seconds = int(status_vars.get('Uptime', 0))
        uptime_days = uptime_seconds // 86400
        uptime_hours = (uptime_seconds % 86400) // 3600
        uptime_mins = (uptime_seconds % 3600) // 60

        # Calculate server start time using MySQL's clock
        mysql_time = self.conn.execute_single(
            "SELECT UNIX_TIMESTAMP() as timestamp"
        )
        mysql_timestamp = int(mysql_time['timestamp'])
        server_start_timestamp = mysql_timestamp - uptime_seconds
        server_start_time = datetime.fromtimestamp(
            server_start_timestamp, timezone.utc
        )

        return uptime_days, uptime_hours, uptime_mins, server_start_time

    def calculate_connection_health(self, status_vars: Dict[str, str]) -> Dict:
        """Calculate connection health metrics.

        Args:
            status_vars: Dict from SHOW GLOBAL STATUS

        Returns:
            Dict with current/max connections, percentages, and status indicators
        """
        max_connections = int(self.conn.execute_single(
            "SHOW VARIABLES LIKE 'max_connections'"
        )['Value'])
        current_connections = int(status_vars.get('Threads_connected', 0))
        max_used_connections = int(status_vars.get('Max_used_connections', 0))

        connection_pct = ((current_connections / max_connections * 100)
                         if max_connections else 0)
        max_used_pct = ((max_used_connections / max_connections * 100)
                       if max_connections else 0)

        if connection_pct < 80:
            connection_status = '✅'
        elif connection_pct < 95:
            connection_status = '⚠️'
        else:
            connection_status = '❌'
        max_used_status = '⚠️' if max_used_pct >= 100 else '✅'

        return {
            'current': current_connections,
            'max': max_connections,
            'percentage': connection_pct,
            'max_used_ever': max_used_connections,
            'max_used_pct': max_used_pct,
            'status': connection_status,
            'max_used_status': max_used_status,
        }

    def calculate_innodb_health(self, status_vars: Dict[str, str]) -> Dict:
        """Calculate InnoDB health metrics.

        Args:
            status_vars: Dict from SHOW GLOBAL STATUS

        Returns:
            Dict with buffer pool hit rate, locks, deadlocks, and status
        """
        innodb_buffer_pool_reads = int(
            status_vars.get('Innodb_buffer_pool_reads', 0)
        )
        innodb_buffer_pool_read_requests = int(
            status_vars.get('Innodb_buffer_pool_read_requests', 1)
        )

        if innodb_buffer_pool_read_requests:
            buffer_hit_rate = (
                100 * (1 - innodb_buffer_pool_reads /
                       innodb_buffer_pool_read_requests)
            )
        else:
            buffer_hit_rate = 0

        if buffer_hit_rate > 99:
            buffer_status = '✅'
        elif buffer_hit_rate > 95:
            buffer_status = '⚠️'
        else:
            buffer_status = '❌'

        row_lock_waits = int(status_vars.get('Innodb_row_lock_waits', 0))
        deadlocks = int(status_vars.get('Innodb_deadlocks', 0))

        return {
            'buffer_hit_rate': buffer_hit_rate,
            'status': buffer_status,
            'row_lock_waits': row_lock_waits,
            'deadlocks': deadlocks,
        }

    def calculate_resource_limits(self, status_vars: Dict[str, str]) -> Dict:
        """Calculate resource limit metrics.

        Args:
            status_vars: Dict from SHOW GLOBAL STATUS

        Returns:
            Dict with open files current/limit, percentage, and status
        """
        open_files = int(status_vars.get('Open_files', 0))
        open_files_limit = int(self.conn.execute_single(
            "SHOW VARIABLES LIKE 'open_files_limit'"
        )['Value'])
        open_files_pct = ((open_files / open_files_limit * 100)
                         if open_files_limit > 0 else 0)

        if open_files_pct < 75:
            open_files_status = '✅'
        elif open_files_pct < 90:
            open_files_status = '⚠️'
        else:
            open_files_status = '❌'

        return {
            'open_files': {
                'current': open_files,
                'limit': open_files_limit,
                'percentage': open_files_pct,
                'status': open_files_status,
            }
        }
