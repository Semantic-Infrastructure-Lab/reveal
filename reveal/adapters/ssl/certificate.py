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
                chain = []
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
        verification = {
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
                    leaf = self._parse_certificate(cert)
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
                for name in san_ext.value:
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
    checks = []
    overall_status = 'pass'

    try:
        leaf, chain, verification = fetcher.fetch_certificate_with_verification(
            host, port
        )

        # Check 1: Certificate expiry
        days = leaf.days_until_expiry
        if days < 0:
            status = 'failure'
            message = f'Certificate expired {abs(days)} days ago'
            overall_status = 'failure'
        elif days < critical_days:
            status = 'failure'
            message = f'Certificate expires in {days} days (critical threshold: {critical_days})'
            overall_status = 'failure'
        elif days < warn_days:
            status = 'warning'
            message = f'Certificate expires in {days} days (warning threshold: {warn_days})'
            if overall_status == 'pass':
                overall_status = 'warning'
        else:
            status = 'pass'
            message = f'Certificate valid for {days} days'

        checks.append({
            'name': 'certificate_expiry',
            'status': status,
            'value': f'{days} days',
            'threshold': f'{warn_days}/{critical_days} days',
            'message': message,
            'severity': 'high',
        })

        # Check 2: Chain verification
        if verification['verified']:
            checks.append({
                'name': 'chain_verification',
                'status': 'pass',
                'value': 'Valid',
                'threshold': 'Trusted chain',
                'message': 'Certificate chain verified by system trust store',
                'severity': 'high',
            })
        else:
            checks.append({
                'name': 'chain_verification',
                'status': 'warning',
                'value': 'Unverified',
                'threshold': 'Trusted chain',
                'message': f'Chain verification failed: {verification["error"]}',
                'severity': 'high',
            })
            if overall_status == 'pass':
                overall_status = 'warning'

        # Check 3: Hostname match
        if verification['hostname_match']:
            checks.append({
                'name': 'hostname_match',
                'status': 'pass',
                'value': 'Match',
                'threshold': f'Matches {host}',
                'message': f'Certificate valid for {host}',
                'severity': 'high',
            })
        else:
            # Check if hostname is in SANs
            hostname_in_san = host in leaf.san or any(
                san.startswith('*.') and host.endswith(san[1:])
                for san in leaf.san
            )
            if hostname_in_san:
                checks.append({
                    'name': 'hostname_match',
                    'status': 'pass',
                    'value': 'Match (SAN)',
                    'threshold': f'Matches {host}',
                    'message': f'Certificate valid for {host} via SAN',
                    'severity': 'high',
                })
            else:
                checks.append({
                    'name': 'hostname_match',
                    'status': 'failure',
                    'value': 'Mismatch',
                    'threshold': f'Matches {host}',
                    'message': f'Certificate not valid for {host}',
                    'severity': 'high',
                })
                overall_status = 'failure'

        # Advanced checks (only if requested)
        if advanced:
            advanced_checks = _run_advanced_checks(host, port, leaf)
            checks.extend(advanced_checks['checks'])
            # Update overall status if advanced checks fail
            if advanced_checks['has_failures'] and overall_status == 'pass':
                overall_status = 'warning'

        # Summary
        passed = sum(1 for c in checks if c['status'] == 'pass')
        warnings = sum(1 for c in checks if c['status'] == 'warning')
        failures = sum(1 for c in checks if c['status'] == 'failure')

        result = {
            'type': 'ssl_check_advanced' if advanced else 'ssl_check',
            'host': host,
            'port': port,
            'status': overall_status,
            'certificate': leaf.to_dict(),
            'checks': checks,
            'summary': {
                'total': len(checks),
                'passed': passed,
                'warnings': warnings,
                'failures': failures,
            },
            'exit_code': 0 if overall_status == 'pass' else (1 if overall_status == 'warning' else 2),
        }

        # Add next steps based on results
        if advanced:
            result['next_steps'] = _generate_remediation_steps(checks, host)

        return result

    except Exception as e:
        return {
            'type': 'ssl_check_advanced' if advanced else 'ssl_check',
            'host': host,
            'port': port,
            'status': 'failure',
            'error': str(e),
            'checks': [{
                'name': 'connection',
                'status': 'failure',
                'value': 'Failed',
                'threshold': 'Successful connection',
                'message': str(e),
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


def _run_advanced_checks(host: str, port: int, cert: CertificateInfo) -> Dict[str, Any]:
    """Run advanced SSL health checks.

    Args:
        host: Hostname
        port: Port number
        cert: Certificate info

    Returns:
        Dict with checks list and has_failures flag
    """
    checks = []
    has_failures = False

    # Check 1: TLS protocol version
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
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


def _generate_remediation_steps(checks: List[Dict[str, Any]], host: str) -> List[str]:
    """Generate remediation steps based on check results.

    Args:
        checks: List of check results
        host: Hostname

    Returns:
        List of remediation steps
    """
    steps = []

    # Check for specific issues
    has_expiry_issue = any(c['name'] == 'certificate_expiry' and c['status'] in ('failure', 'warning') for c in checks)
    has_chain_issue = any(c['name'] == 'chain_verification' and c['status'] != 'pass' for c in checks)
    has_hostname_issue = any(c['name'] == 'hostname_match' and c['status'] == 'failure' for c in checks)
    is_self_signed = any(c['name'] == 'self_signed' and c['value'] == 'Self-signed' for c in checks)
    has_tls_issue = any(c['name'] == 'tls_version' and c['status'] == 'warning' for c in checks)

    if has_expiry_issue:
        steps.append("Renew certificate before expiry (use certbot for Let's Encrypt)")

    if has_chain_issue:
        steps.append("Verify certificate chain includes intermediate certificates")
        steps.append("Check server configuration includes full certificate chain")

    if has_hostname_issue:
        steps.append(f"Verify certificate includes {host} in SANs")
        steps.append("Consider obtaining a new certificate with correct hostname")

    if is_self_signed:
        steps.append("Replace self-signed certificate with CA-signed certificate (e.g., Let's Encrypt)")

    if has_tls_issue:
        steps.append("Upgrade server to support TLS 1.2+ (disable TLS 1.0/1.1)")

    # Add general inspection steps
    if steps:
        steps.append(f"View full certificate: reveal ssl://{host}")
        steps.append(f"Check certificate chain: reveal ssl://{host}/chain")

    return steps
