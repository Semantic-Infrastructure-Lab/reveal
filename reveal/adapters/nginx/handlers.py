"""CLI handlers for nginx file analysis operations.

These handlers implement the nginx-specific CLI flags that operate on
NginxAnalyzer objects: --extract, --check-acl, --validate-nginx-acme,
--global-audit, --check-conflicts, --diagnose, --cpanel-certs.

Moved from reveal/handlers_nginx.py to this package (BACK-097) to keep
nginx operations co-located with other nginx adapter code.
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


_SEVERITY_ORDER = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'INFO': 3}
_SEVERITY_LABEL = {
    'HIGH':   ('HIGH  ', True),
    'MEDIUM': ('MED   ', True),
    'LOW':    ('LOW   ', False),
    'INFO':   ('INFO  ', False),
}


def _handle_domain_extraction(analyzer, canonical_only: bool = False) -> None:
    """Handle domain extraction from analyzer.

    Args:
        analyzer: Analyzer instance
        canonical_only: When True, emit one URI per vhost (primary server_name only)

    Exits:
        With error code 1 if domain extraction not supported
    """
    if hasattr(analyzer, 'extract_ssl_domains'):
        domains = analyzer.extract_ssl_domains(canonical_only=canonical_only)
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


def _render_acme_json(results: list, only_failures: bool, has_failures: bool) -> None:
    """Render ACME audit results as JSON and exit with code 2 on failures."""
    output_rows = [r for r in results if not only_failures or r['has_failure']]
    print(json.dumps({
        'type': 'nginx_acme_audit',
        'has_failures': has_failures,
        'only_failures': only_failures,
        'domains': output_rows,
    }, default=str))
    if has_failures:
        sys.exit(2)


def _render_acme_text(results: list, analyzer, only_failures: bool, verbose: bool,
                      has_failures: bool) -> None:
    """Render ACME audit results as a text table and exit with code 2 on failures."""
    col_domain = max(len(r['domain']) for r in results)
    col_path = max(len(r['acme_path']) for r in results)

    header = (f"  {'domain':<{col_domain}}  {'acme root path':<{col_path}}"
              f"  {'acl':<14}  ssl status")
    print(header)
    print("  " + "─" * (len(header) - 2))

    printed = 0
    analyzer_lines = getattr(analyzer, 'lines', [])
    for r in results:
        acl_col, _ = _format_acl_col(r['acl_status'])
        ssl_col, _ = _format_acme_ssl_col(r['ssl_status'], r['ssl_days'], r['ssl_not_after'])
        if only_failures and not r['has_failure']:
            continue
        print(f"  {r['domain']:<{col_domain}}  {r['acme_path']:<{col_path}}"
              f"  {acl_col:<14}  {ssl_col}")
        if verbose and analyzer_lines:
            line_no = r.get('line', 0)
            if line_no and 0 < line_no <= len(analyzer_lines):
                # Show the location block: the matched line + up to 3 lines ahead (closing brace)
                snippet_lines = analyzer_lines[line_no - 1:line_no + 3]
                snippet = ''.join(snippet_lines).rstrip()
                for sl in snippet.splitlines():
                    print(f"       {line_no}: {sl.rstrip()}")
                    line_no += 1
        printed += 1

    if only_failures and printed == 0:
        print("✅ No failures found.")
    if has_failures:
        sys.exit(2)


def _handle_validate_nginx_acme(analyzer, args=None) -> None:
    """Full ACME pipeline audit: acme root + ACL + live SSL per domain (--validate-nginx-acme)."""
    if not hasattr(analyzer, 'extract_acme_roots'):
        print(f"Error: --validate-nginx-acme not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    only_failures = getattr(args, 'only_failures', False)
    output_format = getattr(args, 'format', 'text')
    from reveal.adapters.ssl.certificate import check_ssl_health  # noqa: I006 — optional heavy dep

    rows = analyzer.extract_acme_roots()
    if not rows:
        if output_format == 'json':
            print(json.dumps({'type': 'nginx_acme_audit', 'domains': [],
                              'has_failures': False, 'message': 'No ACME challenge location blocks found.'}))
        else:
            print("No ACME challenge location blocks found.")
        return

    results = _fetch_acme_ssl_data(rows, check_ssl_health)

    for r in results:
        _, acl_fail = _format_acl_col(r['acl_status'])
        _, ssl_fail = _format_acme_ssl_col(r['ssl_status'], r['ssl_days'], r['ssl_not_after'])
        r['has_failure'] = acl_fail or ssl_fail

    has_failures = any(r['has_failure'] for r in results)

    if output_format == 'json':
        _render_acme_json(results, only_failures, has_failures)
        return

    _render_acme_text(results, analyzer, only_failures,
                      getattr(args, 'verbose', False), has_failures)


def _handle_global_audit(analyzer, args=None) -> None:
    """Audit http{} block + main context for security/operational directives (--global-audit)."""
    if not hasattr(analyzer, 'audit_global_directives'):
        print("Error: --global-audit is only supported for nginx config files.", file=sys.stderr)
        sys.exit(1)

    only_failures = getattr(args, 'only_failures', False)
    output_format = getattr(args, 'format', 'text')

    findings = analyzer.audit_global_directives()
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f['severity'], 99), f['label']))

    missing = [f for f in findings if not f['present']]
    has_failures = bool(missing)

    if output_format == 'json':
        output = [f for f in findings if not only_failures or not f['present']]
        print(json.dumps({
            'type': 'nginx_global_audit',
            'has_failures': has_failures,
            'only_failures': only_failures,
            'findings': output,
        }))
        if has_failures:
            sys.exit(2)
        return

    col_label = max(len(f['label']) for f in findings)
    header = f"  {'directive':<{col_label}}  severity  context  status"
    print(header)
    print("  " + "─" * (len(header) - 2))

    printed = 0
    for f in findings:
        if only_failures and f['present']:
            continue
        sev_str, _ = _SEVERITY_LABEL.get(f['severity'], (f['severity'], False))
        status = "✅ present" if f['present'] else "❌ missing"
        print(f"  {f['label']:<{col_label}}  {sev_str}  {f['context']:<7}  {status}")
        printed += 1

    if only_failures and printed == 0:
        print("✅ No missing directives.")
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

    from reveal.adapters.ssl.certificate import load_certificate_from_file, check_ssl_health  # noqa: I006 — optional heavy dep

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


def _handle_extract_option(analyzer, extract_type: str, args=None) -> None:
    """Handle --extract option with validation.

    Args:
        analyzer: Analyzer instance
        extract_type: Type to extract (e.g., 'domains', 'acme-roots')
        args: Full argument namespace (for --canonical-only and other flags)

    Exits:
        With error code 1 if extract type unknown
    """
    if extract_type == 'domains':
        canonical_only = getattr(args, 'canonical_only', False) if args else False
        _handle_domain_extraction(analyzer, canonical_only=canonical_only)
    elif extract_type == 'acme-roots':
        _handle_acme_roots_extraction(analyzer)
    else:
        print(f"Error: Unknown extract type '{extract_type}'", file=sys.stderr)
        print("Supported types: domains, acme-roots (for nginx configs)", file=sys.stderr)
        sys.exit(1)
