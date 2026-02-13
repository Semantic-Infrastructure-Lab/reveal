"""MySQL performance metrics and InnoDB engine status."""

from typing import Dict, Any


class PerformanceAnalyzer:
    """Analyzes MySQL query performance and InnoDB engine metrics.

    Provides performance insights including query efficiency, table scans,
    thread cache, temporary tables, and InnoDB buffer pool statistics.
    """

    def __init__(self, connection):
        """Initialize with MySQL connection.

        Args:
            connection: MySQLConnection instance
        """
        self.conn = connection

    def _calculate_scan_metrics(self, status_vars: dict) -> dict:
        """Calculate full table scan metrics.

        Args:
            status_vars: MySQL status variables

        Returns:
            Dict with scan metrics and status
        """
        select_scan = int(status_vars.get('Select_scan', 0))
        select_range = int(status_vars.get('Select_range', 0))
        select_total = select_scan + select_range
        scan_ratio = (select_scan / select_total * 100) if select_total > 0 else 0
        handler_rnd = int(status_vars.get('Handler_read_rnd_next', 0))

        scan_status = '✅' if scan_ratio < 10 else '⚠️' if scan_ratio < 25 else '❌'

        return {
            'select_scan_ratio': f'{scan_ratio:.2f}%',
            'status': scan_status,
            'select_scan': f'{select_scan} (since server start)',
            'select_range': f'{select_range} (since server start)',
            'handler_read_rnd_next': f'{handler_rnd} (since server start)',
            'note': 'High scan ratio (>25%) or Handler_read_rnd_next indicates missing indexes'
        }

    def _calculate_thread_cache_metrics(self, status_vars: dict) -> dict:
        """Calculate thread cache efficiency metrics.

        Args:
            status_vars: MySQL status variables

        Returns:
            Dict with thread cache metrics and status
        """
        threads_created = int(status_vars.get('Threads_created', 0))
        connections = int(status_vars.get('Connections', 1))
        thread_cache_miss_rate = (threads_created / connections * 100) if connections > 0 else 0

        thread_status = '✅' if thread_cache_miss_rate < 10 else '⚠️' if thread_cache_miss_rate < 25 else '❌'

        return {
            'miss_rate': f'{thread_cache_miss_rate:.2f}%',
            'status': thread_status,
            'threads_created': f'{threads_created} (since server start)',
            'connections': f'{connections} (since server start)',
            'note': 'Miss rate >10% suggests increasing thread_cache_size'
        }

    def _calculate_temp_table_metrics(self, status_vars: dict) -> dict:
        """Calculate temporary table metrics.

        Args:
            status_vars: MySQL status variables

        Returns:
            Dict with temp table metrics and status
        """
        tmp_disk = int(status_vars.get('Created_tmp_disk_tables', 0))
        tmp_total = int(status_vars.get('Created_tmp_tables', 1))
        tmp_disk_ratio = (tmp_disk / tmp_total * 100) if tmp_total > 0 else 0

        tmp_status = '✅' if tmp_disk_ratio < 25 else '⚠️' if tmp_disk_ratio < 50 else '❌'

        return {
            'disk_ratio': f'{tmp_disk_ratio:.2f}%',
            'status': tmp_status,
            'on_disk': f'{tmp_disk} (since server start)',
            'total': f'{tmp_total} (since server start)',
            'note': 'Ratio >25% suggests increasing tmp_table_size or max_heap_table_size'
        }

    def get_performance(self) -> Dict[str, Any]:
        """Get query performance metrics.

        Returns:
            Dict with QPS, slow queries, table scans, thread cache, temp tables
        """
        timing = self.conn.get_snapshot_context()
        status_vars = {row['Variable_name']: row['Value']
                      for row in self.conn.execute_query("SHOW GLOBAL STATUS")}

        uptime_seconds = timing['uptime_seconds']
        questions = float(status_vars.get('Questions', 0))
        slow_queries = status_vars.get('Slow_queries', 0)

        # Calculate all metrics
        scan_metrics = self._calculate_scan_metrics(status_vars)
        thread_metrics = self._calculate_thread_cache_metrics(status_vars)
        tmp_metrics = self._calculate_temp_table_metrics(status_vars)

        return {
            'type': 'performance',
            **timing,
            'queries_per_second': questions / float(uptime_seconds),
            'slow_queries_total': f"{slow_queries} (since server start)",
            'full_table_scans': scan_metrics,
            'thread_cache_efficiency': thread_metrics,
            'temp_tables': tmp_metrics,
            'sort_merge_passes': f"{status_vars.get('Sort_merge_passes', 0)} (since server start)",
        }

    def get_innodb(self) -> Dict[str, Any]:
        """Get InnoDB engine status.

        Returns:
            Dict with buffer pool hit rate, locks, deadlocks
        """
        timing = self.conn.get_snapshot_context()
        status_vars = {row['Variable_name']: row['Value']
                      for row in self.conn.execute_query("SHOW GLOBAL STATUS")}

        buffer_reads = int(status_vars.get('Innodb_buffer_pool_reads', 0))
        buffer_requests = int(
            status_vars.get('Innodb_buffer_pool_read_requests', 1)
        )
        hit_rate = (100 * (1 - buffer_reads / buffer_requests)
                   if buffer_requests else 0)

        return {
            'type': 'innodb',
            **timing,
            'buffer_pool_hit_rate': f"{hit_rate:.2f}%",
            'buffer_pool_reads': f"{buffer_reads} (since server start)",
            'buffer_pool_read_requests': f"{buffer_requests} (since server start)",
            'row_lock_waits': (
                f"{status_vars.get('Innodb_row_lock_waits', 0)} "
                "(since server start)"
            ),
            'row_lock_time_avg': (
                f"{status_vars.get('Innodb_row_lock_time_avg', 0)} ms"
            ),
            'deadlocks': (
                f"{status_vars.get('Innodb_deadlocks', 0)} "
                "(since server start)"
            ),
        }
