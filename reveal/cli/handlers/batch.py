"""Stdin and batch processing handlers for reveal CLI.

Implements --stdin mode, --batch aggregation, SSL batch checks,
and multi-URI result rendering.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, List, Any

if TYPE_CHECKING:
    from argparse import Namespace


def _passes_ext_filter(target: str, ext_filter: Optional[str]) -> bool:
    """Return True if target passes the extension filter (or no filter is set)."""
    if not ext_filter:
        return True
    allowed = {e.strip().lower().lstrip('.') for e in ext_filter.split(',') if e.strip()}
    return Path(target).suffix.lower().lstrip('.') in allowed


def _process_stdin_uri(target: str, args: 'Namespace', is_batch_mode: bool,
                       is_ssl_batch_check: bool, batch_results: list,
                       ssl_check_results: list) -> None:
    """Process a URI from stdin.

    Args:
        target: URI to process
        args: Parsed arguments
        is_batch_mode: Whether in generic batch mode
        is_ssl_batch_check: Whether in SSL batch check mode
        batch_results: List to collect batch results
        ssl_check_results: List to collect SSL check results
    """
    from ..routing import handle_uri

    # Generic batch mode - collect results from any adapter
    if is_batch_mode:
        result = _collect_batch_result(target, args)
        batch_results.append(result)
        return

    # Legacy SSL-specific batch mode for backward compatibility
    if is_ssl_batch_check and target.startswith('ssl://'):
        ssl_result: Optional[Dict[str, Any]] = _collect_ssl_check_result(target, args)
        if ssl_result:
            ssl_check_results.append(ssl_result)
        return

    # Non-batch URIs go through normal path
    try:
        handle_uri(target, None, args)
    except SystemExit as e:
        # Only warn for actual failures (non-zero exit codes)
        if e.code != 0:
            print(f"Warning: {target} failed, skipping", file=sys.stderr)


def _process_stdin_file(target: str, args: 'Namespace', handle_file_func) -> None:
    """Process a file path from stdin.

    Args:
        target: File path to process
        args: Parsed arguments
        handle_file_func: Function to handle individual files
    """
    path = Path(target)

    # Skip if path doesn't exist (graceful degradation)
    if not path.exists():
        print(f"Warning: {target} not found, skipping", file=sys.stderr)
        return

    # Skip directories (only process files)
    if path.is_dir():
        print(f"Warning: {target} is a directory, skipping (use reveal {target}/ directly)", file=sys.stderr)
        return

    # Process the file
    if path.is_file():
        handle_file_func(str(path), None, args.meta, args.format, args)


def handle_stdin_mode(args: 'Namespace', handle_file_func):
    """Handle --stdin mode to process files/URIs from stdin.

    Args:
        args: Parsed arguments
        handle_file_func: Function to handle individual files

    Supports both file paths and URIs (scheme://resource).
    URIs are routed to the appropriate adapter handler.

    When --batch is used, results are aggregated across all adapters.
    When --check is used with SSL URIs, results are aggregated and
    batch flags (--summary, --only-failures, --expiring-within) are applied.
    """
    if args.element:
        print("Error: Cannot use element extraction with --stdin", file=sys.stderr)
        sys.exit(1)

    # Check if we're in batch mode (explicit --batch or SSL batch checks)
    is_batch_mode = getattr(args, 'batch', False)
    is_ssl_batch_check = getattr(args, 'check', False) and not is_batch_mode

    # Collect results for batch aggregation
    ssl_check_results: List[Dict[str, Any]] = []
    batch_results: List[dict] = []

    # Read paths/URIs from stdin (one per line)
    first_line_checked = False
    for line in sys.stdin:
        target = line.strip()
        if not target:
            continue  # Skip empty lines

        # Detect common mistake: piping a git diff patch instead of file names
        if not first_line_checked:
            first_line_checked = True
            if target.startswith('diff --git ') or target.startswith('--- a/'):
                print(
                    "Error: stdin looks like a git diff patch, not a list of file paths.\n"
                    "Use 'git diff --name-only' to get file names:\n"
                    "  git diff --name-only | reveal --stdin",
                    file=sys.stderr
                )
                sys.exit(1)

        # Check if this is a URI (scheme://resource)
        if '://' in target:
            _process_stdin_uri(target, args, is_batch_mode, is_ssl_batch_check,
                             batch_results, ssl_check_results)
        else:
            # Apply --ext filter for file paths
            if _passes_ext_filter(target, getattr(args, 'ext', None)):
                _process_stdin_file(target, args, handle_file_func)

    # Render aggregated batch results
    if batch_results:
        _render_batch_results(batch_results, args)
        # _render_batch_results handles exit
        return

    # Render aggregated SSL batch results if we collected any (legacy path)
    if ssl_check_results:
        _render_ssl_batch_results(ssl_check_results, args)

    sys.exit(0)


def _collect_ssl_check_result(uri: str, args: 'Namespace') -> Optional[Dict[str, Any]]:
    """Collect SSL check result without rendering.

    Args:
        uri: SSL URI (ssl://domain.com)
        args: CLI arguments

    Returns:
        Check result dict or None on error
    """
    from ...adapters.base import get_adapter_class

    try:
        adapter_class = get_adapter_class('ssl')
        if not adapter_class:
            return None

        adapter = adapter_class(uri)
        result = adapter.check()
        return result  # type: ignore[no-any-return]
    except Exception as e:
        # Return error result so it shows up in batch output
        host = uri.replace('ssl://', '')
        return {
            'host': host,
            'port': 443,
            'status': 'failure',
            'error': str(e),
            'summary': {'total': 1, 'passed': 0, 'warnings': 0, 'failures': 1},
            'exit_code': 2,
        }


def _render_ssl_batch_results(results: list, args: 'Namespace') -> None:
    """Render collected SSL check results as a batch.

    Args:
        results: List of individual check results
        args: CLI arguments with batch flags
    """
    from ...adapters.ssl.renderer import SSLRenderer

    # Build batch result structure
    total = len(results)
    passed = sum(1 for r in results if r.get('status') == 'pass')
    warnings = sum(1 for r in results if r.get('status') == 'warning')
    failures = sum(1 for r in results if r.get('status') == 'failure')

    batch_result = {
        'type': 'ssl_batch_check',
        'source': 'stdin',
        'domains_checked': total,
        'status': 'pass' if failures == 0 and warnings == 0 else (
            'warning' if failures == 0 else 'failure'
        ),
        'summary': {
            'total': total,
            'passed': passed,
            'warnings': warnings,
            'failures': failures,
        },
        'results': results,
        'exit_code': 0 if failures == 0 else 2,
    }

    # Get batch flags from args
    only_failures = getattr(args, 'only_failures', False)
    summary = getattr(args, 'summary', False)
    expiring_within = getattr(args, 'expiring_within', None)

    # Render using SSLRenderer which handles all batch flags
    SSLRenderer.render_check(
        batch_result, args.format,
        only_failures=only_failures,
        summary=summary,
        expiring_within=expiring_within
    )


def _collect_batch_result(uri: str, args: 'Namespace') -> dict:
    """Collect check result from any adapter without rendering.

    Args:
        uri: URI to check (ssl://domain.com, domain://example.com, etc.)
        args: CLI arguments

    Returns:
        Result dict with status and data, or error result
    """
    from ...adapters.base import get_adapter_class

    try:
        # Parse scheme from URI
        if '://' not in uri:
            return {
                'uri': uri,
                'status': 'error',
                'error': 'Invalid URI format (missing scheme://)',
            }

        scheme = uri.split('://')[0]
        adapter_class = get_adapter_class(scheme)

        if not adapter_class:
            return {
                'uri': uri,
                'status': 'error',
                'error': f'No adapter found for scheme: {scheme}',
            }

        # Initialize adapter
        adapter = adapter_class(uri)

        # If --check flag and adapter has check method, use it
        if getattr(args, 'check', False) and hasattr(adapter, 'check'):
            result = adapter.check(
                advanced=getattr(args, 'advanced', False),
                only_failures=getattr(args, 'only_failures', False),
            )
            return {
                'uri': uri,
                'scheme': scheme,
                'status': result.get('status', 'unknown'),
                'data': result,
            }

        # Otherwise get structure
        result = adapter.get_structure()
        return {
            'uri': uri,
            'scheme': scheme,
            'status': 'success',
            'data': result,
        }

    except Exception as e:
        return {
            'uri': uri,
            'scheme': scheme if '://' in uri else 'unknown',
            'status': 'error',
            'error': str(e),
        }


def _aggregate_batch_stats(results: list) -> dict:
    """Aggregate batch statistics.

    Args:
        results: List of individual results

    Returns:
        Dict with total, successful, warnings, failures counts
    """
    return {
        'total': len(results),
        'successful': sum(1 for r in results if r['status'] in ('success', 'pass')),
        'warnings': sum(1 for r in results if r['status'] == 'warning'),
        'failures': sum(1 for r in results if r['status'] in ('failure', 'error')),
    }


def _group_results_by_scheme(results: list) -> dict:
    """Group results by adapter scheme.

    Args:
        results: List of individual results

    Returns:
        Dict mapping scheme to list of results
    """
    by_scheme: Dict[str, List[Any]] = {}
    for result in results:
        scheme = result.get('scheme', 'unknown')
        if scheme not in by_scheme:
            by_scheme[scheme] = []
        by_scheme[scheme].append(result)
    return by_scheme


def _filter_batch_display_results(results: list, only_failures: bool) -> list:
    """Filter results to failures/warnings if requested.

    Args:
        results: All results
        only_failures: Whether to filter to failures only

    Returns:
        Filtered or original results
    """
    if only_failures:
        return [r for r in results if r['status'] in ('failure', 'error', 'warning')]
    return results


def _determine_batch_overall_status(failures: int, warnings: int) -> str:
    """Determine overall batch status.

    Args:
        failures: Number of failures
        warnings: Number of warnings

    Returns:
        Status string: 'pass', 'warning', or 'failure'
    """
    if failures == 0 and warnings == 0:
        return 'pass'
    return 'warning' if failures == 0 else 'failure'


def _get_status_indicator(status: str) -> str:
    """Get status indicator emoji.

    Args:
        status: Status string

    Returns:
        Emoji indicator
    """
    if status in ('success', 'pass'):
        return '✓'
    elif status == 'warning':
        return '⚠'
    else:
        return '✗'


def _render_batch_text_output(stats: dict, overall_status: str,
                               by_scheme: dict, display_results: list,
                               summary_only: bool = False) -> None:
    """Render batch results in text format.

    Args:
        stats: Statistics dict
        overall_status: Overall status string
        by_scheme: Results grouped by scheme
        display_results: Filtered results to display
        summary_only: When True, skip per-URI lines (show header only)
    """
    print(f"\n{'='*60}")
    print("BATCH CHECK RESULTS")
    print(f"{'='*60}")
    print(f"Total URIs: {stats['total']}")
    print(f"Successful: {stats['successful']} ✓")
    if stats['warnings'] > 0:
        print(f"Warnings: {stats['warnings']} ⚠")
    if stats['failures'] > 0:
        print(f"Failures: {stats['failures']} ✗")
    print(f"Overall Status: {overall_status.upper()}")

    if len(by_scheme) > 1:
        print(f"\nAdapters used: {', '.join(by_scheme.keys())}")

    print(f"{'='*60}\n")

    # Skip per-URI lines when --summary is requested
    if summary_only:
        return

    if display_results:
        for result in display_results:
            uri = result['uri']
            status = result['status']
            indicator = _get_status_indicator(status)

            print(f"{indicator} {uri}: {status.upper()}")

            # Show error details
            if 'error' in result:
                print(f"  Error: {result['error']}")


def _calculate_batch_exit_code(failures: int, warnings: int) -> int:
    """Calculate appropriate exit code.

    Args:
        failures: Number of failures
        warnings: Number of warnings

    Returns:
        Exit code (0, 1, or 2)
    """
    if failures > 0:
        return 2
    return 0


def _render_batch_results(results: list, args: 'Namespace') -> None:
    """Render collected batch results with aggregation.

    Args:
        results: List of individual results from different adapters
        args: CLI arguments with batch flags
    """
    import json

    # Aggregate statistics
    stats = _aggregate_batch_stats(results)

    # Group by scheme
    by_scheme = _group_results_by_scheme(results)

    # Filter results if requested
    display_results = _filter_batch_display_results(
        results, getattr(args, 'only_failures', False)
    )

    # Determine overall status
    overall_status = _determine_batch_overall_status(
        stats['failures'], stats['warnings']
    )

    # Build batch output
    batch_result = {
        'type': 'batch_check',
        'total': stats['total'],
        'status': overall_status,
        'summary': {
            'successful': stats['successful'],
            'warnings': stats['warnings'],
            'failures': stats['failures'],
        },
        'adapters': list(by_scheme.keys()),
        'results': display_results,
    }

    summary_only = getattr(args, 'summary', False)

    # Render based on format
    if args.format == 'json':
        if summary_only:
            # Drop per-URI results from JSON when --summary is requested
            batch_result = {k: v for k, v in batch_result.items() if k != 'results'}
        print(json.dumps(batch_result, indent=2))
    else:
        _render_batch_text_output(stats, overall_status, by_scheme, display_results,
                                   summary_only=summary_only)

    # Exit with appropriate code
    exit_code = _calculate_batch_exit_code(stats['failures'], stats['warnings'])
    sys.exit(exit_code)
