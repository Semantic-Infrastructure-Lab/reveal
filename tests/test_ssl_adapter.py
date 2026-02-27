"""Tests for SSL adapter (ssl://)."""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import socket
import ssl
import io
import json
from contextlib import redirect_stdout

import sys
from pathlib import Path

# Add reveal to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.adapters.ssl import SSLAdapter, SSLFetcher, CertificateInfo
from reveal.adapters.ssl.certificate import check_ssl_health
from reveal.adapters.ssl.renderer import SSLRenderer


class TestSSLAdapterInit(unittest.TestCase):
    """Test SSLAdapter initialization and URI parsing."""

    def test_init_with_empty_uri(self):
        """Empty URI should raise TypeError (allows generic handler to try next pattern)."""
        with self.assertRaises(TypeError) as ctx:
            SSLAdapter("")
        self.assertIn("requires a connection string", str(ctx.exception))

    def test_init_with_minimal_uri(self):
        """Minimal URI (just ssl://) should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            SSLAdapter("ssl://")
        self.assertIn("requires hostname", str(ctx.exception))

    def test_init_with_hostname(self):
        """Basic hostname should parse correctly."""
        adapter = SSLAdapter("ssl://example.com")
        self.assertEqual(adapter.host, "example.com")
        self.assertEqual(adapter.port, 443)
        self.assertIsNone(adapter.element)

    def test_init_with_port(self):
        """Hostname with port should parse correctly."""
        adapter = SSLAdapter("ssl://example.com:8443")
        self.assertEqual(adapter.host, "example.com")
        self.assertEqual(adapter.port, 8443)

    def test_init_with_element(self):
        """URI with element should parse correctly."""
        adapter = SSLAdapter("ssl://example.com/san")
        self.assertEqual(adapter.host, "example.com")
        self.assertEqual(adapter.port, 443)
        self.assertEqual(adapter.element, "san")

    def test_init_with_port_and_element(self):
        """URI with port and element should parse correctly."""
        adapter = SSLAdapter("ssl://example.com:8443/chain")
        self.assertEqual(adapter.host, "example.com")
        self.assertEqual(adapter.port, 8443)
        self.assertEqual(adapter.element, "chain")

    def test_init_with_invalid_port(self):
        """Invalid port should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            SSLAdapter("ssl://example.com:notaport")
        self.assertIn("Invalid port", str(ctx.exception))


class TestCertificateInfo(unittest.TestCase):
    """Test CertificateInfo dataclass."""

    def setUp(self):
        """Create a sample certificate."""
        self.now = datetime.now(timezone.utc)
        self.cert = CertificateInfo(
            subject={'commonName': 'example.com', 'organizationName': 'Example Inc'},
            issuer={'commonName': 'Test CA', 'organizationName': 'Test Authority'},
            not_before=self.now - timedelta(days=30),
            not_after=self.now + timedelta(days=60),
            serial_number='123456789',
            version=3,
            san=['example.com', 'www.example.com', '*.example.com'],
        )

    def test_days_until_expiry(self):
        """days_until_expiry should return correct value."""
        # Allow for 1 day variance due to time-of-day in test execution
        self.assertIn(self.cert.days_until_expiry, [59, 60])

    def test_is_expired_false(self):
        """is_expired should return False for valid cert."""
        self.assertFalse(self.cert.is_expired)

    def test_is_expired_true(self):
        """is_expired should return True for expired cert."""
        expired_cert = CertificateInfo(
            subject={},
            issuer={},
            not_before=self.now - timedelta(days=90),
            not_after=self.now - timedelta(days=30),
            serial_number='123',
            version=3,
            san=[],
        )
        self.assertTrue(expired_cert.is_expired)

    def test_common_name(self):
        """common_name should return subject CN."""
        self.assertEqual(self.cert.common_name, 'example.com')

    def test_issuer_name(self):
        """issuer_name should return organization name."""
        self.assertEqual(self.cert.issuer_name, 'Test Authority')

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        d = self.cert.to_dict()
        self.assertEqual(d['common_name'], 'example.com')
        self.assertEqual(d['issuer_name'], 'Test Authority')
        self.assertIn(d['days_until_expiry'], [59, 60])  # Allow variance
        self.assertEqual(len(d['san']), 3)


