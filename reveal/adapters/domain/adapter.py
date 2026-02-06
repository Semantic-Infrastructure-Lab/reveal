"""Domain adapter for DNS, whois, and domain validation (domain://)."""

from typing import Dict, Any, Optional
from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from .dns import (
    get_dns_records, get_dns_summary,
    check_dns_resolution, check_nameserver_response, check_dns_propagation
)
from .renderer import DomainRenderer


@register_adapter('domain')
@register_renderer(DomainRenderer)
class DomainAdapter(ResourceAdapter):
    """Adapter for inspecting domain registration, DNS, and validation.

    Progressive disclosure pattern for domain inspection.

    Usage:
        reveal domain://example.com              # Overview (registrar, DNS, SSL status)
        reveal domain://example.com/dns          # DNS records
        reveal domain://example.com/whois        # WHOIS data
        reveal domain://example.com/ssl          # SSL status (delegates to ssl://)
        reveal domain://example.com --check      # Health checks (DNS propagation, SSL, expiry)

    Elements:
        dns: DNS records (A, AAAA, MX, TXT, NS, CNAME, SOA)
        whois: WHOIS registration data (TODO: requires python-whois)
        ssl: SSL certificate status (delegates to ssl:// adapter)
        registrar: Registrar and nameserver information
    """

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for domain:// adapter.

        Help data loaded from reveal/adapters/help_data/domain.yaml
        to reduce function complexity.
        """
        return load_help_data('domain') or {}

    def __init__(self, connection_string: str = "", **kwargs):
        """Initialize Domain adapter with domain name.

        Args:
            connection_string: domain://example.com[/element]

        Raises:
            TypeError: If no connection string provided (allows generic handler to try next pattern)
            ValueError: If connection string is invalid
        """
        # No-arg initialization should raise TypeError, not ValueError
        # This lets the generic handler try the next pattern
        if not connection_string:
            raise TypeError("DomainAdapter requires a domain name")

        self.connection_string = connection_string
        self.domain = None
        self.element = kwargs.get('element')

        self._parse_connection_string(connection_string)

    def _parse_connection_string(self, uri: str) -> None:
        """Parse domain:// URI into components.

        Args:
            uri: Connection URI (domain://example.com[/element])
        """
        if uri == "domain://":
            raise ValueError("Domain URI requires a domain name: domain://example.com")

        # Remove domain:// prefix
        if uri.startswith("domain://"):
            uri = uri[9:]

        # Split domain from element
        parts = uri.split('/', 1)
        self.domain = parts[0]
        self.element = parts[1] if len(parts) > 1 else self.element

        if not self.domain:
            raise ValueError("Domain URI requires a domain name: domain://example.com")

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get domain overview.

        Returns:
            Dict containing domain summary (~200 tokens)
        """
        # If element was specified in URI, delegate to get_element
        if self.element:
            element_data = self.get_element(self.element)
            if element_data:
                return element_data
            raise ValueError(f"Unknown element: {self.element}")

        # Get DNS summary
        dns_summary = get_dns_summary(self.domain)

        # Get SSL summary (delegate to ssl:// adapter)
        ssl_summary = self._get_ssl_summary()

        # Build next steps
        next_steps = [
            f"DNS details: reveal domain://{self.domain}/dns",
            f"SSL details: reveal ssl://{self.domain}",
            f"Health check: reveal domain://{self.domain} --check",
        ]

        return {
            'type': 'domain_overview',
            'domain': self.domain,
            'dns': {
                'nameservers': dns_summary.get('nameservers', []),
                'a_records': dns_summary.get('a_records', []),
                'has_mx': dns_summary.get('has_mx', False),
                'error': dns_summary.get('error'),
            },
            'ssl': ssl_summary,
            'next_steps': next_steps,
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific domain element.

        Args:
            element_name: Element to retrieve (dns, whois, ssl, registrar)

        Returns:
            Element data or None if not found
        """
        element_handlers = {
            'dns': self._get_dns_records,
            'whois': self._get_whois_info,
            'ssl': self._get_ssl_status,
            'registrar': self._get_registrar_info,
        }

        handler = element_handlers.get(element_name)
        if handler:
            return handler()

        return None

    def _get_dns_records(self) -> Dict[str, Any]:
        """Get all DNS records."""
        try:
            records = get_dns_records(self.domain)
            return {
                'type': 'domain_dns_records',
                'domain': self.domain,
                'records': records,
                'next_steps': [
                    f"Check DNS propagation: reveal domain://{self.domain} --check",
                    f"View SSL certificate: reveal ssl://{self.domain}",
                ],
            }
        except ImportError as e:
            return {
                'type': 'domain_dns_records',
                'domain': self.domain,
                'error': str(e),
                'records': {},
            }

    def _get_whois_info(self) -> Dict[str, Any]:
        """Get WHOIS information (TODO: requires python-whois)."""
        return {
            'type': 'domain_whois',
            'domain': self.domain,
            'error': 'WHOIS lookup not yet implemented (requires python-whois)',
            'next_steps': [
                'Install python-whois: pip install python-whois',
                f"View DNS instead: reveal domain://{self.domain}/dns",
            ],
        }

    def _get_ssl_status(self) -> Dict[str, Any]:
        """Get SSL certificate status (delegates to ssl:// adapter)."""
        from ..ssl.certificate import check_ssl_health

        try:
            ssl_check = check_ssl_health(self.domain, 443)
            return {
                'type': 'domain_ssl_status',
                'domain': self.domain,
                'ssl_check': ssl_check,
                'next_steps': [
                    f"Full SSL details: reveal ssl://{self.domain}",
                    f"Advanced SSL checks: reveal ssl://{self.domain} --check-advanced",
                ],
            }
        except Exception as e:
            return {
                'type': 'domain_ssl_status',
                'domain': self.domain,
                'error': str(e),
            }

    def _get_registrar_info(self) -> Dict[str, Any]:
        """Get registrar and nameserver information."""
        dns_summary = get_dns_summary(self.domain)

        return {
            'type': 'domain_registrar',
            'domain': self.domain,
            'nameservers': dns_summary.get('nameservers', []),
            'note': 'Full registrar info requires WHOIS lookup (not yet implemented)',
            'next_steps': [
                f"View DNS records: reveal domain://{self.domain}/dns",
            ],
        }

    def _get_ssl_summary(self) -> Dict[str, Any]:
        """Get summarized SSL information."""
        from ..ssl.certificate import check_ssl_health

        try:
            ssl_check = check_ssl_health(self.domain, 443)
            cert = ssl_check.get('certificate', {})

            return {
                'has_certificate': ssl_check['status'] != 'failure',
                'days_until_expiry': cert.get('days_until_expiry'),
                'health_status': ssl_check['status'],
                'error': ssl_check.get('error'),
            }
        except Exception as e:
            return {
                'has_certificate': False,
                'days_until_expiry': None,
                'health_status': 'error',
                'error': str(e),
            }

    def check(self, **kwargs) -> Dict[str, Any]:
        """Run domain health checks.

        Args:
            **kwargs: Check options

        Returns:
            Health check result dict
        """
        checks = []

        # Check 1: DNS resolution
        checks.append(check_dns_resolution(self.domain))

        # Check 2: Nameserver response
        checks.append(check_nameserver_response(self.domain))

        # Check 3: DNS propagation
        checks.append(check_dns_propagation(self.domain))

        # Check 4: SSL certificate (delegate to ssl:// adapter)
        from ..ssl.certificate import check_ssl_health
        try:
            ssl_check = check_ssl_health(self.domain, 443)
            # Add SSL expiry as a domain check
            if 'certificate' in ssl_check:
                cert = ssl_check['certificate']
                days = cert.get('days_until_expiry', 0)
                if days < 0:
                    status = 'failure'
                    message = f'SSL certificate expired {abs(days)} days ago'
                elif days < 7:
                    status = 'failure'
                    message = f'SSL certificate expires in {days} days (critical)'
                elif days < 30:
                    status = 'warning'
                    message = f'SSL certificate expires in {days} days'
                else:
                    status = 'pass'
                    message = f'SSL certificate valid for {days} days'

                checks.append({
                    'name': 'ssl_certificate',
                    'status': status,
                    'value': f'{days} days',
                    'threshold': '30+ days',
                    'message': message,
                    'severity': 'high',
                })
            else:
                checks.append({
                    'name': 'ssl_certificate',
                    'status': 'failure',
                    'value': 'No certificate',
                    'threshold': 'Valid certificate',
                    'message': ssl_check.get('error', 'No SSL certificate found'),
                    'severity': 'high',
                })
        except Exception as e:
            checks.append({
                'name': 'ssl_certificate',
                'status': 'failure',
                'value': 'Check failed',
                'threshold': 'Valid certificate',
                'message': f'SSL check failed: {e}',
                'severity': 'high',
            })

        # Compute overall status
        statuses = [c['status'] for c in checks]
        if 'failure' in statuses:
            overall_status = 'failure'
        elif 'warning' in statuses:
            overall_status = 'warning'
        else:
            overall_status = 'pass'

        # Summary
        passed = sum(1 for c in checks if c['status'] == 'pass')
        warnings = sum(1 for c in checks if c['status'] == 'warning')
        failures = sum(1 for c in checks if c['status'] == 'failure')

        # Generate next steps based on failures
        next_steps = []
        if any(c['name'] == 'dns_resolution' and c['status'] == 'failure' for c in checks):
            next_steps.append("Check DNS configuration with registrar")
            next_steps.append(f"View DNS records: reveal domain://{self.domain}/dns")

        if any(c['name'] == 'dns_propagation' and c['status'] == 'warning' for c in checks):
            next_steps.append("DNS propagation in progress - wait and check again")

        if any(c['name'] == 'ssl_certificate' and c['status'] in ('failure', 'warning') for c in checks):
            next_steps.append(f"Inspect SSL certificate: reveal ssl://{self.domain} --check-advanced")

        if not next_steps:
            next_steps.append(f"View DNS records: reveal domain://{self.domain}/dns")
            next_steps.append(f"View SSL certificate: reveal ssl://{self.domain}")

        return {
            'type': 'domain_health_check',
            'domain': self.domain,
            'status': overall_status,
            'checks': checks,
            'summary': {
                'total': len(checks),
                'passed': passed,
                'warnings': warnings,
                'failures': failures,
            },
            'next_steps': next_steps,
            'exit_code': 0 if overall_status == 'pass' else (1 if overall_status == 'warning' else 2),
        }
