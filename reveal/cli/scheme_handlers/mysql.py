"""Handler for mysql:// URIs."""

import sys
import json
from typing import Optional
from argparse import Namespace


def _render_mysql_result(result: dict, format: str = 'text'):
    """Render MySQL adapter results in human-readable format."""
    if format == 'json':
        print(json.dumps(result, indent=2))
        return

    # Handle different result types
    result_type = result.get('type', 'mysql_server')

    if result_type == 'mysql_server':
        # Main health overview
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
            print(f"  Lag: {repl['lag']}s")
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

    else:
        # Element-specific results - just JSON for now
        print(json.dumps(result, indent=2))


def _render_mysql_check_result(result: dict):
    """Render MySQL health check results in human-readable format."""
    status = result['status']
    summary = result['summary']

    # Header with overall status
    status_icon = '✅' if status == 'pass' else '⚠️' if status == 'warning' else '❌'
    print(f"\nMySQL Health Check: {status_icon} {status.upper()}")
    print(f"\nSummary: {summary['passed']}/{summary['total']} passed, {summary['warnings']} warnings, {summary['failures']} failures")
    print()

    # Group checks by status for better readability
    failures = [c for c in result['checks'] if c['status'] == 'failure']
    warnings = [c for c in result['checks'] if c['status'] == 'warning']
    passes = [c for c in result['checks'] if c['status'] == 'pass']

    # Show failures first
    if failures:
        print("❌ Failures:")
        for check in failures:
            print(f"  • {check['name']}: {check['value']} (threshold: {check['threshold']}, severity: {check['severity']})")
        print()

    # Then warnings
    if warnings:
        print("⚠️  Warnings:")
        for check in warnings:
            print(f"  • {check['name']}: {check['value']} (threshold: {check['threshold']}, severity: {check['severity']})")
        print()

    # Finally passes (if verbose or no issues)
    if passes and (not failures and not warnings):
        print("✅ All Checks Passed:")
        for check in passes:
            print(f"  • {check['name']}: {check['value']} (threshold: {check['threshold']})")
        print()

    # Exit code hint
    print(f"Exit code: {result['exit_code']}")


def handle_mysql(adapter_class: type, resource: str, element: Optional[str],
                 args: Namespace) -> None:
    """Handle mysql:// URIs."""
    # Build connection string from resource and element
    connection_string = f"mysql://{resource}"

    adapter = adapter_class(connection_string)

    # Handle --check flag: run health checks with thresholds
    if getattr(args, 'check', False):
        result = adapter.check()

        # Render check results
        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            _render_mysql_check_result(result)

        # Exit with appropriate code
        sys.exit(result['exit_code'])

    # If element is specified, get element details
    if adapter.element:
        result = adapter.get_element(adapter.element)
        if result is None:
            print(f"Error: Element '{adapter.element}' not found", file=sys.stderr)
            print(f"Available elements: connections, performance, innodb, replication, storage, errors, variables, health, databases", file=sys.stderr)
            sys.exit(1)
    else:
        # Get structure (health overview)
        result = adapter.get_structure()

    # Render output
    if args.format == 'json':
        print(json.dumps(result, indent=2))
    else:
        # Pretty-print the structure
        _render_mysql_result(result, args.format)
