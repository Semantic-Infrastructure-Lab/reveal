"""Stdin and batch processing handlers for reveal CLI.

Implements --stdin mode, --batch aggregation, SSL batch checks,
and multi-URI result rendering.
"""

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, List, Any, Tuple

from ...utils.results import outcome_of

if TYPE_CHECKING:
    from argparse import Namespace
    from ..routing.uri import Answer

# Flags this driver applies itself, so each URI's flag ledger (BACK-1514) does not report
# them as having no effect on the adapter: --stdin for every URI, and whatever renders the
# aggregate for --batch and the legacy ssl:// --check batch.
_STDIN_FLAGS = ('stdin',)
_BATCH_FLAGS = ('stdin', 'batch', 'format', 'summary', 'only_failures')
_SSL_BATCH_FLAGS = ('stdin', 'format', 'summary', 'only_failures', 'expiring_within')


def _passes_ext_filter(target: str, ext_filter: Optional[str]) -> bool:
    """Return True if target passes the extension filter (or no filter is set)."""
    if not ext_filter:
        return True
    allowed = {e.strip().lower().lstrip('.') for e in ext_filter.split(',') if e.strip()}
    return Path(target).suffix.lower().lstrip('.') in allowed


def _process_stdin_uri(target: str, args: 'Namespace', is_batch_mode: bool,
                       is_ssl_batch_check: bool, batch_results: list,
                       ssl_check_results: list) -> int:
    """Process a URI from stdin; return its exit code (the batch modes report later: 0).

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
        batch_results.append(_collect_batch_result(target, args))
        return 0

    # Legacy SSL-specific batch mode for backward compatibility
    if is_ssl_batch_check and target.startswith('ssl://'):
        ssl_check_results.append(_collect_ssl_check_result(target, args))
        return 0

    # Non-batch URIs go through the normal path, which prints the answer or the error.
    # A failure no longer reads as a skip that exits 0 (BACK-1556): the run ends with
    # the worst code, and under --check a verdict (1 warnings, 2 failures) is a verdict.
    try:
        handle_uri(target, None, args, consumed=_STDIN_FLAGS)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        if code and not getattr(args, 'check', False):
            print(f"Warning: {target} failed (exit {code}); continuing", file=sys.stderr)
        return code
    return 0


def _process_stdin_file(
    target: str, args: 'Namespace', handle_file_func, is_check_mode: bool = False
) -> Tuple[int, bool]:
    """Process a file path from stdin.

    Args:
        target: File path to process
        args: Parsed arguments
        handle_file_func: Function to handle individual files
        is_check_mode: When True, run quality check and return violation count

    Returns:
        (violation count, degraded) when is_check_mode is True, else (0, False).
        degraded mirrors run_pattern_detection()'s BACK-1099 signal: the file
        didn't parse cleanly or a rule raised, so `violations` on its own
        isn't a trustworthy signal for this file.
    """
    path = Path(target)

    # Skip if path doesn't exist (graceful degradation)
    if not path.exists():
        print(f"Warning: {target} not found, skipping", file=sys.stderr)
        return 0, False

    # Skip directories (only process files)
    if path.is_dir():
        print(f"Warning: {target} is a directory, skipping (use reveal {target}/ directly)", file=sys.stderr)
        return 0, False

    # Process the file
    if not path.is_file():
        return 0, False

    # An unreadable file is skipped like a missing one; in check mode it
    # degrades the run (exit 3) rather than ending the whole batch (BACK-1424).
    if not os.access(path, os.R_OK):
        print(f"Warning: {target} is not readable, skipping", file=sys.stderr)
        return 0, is_check_mode

    if is_check_mode:
        from reveal.file_handler import _get_analyzer_or_exit, _build_file_cli_overrides
        from reveal.checks import run_pattern_detection
        from reveal.config import RevealConfig
        allow_fallback = not getattr(args, 'no_fallback', False)
        analyzer = _get_analyzer_or_exit(str(path), allow_fallback)
        cli_overrides = _build_file_cli_overrides(args)
        config = RevealConfig.get(start_path=path.parent, cli_overrides=cli_overrides or None)
        violations, degraded = run_pattern_detection(
            analyzer, str(path), getattr(args, 'format', 'text'), args, config=config
        )
        return violations, degraded

    if getattr(args, 'validate_schema', None):
        return _validate_schema_of(str(path), args, handle_file_func), False
    handle_file_func(str(path), None, args.meta, args.format, args)
    return 0, False


def _validate_schema_of(target: str, args: 'Namespace', handle_file_func) -> int:
    """``--validate-schema`` on one stdin path: 1 if it failed, so the run goes on to the rest.

    The validation branch ends the process on a failure (exit 1); left alone, the first
    invalid file hid every later path from the run (BACK-1687).
    """
    try:
        handle_file_func(target, None, args.meta, args.format, args)
    except SystemExit as e:
        return 1 if e.code else 0
    return 0


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
    from ..routing.file import reject_stdin_element_flag
    reject_stdin_element_flag(args)  # --section names one element of one file (BACK-1765)
    if args.element:
        print("Error: Cannot use element extraction with --stdin", file=sys.stderr)
        sys.exit(1)

    # Check if we're in batch mode (explicit --batch or SSL batch checks)
    is_batch_mode = getattr(args, 'batch', False)
    is_check_mode = getattr(args, 'check', False)
    is_ssl_batch_check = is_check_mode and not is_batch_mode

    # Collect results for batch aggregation
    ssl_check_results: List[Dict[str, Any]] = []
    batch_results: List[dict] = []
    total_file_violations = 0
    # BACK-1099: at least one --check'd file didn't parse cleanly / a rule
    # raised. total_file_violations alone isn't a trustworthy signal when
    # this is True — same shape as the directory-mode bug already fixed in
    # reveal/cli/file_checker.py; see internal-docs/design/EXIT_CODE_CONTRACT.md.
    any_file_degraded = False
    uri_exit = 0  # the worst exit of a URI answered one at a time (BACK-1556)

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
            uri_exit = max(uri_exit, _process_stdin_uri(target, args, is_batch_mode, is_ssl_batch_check,
                                                         batch_results, ssl_check_results))
        else:
            # Apply --ext filter for file paths
            if _passes_ext_filter(target, getattr(args, 'ext', None)):
                violations, degraded = _process_stdin_file(
                    target, args, handle_file_func, is_check_mode=is_check_mode
                )
                total_file_violations += violations
                any_file_degraded = any_file_degraded or degraded

    # Render aggregated batch results
    if batch_results:
        _render_batch_results(batch_results, args)
        # _render_batch_results handles exit
        return

    # Render aggregated SSL batch results if we collected any (legacy path)
    ssl_exit = _render_ssl_batch_results(ssl_check_results, args) if ssl_check_results else 0

    if is_check_mode:
        # BACK-1099: reuse `reveal check`'s own 0/1/3 contract instead of
        # this path's previous 0/1-only exit, so a degraded/unparseable
        # file piped through --stdin --check is distinguishable from a
        # clean run at the shell level, same as the directory-mode fix.
        # The ssl:// batch's own exit (2 on a failed domain, as `reveal
        # ssl://HOST --check`) counts too: it used to be printed as
        # "Exit code: 2" while the process exited 0 (BACK-1554).
        from reveal.cli.file_checker import check_exit_code
        degraded_count = 1 if any_file_degraded else 0
        exit_zero = getattr(args, 'exit_zero', False)
        file_exit = check_exit_code(
            total_file_violations, files_degraded=degraded_count, exit_zero=exit_zero,
        )
        sys.exit(0 if exit_zero else max(file_exit, ssl_exit, uri_exit))

    sys.exit(1 if total_file_violations > 0 or uri_exit else 0)


def _collect_ssl_check_result(uri: str, args: 'Namespace') -> Dict[str, Any]:
    """One ssl:// check for the legacy ``--stdin --check`` batch, answered by the router
    (resolve_uri): the check gets the same arguments as ``reveal ssl://HOST --check``
    (``--expiring-within``, ``--advanced``, ...). A failed answer, raised or returned, is
    a failed domain in the batch."""
    from ..routing.uri import resolve_uri

    result = resolve_uri(uri, args, consumed=_SSL_BATCH_FLAGS).result
    if outcome_of(result) != 'failed':
        return result  # type: ignore[no-any-return]
    return {
        'host': uri.replace('ssl://', ''),
        'port': 443,
        'status': 'failure',
        'error': result['error'],
        'summary': {'total': 1, 'passed': 0, 'warnings': 0, 'failures': 1},
        'exit_code': 2,
    }


def _render_ssl_batch_results(results: list, args: 'Namespace') -> int:
    """Render collected SSL check results as a batch.

    Args:
        results: List of individual check results
        args: CLI arguments with batch flags

    Returns:
        The batch's exit code: 2 when any domain failed, 1 when any warned, else 0
    """
    from ...adapters.ssl.renderer import SSLRenderer

    # Build batch result structure
    total = len(results)
    passed = sum(1 for r in results if r.get('status') == 'pass')
    warnings = sum(1 for r in results if r.get('status') == 'warning')
    failures = sum(1 for r in results if r.get('status') == 'failure')
    exit_code = _calculate_batch_exit_code(failures, warnings)

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
        'exit_code': exit_code,
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
    return exit_code


def _collect_batch_result(uri: str, args: 'Namespace') -> dict:
    """One ``--batch`` entry: the URI's answer from the router (resolve_uri), not rendered.

    The answer is the one ``reveal URI`` prints: the adapter built by from_uri, the
    missing-path check, element lookup, --check arguments, the flag ledger. The status
    comes from its outcome, so an error result is an error here, as it exits 1 there.
    This used to build the adapter itself as adapter_class(uri), with the whole URI as its
    resource and get_structure() only, and label every returned result 'success'
    (BACK-1554): ast:// found nothing on any path, env://HOME listed the whole environment,
    and a missing path or parameter counted as successful with exit 0.

    Returns:
        {uri, scheme, status, data} plus ``error`` when the answer failed
    """
    from ..routing.uri import UriUsageError, resolve_uri

    scheme = uri.split('://', 1)[0]
    try:
        answer = resolve_uri(uri, args, consumed=_BATCH_FLAGS)
    except UriUsageError as e:
        return {'uri': uri, 'scheme': scheme, 'status': 'error', 'error': e.message}
    entry = {'uri': uri, 'scheme': scheme, 'status': _batch_status(answer), 'data': answer.result}
    if entry['status'] == 'error':
        entry['error'] = answer.result['error']
    return entry


def _batch_status(answer: 'Answer') -> str:
    """A batch entry's status: a failed answer is 'error' and a not-applicable one
    'not_applicable' (outcome_of); a check reports its own status; anything else ran."""
    outcome = outcome_of(answer.result)
    if outcome == 'failed':
        return 'error'
    if outcome == 'not_applicable':
        return 'not_applicable'
    if answer.kind == 'check':
        return str(answer.result.get('status', 'unknown'))
    return 'success'


def _aggregate_batch_stats(results: list) -> dict:
    """Aggregate batch statistics.

    Args:
        results: List of individual results

    Returns:
        Dict with total, successful, warnings, failures, not_applicable counts
    """
    return {
        'total': len(results),
        'successful': sum(1 for r in results if r['status'] in ('success', 'pass')),
        'warnings': sum(1 for r in results if r['status'] == 'warning'),
        'failures': sum(1 for r in results if r['status'] in ('failure', 'error')),
        'not_applicable': sum(1 for r in results if r['status'] == 'not_applicable'),
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
    elif status == 'not_applicable':
        return '–'
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
    if stats['not_applicable'] > 0:
        print(f"Not applicable: {stats['not_applicable']} –")
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
            elif status == 'not_applicable':
                print(f"  Reason: {result['data'].get('reason', '')}")


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
    # A warning (a cert inside --expiring-within) exits 1, as the same check of one
    # host does; batches returned 0, so a CI gate on them never fired (BACK-1557).
    if warnings > 0:
        return 1
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
            'not_applicable': stats['not_applicable'],
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
