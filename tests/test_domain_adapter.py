"""Tests for domain:// adapter (DNS, WHOIS, SSL inspection)."""

import unittest
from unittest.mock import patch, MagicMock, Mock
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.adapters.domain import DomainAdapter


class TestDomainAdapterInit(unittest.TestCase):
    """Test domain adapter initialization."""

    def test_init_with_empty_uri(self):
        """Test initialization with empty URI raises TypeError."""
        with self.assertRaises(TypeError):
            adapter = DomainAdapter("")

    def test_init_with_minimal_uri(self):
        """Test initialization with minimal URI (domain only)."""
        adapter = DomainAdapter("domain://example.com")
        self.assertEqual(adapter.domain, "example.com")
        self.assertIsNone(adapter.element)

    def test_init_with_domain_only(self):
        """Test initialization with domain name only (no protocol)."""
        adapter = DomainAdapter("example.com")
        self.assertEqual(adapter.domain, "example.com")

    def test_init_with_element(self):
        """Test initialization with element (e.g., /dns)."""
        adapter = DomainAdapter("domain://example.com/dns")
        self.assertEqual(adapter.domain, "example.com")
        self.assertEqual(adapter.element, "dns")

    def test_init_with_subdomain(self):
        """Test initialization with subdomain."""
        adapter = DomainAdapter("domain://www.example.com")
        self.assertEqual(adapter.domain, "www.example.com")

    def test_init_with_complex_domain(self):
        """Test initialization with complex domain."""
        adapter = DomainAdapter("domain://api.staging.example.co.uk/ssl")
        self.assertEqual(adapter.domain, "api.staging.example.co.uk")
        self.assertEqual(adapter.element, "ssl")


class TestDomainAdapterStructure(unittest.TestCase):
    """Test domain adapter structure retrieval."""

    @patch('reveal.adapters.domain.adapter.get_dns_summary')
    @patch('reveal.adapters.domain.adapter.DomainAdapter._get_ssl_summary')
    def test_get_structure_basic(self, mock_ssl_summary, mock_dns):
        """Test getting basic domain structure."""
        mock_dns.return_value = {
            'nameservers': ['ns1.example.com', 'ns2.example.com'],
            'a_records': ['192.0.2.1'],
            'has_mx': True,
            'error': None
        }
        mock_ssl_summary.return_value = {
            'status': 'PASS',
            'days_until_expiry': 60,
            'issuer': 'Let\'s Encrypt'
        }

        adapter = DomainAdapter("domain://example.com")
        structure = adapter.get_structure()

        self.assertEqual(structure['domain'], 'example.com')
        self.assertIn('dns', structure)
        self.assertEqual(structure['dns']['nameservers'], ['ns1.example.com', 'ns2.example.com'])
        self.assertIn('ssl', structure)

    @patch('reveal.adapters.domain.adapter.get_dns_summary')
    @patch('reveal.adapters.domain.adapter.DomainAdapter._get_ssl_summary')
    def test_get_structure_dns_error(self, mock_ssl_summary, mock_dns):
        """Test structure when DNS lookup fails."""
        mock_dns.return_value = {
            'nameservers': [],
            'a_records': [],
            'has_mx': False,
            'error': 'NXDOMAIN'
        }
        mock_ssl_summary.return_value = {}

        adapter = DomainAdapter("domain://invalid-domain-xyz123.com")
        structure = adapter.get_structure()

        self.assertEqual(structure['domain'], 'invalid-domain-xyz123.com')
        self.assertEqual(structure['dns']['error'], 'NXDOMAIN')
        self.assertEqual(structure['dns']['a_records'], [])

    @patch('reveal.adapters.domain.adapter.get_dns_summary')
    @patch('reveal.adapters.domain.adapter.DomainAdapter._get_ssl_summary')
    def test_get_structure_next_steps(self, mock_ssl_summary, mock_dns):
        """Test that structure includes next_steps."""
        mock_dns.return_value = {
            'nameservers': ['ns1.example.com'],
            'a_records': ['192.0.2.1'],
            'has_mx': True,
            'error': None
        }
        mock_ssl_summary.return_value = {}

        adapter = DomainAdapter("domain://example.com")
        structure = adapter.get_structure()

        self.assertIn('next_steps', structure)
        self.assertIsInstance(structure['next_steps'], list)


