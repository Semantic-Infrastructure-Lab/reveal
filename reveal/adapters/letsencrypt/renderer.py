"""Renderer for letsencrypt:// adapter."""

import json
from typing import Any, Dict


class LetsEncryptRenderer:
    """Renders Let's Encrypt cert inventory output."""

    @staticmethod
    def render_structure(result: Dict[str, Any], output_format: str = 'text') -> None:
        if output_format == 'json':
            print(json.dumps(result, default=str))
            return
        LetsEncryptRenderer._render_text(result)

    @staticmethod
    def _render_text(result: Dict[str, Any]) -> None:
        live_dir = result.get('live_dir', '/etc/letsencrypt/live')
        if not result.get('live_dir_exists'):
            print(f"⚠️  {live_dir} not found — is this a Let's Encrypt server?")
            return

        certs = result.get('certs', [])
        if not certs:
            print(f"No certs found in {live_dir}")
            return

        dup_check = result.get('duplicate_check')
        orphan_check = result.get('orphan_check')

        # When --check-duplicates returns clean, skip the full cert table — just show conclusion.
        clean_dup_only = (dup_check is not None
                          and dup_check.get('duplicate_group_count', 0) == 0
                          and orphan_check is None)
        if not clean_dup_only:
            _render_cert_table(certs)

        renewal_timer = result.get('renewal_timer')
        if renewal_timer is not None and not clean_dup_only:
            print()
            _render_renewal_timer(renewal_timer)

        if orphan_check is not None:
            print()
            _render_orphan_check(orphan_check)

        if dup_check is not None:
            print()
            _render_duplicate_check(dup_check)

        next_steps = result.get('next_steps', [])
        if next_steps:
            print()
            for step in next_steps:
                print(f"  {step}")

    @staticmethod
    def render_error(error: str) -> None:
        print(f"Error: {error}")


def _expiry_label(days: int, is_expired: bool) -> str:
    if is_expired:
        return f"EXPIRED ({abs(days)}d ago)"
    if days <= 7:
        return f"⚠️  {days}d"
    if days <= 30:
        return f"~{days}d"
    return f"{days}d"


def _render_cert_table(certs: list) -> None:
    col_name = max(len(c.get('name', '')) for c in certs)
    col_cn = max(len(c.get('common_name', c.get('error', ''))) for c in certs)

    header = f"  {'name':<{col_name}}  {'common name':<{col_cn}}  expiry   SANs"
    print(header)
    print("  " + "─" * (len(header) - 2))

    for cert in certs:
        name = cert.get('name', '')
        if 'error' in cert:
            print(f"  {name:<{col_name}}  ⚠️  {cert['error'][:60]}")
            continue
        cn = cert.get('common_name', '')
        days = cert.get('days_until_expiry', 0)
        is_expired = cert.get('is_expired', False)
        san_count = len(cert.get('san', []))
        expiry_str = _expiry_label(days, is_expired)
        print(f"  {name:<{col_name}}  {cn:<{col_cn}}  {expiry_str:<8}  {san_count} name(s)")


def _render_renewal_timer(renewal_timer: dict) -> None:
    if renewal_timer.get('configured'):
        mechanisms = renewal_timer.get('mechanisms', [])
        kinds = {m['kind'] for m in mechanisms}
        label = ' + '.join(sorted(kinds))
        print(f"  ✅ Renewal timer configured ({label})")
        for m in mechanisms:
            print(f"      {m['path']}")
    else:
        print(f"  ⚠️  {renewal_timer.get('warning', 'No renewal timer found')}")


def _render_orphan_check(orphan_check: dict) -> None:
    orphan_count = orphan_check.get('orphan_count', 0)
    nginx_dirs = orphan_check.get('nginx_dirs_scanned', [])
    nginx_paths_found = orphan_check.get('nginx_cert_paths_found', 0)

    print(f"Orphan check (nginx dirs: {', '.join(nginx_dirs)})")
    print(f"  ssl_certificate paths found in nginx: {nginx_paths_found}")

    if orphan_count == 0:
        print("  ✅ No orphaned certs — all certs are referenced by nginx.")
        return

    print(f"  ❌ {orphan_count} orphaned cert(s) (not referenced by any ssl_certificate):")
    for cert in orphan_check.get('orphans', []):
        name = cert.get('name', '')
        days = cert.get('days_until_expiry', 0)
        is_expired = cert.get('is_expired', False)
        expiry_str = _expiry_label(days, is_expired)
        print(f"    {name}  ({expiry_str})  {cert.get('cert_path', '')}")


def _render_duplicate_check(dup_check: dict) -> None:
    group_count = dup_check.get('duplicate_group_count', 0)

    print("Duplicate SAN check")
    if group_count == 0:
        print("  ✅ No duplicate-SAN certs found.")
        return

    print(f"  ⚠️  {group_count} group(s) with identical SANs:")
    for group in dup_check.get('groups', []):
        san_set = group[0].get('san', []) if group else []
        print(f"    SANs: {', '.join(san_set[:3])}{'...' if len(san_set) > 3 else ''}")
        for cert in group:
            days = cert.get('days_until_expiry', 0)
            is_expired = cert.get('is_expired', False)
            expiry_str = _expiry_label(days, is_expired)
            print(f"      {cert.get('name', ''):<30}  {expiry_str}")
