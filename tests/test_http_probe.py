"""Tests for the HTTP probe module (BACK-080).

Tests cover:
- Redirect following and chain recording
- HTTPS redirect detection
- Security header extraction
- Connection error handling
- ssl adapter --probe-http integration
- nginx adapter --probe integration
"""

import unittest
import urllib.error
from unittest.mock import MagicMock, patch
from io import StringIO


# ---------------------------------------------------------------------------
# Helpers — build fake urllib responses
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal urllib response substitute."""
    def __init__(self, status: int, headers: dict = None, url: str = ''):
        self._status = status
        self.headers = MagicMock()
        self.headers.get = lambda k, d=None: (headers or {}).get(k, d)
        self._url = url

    def getcode(self):
        return self._status


class _FakeHTTPError(urllib.error.HTTPError):
    """Substitute for urllib.error.HTTPError with injectable headers."""
    def __init__(self, code: int, headers: dict = None):
        super().__init__(url='http://example.com/', code=code, msg='', hdrs=None, fp=None)
        self._fake_headers = headers or {}
        self.headers = MagicMock()
        self.headers.get = lambda k, d=None: self._fake_headers.get(k, d)


# ---------------------------------------------------------------------------
# Unit tests for probe.py
# ---------------------------------------------------------------------------

from reveal.adapters.ssl.probe import (
    probe_http_redirect,
    _resolve_location,
    render_probe_text,
)


class TestResolveLocation(unittest.TestCase):
    def test_absolute_http_url(self):
        result = _resolve_location('http://example.com/', 'http://other.com/path')
        self.assertEqual(result, 'http://other.com/path')

    def test_absolute_https_url(self):
        result = _resolve_location('http://example.com/', 'https://example.com/')
        self.assertEqual(result, 'https://example.com/')

    def test_root_relative(self):
        result = _resolve_location('http://example.com/foo/', '/bar')
        self.assertEqual(result, 'http://example.com/bar')

    def test_relative_path(self):
        result = _resolve_location('http://example.com/', 'path/to/page')
        self.assertEqual(result, 'http://example.com/path/to/page')


class _MockOpener:
    """Fake urllib opener that replays a scripted sequence of responses."""

    def __init__(self, responses):
        # responses: list of (url_fragment, response_or_exception)
        self._responses = list(responses)
        self._index = 0

    def open(self, req, timeout=10):
        if self._index >= len(self._responses):
            raise urllib.error.URLError("No more mock responses")
        _, resp = self._responses[self._index]
        self._index += 1
        if isinstance(resp, Exception):
            raise resp
        return resp


class TestProbeHttpRedirect(unittest.TestCase):

    def test_plain_redirect_to_https(self):
        """HTTP 301 to HTTPS then 200 at HTTPS endpoint."""
        opener = _MockOpener([
            ('http://example.com/', _FakeHTTPError(301, {'Location': 'https://example.com/'})),
            ('https://example.com/', _FakeResponse(200, {
                'Strict-Transport-Security': 'max-age=31536000',
                'X-Content-Type-Options': 'nosniff',
                'X-Frame-Options': 'SAMEORIGIN',
            })),
        ])
        result = probe_http_redirect('example.com', _opener=opener)

        self.assertEqual(result['host'], 'example.com')
        self.assertTrue(result['redirects_to_https'])
        self.assertEqual(result['final_url'], 'https://example.com/')
        self.assertEqual(len(result['redirect_chain']), 2)
        self.assertEqual(result['redirect_chain'][0]['status'], 301)
        self.assertEqual(result['redirect_chain'][1]['status'], 200)
        self.assertIsNone(result['error'])

        hs = result['https_headers']
        self.assertEqual(hs['hsts'], 'max-age=31536000')
        self.assertEqual(hs['xcto'], 'nosniff')
        self.assertEqual(hs['xfo'], 'SAMEORIGIN')

    def test_direct_200_no_redirect(self):
        """Server returns 200 immediately — no redirect to HTTPS."""
        opener = _MockOpener([
            ('http://example.com/', _FakeResponse(200, {})),
        ])
        result = probe_http_redirect('example.com', _opener=opener)

        self.assertFalse(result['redirects_to_https'])
        self.assertEqual(result['final_url'], 'http://example.com/')
        self.assertEqual(len(result['redirect_chain']), 1)
        self.assertEqual(result['https_headers'], {})

    def test_connection_error(self):
        """URLError surfaces in the error field."""
        opener = _MockOpener([
            ('http://example.com/', urllib.error.URLError('Connection refused')),
        ])
        result = probe_http_redirect('example.com', _opener=opener)

        self.assertIsNotNone(result['error'])
        self.assertIn('Connection refused', result['error'])
        self.assertEqual(result['redirect_chain'], [])
        self.assertFalse(result['redirects_to_https'])

    def test_custom_port(self):
        """Non-80 port is included in the start_url."""
        opener = _MockOpener([
            ('http://example.com:8080/', _FakeResponse(200, {})),
        ])
        result = probe_http_redirect('example.com', port=8080, _opener=opener)
        self.assertEqual(result['start_url'], 'http://example.com:8080/')

    def test_missing_security_headers(self):
        """HTTPS endpoint with no security headers shows None values."""
        opener = _MockOpener([
            ('http://example.com/', _FakeHTTPError(301, {'Location': 'https://example.com/'})),
            ('https://example.com/', _FakeResponse(200, {})),
        ])
        result = probe_http_redirect('example.com', _opener=opener)
        hs = result['https_headers']
        self.assertIsNone(hs.get('hsts'))
        self.assertIsNone(hs.get('xcto'))
        self.assertIsNone(hs.get('xfo'))

    def test_multiple_hops(self):
        """302 → 301 → 200 chain is recorded fully."""
        opener = _MockOpener([
            ('http://example.com/', _FakeHTTPError(302, {'Location': 'http://www.example.com/'})),
            ('http://www.example.com/', _FakeHTTPError(301, {'Location': 'https://www.example.com/'})),
            ('https://www.example.com/', _FakeResponse(200, {})),
        ])
        result = probe_http_redirect('example.com', _opener=opener)
        self.assertEqual(len(result['redirect_chain']), 3)
        self.assertTrue(result['redirects_to_https'])
        self.assertEqual(result['hop_count'], 3)

    def test_redirect_missing_location_header(self):
        """3xx with no Location stops gracefully."""
        opener = _MockOpener([
            ('http://example.com/', _FakeHTTPError(301, {})),
        ])
        result = probe_http_redirect('example.com', _opener=opener)
        self.assertEqual(len(result['redirect_chain']), 1)


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------

class TestRenderProbeText(unittest.TestCase):

    def _capture(self, probe_result):
        from io import StringIO
        import sys
        old = sys.stdout
        sys.stdout = buf = StringIO()
        try:
            render_probe_text(probe_result)
        finally:
            sys.stdout = old
        return buf.getvalue()

    def test_redirects_to_https_shows_checkmark(self):
        probe = {
            'host': 'example.com',
            'start_url': 'http://example.com/',
            'redirect_chain': [
                {'url': 'http://example.com/', 'status': 301},
                {'url': 'https://example.com/', 'status': 200},
            ],
            'final_url': 'https://example.com/',
            'redirects_to_https': True,
            'hop_count': 2,
            'https_headers': {'hsts': 'max-age=31536000', 'xcto': 'nosniff', 'xfo': None, 'csp': None},
            'error': None,
        }
        out = self._capture(probe)
        self.assertIn('Redirects to HTTPS', out)
        self.assertIn('Strict-Transport-Security', out)
        self.assertIn('max-age=31536000', out)

    def test_no_redirect_shows_failure(self):
        probe = {
            'host': 'example.com',
            'start_url': 'http://example.com/',
            'redirect_chain': [{'url': 'http://example.com/', 'status': 200}],
            'final_url': 'http://example.com/',
            'redirects_to_https': False,
            'hop_count': 1,
            'https_headers': {},
            'error': None,
        }
        out = self._capture(probe)
        self.assertIn('Does NOT redirect to HTTPS', out)

    def test_connection_error_output(self):
        probe = {
            'host': 'dead.example.com',
            'start_url': 'http://dead.example.com/',
            'redirect_chain': [],
            'final_url': 'http://dead.example.com/',
            'redirects_to_https': False,
            'hop_count': 0,
            'https_headers': {},
            'error': 'Connection refused',
        }
        out = self._capture(probe)
        self.assertIn('Connection failed', out)
        self.assertIn('Connection refused', out)


# ---------------------------------------------------------------------------
# ssl adapter --probe-http integration
# ---------------------------------------------------------------------------

class TestSSLAdapterProbeHttp(unittest.TestCase):

    def test_probe_http_attached_to_result(self):
        """get_structure with probe_http=True attaches http_probe key."""
        from reveal.adapters.ssl.adapter import SSLAdapter

        # Build a minimal adapter in file-cert mode to avoid network
        # We only test that the flag flows through; the actual network call
        # is covered by probe module tests above.
        mock_probe_result = {
            'host': 'example.com',
            'redirect_chain': [],
            'final_url': 'http://example.com/',
            'redirects_to_https': False,
            'hop_count': 0,
            'https_headers': {},
            'error': None,
        }

        adapter = SSLAdapter.__new__(SSLAdapter)
        adapter.host = 'example.com'
        adapter.port = 443
        adapter.element = None
        adapter._nginx_path = None
        adapter._cert_file_path = None
        adapter._certificate = None
        adapter._chain = []
        adapter._verification = {}

        # Patch _fetch_certificate to no-op and probe_http_redirect to mock
        with patch.object(adapter, '_fetch_certificate'):
            with patch('reveal.adapters.ssl.adapter.probe_http_redirect',
                       return_value=mock_probe_result) as mock_probe:
                result = adapter.get_structure(probe_http=True)

        mock_probe.assert_called_once_with('example.com')
        self.assertIn('http_probe', result)
        self.assertEqual(result['http_probe'], mock_probe_result)

    def test_probe_http_not_called_without_flag(self):
        """get_structure without probe_http=True skips the probe."""
        from reveal.adapters.ssl.adapter import SSLAdapter

        adapter = SSLAdapter.__new__(SSLAdapter)
        adapter.host = 'example.com'
        adapter.port = 443
        adapter.element = None
        adapter._nginx_path = None
        adapter._cert_file_path = None
        adapter._certificate = None
        adapter._chain = []
        adapter._verification = {}

        with patch.object(adapter, '_fetch_certificate'):
            with patch('reveal.adapters.ssl.adapter.probe_http_redirect') as mock_probe:
                result = adapter.get_structure()

        mock_probe.assert_not_called()
        self.assertNotIn('http_probe', result)

    def test_probe_http_skipped_for_file_mode(self):
        """probe_http=True is ignored when adapter is in file cert mode."""
        from reveal.adapters.ssl.adapter import SSLAdapter
        import tempfile, os
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        import datetime

        # Create a minimal self-signed cert for file mode
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"test")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .sign(key, hashes.SHA256())
        )
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
            cert_path = f.name

        try:
            adapter = SSLAdapter(f'ssl://file://{cert_path}')
            with patch('reveal.adapters.ssl.adapter.probe_http_redirect') as mock_probe:
                result = adapter.get_structure(probe_http=True)
            mock_probe.assert_not_called()
            self.assertNotIn('http_probe', result)
        finally:
            os.unlink(cert_path)


# ---------------------------------------------------------------------------
# nginx adapter --probe integration
# ---------------------------------------------------------------------------

class TestNginxAdapterProbe(unittest.TestCase):

    def test_probe_attached_to_vhost_summary(self):
        """get_structure with probe=True and a domain attaches http_probe."""
        from reveal.adapters.nginx.adapter import NginxUriAdapter

        mock_probe_result = {
            'host': 'example.com',
            'redirect_chain': [{'url': 'http://example.com/', 'status': 301},
                                {'url': 'https://example.com/', 'status': 200}],
            'final_url': 'https://example.com/',
            'redirects_to_https': True,
            'hop_count': 2,
            'https_headers': {'hsts': 'max-age=31536000'},
            'error': None,
        }
        mock_summary = {
            'type': 'nginx_vhost_summary',
            'domain': 'example.com',
            'config_file': '/etc/nginx/sites-enabled/example.com',
            'symlink': {},
            'ports': [],
            'upstreams': {},
            'auth': {},
            'locations': [],
            'warnings': [],
            'next_steps': [],
        }

        adapter = NginxUriAdapter.__new__(NginxUriAdapter)
        adapter.connection_string = 'nginx://example.com'
        adapter.domain = 'example.com'
        adapter.element = None

        with patch.object(adapter, '_get_vhost_summary', return_value=mock_summary):
            with patch('reveal.adapters.nginx.adapter.probe_http_redirect',
                       return_value=mock_probe_result) as mock_probe:
                result = adapter.get_structure(probe=True)

        mock_probe.assert_called_once_with('example.com')
        self.assertIn('http_probe', result)
        self.assertEqual(result['http_probe'], mock_probe_result)

    def test_probe_not_called_without_flag(self):
        """get_structure without probe=True skips the probe."""
        from reveal.adapters.nginx.adapter import NginxUriAdapter

        mock_summary = {'type': 'nginx_vhost_summary', 'domain': 'example.com',
                        'config_file': None, 'symlink': {}, 'ports': [], 'upstreams': {},
                        'auth': {}, 'locations': [], 'warnings': [], 'next_steps': []}

        adapter = NginxUriAdapter.__new__(NginxUriAdapter)
        adapter.connection_string = 'nginx://example.com'
        adapter.domain = 'example.com'
        adapter.element = None

        with patch.object(adapter, '_get_vhost_summary', return_value=mock_summary):
            with patch('reveal.adapters.nginx.adapter.probe_http_redirect') as mock_probe:
                result = adapter.get_structure()

        mock_probe.assert_not_called()
        self.assertNotIn('http_probe', result)

    def test_probe_not_called_without_domain(self):
        """probe=True is ignored in overview mode (no domain)."""
        from reveal.adapters.nginx.adapter import NginxUriAdapter

        adapter = NginxUriAdapter.__new__(NginxUriAdapter)
        adapter.connection_string = 'nginx://'
        adapter.domain = None
        adapter.element = None

        with patch.object(adapter, '_get_overview', return_value={'type': 'nginx_sites_overview', 'sites': []}):
            with patch('reveal.adapters.nginx.adapter.probe_http_redirect') as mock_probe:
                result = adapter.get_structure(probe=True)

        mock_probe.assert_not_called()
        self.assertNotIn('http_probe', result)


if __name__ == '__main__':
    unittest.main()