class TestSSLFetcher(unittest.TestCase):
    """Test SSLFetcher certificate fetching."""

    def _mock_cert_dict(self, days_valid=60):
        """Create a mock certificate dict as returned by getpeercert()."""
        now = datetime.now(timezone.utc)
        not_before = now - timedelta(days=30)
        not_after = now + timedelta(days=days_valid)

        return {
            'subject': (
                (('commonName', 'example.com'),),
                (('organizationName', 'Example Inc'),),
            ),
            'issuer': (
                (('commonName', 'Test CA'),),
                (('organizationName', 'Test Authority'),),
            ),
            'notBefore': not_before.strftime('%b %d %H:%M:%S %Y GMT'),
            'notAfter': not_after.strftime('%b %d %H:%M:%S %Y GMT'),
            'serialNumber': '123456789ABCDEF',
            'version': 3,
            'subjectAltName': (
                ('DNS', 'example.com'),
                ('DNS', 'www.example.com'),
            ),
        }

    @patch('socket.create_connection')
    def test_fetch_certificate(self, mock_socket):
        """fetch_certificate should return parsed certificate."""
        # Setup mock
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = self._mock_cert_dict()
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock

        with patch('ssl.create_default_context') as mock_ctx:
            mock_context = MagicMock()
            mock_ctx.return_value = mock_context
            mock_context.wrap_socket.return_value.__enter__.return_value = mock_ssock

            fetcher = SSLFetcher()
            cert, chain = fetcher.fetch_certificate('example.com', 443)

            self.assertEqual(cert.common_name, 'example.com')
            self.assertEqual(len(cert.san), 2)

    @patch('socket.create_connection')
    def test_fetch_certificate_with_verification(self, mock_socket):
        """fetch_certificate_with_verification should return verification status."""
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = self._mock_cert_dict()
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock

        with patch('ssl.create_default_context') as mock_ctx:
            mock_context = MagicMock()
            mock_ctx.return_value = mock_context
            mock_context.wrap_socket.return_value.__enter__.return_value = mock_ssock

            fetcher = SSLFetcher()
            cert, chain, verification = fetcher.fetch_certificate_with_verification(
                'example.com', 443
            )

            self.assertEqual(cert.common_name, 'example.com')
            self.assertTrue(verification['verified'])

    def test_parse_binary_cert_extracts_dates(self):
        """Binary cert parsing should extract real dates, not default to now().

        Regression test for bug where binary cert parsing returned empty dates,
        causing _parse_cert_date to return datetime.now() and make valid certs
        appear expired.
        """
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import Encoding
        from cryptography.hazmat.backends import default_backend
        from datetime import timedelta

        # Generate a test certificate
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com"),
        ])

        # Cert valid for 365 days (NOT expiring today)
        not_before = datetime.now(timezone.utc) - timedelta(days=30)
        not_after = datetime.now(timezone.utc) + timedelta(days=335)

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        # Get DER-encoded binary cert
        binary_cert = cert.public_bytes(encoding=Encoding.DER)

        # Parse it using our method
        fetcher = SSLFetcher()
        parsed = fetcher._parse_binary_cert(binary_cert)

        # Verify dates are NOT empty (the bug was returning '')
        self.assertNotEqual(parsed['notBefore'], '')
        self.assertNotEqual(parsed['notAfter'], '')

        # Verify the dates are reasonable (not today)
        # Parse the dates back
        cert_info = fetcher._parse_certificate(parsed)
        self.assertGreater(cert_info.days_until_expiry, 300)  # Should be ~335 days
        self.assertFalse(cert_info.is_expired)


class TestSSLAdapterStructure(unittest.TestCase):
    """Test SSLAdapter.get_structure()."""

    def setUp(self):
        """Create adapter with mocked fetcher."""
        self.adapter = SSLAdapter("ssl://example.com")
        self.now = datetime.now(timezone.utc)

        # Mock the certificate
        self.mock_cert = CertificateInfo(
            subject={'commonName': 'example.com'},
            issuer={'organizationName': 'Test CA'},
            not_before=self.now - timedelta(days=30),
            not_after=self.now + timedelta(days=60),
            serial_number='123',
            version=3,
            san=['example.com', 'www.example.com'],
        )

        self.mock_verification = {
            'verified': True,
            'hostname_match': True,
            'error': None,
        }

    def test_get_structure_healthy(self):
        """get_structure should return healthy status for valid cert."""
        self.adapter._certificate = self.mock_cert
        self.adapter._verification = self.mock_verification

        result = self.adapter.get_structure()

        self.assertEqual(result['type'], 'ssl_certificate')
        self.assertEqual(result['host'], 'example.com')
        self.assertEqual(result['health_status'], 'HEALTHY')
        self.assertIn(result['days_until_expiry'], [59, 60])  # Allow variance

    def test_get_structure_warning(self):
        """get_structure should return warning for soon-to-expire cert."""
        self.mock_cert = CertificateInfo(
            subject={'commonName': 'example.com'},
            issuer={'organizationName': 'Test CA'},
            not_before=self.now - timedelta(days=330),
            not_after=self.now + timedelta(days=15),  # 15 days left
            serial_number='123',
            version=3,
            san=[],
        )
        self.adapter._certificate = self.mock_cert
        self.adapter._verification = self.mock_verification

        result = self.adapter.get_structure()
        self.assertEqual(result['health_status'], 'WARNING')

    def test_get_structure_critical(self):
        """get_structure should return critical for cert expiring soon."""
        self.mock_cert = CertificateInfo(
            subject={'commonName': 'example.com'},
            issuer={'organizationName': 'Test CA'},
            not_before=self.now - timedelta(days=358),
            not_after=self.now + timedelta(days=3),  # 3 days left
            serial_number='123',
            version=3,
            san=[],
        )
        self.adapter._certificate = self.mock_cert
        self.adapter._verification = self.mock_verification

        result = self.adapter.get_structure()
        self.assertEqual(result['health_status'], 'CRITICAL')

    def test_get_structure_expired(self):
        """get_structure should return expired for expired cert."""
        self.mock_cert = CertificateInfo(
            subject={'commonName': 'example.com'},
            issuer={'organizationName': 'Test CA'},
            not_before=self.now - timedelta(days=395),
            not_after=self.now - timedelta(days=30),  # Expired 30 days ago
            serial_number='123',
            version=3,
            san=[],
        )
        self.adapter._certificate = self.mock_cert
        self.adapter._verification = self.mock_verification

        result = self.adapter.get_structure()
        self.assertEqual(result['health_status'], 'EXPIRED')


