"""Renderer for cPanel adapter output (cpanel://)."""

import json
import sys
from typing import Dict, Any


def _icon_for_ssl_status(status: str) -> str:
    return {
        'ok': '✅',
        'expiring': '⚠️ ',
        'critical': '❌',
        'expired': '❌',
        'missing': '⚫',
        'error': '❌',
    }.get(status, '?')


def _icon_for_acl_status(status: str) -> str:
    return {
        'ok': '✅',
        'denied': '❌',
        'no_docroot': '⚫',
    }.get(status, '⚠️ ')


class CpanelRenderer:
    """Renderer for cPanel user environment results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:
        if format == 'json':
            print(json.dumps(result, indent=2, default=str))
        else:
            result_type = result.get('type', '')
            if result_type == 'cpanel_user':
                CpanelRenderer._render_overview(result)
            elif result_type == 'cpanel_domains':
                CpanelRenderer._render_domains(result)
            elif result_type == 'cpanel_ssl':
                CpanelRenderer._render_ssl(result)
            elif result_type == 'cpanel_acl':
                CpanelRenderer._render_acl(result)
            elif result_type == 'cpanel_full_audit':
                CpanelRenderer._render_full_audit(result)
            elif result_type == 'cpanel_api_reference':
                CpanelRenderer._render_api_reference(result)
            else:
                # Fallback: dump as JSON
                print(json.dumps(result, indent=2, default=str))

        if result.get('type') == 'cpanel_full_audit' and result.get('has_failures'):
            sys.exit(2)

    @staticmethod
    def render_element(result: Dict[str, Any], format: str = 'text') -> None:
        CpanelRenderer.render_structure(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error: {error}", file=sys.stderr)

    @staticmethod
    def _render_overview(r: Dict[str, Any]) -> None:
        username = r.get('username', '?')
        print(f"cPanel user: {username}")
        print(f"  userdata dir: {r.get('userdata_dir', '?')}"
              + (" ✅" if r.get('userdata_accessible') else " ⚠️  not accessible"))
        print(f"  nginx config: {r.get('nginx_config') or '(not found)'}")
        print(f"  domains: {r.get('domain_count', 0)}")

        ssl = r.get('ssl_summary', {})
        if ssl:
            print()
            print("  SSL status:")
            for k, v in ssl.items():
                if v:
                    print(f"    {_icon_for_ssl_status(k)} {k}: {v}")

        steps = r.get('next_steps', [])
        if steps:
            print()
            print("  Next steps:")
            for s in steps:
                print(f"    {s}")

    @staticmethod
    def _render_domains(r: Dict[str, Any]) -> None:
        username = r.get('username', '?')
        domains = r.get('domains', [])
        print(f"Domains for cPanel user: {username}  ({len(domains)} total)")
        if not domains:
            print("  (none found)")
            return

        col_domain = max(len(d['domain']) for d in domains)
        col_type = max(len(d.get('type', '')) for d in domains)
        print()
        print(f"  {'domain':<{col_domain}}  {'type':<{col_type}}  docroot")
        print("  " + "─" * (col_domain + col_type + 40))
        for d in domains:
            print(f"  {d['domain']:<{col_domain}}  {d.get('type', ''):<{col_type}}  {d.get('docroot', '')}")

    @staticmethod
    def _format_live_detail(cert: dict) -> str:
        """Format the live cert status line for --check-live mode."""
        live_s = cert.get('live_status')
        if not live_s:
            return ''
        if cert.get('live_error'):
            return f"     ↳ ⚠️  live: check failed — {cert['live_error'][:50]}"
        live_days = cert.get('live_days_until_expiry')
        live_exp = cert.get('live_not_after', '')
        live_icon = _icon_for_ssl_status(live_s)
        if live_s == 'ok':
            return f"     ↳ {live_icon} live: {live_days}d  ({live_exp})"
        elif live_s in ('expiring', 'critical'):
            return f"     ↳ {live_icon} live: {live_days}d  ({live_exp})"
        elif live_s == 'expired':
            days_ago = abs(live_days or 0)
            return f"     ↳ {live_icon} live: EXPIRED {days_ago}d ago  ({live_exp})"
        else:
            return f"     ↳ {live_icon} live: {live_s}"

    @staticmethod
    def _format_cert_detail(cert: dict, nxdomain: bool, elsewhere: bool = False) -> str:
        """Format the status detail string for one cert row."""
        s = cert['status']
        if s == 'ok':
            detail = f"✅ {cert.get('days_until_expiry')}d  ({cert.get('not_after', '')})"
        elif s in ('expiring', 'critical'):
            detail = f"⚠️  {cert.get('days_until_expiry')}d  ({cert.get('not_after', '')})"
        elif s == 'expired':
            days = abs(cert.get('days_until_expiry', 0) or 0)
            detail = f"❌ EXPIRED {days}d ago  ({cert.get('not_after', '')})"
        elif s == 'missing':
            detail = f"⚫ no cert at {cert.get('cert_path', '')}"
        else:
            detail = f"❌ {cert.get('error', s)}"
        if nxdomain:
            detail += "  [nxdomain]"
        elif elsewhere:
            detail += "  [→ elsewhere]"
        # Append live cert line if present (from --check-live)
        live_line = CpanelRenderer._format_live_detail(cert)
        if live_line:
            detail += f"\n{live_line}"
        return detail

    @staticmethod
    def _render_ssl_summary_line(
        certs: list, summary: dict, dns_excluded: dict, dns_elsewhere: dict
    ) -> None:
        """Print the summary: line for _render_ssl."""
        expired_sub = sum(
            1 for c in certs
            if c.get('status') == 'expired'
            and c.get('domain_type', '') in ('subdomain', 'parked')
        )
        parts = []
        for k, v in summary.items():
            if not v:
                continue
            if k == 'expired' and expired_sub > 0:
                parts.append(f"{v} expired ({expired_sub} subdomain/parked)")
            else:
                parts.append(f"{v} {k}")
        summary_line = f"  summary: {', '.join(parts) or 'none'}"
        if dns_excluded:
            excluded_total = sum(dns_excluded.values())
            excluded_parts = [f"{v} {k}" for k, v in dns_excluded.items() if v]
            summary_line += f"  ({excluded_total} nxdomain-excluded: {', '.join(excluded_parts)})"
        if dns_elsewhere:
            elsewhere_total = sum(dns_elsewhere.values())
            elsewhere_parts = [f"{v} {k}" for k, v in dns_elsewhere.items() if v]
            summary_line += f"  ({elsewhere_total} elsewhere-excluded: {', '.join(elsewhere_parts)})"
        print(summary_line)

    @staticmethod
    def _render_ssl_table(certs: list, dns_verified: bool, r: Dict[str, Any]) -> None:
        """Print the cert table and next steps for _render_ssl."""
        only_failures = r.get('only_failures', False)
        visible_certs = [c for c in certs if not only_failures or c.get('status') != 'ok']
        if only_failures and not visible_certs:
            print("✅ No failures found.")
            return
        col_domain = max(len(c['domain']) for c in visible_certs)
        print()
        print(f"  {'domain':<{col_domain}}  status")
        print("  " + "─" * (col_domain + 40))
        for c in visible_certs:
            nxdomain = dns_verified and not c.get('dns_resolves', True)
            elsewhere = dns_verified and c.get('dns_points_here') is False
            detail = CpanelRenderer._format_cert_detail(c, nxdomain, elsewhere)
            print(f"  {c['domain']:<{col_domain}}  {detail}")
        steps = r.get('next_steps', [])
        if steps:
            print()
            for s in steps:
                print(f"  → {s}")

    @staticmethod
    def _render_ssl(r: Dict[str, Any]) -> None:
        username = r.get('username', '?')
        certs = r.get('certs', [])
        summary = r.get('summary', {})
        dns_verified = r.get('dns_verified', False)
        dns_excluded = r.get('dns_excluded', {})
        dns_elsewhere = r.get('dns_elsewhere', {})
        check_live = r.get('check_live', False)
        print(f"SSL disk certs for cPanel user: {username}")
        print(f"  source: {r.get('cpanel_ssl_dir', '')}/DOMAIN/combined")
        if check_live:
            non_ok = sum(1 for c in certs if c.get('status') != 'ok')
            print(f"  live-check: enabled — fetched live cert for {non_ok} non-ok domain(s)")
        if summary or dns_excluded or dns_elsewhere:
            CpanelRenderer._render_ssl_summary_line(certs, summary, dns_excluded, dns_elsewhere)
        if dns_verified:
            print("  dns-verified: NXDOMAIN and elsewhere-resolving domains excluded from summary counts")
        if not certs:
            print("  (no domains found)")
            return
        CpanelRenderer._render_ssl_table(certs, dns_verified, r)

    @staticmethod
    def _render_acl(r: Dict[str, Any]) -> None:
        username = r.get('username', '?')
        domains = r.get('domains', [])
        summary = r.get('summary', {})
        only_failures = r.get('only_failures', False)
        print(f"Docroot ACL check for cPanel user: {username}")
        if summary:
            parts = [f"{v} {k}" for k, v in summary.items() if v]
            print(f"  summary: {', '.join(parts)}")
        if not domains:
            print("  (no domains found)")
            return

        visible = [d for d in domains if not only_failures or d['acl_status'] == 'denied']
        if only_failures and not visible:
            print("✅ No ACL failures found.")
            return

        col_domain = max(len(d['domain']) for d in visible)
        col_docroot = max(len(d.get('docroot', '')) for d in visible)
        print()
        print(f"  {'domain':<{col_domain}}  {'status':<14}  docroot")
        print("  " + "─" * (col_domain + col_docroot + 20))
        for d in visible:
            icon = _icon_for_acl_status(d['acl_status'])
            status_col = f"{icon} {d['acl_status']}"
            print(f"  {d['domain']:<{col_domain}}  {status_col:<14}  {d.get('docroot', '')}")

        if r.get('has_failures'):
            print()
            print("❌ ACL failures detected — 'nobody' cannot read docroot(s).")
            print("   Fix: chmod o+x on each path component of the docroot.")

        steps = r.get('next_steps', [])
        if steps:
            print()
            for s in steps:
                print(f"  → {s}")

    @staticmethod
    def _render_audit_ssl_section(ssl: dict) -> None:
        """Print the SSL section of a full-audit report."""
        ssl_summary = ssl.get('summary', {})
        ssl_total = ssl.get('cert_count', 0)
        ssl_parts = [f"{v} {k}" for k, v in ssl_summary.items() if v]
        ssl_issues = sum(v for k, v in ssl_summary.items() if k != 'ok' and v)
        ssl_icon = '❌' if ssl_issues else '✅'
        print(f"{ssl_icon} SSL ({ssl_total} domains): {', '.join(ssl_parts) or 'none'}")
        if ssl_issues:
            for c in ssl.get('certs', []):
                if c.get('status') != 'ok':
                    detail = CpanelRenderer._format_cert_detail(c, False)
                    print(f"     {c['domain']}: {detail}")

    @staticmethod
    def _render_audit_acl_section(acl: dict) -> None:
        """Print the ACL section of a full-audit report."""
        acl_summary = acl.get('summary', {})
        acl_total = acl.get('domain_count', 0)
        acl_parts = [f"{v} {k}" for k, v in acl_summary.items() if v]
        acl_has_failures = acl.get('has_failures', False)
        acl_icon = '❌' if acl_has_failures else '✅'
        print(f"{acl_icon} ACL ({acl_total} domains): {', '.join(acl_parts) or 'none'}")
        if acl_has_failures:
            for d in acl.get('domains', []):
                if d['acl_status'] == 'denied':
                    print(f"     {d['domain']}: ❌ denied  ({d.get('docroot', '')})")

    @staticmethod
    def _render_audit_nginx_section(nginx: Any) -> None:
        """Print the nginx ACME section of a full-audit report."""
        if nginx is None:
            print("⚫ nginx: no config found")
            return
        if 'error' in nginx:
            print(f"⚠️  nginx: audit error — {nginx['error']}")
            return
        nginx_total = nginx.get('domain_count', 0)
        if nginx_total == 0:
            print("⚫ nginx: no ACME challenge roots found")
            return
        nginx_fails = [d for d in nginx.get('domains', []) if d.get('has_failure')]
        nginx_ok = nginx_total - len(nginx_fails)
        nginx_parts = []
        if nginx_ok:
            nginx_parts.append(f"{nginx_ok} ok")
        if nginx_fails:
            nginx_parts.append(f"{len(nginx_fails)} issues")
        nginx_icon = '❌' if nginx_fails else '✅'
        print(f"{nginx_icon} nginx ACME ({nginx_total} domains): {', '.join(nginx_parts)}")
        for d in nginx_fails:
            print(f"     {d['domain']}: acl={d['acl_status']} ssl={d['ssl_status']}")

    @staticmethod
    def _render_full_audit(r: Dict[str, Any]) -> None:
        username = r.get('username', '?')
        print(f"Full audit: {username}")
        print("=" * (len(username) + 13))
        print()
        CpanelRenderer._render_audit_ssl_section(r.get('ssl', {}))
        CpanelRenderer._render_audit_acl_section(r.get('acl', {}))
        CpanelRenderer._render_audit_nginx_section(r.get('nginx'))
        print()
        if r.get('has_failures'):
            print("❌ Audit complete — failures detected (exit 2)")
        else:
            print("✅ Audit complete — all checks passed")

    @staticmethod
    def _render_api_reference(r: Dict[str, Any]) -> None:
        """Print the cpanel://help/api quick-reference."""
        print(f"\n{r.get('title', 'WHM & cPanel API Quick Reference')}")
        print("=" * len(r.get('title', '')))

        for section in r.get('sections', []):
            print(f"\n{section['name']}:")
            for cmd in section.get('commands', []):
                print(f"  {cmd['command']}")
                print(f"    {cmd['description']}")

        paths = r.get('filesystem_paths', [])
        if paths:
            print("\nKey Filesystem Paths:")
            for p in paths:
                print(f"  {p['path']}")
                print(f"    {p['description']}")

        types = r.get('domain_types', {})
        if types:
            print("\nDomain Types (critical for SSL troubleshooting):")
            for name, desc in types.items():
                print(f"  {name:<10} — {desc}")

        tips = r.get('tips', [])
        if tips:
            print("\nTips:")
            for tip in tips:
                print(f"  • {tip}")
        print()
