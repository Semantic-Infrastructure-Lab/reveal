"""Domain adapter for DNS, whois, and domain validation (domain://)."""

from typing import Dict, Any, Optional, List
from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from .dns import (
    get_dns_records, get_dns_summary,
    check_dns_resolution, check_nameserver_response, check_dns_propagation,
    check_email_dns, check_ns_authority,
)
from .renderer import DomainRenderer
from ..ssl.certificate import check_ssl_health


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


import urllib.request as _urllib_request
import urllib.error as _urllib_error
import ssl as _ssl_module


class _NoRedirect(_urllib_request.HTTPRedirectHandler):
    """HTTP handler that suppresses redirects so we can record each hop."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _make_absolute_url(location: str, base_url: str) -> str:
    """Make a potentially relative redirect Location header absolute."""
    if location.startswith('/'):
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{location}"
    return location


def _handle_redirect_step(
    opener, req, current: str, chain: list
) -> tuple:
    """Try one HTTP step; return (final_result_or_None, next_url).

    Appends to chain in place. Returns (dict, url) where dict is the
    final result if the request terminated, or None to continue redirecting.
    """
    try:
        resp = opener.open(req, timeout=8)
        code = resp.getcode()
        chain.append({'url': current, 'status': code})
        return {'status': code, 'chain': chain, 'final_url': current}, current
    except _urllib_error.HTTPError as e:
        code = e.code
        chain.append({'url': current, 'status': code})
        if code in (301, 302, 303, 307, 308) and 'Location' in e.headers:
            return None, _make_absolute_url(e.headers['Location'], current)
        return {'status': code, 'chain': chain, 'final_url': current}, current


def _follow_redirect_chain(url: str, max_redirects: int = 5) -> Dict[str, Any]:
    """Follow a URL's redirect chain, returning final status, chain, and any error."""
    chain: list = []
    current = url
    ctx = _ssl_module.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl_module.CERT_NONE

    for _ in range(max_redirects + 1):
        try:
            req = _urllib_request.Request(current, headers={'User-Agent': 'reveal-cli/1.0'})
            opener = _urllib_request.build_opener(
                _urllib_request.HTTPSHandler(context=ctx), _NoRedirect()
            )
            result, current = _handle_redirect_step(opener, req, current, chain)
            if result is not None:
                return result
        except _urllib_error.URLError as e:
            return {'status': None, 'chain': chain, 'error': str(e.reason), 'final_url': current}
        except Exception as e:
            return {'status': None, 'chain': chain, 'error': str(e), 'final_url': current}

    return {'status': None, 'chain': chain, 'error': 'Too many redirects', 'final_url': current}