class TestDomainAdapterElements(unittest.TestCase):
    """Test domain adapter element retrieval."""

    @patch('reveal.adapters.domain.adapter.DomainAdapter._get_dns_records')
    def test_get_element_dns(self, mock_dns):
        """Test getting DNS element."""
        mock_dns.return_value = {
            'domain': 'example.com',
            'records': {
                'a': ['192.0.2.1', '192.0.2.2'],
                'aaaa': ['2001:db8::1'],
                'mx': ['10 mail.example.com'],
                'txt': ['v=spf1 include:_spf.example.com ~all'],
                'ns': ['ns1.example.com', 'ns2.example.com'],
                'cname': [],
                'soa': ['ns1.example.com hostmaster.example.com 2024010100 3600 900 604800 86400']
            }
        }

        adapter = DomainAdapter("domain://example.com/dns")
        element = adapter.get_element('dns')

        self.assertIsNotNone(element)
        self.assertEqual(element['domain'], 'example.com')
        self.assertIn('records', element)
        self.assertEqual(element['records']['a'], ['192.0.2.1', '192.0.2.2'])

    @patch('reveal.adapters.domain.adapter.DomainAdapter._get_ssl_status')
    def test_get_element_ssl(self, mock_ssl):
        """Test getting SSL element (delegates to SSL adapter)."""
        mock_ssl.return_value = {
            'status': 'PASS',
            'days_until_expiry': 60,
            'issuer': 'Let\'s Encrypt',
            'subject': 'example.com',
            'valid_from': '2024-01-01',
            'valid_until': '2024-03-01'
        }

        adapter = DomainAdapter("domain://example.com/ssl")
        element = adapter.get_element('ssl')

        self.assertIsNotNone(element)
        self.assertEqual(element['status'], 'PASS')
        self.assertEqual(element['days_until_expiry'], 60)

    @patch('reveal.adapters.domain.adapter.DomainAdapter._get_whois_info')
    def test_get_element_whois(self, mock_whois):
        """Test getting WHOIS element (not yet implemented)."""
        mock_whois.return_value = {}
        adapter = DomainAdapter("domain://example.com/whois")
        element = adapter.get_element('whois')

        # WHOIS not implemented yet, should return empty dict
        self.assertEqual(element, {})

    @patch('reveal.adapters.domain.adapter.DomainAdapter._get_registrar_info')
    def test_get_element_registrar(self, mock_registrar):
        """Test getting registrar element."""
        mock_registrar.return_value = {}
        adapter = DomainAdapter("domain://example.com/registrar")
        element = adapter.get_element('registrar')

        # Should return registrar info (may be empty without WHOIS)
        self.assertEqual(element, {})

    def test_get_element_unknown(self):
        """Test getting unknown element."""
        adapter = DomainAdapter("domain://example.com/unknown")
        element = adapter.get_element('unknown')

        self.assertIsNone(element)


class TestDomainAdapterCheck(unittest.TestCase):
    """Test domain adapter health check functionality."""

    @patch('reveal.adapters.domain.adapter.check_dns_resolution')
    @patch('reveal.adapters.domain.adapter.check_nameserver_response')
    @patch('reveal.adapters.domain.adapter.check_dns_propagation')
    @patch('reveal.adapters.ssl.certificate.check_ssl_health')
    def test_check_all_pass(self, mock_ssl, mock_propagation, mock_nameserver, mock_resolution):
        """Test health check when all checks pass."""
        mock_resolution.return_value = {
            'name': 'dns_resolution',
            'status': 'pass',
            'value': '1 IP',
            'threshold': 'Resolves',
            'message': 'DNS resolves correctly',
            'severity': 'high'
        }
        mock_nameserver.return_value = {
            'name': 'nameserver_response',
            'status': 'pass',
            'value': 'Responsive',
            'threshold': 'Responsive',
            'message': 'Nameservers responding',
            'severity': 'medium'
        }
        mock_propagation.return_value = {
            'name': 'dns_propagation',
            'status': 'pass',
            'value': 'Propagated',
            'threshold': 'Propagated',
            'message': 'DNS propagated',
            'severity': 'medium'
        }
        mock_ssl.return_value = {
            'status': 'pass',
            'certificate': {'days_until_expiry': 60}
        }

        adapter = DomainAdapter("domain://example.com")
        result = adapter.check()

        self.assertIn('summary', result)
        # At least some checks should have passed
        passed = result['summary'].get('passed', 0)
        self.assertTrue(passed > 0, f"Expected passed > 0, got {passed}")

    @patch('reveal.adapters.domain.adapter.check_dns_resolution')
    @patch('reveal.adapters.domain.adapter.check_nameserver_response')
    @patch('reveal.adapters.domain.adapter.check_dns_propagation')
    @patch('reveal.adapters.ssl.certificate.check_ssl_health')
    def test_check_with_failures(self, mock_ssl, mock_propagation, mock_nameserver, mock_resolution):
        """Test health check with some failures."""
        mock_resolution.return_value = {
            'name': 'dns_resolution',
            'status': 'failure',
            'value': 'No resolution',
            'threshold': 'Resolves',
            'message': 'DNS resolution failed',
            'severity': 'critical'
        }
        mock_nameserver.return_value = {
            'name': 'nameserver_response',
            'status': 'pass',
            'value': 'Responsive',
            'threshold': 'Responsive',
            'message': 'Nameservers responding',
            'severity': 'medium'
        }
        mock_propagation.return_value = {
            'name': 'dns_propagation',
            'status': 'warning',
            'value': 'Partial',
            'threshold': 'Propagated',
            'message': 'Partial propagation',
            'severity': 'medium'
        }
        mock_ssl.return_value = {
            'status': 'pass',
            'certificate': {'days_until_expiry': 60}
        }

        adapter = DomainAdapter("domain://example.com")
        result = adapter.check()

        self.assertIn('summary', result)
        # Should have at least one failure
        failures = result['summary'].get('failures', 0)
        self.assertTrue(failures > 0, f"Expected failures > 0, got {failures}")

    @patch('reveal.adapters.domain.adapter.check_dns_resolution')
    @patch('reveal.adapters.domain.adapter.check_nameserver_response')
    @patch('reveal.adapters.domain.adapter.check_dns_propagation')
    @patch('reveal.adapters.ssl.certificate.check_ssl_health')
    def test_check_only_failures_flag(self, mock_ssl, mock_propagation, mock_nameserver, mock_resolution):
        """Test health check with --only-failures flag."""
        mock_resolution.return_value = {
            'name': 'dns_resolution',
            'status': 'failure',
            'value': 'No resolution',
            'threshold': 'Resolves',
            'message': 'DNS resolution failed',
            'severity': 'critical'
        }
        mock_nameserver.return_value = {
            'name': 'nameserver_response',
            'status': 'pass',
            'value': 'Responsive',
            'threshold': 'Responsive',
            'message': 'Nameservers responding',
            'severity': 'medium'
        }
        mock_propagation.return_value = {
            'name': 'dns_propagation',
            'status': 'pass',
            'value': 'Propagated',
            'threshold': 'Propagated',
            'message': 'DNS propagated',
            'severity': 'medium'
        }
        mock_ssl.return_value = {
            'status': 'pass',
            'certificate': {'days_until_expiry': 60}
        }

        adapter = DomainAdapter("domain://example.com")
        result = adapter.check(only_failures=True)

        # When only_failures=True, should still have summary
        self.assertIn('summary', result)
        # Should have at least one failure recorded
        failures = result['summary'].get('failures', 0)
        self.assertTrue(failures > 0, f"Expected failures > 0, got {failures}")


