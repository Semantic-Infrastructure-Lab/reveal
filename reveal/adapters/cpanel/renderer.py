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
            return

        result_type = result.get('type', '')
        if result_type == 'cpanel_user':
            CpanelRenderer._render_overview(result)
        elif result_type == 'cpanel_domains':
            CpanelRenderer._render_domains(result)
        elif result_type == 'cpanel_ssl':
            CpanelRenderer._render_ssl(result)
        elif result_type == 'cpanel_acl':
            CpanelRenderer._render_acl(result)
        else:
            # Fallback: dump as JSON
            print(json.dumps(result, indent=2, default=str))

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
    def _render_ssl(r: Dict[str, Any]) -> None:
        username = r.get('username', '?')
        certs = r.get('certs', [])
        summary = r.get('summary', {})
        dns_verified = r.get('dns_verified', False)
        dns_excluded = r.get('dns_excluded', {})
        print(f"SSL disk certs for cPanel user: {username}")
        print(f"  source: {r.get('cpanel_ssl_dir', '')}/DOMAIN/combined")
        if summary:
            parts = [f"{v} {k}" for k, v in summary.items() if v]
            summary_line = f"  summary: {', '.join(parts)}"
            if dns_excluded:
                excluded_total = sum(dns_excluded.values())
                excluded_parts = [f"{v} {k}" for k, v in dns_excluded.items() if v]
                summary_line += f"  ({excluded_total} nxdomain-excluded: {', '.join(excluded_parts)})"
            print(summary_line)
        if dns_verified:
            print(f"  dns-verified: NXDOMAIN domains shown but excluded from summary counts")
        if not certs:
            print("  (no domains found)")
            return

        col_domain = max(len(c['domain']) for c in certs)
        print()
        print(f"  {'domain':<{col_domain}}  status")
        print("  " + "─" * (col_domain + 40))
        for c in certs:
            s = c['status']
            nxdomain = dns_verified and not c.get('dns_resolves', True)
            if s == 'ok':
                detail = f"✅ {c.get('days_until_expiry')}d  ({c.get('not_after', '')})"
            elif s in ('expiring', 'critical'):
                detail = f"⚠️  {c.get('days_until_expiry')}d  ({c.get('not_after', '')})"
            elif s == 'expired':
                days = abs(c.get('days_until_expiry', 0) or 0)
                detail = f"❌ EXPIRED {days}d ago  ({c.get('not_after', '')})"
            elif s == 'missing':
                detail = f"⚫ no cert at {c.get('cert_path', '')}"
            else:
                detail = f"❌ {c.get('error', s)}"
            if nxdomain:
                detail += "  [nxdomain]"
            print(f"  {c['domain']:<{col_domain}}  {detail}")

        steps = r.get('next_steps', [])
        if steps:
            print()
            for s in steps:
                print(f"  → {s}")

    @staticmethod
    def _render_acl(r: Dict[str, Any]) -> None:
        username = r.get('username', '?')
        domains = r.get('domains', [])
        summary = r.get('summary', {})
        print(f"Docroot ACL check for cPanel user: {username}")
        if summary:
            parts = [f"{v} {k}" for k, v in summary.items() if v]
            print(f"  summary: {', '.join(parts)}")
        if not domains:
            print("  (no domains found)")
            return

        col_domain = max(len(d['domain']) for d in domains)
        col_docroot = max(len(d.get('docroot', '')) for d in domains)
        print()
        print(f"  {'domain':<{col_domain}}  {'status':<14}  docroot")
        print("  " + "─" * (col_domain + col_docroot + 20))
        for d in domains:
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