def _classify_http_check(scheme: str, chain_result: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a single scheme's chain result into a check dict."""
    port = 80 if scheme == 'http' else 443
    label = f"{scheme.upper()} ({port})"
    status_code = chain_result.get('status')
    error = chain_result.get('error')
    chain = chain_result.get('chain', [])
    final_url = chain_result.get('final_url', '')

    if error:
        check_status, message = 'failure', f"{label}: connection failed — {error}"
    elif status_code is None:
        check_status, message = 'failure', f"{scheme.upper()}: no response"
    elif status_code < 400:
        check_status = 'pass'
        if len(chain) > 1:
            message = f"{label}: {chain[0]['status']} → {final_url} ({status_code})"
        else:
            message = f"{label}: {status_code} OK"
    elif status_code >= 500:
        check_status, message = 'failure', f"{label}: {status_code} server error"
    else:
        check_status, message = 'warning', f"{label}: {status_code}"

    return {
        'name': f'http_{scheme}_response',
        'status': check_status,
        'value': str(status_code) if status_code else 'error',
        'threshold': '2xx or 3xx',
        'message': message,
        'severity': 'medium',
        'redirect_chain': [f"{h['url']} → {h['status']}" for h in chain] if len(chain) > 1 else [],
    }


def _aggregate_http_checks(checks: list) -> Dict[str, Any]:
    """Merge two per-scheme check dicts into one combined result."""
    all_pass = all(c['status'] == 'pass' for c in checks)
    if all_pass and not any(c['redirect_chain'] for c in checks):
        return {
            'name': 'http_response',
            'status': 'pass',
            'value': 'reachable',
            'threshold': '2xx or 3xx',
            'message': f"HTTP/HTTPS responding (HTTP {checks[0]['value']}, HTTPS {checks[1]['value']})",
            'severity': 'medium',
        }
    combined_status = 'pass' if all_pass else ('failure' if any(c['status'] == 'failure' for c in checks) else 'warning')
    return {
        'name': 'http_response',
        'status': combined_status,
        'value': f"HTTP {checks[0]['value']}, HTTPS {checks[1]['value']}",
        'threshold': '2xx or 3xx',
        'message': '; '.join(c['message'] for c in checks),
        'severity': 'medium',
        'http_checks': checks,
    }


def _check_http_response(domain: str) -> Dict[str, Any]:
    """Make actual HTTP/HTTPS requests and report status codes and redirect chain."""
    checks = [
        _classify_http_check(scheme, _follow_redirect_chain(f"{scheme}://{domain}/"))
        for scheme in ('http', 'https')
    ]
    return _aggregate_http_checks(checks)


def _check_http_to_https_redirect(domain: str) -> Dict[str, Any]:
    """Check that HTTP (port 80) properly redirects to HTTPS (port 443).

    Follows the redirect chain from http://domain/ and validates that it
    ends on an https:// URL. Surfaces as a named pass/fail check in --check
    output, distinct from the general http_response reachability check.
    """
    result = _follow_redirect_chain(f"http://{domain}/")
    chain = result.get('chain', [])
    final_url = result.get('final_url', '')
    error = result.get('error')

    if error:
        return {
            'name': 'http_redirect',
            'status': 'warning',
            'value': 'Unreachable',
            'threshold': 'HTTP → HTTPS redirect',
            'message': f'HTTP port 80 unreachable: {error}',
            'severity': 'low',
        }

    first_status = chain[0]['status'] if chain else None
    is_redirect = first_status in (301, 302, 303, 307, 308)
    redirects_to_https = final_url.startswith('https://')

    if is_redirect and redirects_to_https:
        hop_statuses = ' → '.join(str(h['status']) for h in chain)
        return {
            'name': 'http_redirect',
            'status': 'pass',
            'value': f'{first_status} → HTTPS',
            'threshold': 'HTTP → HTTPS redirect',
            'message': f'HTTP redirects to HTTPS ({hop_statuses})',
            'severity': 'medium',
            'details': {
                'chain': [f"{h['url']} ({h['status']})" for h in chain],
                'final_url': final_url,
            },
        }

    if not is_redirect:
        return {
            'name': 'http_redirect',
            'status': 'warning',
            'value': f'{first_status} (no redirect)',
            'threshold': 'HTTP → HTTPS redirect',
            'message': f'HTTP responds {first_status} without redirecting to HTTPS — consider adding redirect',
            'severity': 'medium',
            'details': {'final_url': final_url},
        }

    # is_redirect but stays on HTTP
    return {
        'name': 'http_redirect',
        'status': 'warning',
        'value': f'{first_status} → HTTP',
        'threshold': 'HTTP → HTTPS redirect',
        'message': f'HTTP redirects but stays on HTTP ({first_status} → {final_url[:60]}) — not upgrading to HTTPS',
        'severity': 'medium',
        'details': {'final_url': final_url},
    }


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

    # HTTP response failures
    if any(c['name'] == 'http_response' and c['status'] == 'failure' for c in checks):
        next_steps.append(f"Check nginx config: reveal nginx://{domain}")
        next_steps.append(f"Verify nginx upstream is reachable: reveal nginx://{domain}/upstream")

    # HTTP redirect to unexpected service
    if any(c['name'] == 'http_response' and c['status'] == 'warning' for c in checks):
        next_steps.append(f"Inspect nginx vhost config: reveal nginx://{domain}")

    # Default next steps if all passed
    if not next_steps:
        next_steps.append(f"View DNS records: reveal domain://{domain}/dns")
        next_steps.append(f"View SSL certificate: reveal ssl://{domain}")

    return next_steps


_SCHEMA_ELEMENTS = {
    'dns': 'DNS records (A, AAAA, MX, TXT, NS, CNAME, SOA)',
    'whois': 'WHOIS registration data (requires python-whois)',
    'ssl': 'SSL certificate status (delegates to ssl:// adapter)',
    'registrar': 'Registrar and nameserver information',
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'domain_overview',
        'description': 'Domain overview with DNS and SSL summary',
        'schema': {'type': 'object', 'properties': {
            'contract_version': {'type': 'string'},
            'type': {'type': 'string', 'const': 'domain_overview'},
            'source': {'type': 'string'}, 'source_type': {'type': 'string'},
            'domain': {'type': 'string'},
            'dns': {'type': 'object', 'properties': {
                'nameservers': {'type': 'array'}, 'a_records': {'type': 'array'},
                'has_mx': {'type': 'boolean'}, 'error': {'type': ['string', 'null']},
            }},
            'ssl': {'type': 'object'},
            'next_steps': {'type': 'array'},
        }},
    },
    {
        'type': 'domain_dns',
        'description': 'All DNS records for domain',
        'schema': {'type': 'object', 'properties': {
            'contract_version': {'type': 'string'},
            'type': {'type': 'string', 'const': 'domain_dns'},
            'source': {'type': 'string'}, 'source_type': {'type': 'string'},
            'domain': {'type': 'string'},
            'records': {'type': 'object', 'properties': {
                'A': {'type': 'array'}, 'AAAA': {'type': 'array'}, 'MX': {'type': 'array'},
                'TXT': {'type': 'array'}, 'NS': {'type': 'array'}, 'CNAME': {'type': 'array'},
                'SOA': {'type': 'array'},
            }},
        }},
    },
    {
        'type': 'domain_whois',
        'description': 'WHOIS registration data — registrar, dates, nameservers',
        'schema': {'type': 'object', 'properties': {
            'contract_version': {'type': 'string'},
            'type': {'type': 'string', 'const': 'domain_whois'},
            'source': {'type': 'string'}, 'domain': {'type': 'string'},
            'registrar': {'type': 'string'}, 'creation_date': {'type': 'string'},
            'expiration_date': {'type': 'string'}, 'nameservers': {'type': 'array'},
            'status': {'type': 'array'},
        }},
    },
    {
        'type': 'domain_registrar',
        'description': 'Registrar name and key dates from WHOIS',
        'schema': {'type': 'object', 'properties': {
            'contract_version': {'type': 'string'},
            'type': {'type': 'string', 'const': 'domain_registrar'},
            'source': {'type': 'string'}, 'domain': {'type': 'string'},
            'registrar': {'type': 'string'}, 'creation_date': {'type': 'string'},
            'expiration_date': {'type': 'string'},
        }},
    },
    {
        'type': 'domain_health',
        'description': 'Domain health check results (HTTP status, redirect chain)',
        'schema': {'type': 'object', 'properties': {
            'contract_version': {'type': 'string'},
            'type': {'type': 'string', 'const': 'domain_health'},
            'source': {'type': 'string'}, 'domain': {'type': 'string'},
            'http_status': {'type': 'integer'}, 'https_status': {'type': 'integer'},
            'redirect_chain': {'type': 'array'},
            'checks_passed': {'type': 'integer'}, 'checks_failed': {'type': 'integer'},
        }},
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'domain://example.com', 'description': 'Domain overview — registrar, DNS summary, SSL status', 'output_type': 'domain_overview'},
    {'uri': 'domain://example.com/dns', 'description': 'All DNS records (A, MX, NS, TXT, CNAME, etc.)', 'element': 'dns', 'output_type': 'domain_dns'},
    {'uri': 'domain://example.com/ssl', 'description': 'SSL certificate details (delegates to ssl:// adapter)', 'element': 'ssl', 'output_type': 'ssl_certificate'},
    {'uri': 'domain://example.com/whois', 'description': 'WHOIS registration data — registrar, dates, nameservers (requires python-whois)', 'element': 'whois', 'output_type': 'domain_whois'},
    {'uri': 'domain://example.com/registrar', 'description': 'Registrar name, creation/expiry dates from WHOIS', 'element': 'registrar', 'output_type': 'domain_registrar'},
    {'uri': 'domain://example.com --check', 'description': 'Full health check: DNS propagation + HTTP response + SSL expiry', 'cli_flag': '--check', 'output_type': 'domain_health'},
]

