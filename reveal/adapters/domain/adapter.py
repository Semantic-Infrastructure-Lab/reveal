"""Domain adapter for DNS, whois, and domain validation (domain://)."""

from typing import Dict, Any, Optional, List
from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from .dns import (
    get_dns_records, get_dns_summary,
    check_dns_resolution, check_nameserver_response, check_dns_propagation
)
from .renderer import DomainRenderer


# Helper functions for domain health checks

def _run_dns_checks(domain: str) -> List[Dict[str, Any]]:
    """Run all DNS health checks for a domain.

    Args:
        domain: Domain name to check

    Returns:
        List of DNS check results
    """
    return [
        check_dns_resolution(domain),
        check_nameserver_response(domain),
        check_dns_propagation(domain),
    ]


def _determine_ssl_status(days: int) -> tuple[str, str]:
    """Determine SSL certificate status and message based on days until expiry.

    Args:
        days: Days until SSL certificate expires

    Returns:
        Tuple of (status, message)
    """
    if days < 0:
        return 'failure', f'SSL certificate expired {abs(days)} days ago'
    elif days < 7:
        return 'failure', f'SSL certificate expires in {days} days (critical)'
    elif days < 30:
        return 'warning', f'SSL certificate expires in {days} days'
    else:
        return 'pass', f'SSL certificate valid for {days} days'


def _build_ssl_check_result(status: str, days: int, message: str) -> Dict[str, Any]:
    """Build SSL certificate check result dict.

    Args:
        status: Check status (pass, warning, failure)
        days: Days until expiry
        message: Status message

    Returns:
        SSL check result dict
    """
    return {
        'name': 'ssl_certificate',
        'status': status,
        'value': f'{days} days',
        'threshold': '30+ days',
        'message': message,
        'severity': 'high',
    }


def _build_ssl_failure_result(error_msg: str, value: str = 'Check failed') -> Dict[str, Any]:
    """Build SSL certificate failure check result.

    Args:
        error_msg: Error message
        value: Check value (default: 'Check failed')

    Returns:
        SSL failure check result dict
    """
    return {
        'name': 'ssl_certificate',
        'status': 'failure',
        'value': value,
        'threshold': 'Valid certificate',
        'message': error_msg,
        'severity': 'high',
    }


def _check_ssl_certificate(domain: str, advanced: bool = False) -> Dict[str, Any]:
    """Check SSL certificate health for a domain.

    Args:
        domain: Domain name to check
        advanced: Whether to run advanced SSL checks

    Returns:
        SSL check result dict
    """
    from ..ssl.certificate import check_ssl_health

    try:
        ssl_check = check_ssl_health(domain, 443, advanced=advanced)

        # Process certificate if available
        if 'certificate' in ssl_check:
            cert = ssl_check['certificate']
            days = cert.get('days_until_expiry', 0)
            status, message = _determine_ssl_status(days)
            return _build_ssl_check_result(status, days, message)
        else:
            error_msg = ssl_check.get('error', 'No SSL certificate found')
            return _build_ssl_failure_result(error_msg, value='No certificate')

    except Exception as e:
        return _build_ssl_failure_result(f'SSL check failed: {e}')


def _calculate_overall_status(checks: List[Dict[str, Any]]) -> str:
    """Calculate overall status from check results.

    Args:
        checks: List of check result dicts

    Returns:
        Overall status (failure, warning, or pass)
    """
    statuses = [c['status'] for c in checks]
    if 'failure' in statuses:
        return 'failure'
    elif 'warning' in statuses:
        return 'warning'
    else:
        return 'pass'


def _calculate_check_summary(checks: List[Dict[str, Any]]) -> Dict[str, int]:
    """Calculate summary counts from check results.

    Args:
        checks: List of check result dicts

    Returns:
        Summary dict with total, passed, warnings, failures counts
    """
    return {
        'total': len(checks),
        'passed': sum(1 for c in checks if c['status'] == 'pass'),
        'warnings': sum(1 for c in checks if c['status'] == 'warning'),
        'failures': sum(1 for c in checks if c['status'] == 'failure'),
    }


