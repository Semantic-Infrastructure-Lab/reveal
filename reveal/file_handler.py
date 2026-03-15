"""File handling operations.

This module is separate from cli.routing to avoid circular dependencies with adapters.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


def _get_analyzer_or_exit(path: str, allow_fallback: bool):
    """Get analyzer for path or exit with error.

    Args:
        path: File path
        allow_fallback: Whether to allow fallback analyzers

    Returns:
        Analyzer instance

    Exits:
        With error code 1 if no analyzer found
    """
    from .registry import get_analyzer, get_all_analyzers  # noqa: I006 — circular avoidance
    from .errors import AnalyzerNotFoundError  # noqa: I006 — circular avoidance

    analyzer_class = get_analyzer(path, allow_fallback=allow_fallback)
    if not analyzer_class:
        # Find similar extensions for suggestions
        ext = Path(path).suffix
        similar_exts = None
        if ext:
            analyzers = get_all_analyzers()
            similar_exts = [e for e in analyzers.keys()
                          if ext.lower() in e.lower() or e.lower() in ext.lower()]

        # Create detailed error with suggestions
        error = AnalyzerNotFoundError(
            path=path,
            allow_fallback=allow_fallback,
            similar_extensions=similar_exts
        )

        print(str(error), file=sys.stderr)
        sys.exit(1)

    return analyzer_class(path)


def _build_file_cli_overrides(args: Optional['Namespace']) -> dict:
    """Build CLI overrides dictionary from args.

    Args:
        args: Argument namespace

    Returns:
        CLI overrides dict
    """
    cli_overrides = {}
    if args and getattr(args, 'no_breadcrumbs', False):
        cli_overrides['display'] = {'breadcrumbs': False}
    return cli_overrides


def _handle_domain_extraction(analyzer) -> None:
    """Handle domain extraction from analyzer.

    Args:
        analyzer: Analyzer instance

    Exits:
        With error code 1 if domain extraction not supported
    """
    if hasattr(analyzer, 'extract_ssl_domains'):
        domains = analyzer.extract_ssl_domains()
        for domain in domains:
            print(f"ssl://{domain}")
    else:
        print(f"Error: --extract domains not supported for {type(analyzer).__name__}", file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)


def _handle_acme_roots_extraction(analyzer) -> None:
    """Print ACME challenge root paths and nobody ACL status (N4)."""
    if not hasattr(analyzer, 'extract_acme_roots'):
        print(f"Error: --extract acme-roots not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    rows = analyzer.extract_acme_roots()
    if not rows:
        print("No ACME challenge location blocks found.")
        return

    col_domain = max(len(r['domain']) for r in rows)
    col_path = max(len(r['acme_path']) for r in rows)

    header = (f"  {'domain':<{col_domain}}  {'acme root path':<{col_path}}  acl status")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for r in rows:
        status = r['acl_status']
        if status == 'ok':
            icon = "✅"
            detail = "nobody:read OK"
        elif status == 'denied':
            failing = r.get('acl_failing_path') or ''
            detail = f"❌ DENIED  ({r['acl_message']})"
            icon = ""
        elif status == 'not_found':
            icon = "⚠️ "
            detail = f"path not found: {r['acme_path']}"
        else:
            icon = "❓"
            detail = r['acl_message']

        print(f"  {r['domain']:<{col_domain}}  {r['acme_path']:<{col_path}}  {icon} {detail}")


def _handle_check_acl(analyzer) -> None:
    """Print nobody ACL status for all root directives in config (N1)."""
    if not hasattr(analyzer, 'extract_docroot_acl'):
        print(f"Error: --check-acl not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    rows = analyzer.extract_docroot_acl()
    if not rows:
        print("No root directives found.")
        return

    failures = [r for r in rows if r['acl_status'] != 'ok']
    passes = [r for r in rows if r['acl_status'] == 'ok']

    col_root = max(len(r['root']) for r in rows)
    col_domain = max(len(r['domain']) for r in rows)

    if failures:
        print(f"❌ ACL failures ({len(failures)}):")
        for r in failures:
            msg = r['acl_message']
            print(f"  {r['root']:<{col_root}}  ({r['domain']})  {msg}")
        print()

    if passes:
        print(f"✅ OK ({len(passes)}):")
        for r in passes:
            print(f"  {r['root']:<{col_root}}  ({r['domain']})")
        print()

    exit_code = 2 if failures else 0
    if failures:
        sys.exit(exit_code)


def _format_acl_col(acl_status: str) -> tuple:
    """Return (column_str, is_failure)."""
    if acl_status == 'ok':
        return "✅ ACL ok", False
    if acl_status == 'denied':
        return "❌ ACL DENIED", True
    return f"⚠️  ACL {acl_status}", False


def _format_acme_ssl_col(ssl_status: str, ssl_days, ssl_not_after: str) -> tuple:
    """Return (column_str, is_failure)."""
    if ssl_status == 'healthy':
        col = f"✅ {ssl_days}d"
        if ssl_not_after:
            try:
                dt = datetime.fromisoformat(ssl_not_after.replace('Z', '+00:00'))
                col += f"  ({dt.strftime('%b %d, %Y')})"
            except (ValueError, TypeError):
                pass
        return col, False
    if ssl_status in ('warning', 'critical'):
        return f"⚠️  expires in {ssl_days}d", False
    if ssl_status == 'expired':
        return f"❌ EXPIRED {abs(ssl_days or 0)} days ago", True
    if ssl_status == 'error':
        return f"❌ {ssl_not_after}", True
    return ssl_status, False


def _fetch_acme_ssl_data(rows: list, check_ssl_health) -> list:
    """Enrich ACME rows with live SSL data for each domain."""
    results = []
    for r in rows:
        try:
            ssl_result = check_ssl_health(r['domain'], warn_days=30, critical_days=7)
            leaf = ssl_result.get('leaf', {})
            results.append({**r, 'ssl_status': ssl_result.get('status', 'unknown'),
                            'ssl_days': leaf.get('days_until_expiry'),
                            'ssl_not_after': leaf.get('not_after', '')})
        except Exception as exc:
            results.append({**r, 'ssl_status': 'error', 'ssl_days': None,
                            'ssl_not_after': str(exc)[:60]})
    return results


def _handle_validate_nginx_acme(analyzer, args=None) -> None:
    """Full ACME pipeline audit: acme root + ACL + live SSL per domain (--validate-nginx-acme)."""
    if not hasattr(analyzer, 'extract_acme_roots'):
        print(f"Error: --validate-nginx-acme not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    only_failures = getattr(args, 'only_failures', False)
    output_format = getattr(args, 'format', 'text')
    from .adapters.ssl.certificate import check_ssl_health  # noqa: I006 — optional heavy dep

    rows = analyzer.extract_acme_roots()
    if not rows:
        if output_format == 'json':
            print(json.dumps({'type': 'nginx_acme_audit', 'domains': [],
                              'has_failures': False, 'message': 'No ACME challenge location blocks found.'}))
        else:
            print("No ACME challenge location blocks found.")
        return

    results = _fetch_acme_ssl_data(rows, check_ssl_health)

    # Annotate each row with failure flag for both output paths
    for r in results:
        _, acl_fail = _format_acl_col(r['acl_status'])
        _, ssl_fail = _format_acme_ssl_col(r['ssl_status'], r['ssl_days'], r['ssl_not_after'])
        r['has_failure'] = acl_fail or ssl_fail

    has_failures = any(r['has_failure'] for r in results)

    if output_format == 'json':
        output_rows = [r for r in results if not only_failures or r['has_failure']]
        print(json.dumps({
            'type': 'nginx_acme_audit',
            'has_failures': has_failures,
            'only_failures': only_failures,
            'domains': output_rows,
        }, default=str))
        if has_failures:
            sys.exit(2)
        return

    col_domain = max(len(r['domain']) for r in results)
    col_path = max(len(r['acme_path']) for r in results)

    header = (f"  {'domain':<{col_domain}}  {'acme root path':<{col_path}}"
              f"  {'acl':<14}  ssl status")
    print(header)
    print("  " + "─" * (len(header) - 2))

    printed = 0
    for r in results:
        acl_col, _ = _format_acl_col(r['acl_status'])
        ssl_col, _ = _format_acme_ssl_col(r['ssl_status'], r['ssl_days'], r['ssl_not_after'])

        if only_failures and not r['has_failure']:
            continue
        print(f"  {r['domain']:<{col_domain}}  {r['acme_path']:<{col_path}}"
              f"  {acl_col:<14}  {ssl_col}")
        printed += 1

    if only_failures and printed == 0:
        print("✅ No failures found.")
    if has_failures:
        sys.exit(2)


def _handle_check_conflicts(analyzer) -> None:
    """Detect nginx location prefix overlaps and regex/prefix conflicts (N2)."""
    if not hasattr(analyzer, 'detect_location_conflicts'):
        print(f"Error: --check-conflicts not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    conflicts = analyzer.detect_location_conflicts()
    if not conflicts:
        print("✅ No location conflicts detected.")
        return

    warnings = [c for c in conflicts if c['severity'] == 'warning']
    infos = [c for c in conflicts if c['severity'] == 'info']

    if warnings:
        print(f"⚠️  Conflicts ({len(warnings)}):")
        for c in warnings:
            print(f"\n  [{c['server']}]")
            print(f"    {c['location_a']['path']}  (line {c['location_a']['line']})")
            print(f"    {c['location_b']['path']}  (line {c['location_b']['line']})")
            print(f"    → {c['note']}")
        print()

    if infos:
        print(f"ℹ️  Prefix overlaps ({len(infos)}):")
        for c in infos:
            print(f"\n  [{c['server']}]")
            print(f"    {c['location_a']['path']}  (line {c['location_a']['line']})")
            print(f"    {c['location_b']['path']}  (line {c['location_b']['line']})")
            print(f"    → {c['note']}")
        print()

    if warnings:
        sys.exit(2)


def _resolve_log_path(analyzer, explicit_path: Optional[str]) -> Optional[str]:
    """Resolve nginx error log path: explicit > config directive > default locations."""
    if explicit_path:
        return explicit_path
    resolved = analyzer.get_error_log_path()
    if resolved:
        return resolved
    for candidate in ['/var/log/nginx/error.log', '/usr/local/nginx/logs/error.log']:
        if os.path.exists(candidate):
            return candidate
    return None


def _render_diagnose_table(hits: list, resolved_path: str) -> bool:
    """Print the diagnose results table. Returns True if there are hard failures."""
    LABELS = {
        'permission_denied': '❌ Permission Denied',
        'not_found':         '⚠️  Not Found (ENOENT)',
        'ssl_error':         '❌ SSL Error',
    }
    col_domain = max(len(r['domain']) for r in hits)
    col_pattern = max(len(LABELS.get(r['pattern'], r['pattern'])) for r in hits)

    print(f"nginx error log: {resolved_path}")
    header = (f"  {'domain':<{col_domain}}  {'pattern':<{col_pattern}}"
              f"  {'count':>5}  last seen")
    print(header)
    print("  " + "─" * (len(header) - 2))

    has_failures = False
    for r in hits:
        label = LABELS.get(r['pattern'], r['pattern'])
        if r['pattern'] in ('permission_denied', 'ssl_error'):
            has_failures = True
        print(f"  {r['domain']:<{col_domain}}  {label:<{col_pattern}}"
              f"  {r['count']:>5}  {r['last_seen']}")

    print()
    print("Sample (most recent match per type):")
    seen = set()
    for r in hits:
        key = (r['domain'], r['pattern'])
        if key not in seen:
            print(f"  [{r['domain']} / {r['pattern']}]")
            print(f"    {r['sample']}")
            seen.add(key)
    return has_failures


def _handle_diagnose(analyzer, log_path: Optional[str] = None) -> None:
    """Diagnose ACME / SSL failures from the nginx error log."""
    if not hasattr(analyzer, 'diagnose_acme_errors'):
        print(f"Error: --diagnose not supported for {type(analyzer).__name__}", file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    resolved_path = _resolve_log_path(analyzer, log_path)
    if not resolved_path or not os.path.exists(resolved_path):
        print(f"⚠️  No nginx error log found.", file=sys.stderr)
        if resolved_path:
            print(f"   Checked: {resolved_path}", file=sys.stderr)
        print("   Use --log-path /path/to/error.log to specify the log file.", file=sys.stderr)
        sys.exit(1)

    hits = analyzer.diagnose_acme_errors(resolved_path)
    if not hits:
        print(f"✅ No ACME/SSL errors found in {resolved_path} (last 5,000 lines).")
        return

    has_failures = _render_diagnose_table(hits, resolved_path)
    if has_failures:
        sys.exit(2)


def _load_disk_cert(cert_path: str, load_certificate_from_file) -> dict:
    """Load on-disk cert. Returns dict with status/expiry/serial/not_after keys."""
    if not os.path.exists(cert_path):
        return {'status': 'missing', 'expiry': None, 'serial': None, 'not_after': None}
    try:
        disk_leaf, _ = load_certificate_from_file(cert_path)
        return {
            'status': 'ok',
            'expiry': disk_leaf.days_until_expiry,
            'serial': disk_leaf.serial_number,
            'not_after': disk_leaf.not_after,
        }
    except Exception as exc:
        return {'status': f"error: {str(exc)[:40]}", 'expiry': None, 'serial': None, 'not_after': None}


def _load_live_cert(domain: str, check_ssl_health) -> dict:
    """Fetch live cert via network. Returns dict with status/expiry/serial/not_after keys."""
    try:
        ssl_result = check_ssl_health(domain, warn_days=30, critical_days=7)
        leaf_data = ssl_result.get('leaf', {})
        not_after = None
        not_after_str = leaf_data.get('not_after', '')
        if not_after_str:
            try:
                not_after = datetime.fromisoformat(not_after_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pass
        return {
            'status': ssl_result.get('status', 'unknown'),
            'expiry': leaf_data.get('days_until_expiry'),
            'serial': leaf_data.get('serial_number'),
            'not_after': not_after,
        }
    except Exception as exc:
        return {'status': f"error: {str(exc)[:40]}", 'expiry': None, 'serial': None, 'not_after': None}


def _cert_match_label(disk: dict, live: dict) -> str:
    if disk['serial'] and live['serial']:
        return 'match' if disk['serial'] == live['serial'] else 'STALE'
    if disk['status'] == 'missing':
        return 'no-disk'
    return '?'


def _format_disk_col(disk: dict) -> tuple:
    """Return (column_str, is_failure)."""
    status = disk['status']
    if status == 'missing':
        return "⚫ not found", False
    if status == 'ok':
        days = disk['expiry']
        date_str = disk['not_after'].strftime('%b %d, %Y') if disk['not_after'] else ''
        if days is not None and days < 0:
            return f"❌ EXPIRED {abs(days)}d ago", True
        if days is not None and days < 30:
            return f"⚠️  {days}d  ({date_str})", False
        return (f"✅ {days}d  ({date_str})" if days is not None else "✅ ok"), False
    return f"❌ {status}", True


def _format_live_col(live: dict) -> tuple:
    """Return (column_str, is_failure)."""
    status = live['status']
    days = live['expiry']
    not_after = live['not_after']
    if status == 'healthy':
        date_str = not_after.strftime('%b %d, %Y') if not_after else ''
        return (f"✅ {days}d  ({date_str})" if days is not None else "✅ ok"), False
    if status in ('warning', 'critical'):
        return f"⚠️  {days}d", False
    if status == 'expired':
        return f"❌ EXPIRED {abs(days or 0)}d ago", True
    if status and status.startswith('error'):
        return f"⚠️  {status}", False  # can't reach live cert → unknown, not definitive
    return str(status), False


def _format_match_col(match: str) -> tuple:
    """Return (column_str, is_failure)."""
    if match == 'match':
        return "✅ same cert", False
    if match == 'STALE':
        return "⚠️  STALE (reload nginx)", True
    if match == 'no-disk':
        return "⚫ no disk cert", False
    return f"? {match}", False


def _handle_cpanel_certs(analyzer) -> None:
    """Compare cPanel on-disk certs against live certs per domain (S4 -- --cpanel-certs).

    For each SSL domain found in the nginx config:
    - Looks up /var/cpanel/ssl/apache_tls/DOMAIN/combined (disk cert)
    - Fetches the live cert from the network
    - Compares serial numbers to detect "AutoSSL renewed but nginx hasn't reloaded"
    """
    if not hasattr(analyzer, 'extract_ssl_domains'):
        print(f"Error: --cpanel-certs not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    from .adapters.ssl.certificate import load_certificate_from_file, check_ssl_health  # noqa: I006 — optional heavy dep

    domains = analyzer.extract_ssl_domains()
    if not domains:
        print("No SSL domains found in nginx config.")
        return

    CPANEL_CERT_DIR = "/var/cpanel/ssl/apache_tls"
    rows = []
    for domain in domains:
        cert_path = f"{CPANEL_CERT_DIR}/{domain}/combined"
        disk = _load_disk_cert(cert_path, load_certificate_from_file)
        live = _load_live_cert(domain, check_ssl_health)
        match = _cert_match_label(disk, live)
        rows.append({
            'domain': domain,
            'cert_path': cert_path,
            'disk': disk,
            'live': live,
            'match': match,
        })

    col_domain = max(len(r['domain']) for r in rows)
    header = f"  {'domain':<{col_domain}}  {'disk cert':<28}  {'live cert':<28}  match"
    print(header)
    print("  " + "─" * (len(header) - 2))

    has_failures = False
    for r in rows:
        disk_col, disk_fail = _format_disk_col(r['disk'])
        live_col, live_fail = _format_live_col(r['live'])
        match_col, match_fail = _format_match_col(r['match'])
        has_failures = has_failures or disk_fail or live_fail or match_fail
        print(f"  {r['domain']:<{col_domain}}  {disk_col:<28}  {live_col:<28}  {match_col}")

    print()
    if has_failures:
        sys.exit(2)


def _handle_extract_option(analyzer, extract_type: str) -> None:
    """Handle --extract option with validation.

    Args:
        analyzer: Analyzer instance
        extract_type: Type to extract (e.g., 'domains', 'acme-roots')

    Exits:
        With error code 1 if extract type unknown
    """
    if extract_type == 'domains':
        _handle_domain_extraction(analyzer)
    elif extract_type == 'acme-roots':
        _handle_acme_roots_extraction(analyzer)
    else:
        print(f"Error: Unknown extract type '{extract_type}'", file=sys.stderr)
        print("Supported types: domains, acme-roots (for nginx configs)", file=sys.stderr)
        sys.exit(1)


def handle_file(path: str, element: Optional[str], show_meta: bool,
                output_format: str, args: Optional['Namespace'] = None) -> None:
    """Handle file analysis.

    Args:
        path: File path
        element: Optional element to extract
        show_meta: Whether to show metadata only
        output_format: Output format ('text', 'json', 'grep')
        args: Full argument namespace (for filter options)
    """
    from .display import show_structure, show_metadata, extract_element  # noqa: I006 — circular avoidance
    from .config import RevealConfig  # noqa: I006 — circular avoidance

    # Get analyzer
    allow_fallback = not getattr(args, 'no_fallback', False) if args else True
    analyzer = _get_analyzer_or_exit(path, allow_fallback)

    # Load config with CLI overrides
    cli_overrides = _build_file_cli_overrides(args)
    config = RevealConfig.get(
        start_path=Path(path).parent if Path(path).is_file() else Path(path),
        cli_overrides=cli_overrides if cli_overrides else None
    )

    # Route to appropriate handler based on flags
    if show_meta:
        show_metadata(analyzer, output_format, config=config)
        return

    if args and getattr(args, 'extract', None):
        _handle_extract_option(analyzer, args.extract.lower())
        return

    if args and getattr(args, 'check_acl', False):
        _handle_check_acl(analyzer)
        return

    if args and getattr(args, 'validate_nginx_acme', False):
        _handle_validate_nginx_acme(analyzer, args)
        return

    if args and getattr(args, 'check_conflicts', False):
        _handle_check_conflicts(analyzer)
        return

    if args and getattr(args, 'cpanel_certs', False):
        _handle_cpanel_certs(analyzer)
        return

    if args and getattr(args, 'diagnose', False):
        _handle_diagnose(analyzer, log_path=getattr(args, 'log_path', None))
        return

    if args and getattr(args, 'validate_schema', None):
        from .checks import run_schema_validation  # noqa: I006 — circular avoidance
        run_schema_validation(analyzer, path, args.validate_schema, output_format, args)
        return

    if args and getattr(args, 'check', False):
        from .checks import run_pattern_detection  # noqa: I006 — circular avoidance
        run_pattern_detection(analyzer, path, output_format, args, config=config)
        return

    if element:
        extract_element(analyzer, element, output_format, config=config)
        return

    show_structure(analyzer, output_format, args, config=config)