class TestSSLAdapterElements(unittest.TestCase):
    """Test SSLAdapter.get_element()."""

    def setUp(self):
        """Create adapter with mocked certificate."""
        self.adapter = SSLAdapter("ssl://example.com")
        self.now = datetime.now(timezone.utc)

        self.adapter._certificate = CertificateInfo(
            subject={'commonName': 'example.com', 'organizationName': 'Example Inc'},
            issuer={'commonName': 'Test CA', 'organizationName': 'Test Authority'},
            not_before=self.now - timedelta(days=30),
            not_after=self.now + timedelta(days=60),
            serial_number='123456789',
            version=3,
            san=['example.com', 'www.example.com', '*.api.example.com'],
        )
        self.adapter._chain = []
        self.adapter._verification = {'verified': True, 'hostname_match': True, 'error': None}

    def test_get_element_san(self):
        """get_element('san') should return SANs."""
        result = self.adapter.get_element('san')

        self.assertEqual(result['type'], 'ssl_san')
        self.assertEqual(len(result['san']), 3)
        self.assertEqual(result['wildcard_entries'], ['*.api.example.com'])

    def test_get_element_issuer(self):
        """get_element('issuer') should return issuer details."""
        result = self.adapter.get_element('issuer')

        self.assertEqual(result['type'], 'ssl_issuer')
        self.assertEqual(result['issuer']['organizationName'], 'Test Authority')

    def test_get_element_subject(self):
        """get_element('subject') should return subject details."""
        result = self.adapter.get_element('subject')

        self.assertEqual(result['type'], 'ssl_subject')
        self.assertEqual(result['subject']['commonName'], 'example.com')

    def test_get_element_dates(self):
        """get_element('dates') should return validity dates."""
        result = self.adapter.get_element('dates')

        self.assertEqual(result['type'], 'ssl_dates')
        self.assertIn(result['days_until_expiry'], [59, 60])  # Allow variance
        self.assertFalse(result['is_expired'])

    def test_get_element_chain(self):
        """get_element('chain') should return chain info."""
        result = self.adapter.get_element('chain')

        self.assertEqual(result['type'], 'ssl_chain')
        self.assertEqual(result['chain_length'], 1)  # Just the leaf

    def test_get_element_unknown(self):
        """get_element with unknown element should return None."""
        result = self.adapter.get_element('unknown_element')
        self.assertIsNone(result)


class TestSSLHealthCheck(unittest.TestCase):
    """Test SSL health check functionality."""

    def _create_mock_fetcher(self, days_valid=60, verified=True):
        """Create a mock for SSLFetcher.fetch_certificate_with_verification."""
        now = datetime.now(timezone.utc)
        cert = CertificateInfo(
            subject={'commonName': 'example.com'},
            issuer={'organizationName': 'Test CA'},
            not_before=now - timedelta(days=30),
            not_after=now + timedelta(days=days_valid),
            serial_number='123',
            version=3,
            san=['example.com', 'www.example.com'],
        )
        verification = {
            'verified': verified,
            'hostname_match': verified,
            'error': None if verified else 'Certificate verification failed',
        }
        return cert, [], verification

    @patch.object(SSLFetcher, 'fetch_certificate_with_verification')
    def test_check_healthy(self, mock_fetch):
        """Health check should pass for healthy cert."""
        mock_fetch.return_value = self._create_mock_fetcher(days_valid=60)

        result = check_ssl_health('example.com', 443)

        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['summary']['passed'], 3)
        self.assertEqual(result['exit_code'], 0)

    @patch.object(SSLFetcher, 'fetch_certificate_with_verification')
    def test_check_warning_expiry(self, mock_fetch):
        """Health check should warn for cert expiring soon."""
        mock_fetch.return_value = self._create_mock_fetcher(days_valid=20)

        result = check_ssl_health('example.com', 443, warn_days=30)

        self.assertEqual(result['status'], 'warning')
        expiry_check = next(c for c in result['checks'] if c['name'] == 'certificate_expiry')
        self.assertEqual(expiry_check['status'], 'warning')

    @patch.object(SSLFetcher, 'fetch_certificate_with_verification')
    def test_check_critical_expiry(self, mock_fetch):
        """Health check should fail for cert expiring very soon."""
        mock_fetch.return_value = self._create_mock_fetcher(days_valid=3)

        result = check_ssl_health('example.com', 443, critical_days=7)

        self.assertEqual(result['status'], 'failure')
        expiry_check = next(c for c in result['checks'] if c['name'] == 'certificate_expiry')
        self.assertEqual(expiry_check['status'], 'failure')

    @patch.object(SSLFetcher, 'fetch_certificate_with_verification')
    def test_check_expired(self, mock_fetch):
        """Health check should fail for expired cert."""
        mock_fetch.return_value = self._create_mock_fetcher(days_valid=-10)

        result = check_ssl_health('example.com', 443)

        self.assertEqual(result['status'], 'failure')
        self.assertEqual(result['exit_code'], 2)

    @patch.object(SSLFetcher, 'fetch_certificate_with_verification')
    def test_check_verification_failure(self, mock_fetch):
        """Health check should warn on verification failure."""
        mock_fetch.return_value = self._create_mock_fetcher(days_valid=60, verified=False)

        result = check_ssl_health('example.com', 443)

        chain_check = next(c for c in result['checks'] if c['name'] == 'chain_verification')
        self.assertEqual(chain_check['status'], 'warning')

    @patch.object(SSLFetcher, 'fetch_certificate_with_verification')
    def test_check_connection_error(self, mock_fetch):
        """Health check should handle connection errors."""
        mock_fetch.side_effect = socket.error("Connection refused")

        result = check_ssl_health('example.com', 443)

        self.assertEqual(result['status'], 'failure')
        self.assertIn('error', result)
        self.assertEqual(result['exit_code'], 2)


