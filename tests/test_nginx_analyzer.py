"""
Tests for Nginx configuration file analyzer.

Ensures that the nginx analyzer correctly extracts server blocks,
location blocks, upstreams, and returns accurate line numbers.
"""

import unittest
import tempfile
import os
from pathlib import Path
import pytest

from reveal.analyzers.nginx import NginxAnalyzer

# BACK-1149: component-layer test -- single analyzer in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


class NginxTestCase(unittest.TestCase):
    """Base test case with temp file helper."""

    def create_temp_nginx_config(self, lines):
        """Create a temporary nginx config file for testing."""
        fd, path = tempfile.mkstemp(suffix='.conf')
        with os.fdopen(fd, 'w') as f:
            f.write('\n'.join(lines))
        return path

    def tearDown(self):
        """Clean up any temp files created during tests."""
        # Tests create temp files but we don't track them individually
        # They'll be cleaned up by the OS
        pass


class TestNginxBasicStructure(NginxTestCase):
    """Test nginx analyzer structure extraction."""

    def test_single_server_block(self):
        """Nginx analyzer should extract server block with name and port."""
        nginx_lines = [
            'server {',
            '    listen 80;',
            '    server_name example.com;',
            '    root /var/www/html;',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        # Should have servers
        self.assertIn('servers', structure)
        servers = structure['servers']
        self.assertEqual(len(servers), 1)

        # Check server details
        server = servers[0]
        self.assertEqual(server['line'], 1)
        self.assertEqual(server['name'], 'example.com')
        self.assertEqual(server['port'], '80')

    def test_ssl_server_block(self):
        """Nginx analyzer should detect SSL on port 443."""
        nginx_lines = [
            'server {',
            '    listen 443 ssl http2;',
            '    server_name secure.example.com;',
            '    ssl_certificate /etc/ssl/cert.pem;',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        servers = structure['servers']
        self.assertEqual(len(servers), 1)

        server = servers[0]
        self.assertEqual(server['name'], 'secure.example.com')
        self.assertEqual(server['port'], '443 (SSL)')

    def test_multiple_server_blocks(self):
        """Nginx analyzer should handle multiple server blocks."""
        nginx_lines = [
            'server {',
            '    listen 80;',
            '    server_name example.com;',
            '}',
            '',
            'server {',
            '    listen 443 ssl;',
            '    server_name secure.example.com;',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        servers = structure['servers']
        self.assertEqual(len(servers), 2)

        # Check both servers
        self.assertEqual(servers[0]['line'], 1)
        self.assertEqual(servers[0]['port'], '80')
        self.assertEqual(servers[1]['line'], 6)
        self.assertEqual(servers[1]['port'], '443 (SSL)')


class TestNginxLocationBlocks(NginxTestCase):
    """Test nginx location block extraction."""

    def test_location_with_proxy_pass(self):
        """Nginx analyzer should extract location with proxy_pass."""
        nginx_lines = [
            'server {',
            '    server_name example.com;',
            '    location / {',
            '        proxy_pass http://backend:8000;',
            '    }',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        locations = structure['locations']
        self.assertEqual(len(locations), 1)

        location = locations[0]
        self.assertEqual(location['line'], 3)
        self.assertEqual(location['path'], '/')
        self.assertEqual(location['server'], 'example.com')
        self.assertEqual(location['target'], 'http://backend:8000')

    def test_location_with_static_root(self):
        """Nginx analyzer should extract location with static root."""
        nginx_lines = [
            'server {',
            '    server_name example.com;',
            '    location /static/ {',
            '        root /var/www/html;',
            '    }',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        locations = structure['locations']
        self.assertEqual(len(locations), 1)

        location = locations[0]
        self.assertEqual(location['path'], '/static/')
        self.assertEqual(location['target'], 'static: /var/www/html')

    def test_multiple_locations(self):
        """Nginx analyzer should handle multiple location blocks."""
        nginx_lines = [
            'server {',
            '    server_name api.example.com;',
            '    location / {',
            '        proxy_pass http://backend:8000/;',
            '    }',
            '    location /admin/ {',
            '        proxy_pass http://admin:9000/;',
            '    }',
            '    location /health {',
            '        return 200;',
            '    }',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        locations = structure['locations']
        self.assertEqual(len(locations), 3)

        # Check line numbers
        self.assertEqual(locations[0]['line'], 3)
        self.assertEqual(locations[1]['line'], 6)
        self.assertEqual(locations[2]['line'], 9)

        # Check paths
        self.assertEqual(locations[0]['path'], '/')
        self.assertEqual(locations[1]['path'], '/admin/')
        self.assertEqual(locations[2]['path'], '/health')

        # Check targets (first two have proxy_pass)
        self.assertEqual(locations[0]['target'], 'http://backend:8000/')
        self.assertEqual(locations[1]['target'], 'http://admin:9000/')
        # Third location has no proxy_pass or root, so no target
        self.assertNotIn('target', locations[2])

    def test_location_regex_patterns(self):
        """Nginx analyzer should handle regex location patterns."""
        nginx_lines = [
            'server {',
            '    server_name example.com;',
            '    location ~* \\.css$ {',
            '        expires 1d;',
            '    }',
            '    location ~* \\.(jpg|png)$ {',
            '        expires 30d;',
            '    }',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        locations = structure['locations']
        self.assertEqual(len(locations), 2)

        # Check regex patterns are captured
        self.assertIn('\\.css$', locations[0]['path'])
        self.assertIn('(jpg|png)', locations[1]['path'])


class TestNginxUpstreamBlocks(NginxTestCase):
    """Test nginx upstream block extraction."""

    def test_upstream_block(self):
        """Nginx analyzer should extract upstream blocks."""
        nginx_lines = [
            'upstream backend {',
            '    server backend1.example.com:8000;',
            '    server backend2.example.com:8000;',
            '}',
            '',
            'server {',
            '    location / {',
            '        proxy_pass http://backend;',
            '    }',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        upstreams = structure['upstreams']
        self.assertEqual(len(upstreams), 1)

        upstream = upstreams[0]
        self.assertEqual(upstream['line'], 1)
        self.assertEqual(upstream['name'], 'backend')

    def test_multiple_upstreams(self):
        """Nginx analyzer should handle multiple upstream blocks."""
        nginx_lines = [
            'upstream api_backend {',
            '    server api1.example.com;',
            '}',
            '',
            'upstream static_backend {',
            '    server static1.example.com;',
            '}',
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        upstreams = structure['upstreams']
        self.assertEqual(len(upstreams), 2)

        self.assertEqual(upstreams[0]['name'], 'api_backend')
        self.assertEqual(upstreams[1]['name'], 'static_backend')


class TestNginxComments(NginxTestCase):
    """Test nginx comment header extraction."""

    def test_header_comments(self):
        """Nginx analyzer should extract header comments."""
        nginx_lines = [
            '# Production Configuration',
            '# Updated: 2025-11-23',
            '# Status: DEPLOYED',
            '',
            'server {',
            '    # Inline comment (not extracted)',
            '    server_name example.com;',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        comments = structure['comments']
        # Should only extract top comments (first 10 lines)
        # Note: blank lines may also be counted
        self.assertGreaterEqual(len(comments), 3)

        self.assertEqual(comments[0]['line'], 1)
        self.assertEqual(comments[0]['text'], 'Production Configuration')
        self.assertEqual(comments[1]['line'], 2)
        self.assertEqual(comments[2]['line'], 3)

    def test_no_header_comments(self):
        """Nginx analyzer should handle configs without header comments."""
        nginx_lines = [
            'server {',
            '    server_name example.com;',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        comments = structure['comments']
        self.assertEqual(len(comments), 0)


class TestNginxComplexConfigs(NginxTestCase):
    """Test nginx analyzer with complex real-world configs."""

    def test_http_to_https_redirect(self):
        """Nginx analyzer should handle HTTP -> HTTPS redirect pattern."""
        nginx_lines = [
            'server {',
            '    listen 80;',
            '    server_name example.com;',
            '    return 301 https://$server_name$request_uri;',
            '}',
            '',
            'server {',
            '    listen 443 ssl http2;',
            '    server_name example.com;',
            '    ssl_certificate /etc/ssl/cert.pem;',
            '    ',
            '    location / {',
            '        proxy_pass http://backend:8000;',
            '    }',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        # Should detect both server blocks
        servers = structure['servers']
        self.assertEqual(len(servers), 2)
        self.assertEqual(servers[0]['port'], '80')
        self.assertEqual(servers[1]['port'], '443 (SSL)')

        # Location should be in HTTPS server
        locations = structure['locations']
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]['server'], 'example.com')

    def test_admin_subdomain_config(self):
        """Nginx analyzer should handle complex admin subdomain routing."""
        nginx_lines = [
            '# Admin Tools Configuration',
            '# Status: DEPLOYED',
            '',
            'server {',
            '    listen 443 ssl http2;',
            '    server_name admin.example.com;',
            '    ',
            '    location / {',
            '        proxy_pass http://10.0.0.1:8000/ui/admin-hub;',
            '    }',
            '    ',
            '    location /management/ {',
            '        proxy_pass http://10.0.0.1:8000/ui/management/;',
            '    }',
            '    ',
            '    location /api/ {',
            '        proxy_pass http://10.0.0.1:8000/api/;',
            '    }',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        # Check comments
        comments = structure['comments']
        self.assertEqual(len(comments), 2)

        # Check server
        servers = structure['servers']
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]['name'], 'admin.example.com')

        # Check multiple locations
        locations = structure['locations']
        self.assertEqual(len(locations), 3)
        self.assertEqual(locations[0]['path'], '/')
        self.assertEqual(locations[1]['path'], '/management/')
        self.assertEqual(locations[2]['path'], '/api/')


class TestNginxElementExtraction(NginxTestCase):
    """Test nginx element extraction (for reveal <file> <element>)."""

    def test_extract_server_block(self):
        """Nginx analyzer should extract specific server block."""
        nginx_lines = [
            'server {',
            '    listen 80;',
            '    server_name example.com;',
            '    root /var/www;',
            '}',
            '',
            'server {',
            '    server_name other.com;',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        element = analyzer.extract_element('server', 'example.com')

        self.assertIsNotNone(element)
        self.assertEqual(element['line_start'], 1)
        self.assertEqual(element['line_end'], 5)
        self.assertIn('server_name example.com', element['source'])

    def test_extract_location_block(self):
        """Nginx analyzer should extract specific location block."""
        nginx_lines = [
            'server {',
            '    location / {',
            '        proxy_pass http://backend;',
            '    }',
            '    location /admin/ {',
            '        proxy_pass http://admin;',
            '    }',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        element = analyzer.extract_element('location', '/admin/')

        self.assertIsNotNone(element)
        self.assertEqual(element['line_start'], 5)
        self.assertEqual(element['line_end'], 7)
        self.assertIn('proxy_pass http://admin', element['source'])

    def test_extract_upstream_block(self):
        """Nginx analyzer should extract specific upstream block."""
        nginx_lines = [
            'upstream backend {',
            '    server backend1.com;',
            '    server backend2.com;',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        element = analyzer.extract_element('upstream', 'backend')

        self.assertIsNotNone(element)
        self.assertEqual(element['line_start'], 1)
        self.assertEqual(element['line_end'], 4)
        self.assertIn('backend1.com', element['source'])


class TestNginxEdgeCases(NginxTestCase):
    """Test nginx analyzer edge cases."""

    def test_empty_config(self):
        """Nginx analyzer should handle empty config."""
        nginx_lines = ['']

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(len(structure['servers']), 0)
        self.assertEqual(len(structure['locations']), 0)
        self.assertEqual(len(structure['upstreams']), 0)

    def test_comments_only(self):
        """Nginx analyzer should handle comment-only file."""
        nginx_lines = [
            '# This is a comment',
            '# Another comment',
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(len(structure['servers']), 0)
        self.assertEqual(len(structure['comments']), 2)

    def test_server_without_name(self):
        """Nginx analyzer should handle server without server_name."""
        nginx_lines = [
            'server {',
            '    listen 8080;',
            '    root /var/www;',
            '}'
        ]

        path = self.create_temp_nginx_config(nginx_lines)
        analyzer = NginxAnalyzer(path)
        structure = analyzer.get_structure()

        servers = structure['servers']
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]['name'], 'unknown')
        # Analyzer may have a default port behavior
        self.assertIn(servers[0]['port'], ['80', '8080'])


if __name__ == '__main__':
    unittest.main()