def _generate_domain_next_steps(checks: List[Dict[str, Any]], domain: str) -> List[str]:
    """Generate contextual next steps based on check results.

    Args:
        checks: List of check result dicts
        domain: Domain name

    Returns:
        List of next step suggestions
    """
    next_steps = []

    # DNS resolution failures
    if any(c['name'] == 'dns_resolution' and c['status'] == 'failure' for c in checks):
        next_steps.append("Check DNS configuration with registrar")
        next_steps.append(f"View DNS records: reveal domain://{domain}/dns")

    # DNS propagation warnings
    if any(c['name'] == 'dns_propagation' and c['status'] == 'warning' for c in checks):
        next_steps.append("DNS propagation in progress - wait and check again")

    # SSL certificate issues
    if any(c['name'] == 'ssl_certificate' and c['status'] in ('failure', 'warning') for c in checks):
        next_steps.append(f"Inspect SSL certificate: reveal ssl://{domain} --check-advanced")

    # Default next steps if all passed
    if not next_steps:
        next_steps.append(f"View DNS records: reveal domain://{domain}/dns")
        next_steps.append(f"View SSL certificate: reveal ssl://{domain}")

    return next_steps


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
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for domain:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'domain',
            'description': 'Domain registration, DNS, and SSL inspection with health checks',
            'uri_syntax': 'domain://<domain>[/element]',
            'query_params': {},  # No query parameters
            'elements': {
                'dns': 'DNS records (A, AAAA, MX, TXT, NS, CNAME, SOA)',
                'whois': 'WHOIS registration data (requires python-whois)',
                'ssl': 'SSL certificate status (delegates to ssl:// adapter)',
                'registrar': 'Registrar and nameserver information'
            },
            'cli_flags': [
                '--check',  # DNS propagation, SSL, expiry checks
                '--advanced',  # Advanced DNS diagnostics
                '--only-failures'  # Show only failed checks
            ],
            'supports_batch': False,
            'supports_advanced': True,
            'output_types': [
                {
                    'type': 'domain_overview',
                    'description': 'Domain overview with DNS and SSL summary',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'domain_overview'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'domain': {'type': 'string'},
                            'dns': {
                                'type': 'object',
                                'properties': {
                                    'nameservers': {'type': 'array'},
                                    'a_records': {'type': 'array'},
                                    'has_mx': {'type': 'boolean'},
                                    'error': {'type': ['string', 'null']}
                                }
                            },
                            'ssl': {'type': 'object'},
                            'next_steps': {'type': 'array'}
                        }
                    }
                },
                {
                    'type': 'domain_dns',
                    'description': 'All DNS records for domain',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'domain_dns'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'domain': {'type': 'string'},
                            'records': {
                                'type': 'object',
                                'properties': {
                                    'A': {'type': 'array'},
                                    'AAAA': {'type': 'array'},
                                    'MX': {'type': 'array'},
                                    'TXT': {'type': 'array'},
                                    'NS': {'type': 'array'},
                                    'CNAME': {'type': 'array'},
                                    'SOA': {'type': 'array'}
                                }
                            }
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'domain://example.com',
                    'description': 'Domain overview (registrar, DNS, SSL status)',
                    'output_type': 'domain_overview'
                },
                {
                    'uri': 'domain://example.com/dns',
                    'description': 'All DNS records',
                    'element': 'dns',
                    'output_type': 'domain_dns'
                },
                {
                    'uri': 'domain://example.com/ssl',
                    'description': 'SSL certificate status (delegates to ssl://)',
                    'element': 'ssl',
                    'output_type': 'ssl_certificate'
                },
                {
                    'uri': 'domain://example.com --check',
                    'description': 'Health checks (DNS propagation, SSL, expiry)',
                    'cli_flag': '--check',
                    'output_type': 'domain_health'
                }
            ],
            'notes': [
                'DNS resolution via dnspython library',
                'SSL inspection delegates to ssl:// adapter',
                'WHOIS requires python-whois package (optional)',
                'Health checks include DNS propagation and SSL expiry'
            ]
        }

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
        self.domain: Optional[str] = None
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
        assert self.domain is not None
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
            'contract_version': '1.0',
            'type': 'domain_overview',
            'source': f'domain://{self.domain}',
            'source_type': 'network',
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

    def get_available_elements(self) -> List[Dict[str, str]]:
        """Get list of available domain elements.

        Returns:
            List of available elements with descriptions
        """
        return [
            {
                'name': 'dns',
                'description': 'DNS records (A, AAAA, MX, TXT, NS, CNAME, SOA)',
                'example': f'reveal domain://{self.domain}/dns'
            },
            {
                'name': 'whois',
                'description': 'WHOIS registration data',
                'example': f'reveal domain://{self.domain}/whois'
            },
            {
                'name': 'ssl',
                'description': 'SSL certificate status',
                'example': f'reveal domain://{self.domain}/ssl'
            },
            {
                'name': 'registrar',
                'description': 'Registrar and nameserver information',
                'example': f'reveal domain://{self.domain}/registrar'
            },
        ]

    def _get_dns_records(self) -> Dict[str, Any]:
        """Get all DNS records."""
        assert self.domain is not None
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

        assert self.domain is not None
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
        assert self.domain is not None
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

        assert self.domain is not None
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
            **kwargs: Check options (advanced, only_failures)

        Returns:
            Health check result dict
        """
        assert self.domain is not None
        advanced = kwargs.get('advanced', False)
        only_failures = kwargs.get('only_failures', False)

        # Run all checks
        checks = _run_dns_checks(self.domain)
        checks.append(_check_ssl_certificate(self.domain, advanced))

        # Calculate metrics
        overall_status = _calculate_overall_status(checks)
        summary = _calculate_check_summary(checks)

        # Filter results if requested
        if only_failures:
            checks = [c for c in checks if c['status'] in ('failure', 'warning')]

        # Generate contextual next steps
        next_steps = _generate_domain_next_steps(checks, self.domain)

        return {
            'type': 'domain_health_check',
            'domain': self.domain,
            'status': overall_status,
            'checks': checks,
            'summary': summary,
            'next_steps': next_steps,
            'exit_code': 0 if overall_status == 'pass' else (1 if overall_status == 'warning' else 2),
        }
