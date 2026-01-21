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
    host: str, port: int = 443, warn_days: int = 30, critical_days: int = 7
) -> Dict[str, Any]:
    """Run SSL health checks on a host.

    Args:
        host: Hostname to check
        port: Port number
        warn_days: Days until expiry to trigger warning
        critical_days: Days until expiry to trigger critical

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

        # Summary
        passed = sum(1 for c in checks if c['status'] == 'pass')
        warnings = sum(1 for c in checks if c['status'] == 'warning')
        failures = sum(1 for c in checks if c['status'] == 'failure')

        return {
            'type': 'ssl_check',
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

    except Exception as e:
        return {
            'type': 'ssl_check',
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
