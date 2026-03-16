"""Renderer for AutoSSL adapter output (autossl://)."""

import json
import sys
from typing import Any, Dict, List


_STATUS_ICON = {
    'ok': '✅',
    'incomplete': '⚠️ ',
    'defective': '❌',
    'dcv_failed': '🔴',
    'unknown': '⚫',
}

_IMPEDIMENT_SHORT = {
    'TOTAL_DCV_FAILURE': 'DCV:TOTAL',
    'NO_UNSECURED_DOMAIN_PASSED_DCV': 'DCV:PARTIAL',
}


def _icon(status: str) -> str:
    return _STATUS_ICON.get(status, '⚫')


def _summary_line(summary: Dict[str, int]) -> str:
    parts = []
    for status in ('ok', 'incomplete', 'defective', 'dcv_failed', 'unknown'):
        n = summary.get(status, 0)
        if n:
            parts.append(f"{_icon(status)} {n} {status}")
    return '  '.join(parts) if parts else '(none)'


def _parse_duration(run_start: str, run_end: str) -> str:
    """Return human-readable duration between two ISO timestamps."""
    try:
        from datetime import datetime
        fmt = '%Y-%m-%dT%H:%M:%SZ'
        t0 = datetime.strptime(run_start, fmt)
        t1 = datetime.strptime(run_end, fmt)
        secs = int((t1 - t0).total_seconds())
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60}s"
    except Exception:
        return ''


class AutosslRenderer:
    """Renderer for AutoSSL run results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:
        if format == 'json':
            print(json.dumps(result, indent=2, default=str))
            return

        result_type = result.get('type', '')
        if result_type == 'autossl_runs':
            AutosslRenderer._render_runs(result)
        elif result_type == 'autossl_run':
            if result.get('error'):
                AutosslRenderer._render_error(result)
            else:
                AutosslRenderer._render_run(result)
        elif result_type == 'autossl_error_codes':
            AutosslRenderer._render_error_codes(result)
        else:
            print(json.dumps(result, indent=2, default=str))

    @staticmethod
    def render_element(result: Dict[str, Any], format: str = 'text') -> None:
        AutosslRenderer.render_structure(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error: {error}", file=sys.stderr)

    @staticmethod
    def _render_runs(r: Dict[str, Any]) -> None:
        runs = r.get('runs', [])
        print(f"AutoSSL Runs: {r.get('log_dir', '')}  ({r.get('run_count', 0)} total)")
        if not runs:
            print("  (no runs found — is this a cPanel server?)")
            return
        print()
        print("  Recent runs (newest first):")
        for ts in runs[:20]:
            print(f"    {ts}")
        if len(runs) > 20:
            print(f"    ... ({len(runs) - 20} more)")
        steps = r.get('next_steps', [])
        if steps:
            print()
            for s in steps:
                if s:
                    print(f"  → {s}")

    @staticmethod
    def _render_error(r: Dict[str, Any]) -> None:
        print(f"AutoSSL run: {r.get('run_timestamp', '?')}")
        print(f"  Error: {r.get('error', 'unknown error')}")
        print(f"  Log dir: {r.get('log_dir', '?')}")

    @staticmethod
    def _render_run(r: Dict[str, Any]) -> None:
        ts = r.get('run_timestamp', '?')
        provider = r.get('provider', '?')
        run_start = r.get('run_start', '')
        run_end = r.get('run_end', '')
        duration = _parse_duration(run_start, run_end) if run_start and run_end else ''

        header_parts = [f"AutoSSL Run: {ts}"]
        header_parts.append(f"Provider: {provider}")
        if duration:
            header_parts.append(f"Duration: {duration}")
        print("  ".join(header_parts))

        user_count = r.get('user_count', 0)
        domain_count = r.get('domain_count', 0)
        print(f"  Users: {user_count}  |  Domains: {domain_count}")

        overall = r.get('summary', {})
        if overall:
            print(f"  Summary: {_summary_line(overall)}")

        users = r.get('users', [])
        for user in users:
            AutosslRenderer._render_user(user)

    @staticmethod
    def _render_user(user: Dict[str, Any]) -> None:
        username = user.get('username', '?')
        domain_count = user.get('domain_count', 0)
        summary = user.get('summary', {})
        domains = user.get('domains', [])

        print()
        print(f"User: {username}  ({domain_count} domains)")
        if summary:
            print(f"  {_summary_line(summary)}")

        if not domains:
            print("  (no domains)")
            return

        print()
        AutosslRenderer._render_domain_table(domains)

    @staticmethod
    def _render_domain_table(domains: List[Dict[str, Any]]) -> None:
        # Compute column widths
        max_domain = max((len(d['domain']) for d in domains), default=20)
        max_domain = min(max_domain, 55)  # cap at 55 chars

        header = f"  {'domain':<{max_domain}}  status       expiry    detail"
        print(header)
        print("  " + "─" * (max_domain + 40))

        for d in domains:
            domain = d['domain']
            if len(domain) > max_domain:
                domain = domain[:max_domain - 1] + '…'

            status = d.get('tls_status') or (
                'dcv_failed' if d.get('impediments') else 'unknown'
            )
            icon = _icon(status)
            status_col = f"{icon} {status:<10}"

            # Expiry: show days (+ = future, - = past)
            days = d.get('cert_expiry_days')
            if days is not None:
                expiry_col = f"{days:+.0f}d".rjust(6)
            else:
                expiry_col = "      "

            # Detail: defect codes or impediment codes
            details = []
            codes = d.get('defect_codes', [])
            if codes:
                details.extend(codes[:2])  # max 2 codes inline
            for imp in d.get('impediments', [])[:1]:
                short = _IMPEDIMENT_SHORT.get(imp['code'], imp['code'])
                details.append(short)

            detail_col = ', '.join(details)[:40] if details else ''

            print(f"  {domain:<{max_domain}}  {status_col}  {expiry_col}  {detail_col}")

    @staticmethod
    def _render_error_codes(r: Dict[str, Any]) -> None:
        """Print the autossl://error-codes reference."""
        print(f"\n{r.get('title', 'AutoSSL Error Code Reference')}\n")

        openssl_codes = r.get('openssl_defect_codes', [])
        if openssl_codes:
            print("OpenSSL Defect Codes (appear in autossl://latest output under defect_codes):")
            print()
            for entry in openssl_codes:
                print(f"  {entry['code']}")
                print(f"    Meaning: {entry['meaning']}")
                print(f"    Cause:   {entry['cause']}")
                print(f"    Fix:     {entry['fix']}")
                print()

        dcv_codes = r.get('dcv_impediment_codes', [])
        if dcv_codes:
            print("DCV Impediment Codes (appear under impediments[].code):")
            print()
            for entry in dcv_codes:
                print(f"  {entry['code']}")
                print(f"    Meaning: {entry['meaning']}")
                print(f"    Cause:   {entry['cause']}")
                print(f"    Fix:     {entry['fix']}")
                print()

        tls = r.get('tls_status_values', {})
        if tls:
            print("TLS Status Values (tls_status field in autossl://latest):")
            for k, v in tls.items():
                print(f"  {k:<12} — {v}")
            print()

        steps = r.get('next_steps', [])
        if steps:
            print("Next Steps:")
            for s in steps:
                print(f"  {s}")