_SCHEMA_NOTES = [
    'DNS resolution via dnspython library',
    'SSL inspection delegates to ssl:// adapter',
    'WHOIS requires python-whois package (optional)',
    'Health checks include DNS propagation and SSL expiry',
]


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

    BUDGET_LIST_FIELD = 'checks'

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for domain:// adapter."""
        return {
            'adapter': 'domain',
            'description': 'Domain registration, DNS, and SSL inspection with health checks',
            'uri_syntax': 'domain://<domain>[/element]',
            'query_params': {},
            'elements': _SCHEMA_ELEMENTS,
            'cli_flags': ['--check', '--advanced', '--only-failures'],
            'supports_batch': False,
            'supports_advanced': True,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
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

        # Get WHOIS summary (optional — degrades gracefully if python-whois absent)
        whois_summary = self._get_whois_summary()

        # Build next steps
        next_steps = [
            f"DNS details: reveal domain://{self.domain}/dns",
            f"WHOIS details: reveal domain://{self.domain}/whois",
            f"SSL details: reveal ssl://{self.domain}",
            f"Email DNS: reveal domain://{self.domain}/mail",
            f"HTTP redirect chain: reveal domain://{self.domain}/http",
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
            'whois': whois_summary,
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
            'mail': self._get_email_dns,
            'http': self._get_http_chain,
            'ns-audit': self._get_ns_audit,
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
            {
                'name': 'mail',
                'description': 'Email DNS deliverability (MX, SPF, DMARC)',
                'example': f'reveal domain://{self.domain}/mail'
            },
            {
                'name': 'http',
                'description': 'HTTP redirect chain inspection (port 80 → HTTPS)',
                'example': f'reveal domain://{self.domain}/http'
            },
            {
                'name': 'ns-audit',
                'description': 'NS authority cross-check — detects orphaned/stale nameserver entries',
                'example': f'reveal domain://{self.domain}/ns-audit'
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
        """Get WHOIS registration information via python-whois."""
        assert self.domain is not None
        try:
            import whois  # optional dependency
        except ImportError:
            return {
                'type': 'domain_whois',
                'domain': self.domain,
                'error': 'python-whois not installed',
                'next_steps': [
                    'Install python-whois: pip install python-whois',
                    f"View DNS instead: reveal domain://{self.domain}/dns",
                ],
            }

        try:
            w = whois.whois(self.domain)
        except Exception as e:
            return {
                'type': 'domain_whois',
                'domain': self.domain,
                'error': f"WHOIS lookup failed: {e}",
            }

        def _normalize_date(d: Any) -> Optional[str]:
            """Return ISO date string from a datetime or list of datetimes."""
            if isinstance(d, list):
                d = d[0] if d else None
            if d is None:
                return None
            try:
                return d.strftime('%Y-%m-%d')
            except AttributeError:
                return str(d)

        def _normalize_list(v: Any) -> List[str]:
            """Return a flat list of strings."""
            if v is None:
                return []
            if isinstance(v, str):
                return [v]
            return [str(item) for item in v]

        name_servers = sorted(
            ns.lower() for ns in _normalize_list(w.name_servers)
        )

        return {
            'type': 'domain_whois',
            'domain': self.domain,
            'registrar': w.registrar or None,
            'creation_date': _normalize_date(w.creation_date),
            'expiration_date': _normalize_date(w.expiration_date),
            'name_servers': name_servers,
            'status': _normalize_list(w.status),
            'dnssec': w.dnssec or None,
            'next_steps': [
                f"View DNS records: reveal domain://{self.domain}/dns",
                f"View SSL details: reveal ssl://{self.domain}",
            ],
        }

    def _get_ssl_status(self) -> Dict[str, Any]:
        """Get SSL certificate status (delegates to ssl:// adapter)."""

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
        """Get registrar and nameserver information via WHOIS + DNS."""
        assert self.domain is not None
        dns_summary = get_dns_summary(self.domain)
        whois_info = self._get_whois_info()

        result: Dict[str, Any] = {
            'type': 'domain_registrar',
            'domain': self.domain,
            'nameservers': dns_summary.get('nameservers', []),
            'next_steps': [
                f"View DNS records: reveal domain://{self.domain}/dns",
                f"View full WHOIS: reveal domain://{self.domain}/whois",
            ],
        }

        if not whois_info.get('error'):
            result['registrar'] = whois_info.get('registrar')
            result['creation_date'] = whois_info.get('creation_date')
            result['expiration_date'] = whois_info.get('expiration_date')
        else:
            result['note'] = whois_info['error']

        return result

    def _get_email_dns(self) -> Dict[str, Any]:
        """Get email DNS deliverability checks (MX, SPF, DMARC)."""
        assert self.domain is not None
        checks = check_email_dns(self.domain)

        overall = 'pass'
        if any(c.get('status') == 'failure' for c in checks):
            overall = 'failure'
        elif any(c.get('status') == 'warning' for c in checks):
            overall = 'warning'

        mx_check = next((c for c in checks if c['name'] == 'mx_records'), {})
        spf_check = next((c for c in checks if c['name'] == 'spf_record'), {})
        dmarc_check = next((c for c in checks if c['name'] == 'dmarc_record'), {})

        return {
            'type': 'domain_email_dns',
            'domain': self.domain,
            'status': overall,
            'mx_records': mx_check.get('details', {}).get('mx_records', []),
            'spf_record': (
                spf_check.get('details', {}).get('spf_record')
                or spf_check.get('details', {}).get('spf_records')
            ),
            'dmarc_record': dmarc_check.get('details', {}).get('dmarc_record'),
            'dmarc_policy': dmarc_check.get('details', {}).get('policy'),
            'checks': checks,
            'next_steps': [
                f"Full domain check: reveal domain://{self.domain} --check",
                f"DNS records: reveal domain://{self.domain}/dns",
            ],
        }

    def _get_http_chain(self) -> Dict[str, Any]:
        """Get HTTP redirect chain for both HTTP and HTTPS."""
        assert self.domain is not None
        http_result = _follow_redirect_chain(f"http://{self.domain}/")
        https_result = _follow_redirect_chain(f"https://{self.domain}/")
        redirect_check = _check_http_to_https_redirect(self.domain)

        def _format_chain(result: Dict[str, Any]) -> List[str]:
            chain = result.get('chain', [])
            if not chain:
                return [f"Error: {result.get('error', 'no response')}"]
            return [f"{h['url']} ({h['status']})" for h in chain]

        return {
            'type': 'domain_http_chain',
            'domain': self.domain,
            'http_chain': _format_chain(http_result),
            'https_chain': _format_chain(https_result),
            'http_final_url': http_result.get('final_url', ''),
            'https_final_url': https_result.get('final_url', ''),
            'redirects_to_https': redirect_check['status'] == 'pass',
            'redirect_check': redirect_check,
            'next_steps': [
                f"Full health check: reveal domain://{self.domain} --check",
                f"SSL details: reveal ssl://{self.domain}",
            ],
        }

    def _get_ns_audit(self) -> Dict[str, Any]:
        """Cross-query each NS server to detect orphaned or stale entries."""
        assert self.domain is not None
        result = check_ns_authority(self.domain)
        result['next_steps'] = [
            f"Full DNS records: reveal domain://{self.domain}/dns",
            f"Propagation check: reveal domain://{self.domain} --check",
        ]
        return result

    def _get_whois_summary(self) -> Dict[str, Any]:
        """Get abbreviated WHOIS data for domain overview (registrar + expiry only)."""
        info = self._get_whois_info()
        if info.get('error'):
            return {'available': False, 'error': info['error']}
        return {
            'available': True,
            'registrar': info.get('registrar'),
            'creation_date': info.get('creation_date'),
            'expiration_date': info.get('expiration_date'),
        }

    def _get_ssl_summary(self) -> Dict[str, Any]:
        """Get summarized SSL information."""

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
        checks.append(_check_http_response(self.domain))
        checks.append(_check_http_to_https_redirect(self.domain))
        checks.extend(check_email_dns(self.domain))

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
