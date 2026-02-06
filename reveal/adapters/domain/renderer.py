"""Domain result rendering for CLI output."""

import sys
from typing import Dict, Any

from reveal.rendering import TypeDispatchRenderer


class DomainRenderer(TypeDispatchRenderer):
    """Renderer for Domain adapter results.

    Uses TypeDispatchRenderer for automatic routing to _render_{type}() methods.
    """

    # Type dispatch methods (called automatically based on result['type'])

    @staticmethod
    def _render_domain_overview(result: dict) -> None:
        """Render domain overview."""
        domain = result['domain']
        dns = result['dns']
        ssl = result['ssl']

        print(f"\n{'='*60}")
        print(f"Domain: {domain}")
        print(f"{'='*60}\n")

        # DNS section
        print("DNS Configuration:")
        if dns.get('error'):
            print(f"  Error: {dns['error']}")
        else:
            ns_list = dns.get('nameservers', [])
            if ns_list:
                ns_display = ', '.join(ns_list[:2])
                if len(ns_list) > 2:
                    ns_display += f" (+{len(ns_list) - 2} more)"
                print(f"  Nameservers: {ns_display}")
            else:
                print("  Nameservers: None")

            a_records = dns.get('a_records', [])
            if a_records:
                print(f"  A Records:   {', '.join(a_records)}")
            else:
                print("  A Records:   None")

            mx_icon = '\u2705' if dns.get('has_mx') else '\u274c'
            print(f"  MX Records:  {mx_icon} {'Configured' if dns.get('has_mx') else 'None'}")

        # SSL section
        print("\nSSL Status:")
        if ssl.get('error'):
            print(f"  Error: {ssl['error']}")
        elif ssl.get('has_certificate'):
            status_icons = {
                'pass': '\u2705',
                'warning': '\u26a0\ufe0f',
                'failure': '\u274c',
                'error': '\u274c',
            }
            ssl_icon = status_icons.get(ssl.get('health_status'), '\u2753')
            status_label = ssl.get('health_status', 'unknown').upper()
            print(f"  Status:      {ssl_icon} {status_label}")

            if ssl.get('days_until_expiry') is not None:
                print(f"  Expires in:  {ssl['days_until_expiry']} days")
        else:
            print("  No SSL certificate found")

        # Next steps
        if result.get('next_steps'):
            print(f"\n{'-'*60}")
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  \u2022 {step}")

    @staticmethod
    def _render_domain_dns_records(result: dict) -> None:
        """Render DNS records."""
        domain = result['domain']
        records = result.get('records', {})

        if result.get('error'):
            print(f"\nError: {result['error']}")
            return

        print(f"\nDNS Records for {domain}:\n")

        # Order: NS, A, AAAA, MX, TXT, CNAME, SOA
        record_order = ['ns', 'a', 'aaaa', 'mx', 'txt', 'cname', 'soa']

        for record_type in record_order:
            values = records.get(record_type, [])
            if values:
                print(f"{record_type.upper()} Records:")
                for value in values:
                    print(f"  \u2022 {value}")
                print()

        # Next steps
        if result.get('next_steps'):
            print(f"{'-'*60}")
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  \u2022 {step}")

    @staticmethod
    def _render_domain_whois(result: dict) -> None:
        """Render WHOIS information."""
        domain = result['domain']

        print(f"\nWHOIS Information for {domain}:\n")

        if result.get('error'):
            print(f"Error: {result['error']}\n")

            if result.get('next_steps'):
                print("Next Steps:")
                for step in result['next_steps']:
                    print(f"  \u2022 {step}")
        else:
            # TODO: Implement when python-whois is integrated
            print("  [WHOIS data would display here]")

    @staticmethod
    def _render_domain_ssl_status(result: dict) -> None:
        """Render SSL certificate status."""
        domain = result['domain']

        print(f"\nSSL Certificate Status for {domain}:\n")

        if result.get('error'):
            print(f"Error: {result['error']}\n")
        else:
            ssl_check = result.get('ssl_check', {})

            # Show status
            status = ssl_check.get('status', 'unknown')
            status_icons = {
                'pass': '\u2705',
                'warning': '\u26a0\ufe0f',
                'failure': '\u274c',
            }
            icon = status_icons.get(status, '\u2753')
            print(f"Status: {icon} {status.upper()}\n")

            # Show certificate info
            cert = ssl_check.get('certificate', {})
            if cert:
                print(f"Certificate: {cert.get('common_name', 'Unknown')}")
                print(f"  Issuer:  {cert.get('issuer_name', 'Unknown')}")
                print(f"  Expires: {cert.get('not_after', 'Unknown')[:10]} ({cert.get('days_until_expiry', '?')} days)")
                print()

            # Show check summary
            summary = ssl_check.get('summary', {})
            if summary:
                print(f"Checks: {summary.get('passed', 0)}/{summary.get('total', 0)} passed")
                if summary.get('warnings', 0) > 0:
                    print(f"  \u26a0\ufe0f  {summary['warnings']} warnings")
                if summary.get('failures', 0) > 0:
                    print(f"  \u274c {summary['failures']} failures")
                print()

        # Next steps
        if result.get('next_steps'):
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  \u2022 {step}")

    @staticmethod
    def _render_domain_registrar(result: dict) -> None:
        """Render registrar information."""
        domain = result['domain']

        print(f"\nRegistrar Information for {domain}:\n")

        nameservers = result.get('nameservers', [])
        if nameservers:
            print("Nameservers:")
            for ns in nameservers:
                print(f"  \u2022 {ns}")
            print()

        if result.get('note'):
            print(f"Note: {result['note']}\n")

        # Next steps
        if result.get('next_steps'):
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  \u2022 {step}")

    @staticmethod
    def _render_domain_health_check(result: dict) -> None:
        """Render domain health check results."""
        domain = result['domain']
        checks = result.get('checks', [])
        summary = result['summary']
        status = result['status']

        # Header
        status_icons = {
            'pass': '\u2705',
            'warning': '\u26a0\ufe0f',
            'failure': '\u274c',
        }
        status_icon = status_icons.get(status, '\u2753')

        print(f"\n{'='*60}")
        print(f"Domain Health Check: {domain}")
        print(f"{'='*60}\n")

        print(f"Status: {status_icon} {status.upper()}\n")

        # Summary
        print(f"Summary: {summary['passed']}/{summary['total']} checks passed")
        if summary['warnings'] > 0:
            print(f"  \u26a0\ufe0f  {summary['warnings']} warnings")
        if summary['failures'] > 0:
            print(f"  \u274c {summary['failures']} failures")
        print()

        # Group checks by status
        failures = [c for c in checks if c['status'] == 'failure']
        warnings = [c for c in checks if c['status'] == 'warning']
        passes = [c for c in checks if c['status'] == 'pass']

        # Show failures first
        if failures:
            print("\u274c Failures:")
            for check in failures:
                print(f"  \u2022 {check['name']}: {check['message']}")
            print()

        # Then warnings
        if warnings:
            print("\u26a0\ufe0f  Warnings:")
            for check in warnings:
                print(f"  \u2022 {check['name']}: {check['message']}")
            print()

        # Finally passes (only if no failures/warnings)
        if passes and not failures and not warnings:
            print("\u2705 All Checks Passed:")
            for check in passes:
                print(f"  \u2022 {check['name']}: {check['message']}")
            print()

        # Next steps
        if result.get('next_steps'):
            print(f"{'-'*60}")
            print("Remediation Steps:")
            for step in result['next_steps']:
                print(f"  \u2022 {step}")
            print()

        print(f"Exit code: {result['exit_code']}")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly error messages.

        Args:
            error: Exception to render
        """
        error_msg = str(error)

        if 'dnspython' in error_msg:
            print("Error: dnspython is not installed", file=sys.stderr)
            print("", file=sys.stderr)
            print("Install with: pip install dnspython", file=sys.stderr)
        elif 'Domain URI requires' in error_msg:
            print(f"Error: {error_msg}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Usage: reveal domain://example.com", file=sys.stderr)
        else:
            print(f"Error: {error}", file=sys.stderr)