class TestSSLRenderer(unittest.TestCase):
    """Test SSLRenderer output."""

    def test_render_structure_json(self):
        """render_structure with json format should output JSON."""
        result = {
            'type': 'ssl_certificate',
            'host': 'example.com',
            'port': 443,
            'common_name': 'example.com',
            'issuer': 'Test CA',
            'valid_from': '2024-01-01',
            'valid_until': '2024-12-31',
            'days_until_expiry': 60,
            'health_status': 'HEALTHY',
            'health_icon': '\u2705',
            'san_count': 3,
            'verification': {'chain_valid': True, 'hostname_match': True, 'error': None},
            'next_steps': [],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer.render_structure(result, format='json')

        output = f.getvalue()
        import json
        parsed = json.loads(output)
        self.assertEqual(parsed['host'], 'example.com')

    def test_render_structure_text(self):
        """render_structure with text format should output readable text."""
        result = {
            'type': 'ssl_certificate',
            'host': 'example.com',
            'port': 443,
            'common_name': 'example.com',
            'issuer': 'Test CA',
            'valid_from': '2024-01-01',
            'valid_until': '2024-12-31',
            'days_until_expiry': 60,
            'health_status': 'HEALTHY',
            'health_icon': '\u2705',
            'san_count': 3,
            'verification': {'chain_valid': True, 'hostname_match': True, 'error': None},
            'next_steps': ['reveal ssl://example.com/san'],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer.render_structure(result, format='text')

        output = f.getvalue()
        self.assertIn('example.com', output)
        self.assertIn('HEALTHY', output)
        self.assertIn('60 days', output)

    def test_render_check_pass(self):
        """render_check should format passing checks correctly."""
        result = {
            'type': 'ssl_check',
            'host': 'example.com',
            'port': 443,
            'status': 'pass',
            'certificate': {'common_name': 'example.com', 'days_until_expiry': 60, 'not_after': '2024-12-31'},
            'checks': [
                {'name': 'certificate_expiry', 'status': 'pass', 'message': 'Valid for 60 days'},
            ],
            'summary': {'total': 1, 'passed': 1, 'warnings': 0, 'failures': 0},
            'exit_code': 0,
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer.render_check(result, format='text')

        output = f.getvalue()
        self.assertIn('PASS', output)
        self.assertIn('Exit code: 0', output)

    def test_render_check_with_info_status(self):
        """render_check should display info status checks in Additional Information section."""
        result = {
            'type': 'ssl_check_advanced',
            'host': 'example.com',
            'port': 443,
            'status': 'pass',
            'certificate': {
                'common_name': 'example.com',
                'days_until_expiry': 60,
                'not_after': '2024-12-31'
            },
            'checks': [
                {'name': 'certificate_expiry', 'status': 'pass', 'message': 'Valid for 60 days'},
                {'name': 'tls_version', 'status': 'pass', 'message': 'Using TLSv1.3'},
                {'name': 'certificate_type', 'status': 'info', 'message': 'Wildcard certificate'},
                {'name': 'issuer_type', 'status': 'info', 'message': 'Issued by Test CA'},
            ],
            'summary': {'total': 4, 'passed': 2, 'warnings': 0, 'failures': 0},
            'exit_code': 0,
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer.render_check(result, format='text')

        output = f.getvalue()
        # Verify summary shows correct counts
        self.assertIn('2/4 passed', output)
        # Verify info section is present
        self.assertIn('Additional Information', output)
        # Verify info checks are displayed
        self.assertIn('certificate_type', output)
        self.assertIn('issuer_type', output)
        self.assertIn('Wildcard certificate', output)
        self.assertIn('Issued by Test CA', output)


class TestSSLAdapterHelp(unittest.TestCase):
    """Test SSLAdapter help system."""

    def test_get_help(self):
        """get_help should return help dict."""
        help_data = SSLAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertIn('name', help_data)
        self.assertEqual(help_data['name'], 'ssl')
        self.assertIn('elements', help_data)
        self.assertIn('san', help_data['elements'])


class TestSSLRendererFilters(unittest.TestCase):
    """Test SSLRenderer filter options (Issue #16).

    Tests --only-failures, --summary, and --expiring-within flags
    for batch SSL certificate checks.
    """

    def _create_batch_result(self):
        """Create a batch check result with mixed statuses."""
        return {
            'type': 'ssl_batch_check',
            'source': 'test-batch',
            'domains_checked': 4,
            'status': 'warning',
            'summary': {
                'total': 4,
                'passed': 2,
                'warnings': 1,
                'failures': 1,
            },
            'results': [
                {
                    'host': 'healthy1.example.com',
                    'status': 'pass',
                    'certificate': {'common_name': 'healthy1.example.com', 'days_until_expiry': 90},
                },
                {
                    'host': 'healthy2.example.com',
                    'status': 'pass',
                    'certificate': {'common_name': 'healthy2.example.com', 'days_until_expiry': 60},
                },
                {
                    'host': 'warning.example.com',
                    'status': 'warning',
                    'certificate': {'common_name': 'warning.example.com', 'days_until_expiry': 15},
                },
                {
                    'host': 'failed.example.com',
                    'status': 'failure',
                    'error': 'Connection refused',
                },
            ],
            'exit_code': 2,
        }

    def test_filter_results_only_failures(self):
        """_filter_results with only_failures should exclude passes."""
        result = self._create_batch_result()
        filtered = SSLRenderer._filter_results(result, only_failures=True)

        self.assertEqual(len(filtered['results']), 2)
        statuses = [r['status'] for r in filtered['results']]
        self.assertNotIn('pass', statuses)
        self.assertIn('warning', statuses)
        self.assertIn('failure', statuses)

    def test_filter_results_expiring_within(self):
        """_filter_results with expiring_days should filter by expiry."""
        result = self._create_batch_result()
        filtered = SSLRenderer._filter_results(result, expiring_days=30)

        # Should include warning (15 days) and failure (no cert - included)
        # Should exclude passes (90 and 60 days)
        self.assertEqual(len(filtered['results']), 2)
        hosts = [r['host'] for r in filtered['results']]
        self.assertIn('warning.example.com', hosts)
        self.assertIn('failed.example.com', hosts)

    def test_filter_results_combined(self):
        """_filter_results with both filters should apply both."""
        result = self._create_batch_result()
        # Add a pass that's expiring soon
        result['results'].append({
            'host': 'expiring-soon.example.com',
            'status': 'pass',
            'certificate': {'common_name': 'expiring-soon.example.com', 'days_until_expiry': 20},
        })

        # With only_failures, the expiring-soon pass should still be excluded
        filtered = SSLRenderer._filter_results(result, only_failures=True, expiring_days=30)

        hosts = [r['host'] for r in filtered['results']]
        self.assertNotIn('expiring-soon.example.com', hosts)
        self.assertIn('warning.example.com', hosts)

    def test_filter_results_single_check(self):
        """_filter_results should return unchanged for non-batch results."""
        single_result = {
            'type': 'ssl_check',
            'host': 'example.com',
            'status': 'pass',
        }
        filtered = SSLRenderer._filter_results(single_result, only_failures=True)
        self.assertEqual(filtered, single_result)

    def test_render_batch_check_summary_only(self):
        """render_check with summary_only should show counts only."""
        result = self._create_batch_result()

        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer.render_check(result, format='text', summary=True)

        output = f.getvalue()
        # Summary should show counts
        self.assertIn('4 domains', output)
        self.assertIn('Healthy', output)
        self.assertIn('Warning', output)
        self.assertIn('Failed', output)
        # Should NOT show individual host details
        self.assertNotIn('healthy1.example.com', output)
        self.assertNotIn('warning.example.com', output)

    def test_render_batch_check_only_failures(self):
        """render_check with only_failures should hide passes."""
        result = self._create_batch_result()

        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer.render_check(result, format='text', only_failures=True)

        output = f.getvalue()
        # Should show failures and warnings
        self.assertIn('warning.example.com', output)
        self.assertIn('failed.example.com', output)
        # Healthy section should not appear
        self.assertNotIn('healthy1.example.com', output)

    def test_render_batch_check_expiring_within(self):
        """render_check with expiring_within should filter by days."""
        result = self._create_batch_result()

        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer.render_check(result, format='text', expiring_within='30')

        output = f.getvalue()
        # Should show filter message
        self.assertIn('30 days', output)
        # Should show warning (15 days)
        self.assertIn('warning.example.com', output)

    def test_render_check_json_with_filters(self):
        """render_check with JSON format should still filter."""
        result = self._create_batch_result()

        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer.render_check(result, format='json', only_failures=True)

        output = f.getvalue()
        parsed = json.loads(output)
        self.assertEqual(len(parsed['results']), 2)


class TestSSLBatchDetailOutput(unittest.TestCase):
    """Tests for S1/S5: failure detail and expiry dates in batch output."""

    def _make_expired(self, host, days_ago):
        return {
            'host': host,
            'status': 'failure',
            'certificate': {
                'days_until_expiry': -days_ago,
                'not_after': '2025-11-25T12:00:00+00:00',
            },
        }

    def _make_error(self, host, error):
        return {'host': host, 'status': 'failure', 'error': error}

    def _make_warning(self, host, days, not_after='2026-03-14T12:00:00+00:00'):
        return {
            'host': host,
            'status': 'warning',
            'certificate': {'days_until_expiry': days, 'not_after': not_after},
        }

    def _make_pass(self, host, days, not_after='2026-05-28T12:00:00+00:00'):
        return {
            'host': host,
            'status': 'pass',
            'certificate': {'days_until_expiry': days, 'not_after': not_after},
        }

    # --- _classify_error ---

    def test_classify_dns_failure(self):
        self.assertEqual(
            SSLRenderer._classify_error('[Errno -2] Name or service not known'),
            'DNS FAILURE (NXDOMAIN)',
        )

    def test_classify_nxdomain(self):
        self.assertEqual(
            SSLRenderer._classify_error('getaddrinfo failed: NXDOMAIN'),
            'DNS FAILURE (NXDOMAIN)',
        )

    def test_classify_connection_refused(self):
        self.assertEqual(
            SSLRenderer._classify_error('[Errno 111] Connection refused'),
            'CONNECTION REFUSED',
        )

    def test_classify_timeout(self):
        self.assertIn('TIMEOUT', SSLRenderer._classify_error('timed out'))

    def test_classify_network_unreachable(self):
        self.assertIn('UNREACHABLE', SSLRenderer._classify_error('Network is unreachable'))

    def test_classify_cert_verify(self):
        self.assertIn('VERIFY', SSLRenderer._classify_error('certificate verify failed'))

    def test_classify_unknown_error(self):
        msg = 'something completely unexpected happened'
        result = SSLRenderer._classify_error(msg)
        self.assertTrue(result.startswith('ERROR:'))
        self.assertIn('something completely unexpected', result)

    # --- _format_expiry_date ---

    def test_format_expiry_date_iso(self):
        result = SSLRenderer._format_expiry_date('2025-11-25T12:00:00+00:00')
        self.assertEqual(result, 'Nov 25, 2025')

    def test_format_expiry_date_invalid(self):
        self.assertEqual(SSLRenderer._format_expiry_date('not-a-date'), '')
        self.assertEqual(SSLRenderer._format_expiry_date(None), '')

    # --- _render_failed_domains ---

    def test_failed_expired_shows_days_ago_and_date(self):
        failures = [self._make_expired('dashboard.web-expressions.net', 95)]
        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer._render_failed_domains(failures)
        out = f.getvalue()
        self.assertIn('EXPIRED 95 days ago', out)
        self.assertIn('Nov 25, 2025', out)
        self.assertIn('dashboard.web-expressions.net', out)

    def test_failed_dns_shows_label(self):
        failures = [self._make_error('social.orces.com', '[Errno -2] Name or service not known')]
        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer._render_failed_domains(failures)
        out = f.getvalue()
        self.assertIn('DNS FAILURE (NXDOMAIN)', out)
        self.assertIn('social.orces.com', out)

    def test_failed_connection_refused_shows_label(self):
        failures = [self._make_error('down.example.com', '[Errno 111] Connection refused')]
        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer._render_failed_domains(failures)
        self.assertIn('CONNECTION REFUSED', f.getvalue())

    def test_failed_columns_aligned(self):
        """All rows should be padded to the same host-column width."""
        failures = [
            self._make_expired('short.com', 10),
            self._make_error('a-much-longer-hostname.example.net', '[Errno -2] Name or service not known'),
        ]
        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer._render_failed_domains(failures)
        lines = [l for l in f.getvalue().splitlines() if 'short.com' in l or 'a-much-longer' in l]
        # Labels (EXPIRED / DNS FAILURE) should start at the same column position
        expired_col = lines[0].index('EXPIRED')
        dns_col = lines[1].index('DNS')
        self.assertEqual(expired_col, dns_col)

    def test_failed_no_date_when_not_after_missing(self):
        """Expired cert without not_after should not crash or show empty parens."""
        failures = [{'host': 'x.com', 'status': 'failure',
                     'certificate': {'days_until_expiry': -5}}]
        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer._render_failed_domains(failures)
        out = f.getvalue()
        self.assertIn('EXPIRED 5 days ago', out)
        self.assertNotIn('()', out)

    # --- _render_warning_domains ---

    def test_warning_shows_expires_in_and_date(self):
        warnings = [self._make_warning('soon.example.com', 12)]
        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer._render_warning_domains(warnings)
        out = f.getvalue()
        self.assertIn('expires in 12 days', out)
        self.assertIn('Mar 14, 2026', out)
        self.assertIn('soon.example.com', out)

    def test_warning_no_date_when_not_after_missing(self):
        warnings = [{'host': 'x.com', 'status': 'warning',
                     'certificate': {'days_until_expiry': 20}}]
        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer._render_warning_domains(warnings)
        out = f.getvalue()
        self.assertIn('expires in 20 days', out)
        self.assertNotIn('()', out)

    # --- _render_healthy_domains ---

    def test_healthy_shows_days_and_date(self):
        passes = [self._make_pass('ok.example.com', 90)]
        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer._render_healthy_domains(passes, only_failures=False)
        out = f.getvalue()
        self.assertIn('90 days', out)
        self.assertIn('May 28, 2026', out)
        self.assertIn('ok.example.com', out)

    def test_healthy_hidden_when_only_failures(self):
        passes = [self._make_pass('ok.example.com', 90)]
        f = io.StringIO()
        with redirect_stdout(f):
            SSLRenderer._render_healthy_domains(passes, only_failures=True)
        self.assertEqual(f.getvalue(), '')


class TestSSLAdapterNginxMode(unittest.TestCase):
    """Test SSLAdapter nginx integration (Issue #18).

    Tests ssl://nginx:///path syntax for extracting and checking
    SSL domains from nginx configuration files.
    """

    def test_parse_nginx_uri(self):
        """ssl://nginx:///path should set nginx mode."""
        adapter = SSLAdapter('ssl://nginx:///etc/nginx/nginx.conf')
        self.assertIsNone(adapter.host)  # Indicates batch mode
        self.assertEqual(adapter._nginx_path, '/etc/nginx/nginx.conf')

    def test_parse_nginx_uri_with_glob(self):
        """ssl://nginx:///path/*.conf should handle globs."""
        adapter = SSLAdapter('ssl://nginx:///etc/nginx/conf.d/*.conf')
        self.assertEqual(adapter._nginx_path, '/etc/nginx/conf.d/*.conf')

    def test_get_nginx_domains_structure(self):
        """_get_nginx_domains should return proper structure."""
        import tempfile
        import os

        # Create a test nginx config
        config_content = '''
server {
    listen 443 ssl;
    server_name secure.example.com api.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}

server {
    listen 80;
    server_name www.example.com;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config_content)
            config_file = f.name

        try:
            adapter = SSLAdapter(f'ssl://nginx://{config_file}')
            result = adapter.get_structure()

            self.assertEqual(result['type'], 'ssl_nginx_domains')
            self.assertEqual(result['files_processed'], 1)
            # Should only include SSL-enabled domains
            self.assertIn('secure.example.com', result['domains'])
            self.assertIn('api.example.com', result['domains'])
            # Should NOT include non-SSL domains
            self.assertNotIn('www.example.com', result['domains'])
        finally:
            os.unlink(config_file)

    def test_nginx_domains_filters_invalid(self):
        """extract_ssl_domains should filter localhost, wildcards, IPs."""
        import tempfile
        import os

        config_content = '''
server {
    listen 443 ssl;
    server_name valid.example.com localhost _ *.wildcard.com 192.168.1.1 internal;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config_content)
            config_file = f.name

        try:
            adapter = SSLAdapter(f'ssl://nginx://{config_file}')
            result = adapter.get_structure()

            # Should include valid domain
            self.assertIn('valid.example.com', result['domains'])
            # Should filter out invalid entries
            self.assertNotIn('localhost', result['domains'])
            self.assertNotIn('_', result['domains'])
            self.assertNotIn('*.wildcard.com', result['domains'])
            self.assertNotIn('192.168.1.1', result['domains'])
            self.assertNotIn('internal', result['domains'])  # No dot = not FQDN
        finally:
            os.unlink(config_file)


class TestStdinBatchSSLCheck(unittest.TestCase):
    """Test stdin batch SSL check aggregation (Issue #19).

    Tests that --stdin --check with SSL URIs properly aggregates results
    and supports batch filter flags (--summary, --only-failures, --expiring-within).
    """

    def test_collect_ssl_check_result_success(self):
        """_collect_ssl_check_result should return check result dict."""
        from reveal.cli.handlers import _collect_ssl_check_result
        from argparse import Namespace

        args = Namespace(check=True)

        with patch('reveal.adapters.ssl.adapter.SSLAdapter.check') as mock_check:
            mock_check.return_value = {
                'host': 'example.com',
                'port': 443,
                'status': 'pass',
                'summary': {'total': 1, 'passed': 1, 'warnings': 0, 'failures': 0},
                'exit_code': 0,
            }

            result = _collect_ssl_check_result('ssl://example.com', args)

            self.assertIsNotNone(result)
            self.assertEqual(result['host'], 'example.com')
            self.assertEqual(result['status'], 'pass')

    def test_collect_ssl_check_result_error(self):
        """_collect_ssl_check_result should return failure result on error."""
        from reveal.cli.handlers import _collect_ssl_check_result
        from argparse import Namespace

        args = Namespace(check=True)

        with patch('reveal.adapters.ssl.adapter.SSLAdapter.check') as mock_check:
            mock_check.side_effect = socket.error("Connection refused")

            result = _collect_ssl_check_result('ssl://bad.example.com', args)

            self.assertIsNotNone(result)
            self.assertEqual(result['status'], 'failure')
            self.assertIn('Connection refused', result.get('error', ''))

    def test_render_ssl_batch_results_aggregation(self):
        """_render_ssl_batch_results should build proper batch structure."""
        from reveal.cli.handlers import _render_ssl_batch_results
        from argparse import Namespace

        args = Namespace(
            format='text',
            only_failures=False,
            summary=True,
            expiring_within=None,
        )

        results = [
            {'host': 'a.com', 'status': 'pass', 'certificate': {'days_until_expiry': 60}},
            {'host': 'b.com', 'status': 'warning', 'certificate': {'days_until_expiry': 15}},
            {'host': 'c.com', 'status': 'failure', 'error': 'Connection refused'},
        ]

        f = io.StringIO()
        with redirect_stdout(f):
            _render_ssl_batch_results(results, args)

        output = f.getvalue()
        # Summary mode should show aggregated counts
        self.assertIn('3 domains', output)
        self.assertIn('Healthy', output)
        self.assertIn('Warning', output)
        self.assertIn('Failed', output)

    def test_render_ssl_batch_results_only_failures(self):
        """_render_ssl_batch_results should respect only_failures flag."""
        from reveal.cli.handlers import _render_ssl_batch_results
        from argparse import Namespace

        args = Namespace(
            format='text',
            only_failures=True,
            summary=False,
            expiring_within=None,
        )

        results = [
            {'host': 'healthy.com', 'status': 'pass', 'certificate': {'days_until_expiry': 60}},
            {'host': 'failed.com', 'status': 'failure', 'error': 'Connection refused'},
        ]

        f = io.StringIO()
        with redirect_stdout(f):
            _render_ssl_batch_results(results, args)

        output = f.getvalue()
        # Should show failure
        self.assertIn('failed.com', output)
        # Should NOT show healthy (only_failures=True)
        self.assertNotIn('healthy.com', output)


# ---------------------------------------------------------------------------
# S2: ssl://file:///path — cert file inspection
# ---------------------------------------------------------------------------

class TestSSLFileMode(unittest.TestCase):
    """Tests for ssl://file:///path cert file inspection (S2)."""

    def _make_cert_info(self, cn='file.example.com', days=90):
        expiry = datetime.now(timezone.utc) + timedelta(days=days)
        issue = datetime.now(timezone.utc) - timedelta(days=10)
        return CertificateInfo(
            subject={'commonName': cn},
            issuer={'organizationName': 'Test CA', 'commonName': 'Test CA Root'},
            not_before=issue,
            not_after=expiry,
            serial_number='AABBCC',
            version=3,
            san=[cn, f'www.{cn}'],
            signature_algorithm='sha256WithRSAEncryption',
        )

    def test_parse_connection_string_file_mode(self):
        """ssl://file:///path sets _cert_file_path and clears host."""
        adapter = SSLAdapter.__new__(SSLAdapter)
        adapter.host = None
        adapter.port = 443
        adapter.element = None
        adapter._certificate = None
        adapter._chain = []
        adapter._verification = None
        adapter._nginx_path = None
        adapter._cert_file_path = None
        adapter._fetcher = MagicMock()
        adapter._parse_connection_string('ssl://file:///var/cpanel/ssl/example.com/combined')
        assert adapter._cert_file_path == '/var/cpanel/ssl/example.com/combined'
        assert adapter.host is None

    def test_get_structure_file_mode_healthy(self):
        """get_structure() with file cert shows file_path and HEALTHY status."""
        cert = self._make_cert_info(days=90)
        adapter = SSLAdapter.__new__(SSLAdapter)
        adapter.host = None
        adapter.port = 443
        adapter.element = None
        adapter._certificate = cert
        adapter._chain = []
        adapter._verification = None
        adapter._nginx_path = None
        adapter._cert_file_path = '/path/to/cert.pem'
        adapter._fetcher = MagicMock()

        result = adapter.get_structure()
        assert result['source_type'] == 'file'
        assert result['file_path'] == '/path/to/cert.pem'
        assert result['health_status'] == 'HEALTHY'
        assert result['common_name'] == 'file.example.com'
        assert 'host' not in result
        assert 'verification' not in result

    def test_get_structure_file_mode_expired(self):
        """Expired on-disk cert shows EXPIRED health status."""
        cert = self._make_cert_info(days=-30)
        adapter = SSLAdapter.__new__(SSLAdapter)
        adapter.host = None
        adapter.port = 443
        adapter.element = None
        adapter._certificate = cert
        adapter._chain = []
        adapter._verification = None
        adapter._nginx_path = None
        adapter._cert_file_path = '/path/to/expired.pem'
        adapter._fetcher = MagicMock()

        result = adapter.get_structure()
        assert result['health_status'] == 'EXPIRED'
        assert result['days_until_expiry'] < 0

    def test_get_structure_file_mode_chain_count(self):
        """chain_certs count is included when chain is non-empty."""
        leaf = self._make_cert_info()
        chain = [self._make_cert_info(cn='intermediate.ca')]
        adapter = SSLAdapter.__new__(SSLAdapter)
        adapter.host = None
        adapter.port = 443
        adapter.element = None
        adapter._certificate = leaf
        adapter._chain = chain
        adapter._verification = None
        adapter._nginx_path = None
        adapter._cert_file_path = '/path/combined.pem'
        adapter._fetcher = MagicMock()

        result = adapter.get_structure()
        assert result.get('chain_certs') == 1

    def test_fetch_certificate_calls_load_from_file(self):
        """_fetch_certificate() delegates to load_certificate_from_file for file mode."""
        cert = self._make_cert_info()
        adapter = SSLAdapter.__new__(SSLAdapter)
        adapter.host = None
        adapter.port = 443
        adapter.element = None
        adapter._certificate = None
        adapter._chain = []
        adapter._verification = None
        adapter._nginx_path = None
        adapter._cert_file_path = '/fake/cert.pem'
        adapter._fetcher = MagicMock()

        with patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   return_value=(cert, [])) as mock_load:
            adapter._fetch_certificate()
            mock_load.assert_called_once_with('/fake/cert.pem')
            assert adapter._certificate is cert

    def test_next_steps_suggest_live_check(self):
        """File mode next_steps include a live ssl:// comparison hint."""
        cert = self._make_cert_info(cn='example.com', days=60)
        adapter = SSLAdapter.__new__(SSLAdapter)
        adapter.host = None
        adapter.port = 443
        adapter.element = None
        adapter._certificate = cert
        adapter._chain = []
        adapter._verification = None
        adapter._nginx_path = None
        adapter._cert_file_path = '/path/cert.pem'
        adapter._fetcher = MagicMock()

        result = adapter.get_structure()
        steps = ' '.join(result.get('next_steps', []))
        assert 'ssl://example.com' in steps or 'ssl://' in steps


if __name__ == '__main__':
    unittest.main()
