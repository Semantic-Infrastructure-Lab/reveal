"""File handling operations.

This module is separate from cli.routing to avoid circular dependencies with adapters.
"""

import sys
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
    from .registry import get_analyzer, get_all_analyzers
    from .errors import AnalyzerNotFoundError

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


def _handle_validate_nginx_acme(analyzer) -> None:
    """Full ACME pipeline audit: acme root + ACL + live SSL per domain (--validate-nginx-acme)."""
    if not hasattr(analyzer, 'extract_acme_roots'):
        print(f"Error: --validate-nginx-acme not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    from .adapters.ssl.certificate import check_ssl_health

    rows = analyzer.extract_acme_roots()
    if not rows:
        print("No ACME challenge location blocks found.")
        return

    # Fetch live SSL for each domain
    results = []
    for r in rows:
        domain = r['domain']
        try:
            ssl_result = check_ssl_health(domain, warn_days=30, critical_days=7)
            ssl_status = ssl_result.get('status', 'unknown')
            leaf = ssl_result.get('leaf', {})
            ssl_days = leaf.get('days_until_expiry')
            ssl_not_after = leaf.get('not_after', '')
        except Exception as exc:
            ssl_status = 'error'
            ssl_days = None
            ssl_not_after = str(exc)[:60]
        results.append({**r, 'ssl_status': ssl_status, 'ssl_days': ssl_days,
                        'ssl_not_after': ssl_not_after})

    col_domain = max(len(r['domain']) for r in results)
    col_path = max(len(r['acme_path']) for r in results)

    # Header
    header = (f"  {'domain':<{col_domain}}  {'acme root path':<{col_path}}"
              f"  {'acl':<14}  ssl status")
    print(header)
    print("  " + "─" * (len(header) - 2))

    has_failures = False
    for r in results:
        acl_status = r['acl_status']
        if acl_status == 'ok':
            acl_col = "✅ ACL ok"
        elif acl_status == 'denied':
            acl_col = "❌ ACL DENIED"
            has_failures = True
        else:
            acl_col = f"⚠️  ACL {acl_status}"

        ssl_status = r['ssl_status']
        if ssl_status == 'healthy':
            days = r['ssl_days']
            ssl_col = f"✅ {days}d"
            if r['ssl_not_after']:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(r['ssl_not_after'].replace('Z', '+00:00'))
                    ssl_col += f"  ({dt.strftime('%b %d, %Y')})"
                except (ValueError, TypeError):
                    pass
        elif ssl_status in ('warning', 'critical'):
            days = r['ssl_days']
            ssl_col = f"⚠️  expires in {days}d"
        elif ssl_status == 'expired':
            days = abs(r['ssl_days'] or 0)
            ssl_col = f"❌ EXPIRED {days} days ago"
            has_failures = True
        elif ssl_status == 'error':
            ssl_col = f"❌ {r['ssl_not_after']}"
            has_failures = True
        else:
            ssl_col = ssl_status

        print(f"  {r['domain']:<{col_domain}}  {r['acme_path']:<{col_path}}"
              f"  {acl_col:<14}  {ssl_col}")

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


def _handle_diagnose(analyzer, log_path: Optional[str] = None) -> None:
    """Diagnose ACME / SSL failures from the nginx error log (S3 -- --diagnose).

    Parses the last 5,000 lines of the nginx error log for Permission Denied /
    ENOENT errors on /.well-known/ paths and SSL cert load failures, grouped by
    SSL domain present in the config.
    """
    if not hasattr(analyzer, 'diagnose_acme_errors'):
        print(f"Error: --diagnose not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    import os

    # Resolve log path: arg > config directive > cPanel default > nginx default
    resolved_path = log_path
    if not resolved_path:
        resolved_path = analyzer.get_error_log_path()
    if not resolved_path:
        # cPanel nginx writes to this path by default
        for candidate in [
            '/var/log/nginx/error.log',
            '/usr/local/nginx/logs/error.log',
        ]:
            if os.path.exists(candidate):
                resolved_path = candidate
                break

    if not resolved_path or not os.path.exists(resolved_path):
        print(f"⚠️  No nginx error log found.", file=sys.stderr)
        if resolved_path:
            print(f"   Checked: {resolved_path}", file=sys.stderr)
        print("   Use --log-path /path/to/error.log to specify the log file.",
              file=sys.stderr)
        sys.exit(1)

    hits = analyzer.diagnose_acme_errors(resolved_path)

    if not hits:
        print(f"✅ No ACME/SSL errors found in {resolved_path} (last 5,000 lines).")
        return

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

    if has_failures:
        sys.exit(2)


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

    from .adapters.ssl.certificate import load_certificate_from_file, check_ssl_health

    domains = analyzer.extract_ssl_domains()
    if not domains:
        print("No SSL domains found in nginx config.")
        return

    CPANEL_CERT_DIR = "/var/cpanel/ssl/apache_tls"

    rows = []
    for domain in domains:
        cert_path = f"{CPANEL_CERT_DIR}/{domain}/combined"

        # --- disk cert ---
        disk_expiry = None
        disk_serial = None
        disk_status = None
        disk_not_after = None
        if not __import__('os').path.exists(cert_path):
            disk_status = 'missing'
        else:
            try:
                disk_leaf, _ = load_certificate_from_file(cert_path)
                disk_expiry = disk_leaf.days_until_expiry
                disk_serial = disk_leaf.serial_number
                disk_not_after = disk_leaf.not_after
                disk_status = 'ok'
            except Exception as exc:
                disk_status = f"error: {str(exc)[:40]}"

        # --- live cert ---
        live_expiry = None
        live_serial = None
        live_status = None
        live_not_after = None
        try:
            ssl_result = check_ssl_health(domain, warn_days=30, critical_days=7)
            live_ssl_status = ssl_result.get('status', 'unknown')
            leaf_data = ssl_result.get('leaf', {})
            live_expiry = leaf_data.get('days_until_expiry')
            live_serial = leaf_data.get('serial_number')
            live_not_after_str = leaf_data.get('not_after', '')
            if live_not_after_str:
                try:
                    from datetime import datetime
                    live_not_after = datetime.fromisoformat(
                        live_not_after_str.replace('Z', '+00:00')
                    )
                except (ValueError, TypeError):
                    pass
            live_status = live_ssl_status
        except Exception as exc:
            live_status = f"error: {str(exc)[:40]}"

        # --- match determination ---
        if disk_serial and live_serial:
            match = 'match' if disk_serial == live_serial else 'STALE'
        elif disk_status == 'missing':
            match = 'no-disk'
        else:
            match = '?'

        rows.append({
            'domain': domain,
            'cert_path': cert_path,
            'disk_status': disk_status,
            'disk_expiry': disk_expiry,
            'disk_not_after': disk_not_after,
            'live_status': live_status,
            'live_expiry': live_expiry,
            'live_not_after': live_not_after,
            'match': match,
        })

    col_domain = max(len(r['domain']) for r in rows)

    header = (f"  {'domain':<{col_domain}}  {'disk cert':<28}  {'live cert':<28}  match")
    print(header)
    print("  " + "─" * (len(header) - 2))

    has_failures = False
    for r in rows:
        # disk column
        ds = r['disk_status']
        if ds == 'missing':
            disk_col = "⚫ not found"
        elif ds == 'ok':
            days = r['disk_expiry']
            na = r['disk_not_after']
            date_str = na.strftime('%b %d, %Y') if na else ''
            if days is not None and days < 0:
                disk_col = f"❌ EXPIRED {abs(days)}d ago"
                has_failures = True
            elif days is not None and days < 30:
                disk_col = f"⚠️  {days}d  ({date_str})"
            else:
                disk_col = f"✅ {days}d  ({date_str})" if days is not None else "✅ ok"
        else:
            disk_col = f"❌ {ds}"
            has_failures = True

        # live column
        ls = r['live_status']
        if ls in ('healthy',):
            days = r['live_expiry']
            na = r['live_not_after']
            date_str = na.strftime('%b %d, %Y') if na else ''
            live_col = f"✅ {days}d  ({date_str})" if days is not None else "✅ ok"
        elif ls in ('warning', 'critical'):
            days = r['live_expiry']
            live_col = f"⚠️  {days}d"
        elif ls == 'expired':
            days = abs(r['live_expiry'] or 0)
            live_col = f"❌ EXPIRED {days}d ago"
            has_failures = True
        elif ls and ls.startswith('error'):
            live_col = f"⚠️  {ls}"  # can't reach live cert → unknown, not a definitive failure
        else:
            live_col = str(ls)

        # match column
        match = r['match']
        if match == 'match':
            match_col = "✅ same cert"
        elif match == 'STALE':
            match_col = "⚠️  STALE (reload nginx)"
            has_failures = True
        elif match == 'no-disk':
            match_col = "⚫ no disk cert"
        else:
            match_col = f"? {match}"

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
    from .display import show_structure, show_metadata, extract_element
    from .config import RevealConfig

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
        _handle_validate_nginx_acme(analyzer)
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
        from .checks import run_schema_validation
        run_schema_validation(analyzer, path, args.validate_schema, output_format, args)
        return

    if args and getattr(args, 'check', False):
        from .checks import run_pattern_detection
        run_pattern_detection(analyzer, path, output_format, args, config=config)
        return

    if element:
        extract_element(analyzer, element, output_format, config=config)
        return

    show_structure(analyzer, output_format, args, config=config)
