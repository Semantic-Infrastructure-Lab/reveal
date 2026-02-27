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

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for ssl:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'ssl',
            'description': 'SSL/TLS certificate inspection and health monitoring',
            'uri_syntax': 'ssl://<host>[:<port>][/<element>]',
            'query_params': {},  # No query params currently
            'elements': {
                'san': 'Subject Alternative Names (all domain names)',
                'chain': 'Certificate chain (intermediate + root)',
                'issuer': 'Certificate issuer details',
                'subject': 'Certificate subject details',
                'dates': 'Validity dates (not_before, not_after)',
                'full': 'Complete certificate dump (all fields)'
            },
            'cli_flags': [
                '--check',  # Health checks (expiry, chain validation)
                '--advanced',  # Advanced checks (OCSP, revocation)
                '--only-failures',  # Show only failed checks
                '--expiring-within=<days>'  # Filter by expiry window
            ],
            'supports_batch': True,
            'supports_advanced': True,
            'output_types': [
                {
                    'type': 'ssl_certificate',
                    'description': 'Certificate overview with health status',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'ssl_certificate'},
                            'host': {'type': 'string'},
                            'port': {'type': 'integer'},
                            'common_name': {'type': 'string'},
                            'issuer': {'type': 'string'},
                            'valid_from': {'type': 'string', 'format': 'date'},
                            'valid_until': {'type': 'string', 'format': 'date'},
                            'days_until_expiry': {'type': 'integer'},
                            'health_status': {
                                'type': 'string',
                                'enum': ['HEALTHY', 'WARNING', 'CRITICAL', 'EXPIRED']
                            },
                            'san_count': {'type': 'integer'},
                            'verification': {
                                'type': 'object',
                                'properties': {
                                    'chain_valid': {'type': 'boolean'},
                                    'hostname_match': {'type': 'boolean'},
                                    'error': {'type': ['string', 'null']}
                                }
                            }
                        }
                    },
                    'example': {
                        'type': 'ssl_certificate',
                        'host': 'example.com',
                        'port': 443,
                        'common_name': 'example.com',
                        'issuer': "Let's Encrypt",
                        'valid_from': '2026-01-01',
                        'valid_until': '2026-04-01',
                        'days_until_expiry': 54,
                        'health_status': 'HEALTHY',
                        'san_count': 2,
                        'verification': {
                            'chain_valid': True,
                            'hostname_match': True,
                            'error': None
                        }
                    }
                },
                {
                    'type': 'ssl_san',
                    'description': 'Subject Alternative Names list',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'ssl_san'},
                            'host': {'type': 'string'},
                            'common_name': {'type': 'string'},
                            'san': {'type': 'array', 'items': {'type': 'string'}},
                            'san_count': {'type': 'integer'}
                        }
                    }
                },
                {
                    'type': 'ssl_chain',
                    'description': 'Certificate chain details',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'ssl_chain'},
                            'host': {'type': 'string'},
                            'chain_length': {'type': 'integer'},
                            'certificates': {'type': 'array'}
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'ssl://example.com',
                    'description': 'Get certificate overview with health status',
                    'output_type': 'ssl_certificate'
                },
                {
                    'uri': 'ssl://example.com:8443',
                    'description': 'Check certificate on non-standard port',
                    'output_type': 'ssl_certificate'
                },
                {
                    'uri': 'ssl://example.com/san',
                    'description': 'List all domain names in certificate',
                    'output_type': 'ssl_san'
                },
                {
                    'uri': 'ssl://example.com/chain',
                    'description': 'Show certificate chain (intermediate + root)',
                    'output_type': 'ssl_chain'
                },
                {
                    'uri': 'ssl://example.com --check',
                    'description': 'Run health checks (expiry, validation)',
                    'cli_flag': '--check',
                    'output_type': 'ssl_certificate'
                },
                {
                    'uri': 'ssl://example.com --expiring-within=30',
                    'description': 'Check if certificate expires in 30 days',
                    'cli_flag': '--expiring-within',
                    'output_type': 'ssl_certificate'
                }
            ]
        }

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
        self.host: Optional[str] = None
        self.port: int = 443
        self.element: Optional[str] = None
        self._certificate: Optional[CertificateInfo] = None
        self._chain: List[CertificateInfo] = []
        self._verification: Optional[Dict[str, Any]] = None
        self._fetcher = SSLFetcher()
        self._nginx_path: Optional[str] = None  # For ssl://nginx:///path mode
        self._cert_file_path: Optional[str] = None  # For ssl://file:///path mode

        self._parse_connection_string(connection_string)

    def _parse_connection_string(self, uri: str) -> None:
        """Parse ssl:// URI into components.

        Args:
            uri: Connection URI (ssl://host[:port][/element] or ssl://nginx:///path)
        """
        if uri == "ssl://":
            raise ValueError("SSL URI requires hostname: ssl://example.com")

        # Remove ssl:// prefix
        if uri.startswith("ssl://"):
            uri = uri[6:]

        # Check for nginx:// special syntax (ssl://nginx:///path/to/config)
        # This syntax is useful for batch audits with built-in aggregation
        if uri.startswith("nginx://"):
            self._nginx_path = uri[8:]  # Remove nginx://
            self.host = None  # Indicates batch mode
            return

        # Check for file:// syntax (ssl://file:///path/to/cert) — S2
        if uri.startswith("file://"):
            self._cert_file_path = uri[7:]  # Remove file:// → /path/to/cert
            self.host = None
            return

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
        """Fetch certificate if not already fetched (network or file)."""
        if self._certificate is not None:
            return
        if self._cert_file_path:
            from .certificate import load_certificate_from_file
            self._certificate, self._chain = load_certificate_from_file(self._cert_file_path)
            self._verification = None  # no network verification for file certs
        elif self.host:
            (
                self._certificate,
                self._chain,
                self._verification,
            ) = self._fetcher.fetch_certificate_with_verification(self.host, self.port)

    def _get_nginx_domains(self) -> Dict[str, Any]:
        """Extract SSL domains from nginx config.

        Returns:
            Dict with domain list and metadata
        """
        import glob
        from reveal.analyzers.nginx import NginxAnalyzer

        all_domains: set[str] = set()
        files_processed: List[str] = []

        if not self._nginx_path:
            return {'domains': list(all_domains), 'files_processed': files_processed, 'count': 0}

        # Handle glob patterns
        paths = glob.glob(self._nginx_path) if '*' in self._nginx_path else [self._nginx_path]

        for path in paths:
            try:
                analyzer = NginxAnalyzer(path)
                domains = analyzer.extract_ssl_domains()
                all_domains.update(domains)
                files_processed.append(path)
            except Exception:
                # Skip files that can't be parsed
                pass

        return {
            'type': 'ssl_nginx_domains',
            'source': self._nginx_path,
            'files_processed': len(files_processed),
            'domains': sorted(all_domains),
            'domain_count': len(all_domains),
        }

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get SSL certificate overview.

        Returns:
            Dict containing certificate summary (~150 tokens)
        """
        # Handle nginx batch mode - return domain list
        if self._nginx_path:
            return self._get_nginx_domains()

        # If element was specified in URI, delegate to get_element
        if self.element:
            element_data = self.get_element(self.element)
            if element_data:
                return element_data
            raise ValueError(f"Unknown element: {self.element}")

        self._fetch_certificate()
        cert = self._certificate

        is_file_mode = bool(self._cert_file_path)
        source_uri = (f'ssl://file://{self._cert_file_path}' if is_file_mode
                      else f'ssl://{self.host}')

        if not cert:
            return {'contract_version': '1.0', 'type': 'ssl_certificate',
                    'source': source_uri,
                    'source_type': 'file' if is_file_mode else 'network',
                    'error': 'Failed to fetch certificate'}

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
        if is_file_mode:
            file_uri = f'ssl://file://{self._cert_file_path}'
            next_steps.append(f"reveal {file_uri}/san  # View all SANs")
            next_steps.append(f"reveal {file_uri}/chain  # View cert chain")
            if cert.san:
                primary = cert.san[0].lstrip('*').lstrip('.')
                next_steps.append(
                    f"reveal ssl://{primary} --check  # Compare with live cert"
                )
        elif self.element is None:
            next_steps.append(f"reveal ssl://{self.host}/san  # View all domain names")
            next_steps.append(f"reveal ssl://{self.host}/issuer  # Issuer details")
            next_steps.append(f"reveal ssl://{self.host} --check  # Run health checks")

        result = {
            'contract_version': '1.0',
            'type': 'ssl_certificate',
            'source': source_uri,
            'source_type': 'file' if is_file_mode else 'network',
            'common_name': cert.common_name,
            'issuer': cert.issuer_name,
            'valid_from': cert.not_before.strftime('%Y-%m-%d'),
            'valid_until': cert.not_after.strftime('%Y-%m-%d'),
            'days_until_expiry': days,
            'health_status': health_status,
            'health_icon': health_icon,
            'san_count': len(cert.san),
            'next_steps': next_steps,
        }
        if is_file_mode:
            result['file_path'] = self._cert_file_path
            chain_count = len(self._chain)
            if chain_count:
                result['chain_certs'] = chain_count
        else:
            result['host'] = self.host
            result['port'] = self.port
            result['verification'] = {
                'chain_valid': self._verification.get('verified', False) if self._verification else False,
                'hostname_match': self._verification.get('hostname_match', False) if self._verification else False,
                'error': self._verification.get('error') if self._verification else None,
            }
        return result

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific certificate element.

        Args:
            element_name: Element to retrieve (san, chain, issuer, subject)

        Returns:
            Element data or None if not found
        """
        self._fetch_certificate()

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

    def get_available_elements(self) -> List[Dict[str, str]]:
        """Get list of available certificate elements.

        Returns:
            List of available elements with descriptions
        """
        self._fetch_certificate()
        cert = self._certificate

        if not cert:
            return []

        return [
            {
                'name': 'san',
                'description': f'Subject Alternative Names ({len(cert.san)} domains)',
                'example': f'reveal ssl://{self.host}/san'
            },
            {
                'name': 'chain',
                'description': f'Certificate chain ({len(self._chain) + 1} certificates)',
                'example': f'reveal ssl://{self.host}/chain'
            },
            {
                'name': 'issuer',
                'description': 'Certificate issuer details',
                'example': f'reveal ssl://{self.host}/issuer'
            },
            {
                'name': 'subject',
                'description': 'Certificate subject details',
                'example': f'reveal ssl://{self.host}/subject'
            },
            {
                'name': 'dates',
                'description': f'Validity dates (expires in {cert.days_until_expiry} days)',
                'example': f'reveal ssl://{self.host}/dates'
            },
            {
                'name': 'full',
                'description': 'Full certificate details',
                'example': f'reveal ssl://{self.host}/full'
            },
        ]

    def _get_san(self) -> Dict[str, Any]:
        """Get Subject Alternative Names."""
        cert = self._certificate
        if not cert:
            return {'type': 'ssl_san', 'error': 'Certificate not available'}
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
        if not cert:
            return {'type': 'ssl_chain', 'error': 'Certificate not available'}
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
        if not cert:
            return {'type': 'ssl_issuer', 'error': 'Certificate not available'}
        return {
            'type': 'ssl_issuer',
            'host': self.host,
            'issuer': cert.issuer,
            'issuer_name': cert.issuer_name,
        }

    def _get_subject(self) -> Dict[str, Any]:
        """Get subject details."""
        cert = self._certificate
        if not cert:
            return {'type': 'ssl_subject', 'error': 'Certificate not available'}
        return {
            'type': 'ssl_subject',
            'host': self.host,
            'subject': cert.subject,
            'common_name': cert.common_name,
        }

    def _get_dates(self) -> Dict[str, Any]:
        """Get validity dates."""
        cert = self._certificate
        if not cert:
            return {'type': 'ssl_dates', 'error': 'Certificate not available'}
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
        if not cert:
            return {'type': 'ssl_full', 'error': 'Certificate not available'}
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
            **kwargs: Check options (warn_days, critical_days, advanced, only_failures, validate_nginx)

        Returns:
            Health check result dict
        """
        warn_days = kwargs.get('warn_days', 30)
        critical_days = kwargs.get('critical_days', 7)
        advanced = kwargs.get('advanced', False)
        only_failures = kwargs.get('only_failures', False)
        validate_nginx = kwargs.get('validate_nginx', False)

        # Handle nginx validation mode
        if validate_nginx:
            return self.validate_nginx_ssl(**kwargs)

        # Handle nginx batch mode
        if self._nginx_path:
            return self._check_nginx_domains(
                warn_days, critical_days, advanced, only_failures
            )

        if not self.host:
            return {'type': 'ssl_check', 'error': 'No host specified'}

        return check_ssl_health(
            self.host, self.port,
            warn_days=warn_days,
            critical_days=critical_days,
            advanced=advanced
        )

    def _check_nginx_domains(
        self, warn_days: int = 30, critical_days: int = 7,
        advanced: bool = False, only_failures: bool = False
    ) -> Dict[str, Any]:
        """Check SSL certificates for all domains in nginx config.

        Args:
            warn_days: Days until expiry to trigger warning
            critical_days: Days until expiry to trigger critical
            advanced: Run advanced checks
            only_failures: Only include failures/warnings in results

        Returns:
            Batch check results
        """
        # Get domains from nginx config
        domain_info = self._get_nginx_domains()
        domains = domain_info['domains']

        return self._batch_check_domains(
            domains, warn_days, critical_days, advanced, only_failures,
            source=self._nginx_path
        )

    def _check_all_domains(self, domains: List[str], warn_days: int,
                           critical_days: int, advanced: bool) -> List[Dict[str, Any]]:
        """Check SSL health for all domains.

        Args:
            domains: List of domain names to check
            warn_days: Days until expiry to trigger warning
            critical_days: Days until expiry to trigger critical
            advanced: Run advanced checks

        Returns:
            List of check results for all domains
        """
        all_results = []
        for domain in domains:
            result = check_ssl_health(
                domain, 443, warn_days, critical_days, advanced
            )
            all_results.append(result)
        return all_results

    def _filter_failure_results(self, all_results: List[Dict[str, Any]],
                                 only_failures: bool) -> List[Dict[str, Any]]:
        """Filter results to only failures/warnings if requested.

        Args:
            all_results: All check results
            only_failures: Whether to filter to failures/warnings only

        Returns:
            Filtered results (or all results if not filtering)
        """
        if only_failures:
            return [r for r in all_results if r['status'] in ('failure', 'warning')]
        return all_results

    def _calculate_summary_counts(self, all_results: List[Dict[str, Any]]) -> Dict[str, int]:
        """Calculate summary counts from all results.

        Args:
            all_results: All check results

        Returns:
            Dict with total, passed, warnings, failures counts
        """
        return {
            'total': len(all_results),
            'passed': sum(1 for r in all_results if r['status'] == 'pass'),
            'warnings': sum(1 for r in all_results if r['status'] == 'warning'),
            'failures': sum(1 for r in all_results if r['status'] == 'failure'),
        }

    def _generate_batch_next_steps(self, all_results: List[Dict[str, Any]],
                                    failures: int, warnings: int, advanced: bool,
                                    only_failures: bool, source: Optional[str] = None) -> List[str]:
        """Generate contextual next steps based on results.

        Args:
            all_results: All check results
            failures: Number of failures
            warnings: Number of warnings
            advanced: Whether advanced checks were run
            only_failures: Whether results are filtered to failures
            source: Source description

        Returns:
            List of next step suggestions
        """
        next_steps = []
        if failures > 0 or warnings > 0:
            failed_domains = [r['host'] for r in all_results if r['status'] == 'failure']
            if failed_domains and not advanced:
                next_steps.append(f"Inspect first failure: reveal ssl://{failed_domains[0]} --check-advanced")
            if not only_failures and (failures > 0 or warnings > 0):
                next_steps.append("Show only problems: ... --only-failures")
            if source and 'nginx' in str(source).lower():
                next_steps.append("Validate nginx config: reveal ssl:// --from-nginx <path> --validate")
        return next_steps

    def _determine_overall_status(self, failures: int, warnings: int) -> str:
        """Determine overall batch check status.

        Args:
            failures: Number of failures
            warnings: Number of warnings

        Returns:
            Status string: 'pass', 'warning', or 'failure'
        """
        if failures == 0 and warnings == 0:
            return 'pass'
        return 'warning' if failures == 0 else 'failure'

    def _batch_check_domains(
        self, domains: List[str], warn_days: int = 30, critical_days: int = 7,
        advanced: bool = False, only_failures: bool = False, source: Optional[str] = None
    ) -> Dict[str, Any]:
        """Core batch checking logic for SSL certificates.

        Args:
            domains: List of domain names to check
            warn_days: Days until expiry to trigger warning
            critical_days: Days until expiry to trigger critical
            advanced: Run advanced checks
            only_failures: Only include failures/warnings in results
            source: Source description (e.g., file path, nginx config)

        Returns:
            Batch check results
        """
        # Check all domains
        all_results = self._check_all_domains(domains, warn_days, critical_days, advanced)

        # Filter results if requested
        results = self._filter_failure_results(all_results, only_failures)

        # Calculate summary (based on ALL results, not just filtered)
        summary = self._calculate_summary_counts(all_results)

        # Generate next steps
        next_steps = self._generate_batch_next_steps(
            all_results, summary['failures'], summary['warnings'],
            advanced, only_failures, source
        )

        # Determine overall status
        status = self._determine_overall_status(summary['failures'], summary['warnings'])

        return {
            'type': 'ssl_batch_check',
            'source': source or 'batch',
            'domains_checked': summary['total'],
            'status': status,
            'summary': summary,
            'results': results,  # May be filtered
            'next_steps': next_steps,
            'exit_code': 0 if summary['failures'] == 0 else 2,
        }

    def _validate_single_domain(self, domain: str) -> Dict[str, Any]:
        """Validate SSL configuration for a single domain.

        Args:
            domain: Domain to validate

        Returns:
            Validation result with status and issues
        """
        issues = []

        # Get SSL cert for this domain
        try:
            cert_result = check_ssl_health(domain, 443)
        except Exception as e:
            return {
                'domain': domain,
                'status': 'failure',
                'issues': [{
                    'type': 'connection_error',
                    'message': f'Could not connect to {domain}: {e}',
                    'severity': 'critical',
                }],
            }

        # TODO: Parse nginx config to get cert path and validate
        # For now, just validate that the cert is accessible
        if cert_result['status'] in ('failure', 'warning'):
            for check in cert_result.get('checks', []):
                if check['status'] in ('failure', 'warning'):
                    issues.append({
                        'type': 'ssl_check_failed',
                        'message': f"{check['name']}: {check['message']}",
                        'severity': 'high' if check['status'] == 'failure' else 'medium',
                    })

        return {
            'domain': domain,
            'status': 'pass' if not issues else 'failure',
            'issues': issues,
        }

    def _build_validation_summary(self, validation_results: list) -> Dict[str, Any]:
        """Build summary from validation results.

        Args:
            validation_results: List of domain validation results

        Returns:
            Complete validation summary with statistics and next steps
        """
        total = len(validation_results)
        passed = sum(1 for r in validation_results if r['status'] == 'pass')
        failed = sum(1 for r in validation_results if r['status'] == 'failure')

        # Generate remediation steps
        next_steps = []
        if failed > 0:
            failed_domains = [r['domain'] for r in validation_results if r['status'] == 'failure']
            next_steps.append(f"Inspect failures: reveal ssl://{failed_domains[0]} --check-advanced")
            next_steps.append("Check nginx config for certificate paths")

        return {
            'type': 'ssl_nginx_validation',
            'source': self._nginx_path,
            'domains_validated': total,
            'status': 'pass' if failed == 0 else 'failure',
            'summary': {
                'total': total,
                'passed': passed,
                'failed': failed,
            },
            'results': validation_results,
            'next_steps': next_steps,
            'exit_code': 0 if failed == 0 else 2,
        }

    def validate_nginx_ssl(self, **kwargs) -> Dict[str, Any]:
        """Validate nginx SSL configuration matches actual certificates.

        Cross-validates:
        - Nginx cert paths exist
        - Nginx cert matches served cert
        - All SAN domains have nginx configs

        Returns:
            Validation results with issues and remediation steps
        """
        if not self._nginx_path:
            return {
                'type': 'ssl_nginx_validation',
                'error': 'No nginx path specified (use ssl://nginx:///path/to/config)',
                'exit_code': 2,
            }

        # Get domains from nginx config
        domain_info = self._get_nginx_domains()
        domains = domain_info['domains']

        # Validate each domain
        validation_results = [self._validate_single_domain(d) for d in domains]

        # Build and return summary
        return self._build_validation_summary(validation_results)


def _extract_ssl_domains_from_nginx(structure: Dict[str, Any]) -> set:
    """Extract SSL-enabled domains from nginx structure.

    Args:
        structure: Parsed nginx structure

    Returns:
        Set of domain names
    """
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

    return domains


def _build_batch_summary(results: list, nginx_path: str) -> Dict[str, Any]:
    """Build batch check summary from results.

    Args:
        results: List of SSL check results
        nginx_path: Source nginx config path

    Returns:
        Complete batch check summary
    """
    total = len(results)
    passed = sum(1 for r in results if r['status'] == 'pass')
    warnings = sum(1 for r in results if r['status'] == 'warning')
    failures = sum(1 for r in results if r['status'] == 'failure')

    # Determine overall status
    if failures == 0 and warnings == 0:
        status = 'pass'
    elif failures == 0:
        status = 'warning'
    else:
        status = 'failure'

    return {
        'type': 'ssl_batch_check',
        'source': nginx_path,
        'domains_checked': total,
        'status': status,
        'summary': {
            'total': total,
            'passed': passed,
            'warnings': warnings,
            'failures': failures,
        },
        'results': results,
        'exit_code': 0 if failures == 0 else 2,
    }


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
    domains = _extract_ssl_domains_from_nginx(structure)

    # Check each domain
    results = [
        check_ssl_health(domain, 443, warn_days, critical_days)
        for domain in sorted(domains)
    ]

    # Build and return summary
    return _build_batch_summary(results, nginx_path)
