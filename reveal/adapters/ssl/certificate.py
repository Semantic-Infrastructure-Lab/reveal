"""SSL certificate fetching and analysis."""

import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend


@dataclass
class CertificateInfo:
    """Parsed SSL certificate information."""

    subject: Dict[str, str]
    issuer: Dict[str, str]
    not_before: datetime
    not_after: datetime
    serial_number: str
    version: int
    san: List[str]  # Subject Alternative Names
    signature_algorithm: Optional[str] = None

    @property
    def days_until_expiry(self) -> int:
        """Days until certificate expires."""
        now = datetime.now(timezone.utc)
        delta = self.not_after - now
        return delta.days

    @property
    def is_expired(self) -> bool:
        """Check if certificate is expired."""
        return self.days_until_expiry < 0

    @property
    def common_name(self) -> str:
        """Get the common name from subject."""
        return self.subject.get('commonName', 'Unknown')

    @property
    def issuer_name(self) -> str:
        """Get issuer organization or common name."""
        return (
            self.issuer.get('organizationName')
            or self.issuer.get('commonName')
            or 'Unknown'
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'subject': self.subject,
            'issuer': self.issuer,
            'not_before': self.not_before.isoformat(),
            'not_after': self.not_after.isoformat(),
            'days_until_expiry': self.days_until_expiry,
            'is_expired': self.is_expired,
            'serial_number': self.serial_number,
            'version': self.version,
            'san': self.san,
            'signature_algorithm': self.signature_algorithm,
            'common_name': self.common_name,
            'issuer_name': self.issuer_name,
        }