class TestDomainAdapterSchema(unittest.TestCase):
    """Test domain adapter schema generation."""

    def test_get_schema(self):
        """Test getting machine-readable schema."""
        schema = DomainAdapter.get_schema()

        self.assertEqual(schema['adapter'], 'domain')
        self.assertIn('description', schema)
        self.assertIn('uri_syntax', schema)
        self.assertIn('elements', schema)
        self.assertIn('dns', schema['elements'])
        self.assertIn('whois', schema['elements'])
        self.assertIn('ssl', schema['elements'])
        self.assertIn('registrar', schema['elements'])

    def test_schema_cli_flags(self):
        """Test schema includes CLI flags."""
        schema = DomainAdapter.get_schema()

        self.assertIn('cli_flags', schema)
        self.assertIn('--check', schema['cli_flags'])
        self.assertIn('--advanced', schema['cli_flags'])
        self.assertIn('--only-failures', schema['cli_flags'])

    def test_schema_output_types(self):
        """Test schema includes output type definitions."""
        schema = DomainAdapter.get_schema()

        self.assertIn('output_types', schema)
        self.assertIsInstance(schema['output_types'], list)
        # Should have domain_overview and domain_dns types
        output_type_names = [ot['type'] for ot in schema['output_types']]
        self.assertIn('domain_overview', output_type_names)
        self.assertIn('domain_dns', output_type_names)


class TestDomainAdapterHelp(unittest.TestCase):
    """Test domain adapter help system."""

    def test_get_help(self):
        """Test getting help documentation."""
        help_data = DomainAdapter.get_help()

        self.assertIsNotNone(help_data)
        self.assertIsInstance(help_data, dict)


class TestDomainAdapterIntegration(unittest.TestCase):
    """Integration tests for domain adapter end-to-end."""

    @patch('reveal.adapters.domain.adapter.get_dns_summary')
    @patch('reveal.adapters.domain.adapter.DomainAdapter._get_ssl_summary')
    @patch('reveal.adapters.domain.adapter.DomainAdapter._get_dns_records')
    def test_full_domain_inspection_flow(self, mock_dns_records, mock_ssl_summary, mock_dns_summary):
        """Test full domain inspection workflow."""
        mock_dns_summary.return_value = {
            'nameservers': ['ns1.example.com'],
            'a_records': ['192.0.2.1'],
            'has_mx': True,
            'error': None
        }
        mock_ssl_summary.return_value = {}
        mock_dns_records.return_value = {
            'domain': 'example.com',
            'records': {
                'a': ['192.0.2.1'],
                'aaaa': [],
                'mx': ['10 mail.example.com'],
                'txt': [],
                'ns': ['ns1.example.com'],
                'cname': [],
                'soa': []
            }
        }

        # Test overview
        adapter = DomainAdapter("domain://example.com")
        structure = adapter.get_structure()
        self.assertEqual(structure['domain'], 'example.com')
        self.assertIn('dns', structure)

        # Test DNS element
        dns_element = adapter.get_element('dns')
        self.assertIsNotNone(dns_element)
        self.assertIn('records', dns_element)


if __name__ == '__main__':
    unittest.main()
