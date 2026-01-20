"""SSL certificate result rendering for CLI output."""

import json
import sys
from typing import Dict, Any


class SSLRenderer:
    """Renderer for SSL adapter results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render SSL adapter structure results.

        Args:
            result: Result dictionary from SSLAdapter
            format: Output format ('text' or 'json')
        """
        if format == 'json':
            print(json.dumps(result, indent=2))
            return

        result_type = result.get('type', 'ssl_certificate')

        if result_type == 'ssl_certificate':
            SSLRenderer._render_certificate_overview(result)
        elif result_type == 'ssl_san':
            SSLRenderer._render_san(result)
        elif result_type == 'ssl_chain':
            SSLRenderer._render_chain(result)
        elif result_type == 'ssl_issuer':
            SSLRenderer._render_issuer(result)
        elif result_type == 'ssl_subject':
            SSLRenderer._render_subject(result)
        elif result_type == 'ssl_dates':
            SSLRenderer._render_dates(result)
        elif result_type == 'ssl_full':
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps(result, indent=2))

    @staticmethod
    def _render_certificate_overview(result: dict) -> None:
        """Render main certificate overview."""
        host = result['host']
        port = result['port']

        print(f"SSL Certificate: {host}" + (f":{port}" if port != 443 else ""))
        print()

        # Status line
        icon = result['health_icon']
        status = result['health_status']
        days = result['days_until_expiry']
        print(f"Status: {icon} {status} ({days} days until expiry)")
        print()

        # Certificate details
        print("Certificate:")
        print(f"  Common Name: {result['common_name']}")
        print(f"  Issuer: {result['issuer']}")
        print(f"  Valid: {result['valid_from']} to {result['valid_until']}")
        print(f"  SANs: {result['san_count']} domain(s)")
        print()

        # Verification
        v = result['verification']
        print("Verification:")
        chain_icon = '\u2705' if v['chain_valid'] else '\u274c'
        host_icon = '\u2705' if v['hostname_match'] else '\u274c'
        print(f"  Chain Valid: {chain_icon}")
        print(f"  Hostname Match: {host_icon}")
        if v.get('error'):
            print(f"  Error: {v['error']}")
        print()

        # Next steps
        if result.get('next_steps'):
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  {step}")

    @staticmethod
    def _render_san(result: dict) -> None:
        """Render Subject Alternative Names."""
        print(f"SSL SANs for {result['host']}")
        print(f"Common Name: {result['common_name']}")
        print(f"Total SANs: {result['san_count']}")
        print()

        # Group by wildcard vs specific
        wildcards = result.get('wildcard_entries', [])
        specifics = [s for s in result['san'] if not s.startswith('*.')]

        if wildcards:
            print("Wildcard Entries:")
            for san in sorted(wildcards):
                print(f"  {san}")
            print()

        if specifics:
            print("Specific Domains:")
            for san in sorted(specifics):
                print(f"  {san}")

    @staticmethod
    def _render_chain(result: dict) -> None:
        """Render certificate chain."""
        print(f"SSL Chain for {result['host']}")
        print(f"Chain Length: {result['chain_length']}")
        print()

        print("Leaf Certificate:")
        leaf = result['leaf']
        print(f"  CN: {leaf['common_name']}")
        print(f"  Issuer: {leaf['issuer']}")
        print()

        if result['chain']:
            print("Intermediate Certificates:")
            for i, cert in enumerate(result['chain'], 1):
                print(f"  [{i}] {cert.get('common_name', 'Unknown')}")
                print(f"      Issuer: {cert.get('issuer_name', 'Unknown')}")

        v = result['verification']
        print()
        print(f"Verified: {'Yes' if v.get('verified') else 'No'}")
        if v.get('error'):
            print(f"Error: {v['error']}")

    @staticmethod
    def _render_issuer(result: dict) -> None:
        """Render issuer details."""
        print(f"SSL Issuer for {result['host']}")
        print()

        issuer = result['issuer']
        print("Issuer Details:")
        for key, value in issuer.items():
            # Convert camelCase to readable
            readable_key = ''.join(
                ' ' + c if c.isupper() else c for c in key
            ).strip().title()
            print(f"  {readable_key}: {value}")

    @staticmethod
    def _render_subject(result: dict) -> None:
        """Render subject details."""
        print(f"SSL Subject for {result['host']}")
        print()

        subject = result['subject']
        print("Subject Details:")
        for key, value in subject.items():
            readable_key = ''.join(
                ' ' + c if c.isupper() else c for c in key
            ).strip().title()
            print(f"  {readable_key}: {value}")

    @staticmethod
    def _render_dates(result: dict) -> None:
        """Render validity dates."""
        print(f"SSL Validity for {result['host']}")
        print()
        print(f"Not Before: {result['not_before']}")
        print(f"Not After: {result['not_after']}")
        print(f"Days Until Expiry: {result['days_until_expiry']}")
        print(f"Expired: {'Yes' if result['is_expired'] else 'No'}")

    @staticmethod
    def render_check(result: dict, format: str = 'text') -> None:
        """Render SSL health check results.

        Args:
            result: Check result dictionary from SSLAdapter.check()
            format: Output format ('text' or 'json')
        """
        if format == 'json':
            print(json.dumps(result, indent=2))
            return

        result_type = result.get('type', 'ssl_check')

        if result_type == 'ssl_batch_check':
            SSLRenderer._render_batch_check(result)
            return

        # Single host check
        status = result['status']
        host = result['host']
        port = result['port']

        # Header with overall status
        status_icon = '\u2705' if status == 'pass' else '\u26a0\ufe0f' if status == 'warning' else '\u274c'
        port_str = f":{port}" if port != 443 else ""
        print(f"\nSSL Health Check: {host}{port_str}")
        print(f"Status: {status_icon} {status.upper()}")

        summary = result['summary']
        print(f"\nSummary: {summary['passed']}/{summary['total']} passed, "
              f"{summary['warnings']} warnings, {summary['failures']} failures")
        print()

        # Show certificate info if available
        if 'certificate' in result:
            cert = result['certificate']
            print(f"Certificate: {cert.get('common_name', 'Unknown')}")
            print(f"  Expires: {cert.get('not_after', 'Unknown')[:10]} "
                  f"({cert.get('days_until_expiry', '?')} days)")
            print()

        # Group checks by status
        checks = result.get('checks', [])
        failures = [c for c in checks if c['status'] == 'failure']
        warnings = [c for c in checks if c['status'] == 'warning']
        passes = [c for c in checks if c['status'] == 'pass']

        if failures:
            print("\u274c Failures:")
            for check in failures:
                print(f"  \u2022 {check['name']}: {check['message']}")
            print()

        if warnings:
            print("\u26a0\ufe0f  Warnings:")
            for check in warnings:
                print(f"  \u2022 {check['name']}: {check['message']}")
            print()

        if passes and not failures and not warnings:
            print("\u2705 All Checks Passed:")
            for check in passes:
                print(f"  \u2022 {check['name']}: {check['message']}")
            print()

        print(f"Exit code: {result['exit_code']}")

    @staticmethod
    def _render_batch_check(result: dict) -> None:
        """Render batch SSL check results."""
        status = result['status']
        source = result['source']

        status_icon = '\u2705' if status == 'pass' else '\u26a0\ufe0f' if status == 'warning' else '\u274c'
        print(f"\nSSL Batch Check: {source}")
        print(f"Status: {status_icon} {status.upper()}")

        summary = result['summary']
        print(f"\nDomains Checked: {result['domains_checked']}")
        print(f"Summary: {summary['passed']} passed, "
              f"{summary['warnings']} warnings, {summary['failures']} failures")
        print()

        # Group by status
        results = result.get('results', [])
        failures = [r for r in results if r['status'] == 'failure']
        warnings = [r for r in results if r['status'] == 'warning']
        passes = [r for r in results if r['status'] == 'pass']

        if failures:
            print("\u274c Failed:")
            for r in failures:
                host = r['host']
                if 'certificate' in r:
                    days = r['certificate'].get('days_until_expiry', '?')
                    print(f"  {host}: {days} days")
                elif 'error' in r:
                    print(f"  {host}: {r['error']}")
                else:
                    print(f"  {host}")
            print()

        if warnings:
            print("\u26a0\ufe0f  Warnings:")
            for r in warnings:
                host = r['host']
                days = r.get('certificate', {}).get('days_until_expiry', '?')
                print(f"  {host}: {days} days")
            print()

        if passes:
            print("\u2705 Healthy:")
            for r in passes:
                host = r['host']
                days = r.get('certificate', {}).get('days_until_expiry', '?')
                print(f"  {host}: {days} days")
            print()

        print(f"Exit code: {result['exit_code']}")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly error messages.

        Args:
            error: Exception to render
        """
        error_msg = str(error)

        if 'getaddrinfo failed' in error_msg or 'Name or service not known' in error_msg:
            print("Error: Could not resolve hostname", file=sys.stderr)
            print("", file=sys.stderr)
            print("Check that the domain name is correct and DNS is working.", file=sys.stderr)
        elif 'Connection refused' in error_msg:
            print("Error: Connection refused", file=sys.stderr)
            print("", file=sys.stderr)
            print("The server is not accepting connections on this port.", file=sys.stderr)
        elif 'timed out' in error_msg.lower():
            print("Error: Connection timed out", file=sys.stderr)
            print("", file=sys.stderr)
            print("The server did not respond. Check network connectivity.", file=sys.stderr)
        else:
            print(f"Error: {error}", file=sys.stderr)