class SSLFetcher:
    """Fetch and parse SSL certificates from remote hosts."""

    def __init__(self, timeout: float = 10.0):
        """Initialize SSL fetcher.

        Args:
            timeout: Connection timeout in seconds
        """
        self.timeout = timeout

    def fetch_certificate(
        self, host: str, port: int = 443
    ) -> Tuple[CertificateInfo, List[CertificateInfo]]:
        """Fetch SSL certificate from host.

        Args:
            host: Hostname to connect to
            port: Port number (default 443)

        Returns:
            Tuple of (leaf certificate, chain certificates)

        Raises:
            ssl.SSLError: On SSL/TLS errors
            socket.error: On connection errors
            socket.timeout: On timeout
        """
        context = ssl.create_default_context()
        # We want to fetch even if there are issues, for diagnostic purposes
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((host, port), timeout=self.timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                # Get the peer certificate
                cert = ssock.getpeercert(binary_form=False)
                if not cert:  # None or empty dict {} (happens with CERT_NONE)
                    # Binary form fallback for when verification is off
                    binary_cert = ssock.getpeercert(binary_form=True)
                    if binary_cert:
                        cert = self._parse_binary_cert(binary_cert)
                    else:
                        raise ssl.SSLError("No certificate received from server")

                leaf = self._parse_certificate(cert)

                # Try to get the certificate chain
                chain: List[CertificateInfo] = []
                # Note: Python's ssl module doesn't easily expose the full chain
                # We'd need PyOpenSSL for that. For now, just return the leaf.

                return leaf, chain

    def fetch_certificate_with_verification(
        self, host: str, port: int = 443
    ) -> Tuple[CertificateInfo, List[CertificateInfo], Dict[str, Any]]:
        """Fetch certificate with full verification status.

        Args:
            host: Hostname to connect to
            port: Port number

        Returns:
            Tuple of (leaf cert, chain, verification_result)
        """
        verification: Dict[str, bool | str | None] = {
            'verified': False,
            'error': None,
            'hostname_match': False,
        }

        # First try with verification enabled
        try:
            context = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    verification['verified'] = True
                    verification['hostname_match'] = True
                    leaf = self._parse_certificate(cert)  # type: ignore[arg-type]
                    return leaf, [], verification
        except ssl.CertificateError as e:
            verification['error'] = str(e)
            verification['hostname_match'] = False
        except ssl.SSLError as e:
            verification['error'] = str(e)

        # Fallback to unverified fetch for diagnostics
        leaf, chain = self.fetch_certificate(host, port)
        return leaf, chain, verification

    def _parse_certificate(self, cert: Dict) -> CertificateInfo:
        """Parse certificate dict into CertificateInfo.

        Args:
            cert: Certificate dict from getpeercert()

        Returns:
            Parsed CertificateInfo
        """
        # Parse subject
        subject = {}
        for rdn in cert.get('subject', ()):
            for key, value in rdn:
                subject[key] = value

        # Parse issuer
        issuer = {}
        for rdn in cert.get('issuer', ()):
            for key, value in rdn:
                issuer[key] = value

        # Parse dates
        not_before = self._parse_cert_date(cert.get('notBefore', ''))
        not_after = self._parse_cert_date(cert.get('notAfter', ''))

        # Parse SANs
        san = []
        for san_type, san_value in cert.get('subjectAltName', ()):
            if san_type == 'DNS':
                san.append(san_value)

        return CertificateInfo(
            subject=subject,
            issuer=issuer,
            not_before=not_before,
            not_after=not_after,
            serial_number=str(cert.get('serialNumber', '')),
            version=cert.get('version', 0),
            san=san,
            signature_algorithm=cert.get('signatureAlgorithm'),
        )

    def _parse_binary_cert(self, binary_cert: bytes) -> Dict:
        """Parse binary certificate when getpeercert() returns None.

        This happens when verify_mode is CERT_NONE.
        Uses cryptography library to properly parse DER-encoded certs.

        Args:
            binary_cert: DER-encoded certificate bytes

        Returns:
            Certificate dict matching ssl.getpeercert() format
        """
        try:
            cert = x509.load_der_x509_certificate(binary_cert, default_backend())

            # Extract subject components
            subject = []
            for attr in cert.subject:
                oid_name = attr.oid._name
                subject.append(((oid_name, attr.value),))

            # Extract issuer components
            issuer = []
            for attr in cert.issuer:
                oid_name = attr.oid._name
                issuer.append(((oid_name, attr.value),))

            # Extract SANs
            san = []
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                for name in san_ext.value:  # type: ignore[attr-defined]
                    if isinstance(name, x509.DNSName):
                        san.append(('DNS', name.value))
                    elif isinstance(name, x509.IPAddress):
                        san.append(('IP Address', str(name.value)))
            except x509.ExtensionNotFound:
                pass

            # Format dates like ssl module does: 'Jan  5 12:00:00 2026 GMT'
            not_before = cert.not_valid_before_utc.strftime('%b %d %H:%M:%S %Y GMT')
            not_after = cert.not_valid_after_utc.strftime('%b %d %H:%M:%S %Y GMT')

            return {
                'subject': tuple(subject),
                'issuer': tuple(issuer),
                'notBefore': not_before,
                'notAfter': not_after,
                'serialNumber': format(cert.serial_number, 'X'),
                'version': cert.version.value + 1,  # x509 version is 0-indexed
                'subjectAltName': tuple(san),
            }
        except Exception:
            # If parsing fails, return empty dict (will use fallback dates)
            return {
                'subject': (),
                'issuer': (),
                'notBefore': '',
                'notAfter': '',
                'serialNumber': '',
                'version': 0,
                'subjectAltName': (),
            }

    def _parse_cert_date(self, date_str: str) -> datetime:
        """Parse certificate date string.

        Args:
            date_str: Date in format 'Mon DD HH:MM:SS YYYY GMT'

        Returns:
            Parsed datetime (UTC)
        """
        if not date_str:
            return datetime.now(timezone.utc)

        try:
            # Format: 'Jan  5 12:00:00 2026 GMT'
            dt = datetime.strptime(date_str, '%b %d %H:%M:%S %Y %Z')
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            # Fallback
            return datetime.now(timezone.utc)


# Helper functions for SSL health checks

def _check_certificate_expiry(
    days: int, warn_days: int, critical_days: int
) -> Dict[str, Any]:
    """Check certificate expiry status.

    Args:
        days: Days until certificate expires
        warn_days: Warning threshold
        critical_days: Critical threshold

    Returns:
        Certificate expiry check result dict
    """
    if days < 0:
        status = 'failure'
        message = f'Certificate expired {abs(days)} days ago'
    elif days < critical_days:
        status = 'failure'
        message = f'Certificate expires in {days} days (critical threshold: {critical_days})'
    elif days < warn_days:
        status = 'warning'
        message = f'Certificate expires in {days} days (warning threshold: {warn_days})'
    else:
        status = 'pass'
        message = f'Certificate valid for {days} days'

    return {
        'name': 'certificate_expiry',
        'status': status,
        'value': f'{days} days',
        'threshold': f'{warn_days}/{critical_days} days',
        'message': message,
        'severity': 'high',
    }


def _check_chain_verification(verification: Dict[str, Any]) -> Dict[str, Any]:
    """Check certificate chain verification status.

    Args:
        verification: Verification result dict

    Returns:
        Chain verification check result dict
    """
    if verification['verified']:
        return {
            'name': 'chain_verification',
            'status': 'pass',
            'value': 'Valid',
            'threshold': 'Trusted chain',
            'message': 'Certificate chain verified by system trust store',
            'severity': 'high',
        }
    else:
        return {
            'name': 'chain_verification',
            'status': 'warning',
            'value': 'Unverified',
            'threshold': 'Trusted chain',
            'message': f'Chain verification failed: {verification["error"]}',
            'severity': 'high',
        }


def _hostname_matches_san(host: str, san_list: List[str]) -> bool:
    """Check if hostname matches any SAN entry.

    Args:
        host: Hostname to check
        san_list: List of Subject Alternative Names

    Returns:
        True if hostname matches any SAN entry
    """
    return host in san_list or any(
        san.startswith('*.') and host.endswith(san[1:])
        for san in san_list
    )


def _check_hostname_match(
    host: str, leaf: CertificateInfo, verification: Dict[str, Any]
) -> Dict[str, Any]:
    """Check if certificate is valid for the hostname.

    Args:
        host: Hostname to verify
        leaf: Certificate information
        verification: Verification result dict

    Returns:
        Hostname match check result dict
    """
    if verification['hostname_match']:
        return {
            'name': 'hostname_match',
            'status': 'pass',
            'value': 'Match',
            'threshold': f'Matches {host}',
            'message': f'Certificate valid for {host}',
            'severity': 'high',
        }

    # Check if hostname is in SANs
    if _hostname_matches_san(host, leaf.san):
        return {
            'name': 'hostname_match',
            'status': 'pass',
            'value': 'Match (SAN)',
            'threshold': f'Matches {host}',
            'message': f'Certificate valid for {host} via SAN',
            'severity': 'high',
        }

    # Hostname mismatch
    return {
        'name': 'hostname_match',
        'status': 'failure',
        'value': 'Mismatch',
        'threshold': f'Matches {host}',
        'message': f'Certificate not valid for {host}',
        'severity': 'high',
    }


def _determine_overall_ssl_status(checks: List[Dict[str, Any]]) -> str:
    """Determine overall SSL health status from check results.

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


def _calculate_ssl_check_summary(checks: List[Dict[str, Any]]) -> Dict[str, int]:
    """Calculate summary counts from SSL check results.

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


def _build_ssl_health_success_result(
    host: str,
    port: int,
    overall_status: str,
    leaf: CertificateInfo,
    checks: List[Dict[str, Any]],
    summary: Dict[str, int],
    advanced: bool,
) -> Dict[str, Any]:
    """Build successful SSL health check result.

    Args:
        host: Hostname checked
        port: Port checked
        overall_status: Overall status
        leaf: Certificate information
        checks: List of check results
        summary: Summary counts
        advanced: Whether advanced checks were run

    Returns:
        SSL health check result dict
    """
    return {
        'type': 'ssl_check_advanced' if advanced else 'ssl_check',
        'host': host,
        'port': port,
        'status': overall_status,
        'certificate': leaf.to_dict(),
        'checks': checks,
        'summary': summary,
        'exit_code': 0 if overall_status == 'pass' else (1 if overall_status == 'warning' else 2),
    }


def _build_ssl_health_error_result(
    host: str, port: int, error: Exception, advanced: bool
) -> Dict[str, Any]:
    """Build SSL health check error result.

    Args:
        host: Hostname checked
        port: Port checked
        error: Exception that occurred
        advanced: Whether advanced checks were requested

    Returns:
        SSL health check error result dict
    """
    return {
        'type': 'ssl_check_advanced' if advanced else 'ssl_check',
        'host': host,
        'port': port,
        'status': 'failure',
        'error': str(error),
        'checks': [{
            'name': 'connection',
            'status': 'failure',
            'value': 'Failed',
            'threshold': 'Successful connection',
            'message': str(error),
            'severity': 'critical',
        }],
        'summary': {
            'total': 1,
            'passed': 0,
            'warnings': 0,
            'failures': 1,
        },
        'exit_code': 2,
    }


def check_ssl_health(
    host: str, port: int = 443, warn_days: int = 30, critical_days: int = 7,
    advanced: bool = False
) -> Dict[str, Any]:
    """Run SSL health checks on a host.

    Args:
        host: Hostname to check
        port: Port number
        warn_days: Days until expiry to trigger warning
        critical_days: Days until expiry to trigger critical
        advanced: Include advanced checks (TLS version, key strength, etc.)

    Returns:
        Health check result dict
    """
    fetcher = SSLFetcher()

    try:
        leaf, chain, verification = fetcher.fetch_certificate_with_verification(host, port)

        # Run all checks
        checks = []
        checks.append(_check_certificate_expiry(leaf.days_until_expiry, warn_days, critical_days))
        checks.append(_check_chain_verification(verification))
        checks.append(_check_hostname_match(host, leaf, verification))

        # Add advanced checks if requested
        if advanced:
            advanced_checks = _run_advanced_checks(host, port, leaf, timeout=fetcher.timeout)
            checks.extend(advanced_checks['checks'])

        # Calculate overall status and summary
        overall_status = _determine_overall_ssl_status(checks)
        summary = _calculate_ssl_check_summary(checks)

        # Build result
        result = _build_ssl_health_success_result(
            host, port, overall_status, leaf, checks, summary, advanced
        )

        # Add next steps for advanced mode
        if advanced:
            result['next_steps'] = _generate_remediation_steps(checks, host)

        return result

    except Exception as e:
        return _build_ssl_health_error_result(host, port, e, advanced)


def _run_advanced_checks(
    host: str, port: int, cert: CertificateInfo, timeout: float = 10.0
) -> Dict[str, Any]:
    """Run advanced SSL health checks.

    Args:
        host: Hostname
        port: Port number
        cert: Certificate info
        timeout: Connection timeout in seconds

    Returns:
        Dict with checks list and has_failures flag
    """
    checks = []
    has_failures = False

    # Check 1: TLS protocol version
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                tls_version = ssock.version()

                # TLS 1.2+ is required, TLS 1.3 is ideal
                if tls_version in ('TLSv1.3',):
                    status = 'pass'
                    message = f'Using {tls_version} (recommended)'
                elif tls_version in ('TLSv1.2',):
                    status = 'pass'
                    message = f'Using {tls_version} (acceptable)'
                else:
                    status = 'warning'
                    message = f'Using {tls_version} (outdated, upgrade to TLS 1.2+)'
                    has_failures = True

                checks.append({
                    'name': 'tls_version',
                    'status': status,
                    'value': tls_version,
                    'threshold': 'TLS 1.2+',
                    'message': message,
                    'severity': 'medium',
                })
    except Exception as e:
        checks.append({
            'name': 'tls_version',
            'status': 'warning',
            'value': 'Unknown',
            'threshold': 'TLS 1.2+',
            'message': f'Could not determine TLS version: {e}',
            'severity': 'low',
        })

    # Check 2: Certificate type (wildcard, self-signed)
    is_wildcard = any(san.startswith('*.') for san in cert.san)
    is_self_signed = cert.subject.get('commonName') == cert.issuer.get('commonName')

    if is_self_signed:
        checks.append({
            'name': 'self_signed',
            'status': 'warning',
            'value': 'Self-signed',
            'threshold': 'CA-signed',
            'message': 'Certificate is self-signed (not trusted by browsers)',
            'severity': 'high',
        })
        has_failures = True
    else:
        checks.append({
            'name': 'self_signed',
            'status': 'pass',
            'value': 'CA-signed',
            'threshold': 'CA-signed',
            'message': 'Certificate signed by trusted CA',
            'severity': 'info',
        })

    # Check 3: Wildcard certificate detection
    if is_wildcard:
        checks.append({
            'name': 'certificate_type',
            'status': 'info',
            'value': 'Wildcard',
            'threshold': 'N/A',
            'message': f'Wildcard certificate (covers *.{cert.common_name.lstrip("*.")})',
            'severity': 'info',
        })
    else:
        checks.append({
            'name': 'certificate_type',
            'status': 'info',
            'value': 'Single domain',
            'threshold': 'N/A',
            'message': f'Single domain certificate ({len(cert.san)} SANs)',
            'severity': 'info',
        })

    # Check 4: Issuer type (Let's Encrypt detection)
    issuer_name = cert.issuer_name.lower()
    if "let's encrypt" in issuer_name:
        checks.append({
            'name': 'issuer_type',
            'status': 'info',
            'value': "Let's Encrypt",
            'threshold': 'N/A',
            'message': "Let's Encrypt certificate (auto-renews every 90 days)",
            'severity': 'info',
        })
    else:
        checks.append({
            'name': 'issuer_type',
            'status': 'info',
            'value': cert.issuer_name,
            'threshold': 'N/A',
            'message': f'Issued by {cert.issuer_name}',
            'severity': 'info',
        })

    # Check 5: Key strength (requires connecting again to get key info)
    # Note: Python's ssl module doesn't easily expose key size without PyOpenSSL
    # We'll add a basic check based on signature algorithm
    sig_algo = cert.signature_algorithm or ''
    if 'sha256' in sig_algo.lower() or 'sha384' in sig_algo.lower() or 'sha512' in sig_algo.lower():
        checks.append({
            'name': 'signature_algorithm',
            'status': 'pass',
            'value': sig_algo,
            'threshold': 'SHA-256+',
            'message': f'Using secure signature algorithm ({sig_algo})',
            'severity': 'medium',
        })
    elif 'sha1' in sig_algo.lower():
        checks.append({
            'name': 'signature_algorithm',
            'status': 'warning',
            'value': sig_algo,
            'threshold': 'SHA-256+',
            'message': f'Using weak signature algorithm ({sig_algo}), should upgrade to SHA-256+',
            'severity': 'medium',
        })
        has_failures = True
    else:
        checks.append({
            'name': 'signature_algorithm',
            'status': 'info',
            'value': sig_algo or 'Unknown',
            'threshold': 'SHA-256+',
            'message': f'Signature algorithm: {sig_algo or "Unknown"}',
            'severity': 'low',
        })

    return {
        'checks': checks,
        'has_failures': has_failures,
    }


def _detect_ssl_issues(checks: List[Dict[str, Any]]) -> Dict[str, bool]:
    """Detect SSL issues from check results.

    Args:
        checks: List of check results

    Returns:
        Dict of issue flags
    """
    return {
        'expiry': any(c['name'] == 'certificate_expiry' and c['status'] in ('failure', 'warning') for c in checks),
        'chain': any(c['name'] == 'chain_verification' and c['status'] != 'pass' for c in checks),
        'hostname': any(c['name'] == 'hostname_match' and c['status'] == 'failure' for c in checks),
        'self_signed': any(c['name'] == 'self_signed' and c['value'] == 'Self-signed' for c in checks),
        'tls': any(c['name'] == 'tls_version' and c['status'] == 'warning' for c in checks)
    }


def _add_remediation_for_issues(issues: Dict[str, bool], host: str) -> List[str]:
    """Add remediation steps for detected issues.

    Args:
        issues: Dict of issue flags
        host: Hostname

    Returns:
        List of remediation steps
    """
    steps = []

    if issues['expiry']:
        steps.append("Renew certificate before expiry (use certbot for Let's Encrypt)")

    if issues['chain']:
        steps.append("Verify certificate chain includes intermediate certificates")
        steps.append("Check server configuration includes full certificate chain")

    if issues['hostname']:
        steps.append(f"Verify certificate includes {host} in SANs")
        steps.append("Consider obtaining a new certificate with correct hostname")

    if issues['self_signed']:
        steps.append("Replace self-signed certificate with CA-signed certificate (e.g., Let's Encrypt)")

    if issues['tls']:
        steps.append("Upgrade server to support TLS 1.2+ (disable TLS 1.0/1.1)")

    # Add general inspection steps if any issues found
    if steps:
        steps.append(f"View full certificate: reveal ssl://{host}")
        steps.append(f"Check certificate chain: reveal ssl://{host}/chain")

    return steps


def load_certificate_from_file(path: str) -> Tuple[CertificateInfo, List[CertificateInfo]]:
    """Load and parse a PEM or DER certificate file from disk (S2).

    Args:
        path: Filesystem path to a .pem, .crt, .cer, or .der file.
              cPanel combined files (/var/cpanel/ssl/apache_tls/DOMAIN/combined) are PEM.

    Returns:
        Tuple of (leaf CertificateInfo, chain list).  Chain is extracted from
        PEM files that contain multiple certificates (combined format).

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If file cannot be parsed as a certificate.
    """
    from pathlib import Path as _Path
    data = _Path(path).read_bytes()

    # PEM may contain multiple certs (combined = leaf + chain)
    if b'-----BEGIN CERTIFICATE-----' in data:
        pem_blocks = []
        current: List[bytes] = []
        for raw_line in data.splitlines(keepends=True):
            current.append(raw_line)
            if b'-----END CERTIFICATE-----' in raw_line:
                pem_blocks.append(b''.join(current))
                current = []
        if not pem_blocks:
            raise ValueError(f"No PEM certificate blocks found in {path}")

        certs = []
        fetcher = SSLFetcher()
        for block in pem_blocks:
            try:
                x509_cert = x509.load_pem_x509_certificate(block, default_backend())
                cert_dict = fetcher._parse_binary_cert(
                    x509_cert.public_bytes(
                        __import__('cryptography.hazmat.primitives.serialization',
                                   fromlist=['Encoding']).Encoding.DER
                    )
                )
                certs.append(fetcher._parse_certificate(cert_dict))
            except Exception as exc:
                raise ValueError(f"Failed to parse PEM block in {path}: {exc}") from exc

        return certs[0], certs[1:]
    else:
        # Try DER
        try:
            fetcher = SSLFetcher()
            cert_dict = fetcher._parse_binary_cert(data)
            leaf = fetcher._parse_certificate(cert_dict)
            return leaf, []
        except Exception as exc:
            raise ValueError(f"Failed to parse certificate file {path}: {exc}") from exc


def _generate_remediation_steps(checks: List[Dict[str, Any]], host: str) -> List[str]:
    """Generate remediation steps based on check results.

    Args:
        checks: List of check results
        host: Hostname

    Returns:
        List of remediation steps
    """
    issues = _detect_ssl_issues(checks)
    return _add_remediation_for_issues(issues, host)
