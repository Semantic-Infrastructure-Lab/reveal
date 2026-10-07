"""CLI handlers for nginx file analysis operations.

These handlers implement the nginx-specific CLI flags that operate on
NginxAnalyzer objects: --extract, --check-acl, --validate-nginx-acme,
--global-audit, --check-conflicts, --diagnose, --cpanel-certs.

Moved from reveal/handlers_nginx.py to this package (BACK-097) to keep
nginx operations co-located with other nginx adapter code.

Each handler returns a FlagOutput (stdout text, stderr text, exit code) instead of
printing and exiting; reveal.file_handler writes it out in one place (BACK-916).
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from reveal.utils.lines import split_lines

if TYPE_CHECKING:
    from argparse import Namespace


_SEVERITY_ORDER = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'INFO': 3}
_SEVERITY_LABEL = {
    'HIGH':   ('HIGH  ', True),
    'MEDIUM': ('MED   ', True),
    'LOW':    ('LOW   ', False),
    'INFO':   ('INFO  ', False),
}


@dataclass
class FlagOutput:
    """What a flag handler produced: stdout lines, stderr lines and the exit code."""
    out: List[str] = field(default_factory=list)
    err: List[str] = field(default_factory=list)
    code: int = 0

    def line(self, text: str = '') -> None:
        self.out.append(text)

    def exit_if(self, failed: bool) -> 'FlagOutput':
        """Exit 2 when the audit found failures."""
        if failed:
            self.code = 2
        return self

    @property
    def stdout(self) -> str:
        return ''.join(f"{text}\n" for text in self.out)

    @property
    def stderr(self) -> str:
        return ''.join(f"{text}\n" for text in self.err)


def _error(*lines: str) -> FlagOutput:
    """A failed handler: the message on stderr, exit 1."""
    return FlagOutput(err=list(lines), code=1)


def _unsupported(flag: str, analyzer) -> FlagOutput:
    return _error(f"Error: {flag} not supported for {type(analyzer).__name__}",
                  "This option is available for nginx config files.")


def _handle_domain_extraction(analyzer, canonical_only: bool = False) -> FlagOutput:
    """Handle domain extraction from analyzer.

    Args:
        analyzer: Analyzer instance
        canonical_only: When True, emit one URI per vhost (primary server_name only)

    Exit code 1 if domain extraction not supported.
    """
    if not hasattr(analyzer, 'extract_ssl_domains'):
        return _unsupported("--extract domains", analyzer)
    result = FlagOutput()
    for domain in analyzer.extract_ssl_domains(canonical_only=canonical_only):
        result.line(f"ssl://{domain}")
    return result


def _acme_root_detail(r: dict) -> tuple:
    """Return (icon, detail) for one ACME root row."""
    status = r['acl_status']
    if status == 'ok':
        return "✅", "nobody:read OK"
    if status == 'denied':
        return "", f"❌ DENIED  ({r['acl_message']})"
    if status == 'not_found':
        return "⚠️ ", f"path not found: {r['acme_path']}"
    return "❓", r['acl_message']


def _handle_acme_roots_extraction(analyzer) -> FlagOutput:
    """ACME challenge root paths and nobody ACL status (N4)."""
    if not hasattr(analyzer, 'extract_acme_roots'):
        return _unsupported("--extract acme-roots", analyzer)

    result = FlagOutput()
    rows = analyzer.extract_acme_roots()
    if not rows:
        result.line("No ACME challenge location blocks found.")
        return result

    col_domain = max(len(r['domain']) for r in rows)
    col_path = max(len(r['acme_path']) for r in rows)

    header = (f"  {'domain':<{col_domain}}  {'acme root path':<{col_path}}  acl status")
    result.line(header)
    result.line("  " + "-" * (len(header) - 2))

    for r in rows:
        icon, detail = _acme_root_detail(r)
        result.line(f"  {r['domain']:<{col_domain}}  {r['acme_path']:<{col_path}}  {icon} {detail}")
    return result


def _handle_check_acl(analyzer) -> FlagOutput:
    """Nobody ACL status for all root directives in config (N1)."""
    if not hasattr(analyzer, 'extract_docroot_acl'):
        return _unsupported("--check-acl", analyzer)

    result = FlagOutput()
    rows = analyzer.extract_docroot_acl()
    if not rows:
        result.line("No root directives found.")
        return result

    failures = [r for r in rows if r['acl_status'] != 'ok']
    passes = [r for r in rows if r['acl_status'] == 'ok']

    col_root = max(len(r['root']) for r in rows)
    col_domain = max(len(r['domain']) for r in rows)

    if failures:
        result.line(f"❌ ACL failures ({len(failures)}):")
        for r in failures:
            result.line(f"  {r['root']:<{col_root}}  ({r['domain']})  {r['acl_message']}")
        result.line()

    if passes:
        result.line(f"✅ OK ({len(passes)}):")
        for r in passes:
            result.line(f"  {r['root']:<{col_root}}  ({r['domain']})")
        result.line()

    return result.exit_if(bool(failures))


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
                            'ssl_not_after': str(exc)[:60], 'error': str(exc)})
    return results


def _render_acme_json(results: list, only_failures: bool, has_failures: bool) -> FlagOutput:
    """ACME audit results as JSON; exit 2 on failures."""
    output_rows = [r for r in results if not only_failures or r['has_failure']]
    result = FlagOutput()
    result.line(json.dumps({
        'type': 'nginx_acme_audit',
        'has_failures': has_failures,
        'only_failures': only_failures,
        'domains': output_rows,
    }, default=str))
    return result.exit_if(has_failures)


def _acme_verbose_snippet(r: dict, analyzer_lines: list) -> List[str]:
    """The location block behind one ACME row: the matched line + up to 3 lines ahead."""
    line_no = r.get('line', 0)
    if not (line_no and 0 < line_no <= len(analyzer_lines)):
        return []
    snippet = ''.join(analyzer_lines[line_no - 1:line_no + 3]).rstrip()
    return [f"       {line_no + offset}: {sl.rstrip()}"
            for offset, sl in enumerate(split_lines(snippet))]


def _render_acme_text(results: list, analyzer, only_failures: bool, verbose: bool,
                      has_failures: bool) -> FlagOutput:
    """ACME audit results as a text table; exit 2 on failures."""
    result = FlagOutput()
    col_domain = max(len(r['domain']) for r in results)
    col_path = max(len(r['acme_path']) for r in results)

    header = (f"  {'domain':<{col_domain}}  {'acme root path':<{col_path}}"
              f"  {'acl':<14}  ssl status")
    result.line(header)
    result.line("  " + "─" * (len(header) - 2))

    printed = 0
    analyzer_lines = getattr(analyzer, 'lines', [])
    for r in results:
        acl_col, _ = _format_acl_col(r['acl_status'])
        ssl_col, _ = _format_acme_ssl_col(r['ssl_status'], r['ssl_days'], r['ssl_not_after'])
        if only_failures and not r['has_failure']:
            continue
        result.line(f"  {r['domain']:<{col_domain}}  {r['acme_path']:<{col_path}}"
                    f"  {acl_col:<14}  {ssl_col}")
        if verbose and analyzer_lines:
            for snippet_line in _acme_verbose_snippet(r, analyzer_lines):
                result.line(snippet_line)
        printed += 1

    if only_failures and printed == 0:
        result.line("✅ No failures found.")
    return result.exit_if(has_failures)


def _handle_validate_nginx_acme(analyzer, args=None) -> FlagOutput:
    """Full ACME pipeline audit: acme root + ACL + live SSL per domain (--validate-nginx-acme)."""
    if not hasattr(analyzer, 'extract_acme_roots'):
        return _unsupported("--validate-nginx-acme", analyzer)

    only_failures = getattr(args, 'only_failures', False)
    output_format = getattr(args, 'format', 'text')
    from reveal.adapters.ssl.certificate import check_ssl_health  # noqa: I006 — optional heavy dep

    rows = analyzer.extract_acme_roots()
    if not rows:
        result = FlagOutput()
        if output_format == 'json':
            result.line(json.dumps({'type': 'nginx_acme_audit', 'domains': [],
                                    'has_failures': False,
                                    'message': 'No ACME challenge location blocks found.'}))
        else:
            result.line("No ACME challenge location blocks found.")
        return result

    results = _fetch_acme_ssl_data(rows, check_ssl_health)

    for r in results:
        _, acl_fail = _format_acl_col(r['acl_status'])
        _, ssl_fail = _format_acme_ssl_col(r['ssl_status'], r['ssl_days'], r['ssl_not_after'])
        r['has_failure'] = acl_fail or ssl_fail

    has_failures = any(r['has_failure'] for r in results)

    if output_format == 'json':
        return _render_acme_json(results, only_failures, has_failures)

    return _render_acme_text(results, analyzer, only_failures,
                             getattr(args, 'verbose', False), has_failures)


def _handle_global_audit(analyzer, args=None) -> FlagOutput:
    """Audit http{} block + main context for security/operational directives (--global-audit)."""
    if not hasattr(analyzer, 'audit_global_directives'):
        return _error("Error: --global-audit is only supported for nginx config files.")

    only_failures = getattr(args, 'only_failures', False)
    output_format = getattr(args, 'format', 'text')

    findings = analyzer.audit_global_directives()
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f['severity'], 99), f['label']))

    has_failures = any(not f['present'] for f in findings)
    result = FlagOutput()

    if output_format == 'json':
        output = [f for f in findings if not only_failures or not f['present']]
        result.line(json.dumps({
            'type': 'nginx_global_audit',
            'has_failures': has_failures,
            'only_failures': only_failures,
            'findings': output,
        }))
        return result.exit_if(has_failures)

    col_label = max(len(f['label']) for f in findings)
    header = f"  {'directive':<{col_label}}  severity  context  status"
    result.line(header)
    result.line("  " + "─" * (len(header) - 2))

    printed = 0
    for f in findings:
        if only_failures and f['present']:
            continue
        sev_str, _ = _SEVERITY_LABEL.get(f['severity'], (f['severity'], False))
        status = "✅ present" if f['present'] else "❌ missing"
        result.line(f"  {f['label']:<{col_label}}  {sev_str}  {f['context']:<7}  {status}")
        printed += 1

    if only_failures and printed == 0:
        result.line("✅ No missing directives.")
    return result.exit_if(has_failures)


def _conflict_lines(c: dict) -> List[str]:
    """One conflict: the server, both locations and the note."""
    return [f"\n  [{c['server']}]",
            f"    {c['location_a']['path']}  (line {c['location_a']['line']})",
            f"    {c['location_b']['path']}  (line {c['location_b']['line']})",
            f"    → {c['note']}"]


def _handle_check_conflicts(analyzer) -> FlagOutput:
    """Detect nginx location prefix overlaps and regex/prefix conflicts (N2)."""
    if not hasattr(analyzer, 'detect_location_conflicts'):
        return _unsupported("--check-conflicts", analyzer)

    result = FlagOutput()
    conflicts = analyzer.detect_location_conflicts()
    if not conflicts:
        result.line("✅ No location conflicts detected.")
        return result

    warnings = [c for c in conflicts if c['severity'] == 'warning']
    infos = [c for c in conflicts if c['severity'] == 'info']

    for heading, group in ((f"⚠️  Conflicts ({len(warnings)}):", warnings),
                           (f"ℹ️  Prefix overlaps ({len(infos)}):", infos)):
        if not group:
            continue
        result.line(heading)
        for c in group:
            result.out.extend(_conflict_lines(c))
        result.line()

    return result.exit_if(bool(warnings))


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


def _render_diagnose_table(hits: list, resolved_path: str, result: FlagOutput) -> bool:
    """Add the diagnose results table to `result`. Returns True if there are hard failures."""
    LABELS = {
        'permission_denied': '❌ Permission Denied',
        'not_found':         '⚠️  Not Found (ENOENT)',
        'ssl_error':         '❌ SSL Error',
    }
    col_domain = max(len(r['domain']) for r in hits)
    col_pattern = max(len(LABELS.get(r['pattern'], r['pattern'])) for r in hits)

    result.line(f"nginx error log: {resolved_path}")
    header = (f"  {'domain':<{col_domain}}  {'pattern':<{col_pattern}}"
              f"  {'count':>5}  last seen")
    result.line(header)
    result.line("  " + "─" * (len(header) - 2))

    has_failures = False
    for r in hits:
        label = LABELS.get(r['pattern'], r['pattern'])
        if r['pattern'] in ('permission_denied', 'ssl_error'):
            has_failures = True
        result.line(f"  {r['domain']:<{col_domain}}  {label:<{col_pattern}}"
                    f"  {r['count']:>5}  {r['last_seen']}")

    result.line()
    result.line("Sample (most recent match per type):")
    seen = set()
    for r in hits:
        key = (r['domain'], r['pattern'])
        if key not in seen:
            result.line(f"  [{r['domain']} / {r['pattern']}]")
            result.line(f"    {r['sample']}")
            seen.add(key)
    return has_failures


def _handle_diagnose(analyzer, log_path: Optional[str] = None) -> FlagOutput:
    """Diagnose ACME / SSL failures from the nginx error log."""
    if not hasattr(analyzer, 'diagnose_acme_errors'):
        return _error(f"Error: --diagnose not supported for {type(analyzer).__name__}",
                      "This option is available for nginx config files.")

    resolved_path = _resolve_log_path(analyzer, log_path)
    if not resolved_path or not os.path.exists(resolved_path):
        lines = ["⚠️  No nginx error log found."]
        if resolved_path:
            lines.append(f"   Checked: {resolved_path}")
        lines.append("   Use --log-path /path/to/error.log to specify the log file.")
        return _error(*lines)

    result = FlagOutput()
    hits = analyzer.diagnose_acme_errors(resolved_path)
    if not hits:
        result.line(f"✅ No ACME/SSL errors found in {resolved_path} (last 5,000 lines).")
        return result

    return result.exit_if(_render_diagnose_table(hits, resolved_path, result))


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


def _handle_cpanel_certs(analyzer, args=None) -> FlagOutput:
    """Compare cPanel on-disk certs against live certs per domain (S4 -- --cpanel-certs).

    For each SSL domain found in the nginx config:
    - Looks up /var/cpanel/ssl/apache_tls/DOMAIN/combined (disk cert)
    - Fetches the live cert from the network
    - Compares serial numbers to detect "AutoSSL renewed but nginx hasn't reloaded"

    By default uses canonical_only=True to skip www/mail/alias server_name variants —
    they share the parent domain's cert and have no disk cert of their own, which
    would produce ~85% no-disk-cert noise on large cPanel configs. Pass --all to
    include all aliases.

    Use --only-failures to skip rows where disk cert is not found (further noise reduction).
    """
    if not hasattr(analyzer, 'extract_ssl_domains'):
        return _unsupported("--cpanel-certs", analyzer)

    from reveal.adapters.ssl.certificate import load_certificate_from_file, check_ssl_health  # noqa: I006 — optional heavy dep

    show_all = getattr(args, 'all', False)
    only_failures = getattr(args, 'only_failures', False)
    result = FlagOutput()

    domains = analyzer.extract_ssl_domains(canonical_only=not show_all)
    if not domains:
        result.line("No SSL domains found in nginx config.")
        return result

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

    # --only-failures: skip rows where disk cert is simply absent (expected for alias domains)
    if only_failures:
        rows = [r for r in rows if r['disk'].get('status') != 'missing']

    if not rows:
        result.line("✅ No failures found.")
        return result

    col_domain = max(len(r['domain']) for r in rows)
    header = f"  {'domain':<{col_domain}}  {'disk cert':<28}  {'live cert':<28}  match"
    result.line(header)
    result.line("  " + "─" * (len(header) - 2))

    has_failures = False
    for r in rows:
        disk_col, disk_fail = _format_disk_col(r['disk'])
        live_col, live_fail = _format_live_col(r['live'])
        match_col, match_fail = _format_match_col(r['match'])
        has_failures = has_failures or disk_fail or live_fail or match_fail
        result.line(f"  {r['domain']:<{col_domain}}  {disk_col:<28}  {live_col:<28}  {match_col}")

    result.line()
    return result.exit_if(has_failures)


def _handle_extract_option(analyzer, extract_type: str, args=None) -> FlagOutput:
    """Handle --extract option with validation.

    Args:
        analyzer: Analyzer instance
        extract_type: Type to extract (e.g., 'domains', 'acme-roots')
        args: Full argument namespace (for --canonical-only and other flags)

    Exit code 1 if extract type unknown.
    """
    if extract_type == 'domains':
        canonical_only = getattr(args, 'canonical_only', False) if args else False
        return _handle_domain_extraction(analyzer, canonical_only=canonical_only)
    if extract_type == 'acme-roots':
        return _handle_acme_roots_extraction(analyzer)
    return _error(f"Error: Unknown extract type '{extract_type}'",
                  "Supported types: domains, acme-roots (for nginx configs)")
