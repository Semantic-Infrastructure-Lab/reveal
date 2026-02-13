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
