"""SSL certificate adapter (ssl://)."""

from typing import Dict, Any, List, Optional
from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from .certificate import SSLFetcher, CertificateInfo, check_ssl_health
from .renderer import SSLRenderer


@register_adapter('ssl')
@register_renderer(SSLRenderer)
class SSLAdapter(ResourceAdapter):
    """Adapter for inspecting SSL certificates via ssl:// URIs.

    Progressive disclosure pattern for SSL certificate inspection.

    Usage:
        reveal ssl://example.com              # Certificate overview
        reveal ssl://example.com:8443         # Non-standard port
        reveal ssl://example.com --check      # Health checks (expiry, chain)
        reveal ssl:// --from-nginx config     # Batch check from nginx config

    Elements:
        reveal ssl://example.com/san          # Subject Alternative Names
        reveal ssl://example.com/chain        # Certificate chain
        reveal ssl://example.com/issuer       # Issuer details
    """

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for ssl:// adapter.

        Help data loaded from reveal/adapters/help_data/ssl.yaml
        to reduce function complexity.
        """
        return load_help_data('ssl') or {}

    def __init__(self, connection_string: str = ""):
        """Initialize SSL adapter with host details.

        Args:
            connection_string: ssl://host[:port][/element]

        Raises:
            TypeError: If no connection string provided (allows generic handler to try next pattern)
            ValueError: If connection string is invalid
        """
        # No-arg initialization should raise TypeError, not ValueError
        # This lets the generic handler try the next pattern
        if not connection_string:
            raise TypeError("SSLAdapter requires a connection string")

        self.connection_string = connection_string
        self.host = None
        self.port = 443
        self.element = None
        self._certificate: Optional[CertificateInfo] = None
        self._chain: List[CertificateInfo] = []
        self._verification: Optional[Dict[str, Any]] = None
        self._fetcher = SSLFetcher()

        self._parse_connection_string(connection_string)

    def _parse_connection_string(self, uri: str) -> None:
        """Parse ssl:// URI into components.

        Args:
            uri: Connection URI (ssl://host[:port][/element])
        """
        if uri == "ssl://":
            raise ValueError("SSL URI requires hostname: ssl://example.com")

        # Remove ssl:// prefix
        if uri.startswith("ssl://"):
            uri = uri[6:]

        # Split host:port from element
        parts = uri.split('/', 1)
        host_port = parts[0]
        self.element = parts[1] if len(parts) > 1 else None

        # Parse host:port
        if ':' in host_port:
            host, port_str = host_port.rsplit(':', 1)
            try:
                self.port = int(port_str)
            except ValueError:
                raise ValueError(f"Invalid port number: {port_str}")
            self.host = host
        else:
            self.host = host_port

        if not self.host:
            raise ValueError("SSL URI requires hostname: ssl://example.com")

    def _fetch_certificate(self) -> None:
        """Fetch certificate if not already fetched."""
        if self._certificate is None:
            (
                self._certificate,
                self._chain,
                self._verification,
            ) = self._fetcher.fetch_certificate_with_verification(self.host, self.port)

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get SSL certificate overview.

        Returns:
            Dict containing certificate summary (~150 tokens)
        """
        # If element was specified in URI, delegate to get_element
        if self.element:
            element_data = self.get_element(self.element)
            if element_data:
                return element_data
            raise ValueError(f"Unknown element: {self.element}")

        self._fetch_certificate()
        cert = self._certificate

        # Determine health status
        days = cert.days_until_expiry
        if days < 0:
            health_status = 'EXPIRED'
            health_icon = '\u274c'  # Red X
        elif days < 7:
            health_status = 'CRITICAL'
            health_icon = '\u274c'
        elif days < 30:
            health_status = 'WARNING'
            health_icon = '\u26a0\ufe0f'  # Warning
        else:
            health_status = 'HEALTHY'
            health_icon = '\u2705'  # Green check

        # Build next steps
        next_steps = []
        if self.element is None:
            next_steps.append(f"reveal ssl://{self.host}/san  # View all domain names")
            next_steps.append(f"reveal ssl://{self.host}/issuer  # Issuer details")
            next_steps.append(f"reveal ssl://{self.host} --check  # Run health checks")

        return {
            'type': 'ssl_certificate',
            'host': self.host,
            'port': self.port,
            'common_name': cert.common_name,
            'issuer': cert.issuer_name,
            'valid_from': cert.not_before.strftime('%Y-%m-%d'),
            'valid_until': cert.not_after.strftime('%Y-%m-%d'),
            'days_until_expiry': days,
            'health_status': health_status,
            'health_icon': health_icon,
            'san_count': len(cert.san),
            'verification': {
                'chain_valid': self._verification.get('verified', False),
                'hostname_match': self._verification.get('hostname_match', False),
                'error': self._verification.get('error'),
            },
            'next_steps': next_steps,
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific certificate element.

        Args:
            element_name: Element to retrieve (san, chain, issuer, subject)

        Returns:
            Element data or None if not found
        """
        self._fetch_certificate()
        cert = self._certificate

        element_handlers = {
            'san': self._get_san,
            'chain': self._get_chain,
            'issuer': self._get_issuer,
            'subject': self._get_subject,
            'dates': self._get_dates,
            'full': self._get_full,
        }

        handler = element_handlers.get(element_name)
        if handler:
            return handler()

        return None

    def _get_san(self) -> Dict[str, Any]:
        """Get Subject Alternative Names."""
        cert = self._certificate
        return {
            'type': 'ssl_san',
            'host': self.host,
            'common_name': cert.common_name,
            'san': cert.san,
            'san_count': len(cert.san),
            'wildcard_entries': [s for s in cert.san if s.startswith('*.')],
        }

    def _get_chain(self) -> Dict[str, Any]:
        """Get certificate chain information."""
        cert = self._certificate
        return {
            'type': 'ssl_chain',
            'host': self.host,
            'leaf': {
                'common_name': cert.common_name,
                'issuer': cert.issuer_name,
            },
            'chain': [c.to_dict() for c in self._chain],
            'chain_length': len(self._chain) + 1,  # +1 for leaf
            'verification': self._verification,
        }

    def _get_issuer(self) -> Dict[str, Any]:
        """Get issuer details."""
        cert = self._certificate
        return {
            'type': 'ssl_issuer',
            'host': self.host,
            'issuer': cert.issuer,
            'issuer_name': cert.issuer_name,
        }

    def _get_subject(self) -> Dict[str, Any]:
        """Get subject details."""
        cert = self._certificate
        return {
            'type': 'ssl_subject',
            'host': self.host,
            'subject': cert.subject,
            'common_name': cert.common_name,
        }

    def _get_dates(self) -> Dict[str, Any]:
        """Get validity dates."""
        cert = self._certificate
        return {
            'type': 'ssl_dates',
            'host': self.host,
            'not_before': cert.not_before.isoformat(),
            'not_after': cert.not_after.isoformat(),
            'days_until_expiry': cert.days_until_expiry,
            'is_expired': cert.is_expired,
        }

    def _get_full(self) -> Dict[str, Any]:
        """Get full certificate details."""
        cert = self._certificate
        return {
            'type': 'ssl_full',
            'host': self.host,
            'port': self.port,
            'certificate': cert.to_dict(),
            'verification': self._verification,
        }

    def check(self, **kwargs) -> Dict[str, Any]:
        """Run SSL health checks.

        Args:
            **kwargs: Check options (warn_days, critical_days)

        Returns:
            Health check result dict
        """
        warn_days = kwargs.get('warn_days', 30)
        critical_days = kwargs.get('critical_days', 7)

        return check_ssl_health(
            self.host, self.port,
            warn_days=warn_days,
            critical_days=critical_days
        )


def batch_check_from_nginx(
    nginx_path: str, warn_days: int = 30, critical_days: int = 7
) -> Dict[str, Any]:
    """Check SSL certificates for all domains in an nginx config.

    Args:
        nginx_path: Path to nginx configuration file
        warn_days: Days until expiry to trigger warning
        critical_days: Days until expiry to trigger critical

    Returns:
        Batch check results
    """
    from reveal.analyzers.nginx import NginxAnalyzer

    # Parse nginx config
    analyzer = NginxAnalyzer(nginx_path)
    structure = analyzer.get_structure()

    # Extract domains from SSL server blocks
    domains = set()
    servers = structure.get('servers', [])

    for server in servers:
        signature = server.get('signature', '')
        # Look for SSL servers (port 443 or SSL indicator)
        if '443' in signature or 'SSL' in signature:
            # Extract domain from signature (format: "domain.com [443 (SSL)]")
            domain = signature.split()[0] if signature else None
            if domain and domain != '_':  # Skip default server
                domains.add(domain)

    # Check each domain
    results = []
    for domain in sorted(domains):
        result = check_ssl_health(domain, 443, warn_days, critical_days)
        results.append(result)

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r['status'] == 'pass')
    warnings = sum(1 for r in results if r['status'] == 'warning')
    failures = sum(1 for r in results if r['status'] == 'failure')

    return {
        'type': 'ssl_batch_check',
        'source': nginx_path,
        'domains_checked': total,
        'status': 'pass' if failures == 0 and warnings == 0 else (
            'warning' if failures == 0 else 'failure'
        ),
        'summary': {
            'total': total,
            'passed': passed,
            'warnings': warnings,
            'failures': failures,
        },
        'results': results,
        'exit_code': 0 if failures == 0 else 2,
    }
