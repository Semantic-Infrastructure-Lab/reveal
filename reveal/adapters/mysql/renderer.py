"""MySQL result rendering for CLI output."""

import sys

from reveal.rendering import TypeDispatchRenderer


class MySQLRenderer(TypeDispatchRenderer):
    """Renderer for MySQL adapter results.

    Uses TypeDispatchRenderer for automatic routing to _render_{type}() methods.
    """

    @staticmethod
    def _render_mysql_server(result: dict) -> None:
        """Render main health overview."""
        print(f"MySQL Server: {result['server']}")
        print(f"Version: {result['version']}")
        print(f"Uptime: {result['uptime']}")
        print()

        conn = result['connection_health']
        print(f"Connection Health: {conn['status']}")
        print(f"  Current: {conn['current']} / {conn['max']} max ({conn['percentage']})")
        print()

        perf = result['performance']
        print("Performance:")
        print(f"  QPS: {perf['qps']} queries/sec")
        print(f"  Slow Queries: {perf['slow_queries']}")
        print(f"  Threads Running: {perf['threads_running']}")
        print()

        innodb = result['innodb_health']
        print(f"InnoDB Health: {innodb['status']}")
        print(f"  Buffer Pool Hit Rate: {innodb['buffer_pool_hit_rate']}")
        print(f"  Row Lock Waits: {innodb['row_lock_waits']}")
        print(f"  Deadlocks: {innodb['deadlocks']}")
        print()

        repl = result['replication']
        print(f"Replication: {repl['role']}")
        if 'lag' in repl:
            lag = repl['lag']
            lag_display = f"{lag}s" if isinstance(lag, (int, float)) else str(lag)
            print(f"  Lag: {lag_display}")
        if 'slaves' in repl:
            print(f"  Slaves: {repl['slaves']}")
        print()

        storage = result['storage']
        print("Storage:")
        print(f"  Total: {storage['total_size_gb']:.2f} GB across {storage['database_count']} databases")
        print(f"  Largest: {storage['largest_db']}")
        print()

        print(f"Health Status: {result['health_status']}")
        print("Issues:")
        for issue in result['health_issues']:
            print(f"  • {issue}")
        print()

        print("Next Steps:")
        for step in result['next_steps']:
            print(f"  {step}")
        print()

        # Available elements (Phase 5: Element Discovery)
        if result.get('available_elements'):
            print("📍 Available elements:")
            for elem in result['available_elements']:
                name = elem['name']
                desc = elem['description']
                print(f"  /{name:<15} {desc}")
            print()
            # Show example usage hint with first element
            if result['available_elements']:
                example = result['available_elements'][0]['example']
                print(f"💡 Try: {example}")

    @staticmethod
    def _print_measurement_window(result: dict) -> None:
        """Print the shared snapshot-timing line most elements carry."""
        window = result.get('measurement_window')
        if window:
            print(f"Measurement window: {window}")
            print()

    @staticmethod
    def _render_connections(result: dict) -> None:
        """Render connections/processlist element."""
        print("MySQL Connections")
        MySQLRenderer._print_measurement_window(result)

        print(f"Total Connections: {result['total_connections']}")
        print()

        print("By State:")
        for state, count in result['by_state'].items():
            print(f"  {state}: {count}")
        print()

        long_running = result['long_running_queries']
        print(f"Long-Running Queries (>5s): {len(long_running)}")
        for q in long_running:
            print(f"  [{q['id']}] {q['user']}@{q['db']} - {q['time']}s ({q['state']})")
            if q['info']:
                print(f"    {q['info']}")

    @staticmethod
    def _render_errors(result: dict) -> None:
        """Render error-indicator element."""
        print("MySQL Errors")
        MySQLRenderer._print_measurement_window(result)

        print(f"Aborted Clients: {result['aborted_clients']}")
        print(f"Aborted Connects: {result['aborted_connects']}")
        print(f"Connection Errors (internal): {result['connection_errors_internal']}")
        print(f"Connection Errors (max_connections): {result['connection_errors_max_connections']}")

    @staticmethod
    def _render_variables(result: dict) -> None:
        """Render server-variables element."""
        print("MySQL Variables")
        MySQLRenderer._print_measurement_window(result)

        for name, value in result['variables'].items():
            print(f"  {name}: {value}")

    @staticmethod
    def _render_databases(result: dict) -> None:
        """Render database-list element."""
        databases = result['databases']
        print(f"MySQL Databases ({len(databases)})")
        MySQLRenderer._print_measurement_window(result)

        for db in databases:
            print(f"  • {db}")

    @staticmethod
    def _render_indexes(result: dict) -> None:
        """Render index-usage element."""
        print("MySQL Index Usage")
        print(f"Measurement basis: {result['measurement_basis']} (since {result['measurement_start_time']})")
        ps_status = result['performance_schema_status']
        print(f"Performance Schema: {'enabled' if ps_status.get('enabled') else 'disabled'}")
        print()

        most_used = result['most_used']
        print(f"Most Used Indexes (top {len(most_used)}):")
        for row in most_used:
            print(f"  {row['object_schema']}.{row['object_name']}.{row['index_name']}: "
                  f"{row['total_accesses']} accesses ({row['read_pct']}% read)")
        print()

        unused = result['unused']
        print(f"Unused Indexes: {result['unused_count']}")
        for row in unused:
            print(f"  {row['object_schema']}.{row['object_name']}.{row['index_name']}")

    @staticmethod
    def _render_slow_queries(result: dict) -> None:
        """Render slow-query-log element."""
        if 'error' in result:
            print("MySQL Slow Queries: unavailable")
            print(f"  {result['message']}")
            print(f"  ({result['error']})")
            return

        print(f"MySQL Slow Queries (last {result['period']})")
        print()

        summary = result['summary'] or {}
        print("Summary:")
        print(f"  Total: {summary.get('total_slow_queries', 0)}")
        print(f"  Avg time: {summary.get('avg_time')}s "
              f"(min {summary.get('min_time')}s, max {summary.get('max_time')}s)")
        print(f"  Rows examined: {summary.get('total_rows_examined', 0)}")
        print()

        top_queries = result['top_queries']
        print(f"Top Queries ({len(top_queries)}):")
        for q in top_queries:
            print(f"  [{q['query_time_seconds']}s] {q['user_host']} - {q['rows_examined']} rows examined")
            print(f"    {q['query_preview']}")

    @staticmethod
    def _render_tables(result: dict) -> None:
        """Render table I/O statistics element."""
        print(f"MySQL Table I/O ({result['table_count']} tables)")
        print(f"Measurement basis: {result['measurement_basis']} (since {result['measurement_start_time']})")
        print()

        for entry in result['tables']:
            print(f"  {entry['table_name']}: {entry['reads']} reads / {entry['writes']} writes "
                  f"(ratio {entry['read_write_ratio']}), {entry['total_time_hours']}h total")
            if entry['alert']:
                print(f"    ⚠️  {entry['alert']}: {entry['recommendation']}")
        print()

        print(f"Alerts: {result['alert_count']}")
        for alert in result['alerts']:
            print(f"  • {alert['table']}: {alert['type']} - {alert['recommendation']}")

    @staticmethod
    def _render_performance(result: dict) -> None:
        """Render query-performance element."""
        print("MySQL Performance")
        MySQLRenderer._print_measurement_window(result)

        print(f"QPS: {result['queries_per_second']:.2f}")
        print(f"Slow Queries: {result['slow_queries_total']}")
        print(f"Sort Merge Passes: {result['sort_merge_passes']}")
        print()

        scans = result['full_table_scans']
        print(f"Full Table Scans: {scans['status']} {scans['select_scan_ratio']}")
        print(f"  {scans['note']}")
        print()

        threads = result['thread_cache_efficiency']
        print(f"Thread Cache: {threads['status']} {threads['miss_rate']} miss rate")
        print(f"  {threads['note']}")
        print()

        tmp = result['temp_tables']
        print(f"Temp Tables: {tmp['status']} {tmp['disk_ratio']} on disk")
        print(f"  {tmp['note']}")

    @staticmethod
    def _render_innodb(result: dict) -> None:
        """Render InnoDB engine-status element."""
        print("MySQL InnoDB")
        MySQLRenderer._print_measurement_window(result)

        print(f"Buffer Pool Hit Rate: {result['buffer_pool_hit_rate']}")
        print(f"  Reads: {result['buffer_pool_reads']}")
        print(f"  Read Requests: {result['buffer_pool_read_requests']}")
        print(f"Row Lock Waits: {result['row_lock_waits']}")
        print(f"Row Lock Time (avg): {result['row_lock_time_avg']}")
        print(f"Deadlocks: {result['deadlocks']}")

    @staticmethod
    def _render_replication(result: dict) -> None:
        """Render replication-status element."""
        role = result['role']
        print(f"MySQL Replication: {role}")
        print()

        if role == 'Slave':
            print(f"Master: {result['master_host']}:{result['master_port']}")
            print(f"IO Running: {result['io_running']}")
            print(f"SQL Running: {result['sql_running']}")
            print(f"Seconds Behind Master: {result['seconds_behind_master']}")
            print(f"Last Error: {result['last_error']}")
        elif role == 'Master':
            slaves = result['slaves']
            print(f"Slaves: {len(slaves)}")
            for s in slaves:
                print(f"  • server_id={s['server_id']} host={s['host']}")
        else:
            print(result['message'])

    @staticmethod
    def _render_storage(result: dict) -> None:
        """Render storage-by-database element."""
        print("MySQL Storage")
        MySQLRenderer._print_measurement_window(result)

        for db in result['databases']:
            print(f"  {db['db_name']}: {db['size_gb']} GB "
                  f"({db['table_count']} tables, {db['data_gb']} data / {db['index_gb']} index)")

    @staticmethod
    def _render_database_storage(result: dict) -> None:
        """Render storage/<db_name> element (per-table breakdown)."""
        print(f"MySQL Storage: {result['database']}")
        MySQLRenderer._print_measurement_window(result)

        for t in result['tables']:
            print(f"  {t['table_name']} ({t['engine']}): {t['size_mb']} MB, {t['table_rows']} rows")

    @staticmethod
    def _get_status_icon(status: str) -> str:
        """Get icon for check status."""
        if status == 'pass':
            return '✅'
        elif status == 'warning':
            return '⚠️'
        else:
            return '❌'

    @staticmethod
    def _group_checks_by_status(checks: list) -> tuple:
        """Group checks into failures, warnings, and passes.

        Returns:
            Tuple of (failures, warnings, passes)
        """
        failures = [c for c in checks if c['status'] == 'failure']
        warnings = [c for c in checks if c['status'] == 'warning']
        passes = [c for c in checks if c['status'] == 'pass']
        return failures, warnings, passes

    @staticmethod
    def _render_check_group(checks: list, title: str, icon: str, show_severity: bool = False) -> None:
        """Render a group of checks.

        Args:
            checks: List of checks to render
            title: Group title
            icon: Icon for the group
            show_severity: Whether to show severity in output
        """
        if not checks:
            return

        print(f"{icon} {title}:")
        for check in checks:
            if show_severity:
                print(f"  • {check['name']}: {check['value']} (threshold: {check['threshold']}, severity: {check['severity']})")
            else:
                print(f"  • {check['name']}: {check['value']} (threshold: {check['threshold']})")
        print()

    @classmethod
    def render_check(cls, result: dict, format: str = 'text',
                     only_failures: bool = False, **kwargs) -> None:
        """Render MySQL health check results.

        Args:
            result: Check result dictionary from MySQLAdapter.check()
            format: Output format ('text' or 'json')
            only_failures: Only show failed/warning results (not passing)
            **kwargs: Additional render options (ignored for compatibility)
        """
        if cls.should_render_json(format):
            cls.render_json(result)
            return

        status = result['status']
        summary = result['summary']

        # Header with overall status
        status_icon = cls._get_status_icon(status)
        print(f"\nMySQL Health Check: {status_icon} {status.upper()}")
        print(f"\nSummary: {summary['passed']}/{summary['total']} passed, {summary['warnings']} warnings, {summary['failures']} failures")
        print()

        # Group checks by status
        failures, warnings, passes = cls._group_checks_by_status(result['checks'])

        # Render each group
        cls._render_check_group(failures, "Failures", "❌", show_severity=True)
        cls._render_check_group(warnings, "Warnings", "⚠️", show_severity=True)

        if not only_failures:
            cls._render_check_group(passes, "Passed", "✅")

        # Exit code hint
        print(f"Exit code: {result['exit_code']}")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly error messages.

        Args:
            error: Exception to render
        """
        if isinstance(error, ImportError):
            print("Error: mysql:// adapter requires pymysql", file=sys.stderr)
            print("", file=sys.stderr)
            print("Install with:", file=sys.stderr)
            print("  pip install reveal-cli[database]", file=sys.stderr)
            print("  # or", file=sys.stderr)
            print("  pip install pymysql", file=sys.stderr)
        else:
            # Generic error display
            print(f"Error: {error}", file=sys.stderr)
