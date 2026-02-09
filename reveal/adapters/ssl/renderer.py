"""SSL certificate result rendering for CLI output."""

import sys

from reveal.rendering import TypeDispatchRenderer


class SSLRenderer(TypeDispatchRenderer):
    """Renderer for SSL adapter results.

    Uses TypeDispatchRenderer for automatic routing to _render_{type}() methods.
    """

    # Type dispatch methods (called automatically based on result['type'])

    @staticmethod
    def _render_ssl_certificate(result: dict) -> None:
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
            print()

        # Available elements (Phase 5: Element Discovery)
        if result.get('available_elements'):
            print("📍 Available elements:")
            for elem in result['available_elements']:
                name = elem['name']
                desc = elem['description']
                print(f"  /{name:<12} {desc}")
            print()
            # Show example usage hint with first element
            if result['available_elements']:
                example = result['available_elements'][0]['example']
                print(f"💡 Try: {example}")

    @staticmethod
    def _render_ssl_san(result: dict) -> None:
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
    def _render_ssl_chain(result: dict) -> None:
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
    def _render_ssl_issuer(result: dict) -> None:
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
    def _render_ssl_subject(result: dict) -> None:
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
    def _render_ssl_dates(result: dict) -> None:
        """Render validity dates."""
        print(f"SSL Validity for {result['host']}")
        print()
        print(f"Not Before: {result['not_before']}")
        print(f"Not After: {result['not_after']}")
        print(f"Days Until Expiry: {result['days_until_expiry']}")
        print(f"Expired: {'Yes' if result['is_expired'] else 'No'}")

    @staticmethod
    def _render_ssl_nginx_domains(result: dict) -> None:
        """Render SSL domains extracted from nginx config."""
        print(f"SSL Domains from Nginx Config")
        print(f"Source: {result['source']}")
        print(f"Files Processed: {result['files_processed']}")
        print(f"Domains Found: {result['domain_count']}")
        print()

        if result['domains']:
            print("Domains:")
            for domain in result['domains']:
                print(f"  {domain}")
            print()
            print("To check SSL certificates:")
            print(f"  reveal ssl://nginx://{result['source']} --check")
        else:
            print("No SSL-enabled domains found in config.")

    @classmethod
    def render_check(cls, result: dict, format: str = 'text',
                     only_failures: bool = False, summary: bool = False,
                     expiring_within: str = None) -> None:
        """Render SSL health check results.

        Args:
            result: Check result dictionary from SSLAdapter.check()
            format: Output format ('text' or 'json')
            only_failures: Only show failed/warning results
            summary: Show aggregated summary only
            expiring_within: Filter to certs expiring within N days
        """
        # Parse expiring_within if provided
        expiring_days = None
        if expiring_within:
            try:
                expiring_days = int(expiring_within.rstrip('d'))
            except ValueError:
                pass

        # Apply filters to result for JSON output
        if cls.should_render_json(format):
            filtered = cls._filter_results(result, only_failures, expiring_days)
            cls.render_json(filtered)
            return

        result_type = result.get('type', 'ssl_check')

        if result_type == 'ssl_batch_check':
            cls._render_ssl_batch_check(result, only_failures, summary, expiring_days)
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
        infos = [c for c in checks if c['status'] == 'info']

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

        if infos:
            print("\u2139\ufe0f  Additional Information:")
            for check in infos:
                print(f"  \u2022 {check['name']}: {check['message']}")
            print()

        # Show next steps if available
        if result.get('next_steps'):
            print("\nNext Steps:")
            for step in result['next_steps']:
                print(f"  • {step}")

        print(f"\nExit code: {result['exit_code']}")

    @staticmethod
    def _filter_results(result: dict, only_failures: bool = False,
                        expiring_days: int = None) -> dict:
        """Filter check results based on criteria.

        Args:
            result: Original result dict
            only_failures: Only include failed/warning results
            expiring_days: Only include certs expiring within N days

        Returns:
            Filtered result dict (copy)
        """
        if result.get('type') != 'ssl_batch_check':
            return result

        filtered = result.copy()
        results = result.get('results', [])

        # Apply filters
        if only_failures:
            results = [r for r in results if r['status'] in ('failure', 'warning')]

        if expiring_days is not None:
            def within_days(r):
                days = r.get('certificate', {}).get('days_until_expiry')
                if days is None:
                    return r['status'] == 'failure'  # Include errors
                return days <= expiring_days
            results = [r for r in results if within_days(r)]

        filtered['results'] = results
        return filtered

    @staticmethod
    def _filter_batch_results(all_results: list, only_failures: bool,
                               expiring_days: int = None) -> list:
        """Apply filters to batch check results.

        Args:
            all_results: List of check results
            only_failures: Only include failed/warning results
            expiring_days: Only include certs expiring within N days

        Returns:
            Filtered list of results
        """
        filtered = all_results

        if expiring_days is not None:
            def within_days(r):
                days = r.get('certificate', {}).get('days_until_expiry')
                if days is None:
                    return r['status'] == 'failure'
                return days <= expiring_days
            filtered = [r for r in filtered if within_days(r)]

        if only_failures:
            filtered = [r for r in filtered if r['status'] in ('failure', 'warning')]

        return filtered

    @staticmethod
    def _group_results_by_status(all_results: list) -> tuple:
        """Group results into failures, warnings, and passes.

        Args:
            all_results: List of check results

        Returns:
            Tuple of (failures, warnings, passes)
        """
        failures = [r for r in all_results if r['status'] == 'failure']
        warnings = [r for r in all_results if r['status'] == 'warning']
        passes = [r for r in all_results if r['status'] == 'pass']
        return failures, warnings, passes

    @staticmethod
    def _render_batch_summary_mode(result: dict, passes: list, warnings: list,
                                    failures: list, expiring_days: int = None) -> None:
        """Render summary mode output (aggregated counts only).

        Args:
            result: Batch check result dict
            passes: List of passed results
            warnings: List of warning results
            failures: List of failed results
            expiring_days: Filter value if applied
        """
        original_summary = result.get('summary', {})
        print(f"\nSSL Audit: {result.get('domains_checked', len(result.get('results', [])))} domains")
        print(f"✅ Healthy (>30d): {original_summary.get('passed', len(passes))}")
        print(f"⚠️  Warning (<30d): {original_summary.get('warnings', len(warnings))}")
        print(f"❌ Failed/Expired: {original_summary.get('failures', len(failures))}")
        if expiring_days:
            print(f"\n(Filtered to ≤{expiring_days} days)")
        print(f"\nExit code: {result.get('exit_code', 0)}")

    @staticmethod
    def _render_batch_header(source: str, status: str, result: dict,
                             expiring_days: int = None, only_failures: bool = False) -> None:
        """Render batch check header with status and summary.

        Args:
            source: Source identifier (e.g., 'stdin')
            status: Overall status ('pass', 'warning', 'failure')
            result: Batch check result dict
            expiring_days: Filter value if applied
            only_failures: Whether filtering to failures only
        """
        status_icon = '\u2705' if status == 'pass' else '\u26a0\ufe0f' if status == 'warning' else '\u274c'
        print(f"\nSSL Batch Check: {source}")
        print(f"Status: {status_icon} {status.upper()}")

        summary = result['summary']
        print(f"\nDomains Checked: {result['domains_checked']}")
        print(f"Summary: {summary['passed']} passed, "
              f"{summary['warnings']} warnings, {summary['failures']} failures")

        if expiring_days:
            print(f"Filter: showing certs expiring within {expiring_days} days")
        if only_failures:
            print("Filter: showing failures and warnings only")
        print()

    @staticmethod
    def _render_failed_domains(failures: list) -> None:
        """Render failed domains section.

        Args:
            failures: List of failed check results
        """
        if not failures:
            return

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

    @staticmethod
    def _render_warning_domains(warnings: list) -> None:
        """Render warning domains section.

        Args:
            warnings: List of warning check results
        """
        if not warnings:
            return

        print("\u26a0\ufe0f  Warnings:")
        for r in warnings:
            host = r['host']
            days = r.get('certificate', {}).get('days_until_expiry', '?')
            print(f"  {host}: {days} days")
        print()

    @staticmethod
    def _render_healthy_domains(passes: list, only_failures: bool) -> None:
        """Render healthy domains section (if not filtering to failures only).

        Args:
            passes: List of passed check results
            only_failures: Whether filtering to failures only
        """
        if not passes or only_failures:
            return

        print("\u2705 Healthy:")
        for r in passes:
            host = r['host']
            days = r.get('certificate', {}).get('days_until_expiry', '?')
            print(f"  {host}: {days} days")
        print()

    @staticmethod
    def _render_next_steps(result: dict) -> None:
        """Render next steps section if available.

        Args:
            result: Batch check result dict
        """
        if not result.get('next_steps'):
            return

        print("Next Steps:")
        for step in result['next_steps']:
            print(f"  • {step}")
        print()

    @staticmethod
    def _render_ssl_batch_check(result: dict, only_failures: bool = False,
                                 summary_only: bool = False,
                                 expiring_days: int = None) -> None:
        """Render batch SSL check results.

        Args:
            result: Batch check result dict
            only_failures: Only show failed/warning results
            summary_only: Show aggregated summary without details
            expiring_days: Filter to certs expiring within N days
        """
        status = result['status']
        source = result.get('source', 'stdin')
        all_results = result.get('results', [])

        # Apply filters
        all_results = SSLRenderer._filter_batch_results(all_results, only_failures, expiring_days)

        # Group by status
        failures, warnings, passes = SSLRenderer._group_results_by_status(all_results)

        # Summary mode - aggregated counts only
        if summary_only:
            SSLRenderer._render_batch_summary_mode(result, passes, warnings, failures, expiring_days)
            return

        # Full output
        SSLRenderer._render_batch_header(source, status, result, expiring_days, only_failures)
        SSLRenderer._render_failed_domains(failures)
        SSLRenderer._render_warning_domains(warnings)
        SSLRenderer._render_healthy_domains(passes, only_failures)
        SSLRenderer._render_next_steps(result)

        print(f"Exit code: {result['exit_code']}")

    @staticmethod
    def _render_ssl_nginx_validation(result: dict) -> None:
        """Render nginx SSL validation results."""
        if 'error' in result:
            print(f"\nError: {result['error']}")
            return

        source = result.get('source', 'unknown')
        status = result['status']
        status_icon = '\u2705' if status == 'pass' else '\u274c'

        print(f"\nSSL/Nginx Configuration Validation: {source}")
        print(f"Status: {status_icon} {status.upper()}")

        summary = result['summary']
        print(f"\nDomains Validated: {result['domains_validated']}")
        print(f"Summary: {summary['passed']} passed, {summary['failed']} failed")
        print()

        # Show failures
        failures = [r for r in result['results'] if r['status'] == 'failure']
        if failures:
            print("\u274c Failed Validations:")
            for r in failures:
                print(f"\n  Domain: {r['domain']}")
                for issue in r['issues']:
                    severity_icon = '\u274c' if issue['severity'] == 'critical' else '\u26a0\ufe0f'
                    print(f"    {severity_icon} {issue['type']}: {issue['message']}")
            print()

        # Show passes if no failures
        if not failures:
            passes = [r for r in result['results'] if r['status'] == 'pass']
            print("\u2705 All Validations Passed:")
            for r in passes:
                print(f"  • {r['domain']}")
            print()

        # Show next steps
        if result.get('next_steps'):
            print("Remediation Steps:")
            for step in result['next_steps']:
                print(f"  • {step}")
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
