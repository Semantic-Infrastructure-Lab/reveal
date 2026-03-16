"""Domain result rendering for CLI output."""

import sys

from reveal.rendering import TypeDispatchRenderer


class DomainRenderer(TypeDispatchRenderer):
    """Renderer for Domain adapter results.

    Uses TypeDispatchRenderer for automatic routing to _render_{type}() methods.
    """

    # Type dispatch methods (called automatically based on result['type'])

    @staticmethod
    def _print_domain_header(domain: str) -> None:
        """Print domain header."""
        print(f"\n{'='*60}")
        print(f"Domain: {domain}")
        print(f"{'='*60}\n")

    @staticmethod
    def _print_dns_section(dns: dict) -> None:
        """Print DNS configuration section."""
        print("DNS Configuration:")
        if dns.get('error'):
            print(f"  Error: {dns['error']}")
            return

        # Nameservers
        ns_list = dns.get('nameservers', [])
        if ns_list:
            ns_display = ', '.join(ns_list[:2])
            if len(ns_list) > 2:
                ns_display += f" (+{len(ns_list) - 2} more)"
            print(f"  Nameservers: {ns_display}")
        else:
            print("  Nameservers: None")

        # A Records
        a_records = dns.get('a_records', [])
        print(f"  A Records:   {', '.join(a_records) if a_records else 'None'}")

        # MX Records
        mx_icon = '\u2705' if dns.get('has_mx') else '\u274c'
        print(f"  MX Records:  {mx_icon} {'Configured' if dns.get('has_mx') else 'None'}")

    @staticmethod
    def _print_ssl_section(ssl: dict) -> None:
        """Print SSL status section."""
        print("\nSSL Status:")
        if ssl.get('error'):
            print(f"  Error: {ssl['error']}")
        elif ssl.get('has_certificate'):
            # Use shared status icons
            ssl_icon = DomainRenderer._STATUS_ICONS.get(str(ssl.get('health_status', 'unknown')), '\u2753')
            status_label = ssl.get('health_status', 'unknown').upper()
            print(f"  Status:      {ssl_icon} {status_label}")

            if ssl.get('days_until_expiry') is not None:
                print(f"  Expires in:  {ssl['days_until_expiry']} days")
        else:
            print("  No SSL certificate found")

    @staticmethod
    def _print_available_elements(elements: list) -> None:
        """Print available elements section."""
        if not elements:
            return

        print(f"\n{'-'*60}")
        print("📍 Available elements:")
        for elem in elements:
            name = elem['name']
            desc = elem['description']
            print(f"  /{name:<12} {desc}")
        print()

        # Show example usage hint
        example = elements[0]['example']
        print(f"💡 Try: {example}")

    @staticmethod
    def _print_whois_section(whois: dict) -> None:
        """Print WHOIS summary section."""
        print("\nRegistration:")
        if not whois.get('available'):
            err = whois.get('error', 'WHOIS unavailable')
            print(f"  {err}")
            return
        registrar = whois.get('registrar') or 'Unknown'
        expiry = whois.get('expiration_date') or 'Unknown'
        created = whois.get('creation_date') or 'Unknown'
        print(f"  Registrar:  {registrar}")
        print(f"  Created:    {created}")
        print(f"  Expires:    {expiry}")

    @staticmethod
    def _render_domain_overview(result: dict) -> None:
        """Render domain overview."""
        DomainRenderer._print_domain_header(result['domain'])
        DomainRenderer._print_dns_section(result['dns'])
        DomainRenderer._print_ssl_section(result['ssl'])
        if result.get('whois'):
            DomainRenderer._print_whois_section(result['whois'])

        # Use existing remediation helper if available
        if result.get('next_steps'):
            print(f"\n{'-'*60}")
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  \u2022 {step}")

        DomainRenderer._print_available_elements(result.get('available_elements', []))

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
            print(f"  Error: {result['error']}\n")
            if result.get('next_steps'):
                print("Next Steps:")
                for step in result['next_steps']:
                    print(f"  \u2022 {step}")
            return

        # Registrar
        registrar = result.get('registrar') or 'Unknown'
        print(f"  Registrar:    {registrar}")

        # Dates
        creation = result.get('creation_date') or 'Unknown'
        expiry = result.get('expiration_date') or 'Unknown'
        print(f"  Created:      {creation}")
        print(f"  Expires:      {expiry}")

        # Nameservers
        name_servers = result.get('name_servers', [])
        if name_servers:
            print(f"  Name Servers: {name_servers[0]}")
            for ns in name_servers[1:]:
                print(f"                {ns}")
        else:
            print("  Name Servers: None")

        # Status
        status_list = result.get('status', [])
        if status_list:
            # Strip URL suffix from status strings for readability
            status_display = status_list[0].split(' ')[0] if status_list else 'Unknown'
            print(f"  Status:       {status_display}")

        # DNSSEC
        dnssec = result.get('dnssec') or 'Unknown'
        print(f"  DNSSEC:       {dnssec}")

        # Next steps
        if result.get('next_steps'):
            print(f"\n{'-'*60}")
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  \u2022 {step}")

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

        # WHOIS-sourced fields (present when python-whois is installed)
        if result.get('registrar'):
            print(f"  Registrar:  {result['registrar']}")
        if result.get('creation_date'):
            print(f"  Created:    {result['creation_date']}")
        if result.get('expiration_date'):
            print(f"  Expires:    {result['expiration_date']}")
        if result.get('registrar') or result.get('creation_date'):
            print()

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

    # Status icons for health checks
    _STATUS_ICONS = {
        'pass': '\u2705',
        'warning': '\u26a0\ufe0f',
        'failure': '\u274c',
    }

    @staticmethod
    def _print_health_check_header(domain: str, status: str) -> None:
        """Print health check header with status."""
        status_icon = DomainRenderer._STATUS_ICONS.get(status, '\u2753')
        print(f"\n{'='*60}")
        print(f"Domain Health Check: {domain}")
        print(f"{'='*60}\n")
        print(f"Status: {status_icon} {status.upper()}\n")

    @staticmethod
    def _print_health_check_summary(summary: dict) -> None:
        """Print health check summary statistics."""
        print(f"Summary: {summary['passed']}/{summary['total']} checks passed")
        if summary['warnings'] > 0:
            print(f"  \u26a0\ufe0f  {summary['warnings']} warnings")
        if summary['failures'] > 0:
            print(f"  \u274c {summary['failures']} failures")
        print()

    @staticmethod
    def _group_checks_by_status(checks: list) -> dict:
        """Group checks by their status."""
        return {
            'failures': [c for c in checks if c['status'] == 'failure'],
            'warnings': [c for c in checks if c['status'] == 'warning'],
            'passes': [c for c in checks if c['status'] == 'pass'],
        }

    @staticmethod
    def _print_check_group(title: str, icon: str, checks: list) -> None:
        """Print a group of checks with icon and title."""
        if checks:
            print(f"{icon} {title}:")
            for check in checks:
                print(f"  \u2022 {check['name']}: {check['message']}")
            print()

    @staticmethod
    def _print_remediation_steps(steps: list) -> None:
        """Print remediation steps."""
        if steps:
            print(f"{'-'*60}")
            print("Remediation Steps:")
            for step in steps:
                print(f"  \u2022 {step}")
            print()

    @staticmethod
    def _render_domain_health_check(result: dict) -> None:
        """Render domain health check results."""
        # Extract data
        domain = result['domain']
        checks = result.get('checks', [])
        summary = result['summary']
        status = result['status']

        # Print header and summary
        DomainRenderer._print_health_check_header(domain, status)
        DomainRenderer._print_health_check_summary(summary)

        # Group and print checks
        grouped = DomainRenderer._group_checks_by_status(checks)
        DomainRenderer._print_check_group("Failures", "\u274c", grouped['failures'])
        DomainRenderer._print_check_group("Warnings", "\u26a0\ufe0f", grouped['warnings'])

        # Only show passes if no failures/warnings
        if grouped['passes'] and not grouped['failures'] and not grouped['warnings']:
            DomainRenderer._print_check_group("All Checks Passed", "\u2705", grouped['passes'])

        # Print remediation and exit code
        DomainRenderer._print_remediation_steps(result.get('next_steps', []))
        print(f"Exit code: {result['exit_code']}")

    @staticmethod
    def _render_domain_email_dns(result: dict) -> None:
        """Render email DNS deliverability check results."""
        domain = result['domain']
        status = result.get('status', 'unknown')
        status_icon = DomainRenderer._STATUS_ICONS.get(status, '\u2753')

        print(f"\nEmail DNS for {domain}:\n")
        print(f"Status: {status_icon} {status.upper()}\n")

        checks = result.get('checks', [])
        for check in checks:
            icon = DomainRenderer._STATUS_ICONS.get(check['status'], '\u2753')
            print(f"  {icon} {check['name']}: {check['message']}")
            details = check.get('details', {})
            if details:
                if check['name'] == 'mx_records':
                    for mx in details.get('mx_records', [])[:3]:
                        print(f"      {mx}")
                elif check['name'] == 'spf_record':
                    spf = details.get('spf_record', '')
                    print(f"      {spf[:70]}{'...' if len(spf) > 70 else ''}")
                elif check['name'] == 'dmarc_record':
                    dmarc = details.get('dmarc_record', '')
                    print(f"      {dmarc[:70]}{'...' if len(dmarc) > 70 else ''}")

        if result.get('next_steps'):
            print(f"\n{'-'*60}")
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  \u2022 {step}")

    @staticmethod
    def _render_domain_http_chain(result: dict) -> None:
        """Render HTTP redirect chain inspection."""
        domain = result['domain']
        redirects = result.get('redirects_to_https', False)
        redirect_icon = '\u2705' if redirects else '\u26a0\ufe0f'

        print(f"\nHTTP Redirect Chain for {domain}:\n")
        print(f"HTTP → HTTPS redirect: {redirect_icon} {'Yes' if redirects else 'No'}\n")

        http_chain = result.get('http_chain', [])
        if http_chain:
            print("HTTP (port 80):")
            for hop in http_chain:
                print(f"  \u2192 {hop}")
            print()

        https_chain = result.get('https_chain', [])
        if https_chain:
            print("HTTPS (port 443):")
            for hop in https_chain:
                print(f"  \u2192 {hop}")
            print()

        redirect_check = result.get('redirect_check', {})
        if redirect_check and redirect_check.get('status') != 'pass':
            icon = DomainRenderer._STATUS_ICONS.get(redirect_check['status'], '\u2753')
            print(f"{icon} {redirect_check['message']}")
            print()

        if result.get('next_steps'):
            print(f"{'-'*60}")
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  \u2022 {step}")

    @staticmethod
    def _render_domain_ns_audit(result: dict) -> None:
        """Render NS authority cross-check results."""
        domain = result.get('domain', '')
        status = result.get('status', 'unknown')
        summary = result.get('summary', '')
        registered = result.get('registered_nameservers', [])
        servers = result.get('servers', [])
        orphaned = result.get('orphaned', [])
        consensus = result.get('consensus_ns_records', [])

        STATUS_ICONS = {'ok': '✅', 'warning': '⚠️', 'critical': '❌', 'error': '❌', 'skipped': '⏭️'}
        icon = STATUS_ICONS.get(status, '❓')

        print(f"\nNS Authority Audit: {domain}")
        print(f"{'─' * (22 + len(domain))}")
        print(f"\n{icon} {summary}\n")

        if servers:
            print(f"Registered NS ({len(registered)}):")
            for server in servers:
                ns = server.get('nameserver', '?')
                ip = server.get('ip') or 'unresolved'
                s = server.get('status', '?')
                agrees = server.get('agrees_with_consensus', False)
                ns_returned = server.get('ns_records', [])
                error = server.get('error')

                server_icon = '✅' if s == 'ok' and agrees else ('⚠️' if s in ('query_failed',) else '❌')
                print(f"  {server_icon} {ns}  [{ip}]")
                if error:
                    print(f"       Error: {error}")
                elif ns_returned:
                    if not agrees:
                        print(f"       NS returned: {', '.join(ns_returned)}")
                print()

        if consensus:
            print(f"Consensus NS set ({len(consensus)}):")
            for ns in consensus:
                print(f"  • {ns}")
            print()

        if orphaned:
            print(f"⚠️  Orphaned entries ({len(orphaned)}) — listed but not in consensus:")
            for ns in orphaned:
                print(f"  ✗ {ns}")
            print()

        if result.get('next_steps'):
            print(f"{'─' * 60}")
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  • {step}")

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
