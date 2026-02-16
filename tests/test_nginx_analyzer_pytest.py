"""Tests for nginx configuration analyzer."""

import tempfile
import os
import time
import pytest
from reveal.analyzers.nginx import NginxAnalyzer


def safe_unlink(filepath, retries=5, delay=0.5):
    """Safely remove a file, with retries for Windows file locking issues."""
    import gc
    import stat

    for attempt in range(retries):
        try:
            if os.path.exists(filepath):
                # Force garbage collection to release file handles
                gc.collect()
                # Make file writable on Windows
                try:
                    os.chmod(filepath, stat.S_IWRITE)
                except Exception:
                    pass
                os.unlink(filepath)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                # Last attempt failed, just pass
                # (CI will clean up temp files eventually)
                pass


@pytest.fixture
def simple_nginx_config():
    """Create a simple nginx configuration file."""
    config = """
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://localhost:3000;
    }
}

upstream backend {
    server localhost:5000;
}
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        f.write(config)
        f.flush()
        yield f.name
    safe_unlink(f.name)


@pytest.fixture
def complex_nginx_config():
    """Create a complex nginx configuration with multiple servers."""
    config = """
# Main configuration
# Production servers

server {
    listen 443 ssl;
    server_name api.example.com;

    location /api/v1 {
        proxy_pass http://api_backend;
    }

    location /health {
        return 200 'healthy';
    }
}

server {
    listen 80;
    server_name static.example.com;

    location / {
        root /var/www/html;
    }
}

upstream api_backend {
    server 10.0.1.1:8080;
    server 10.0.1.2:8080;
}

upstream cache_backend {
    server localhost:6379;
}
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        f.write(config)
        f.flush()
        yield f.name
    safe_unlink(f.name)


class TestNginxAnalyzer:
    """Test suite for NginxAnalyzer."""

    def test_simple_structure(self, simple_nginx_config):
        """Test parsing a simple nginx configuration."""
        analyzer = NginxAnalyzer(simple_nginx_config)
        structure = analyzer.get_structure()

        assert len(structure['servers']) == 1
        assert len(structure['locations']) == 1
        assert len(structure['upstreams']) == 1

    def test_server_parsing(self, simple_nginx_config):
        """Test server block parsing."""
        analyzer = NginxAnalyzer(simple_nginx_config)
        structure = analyzer.get_structure()

        server = structure['servers'][0]
        assert server['name'] == 'example.com'
        assert server['port'] == '80'
        assert 'line' in server

    def test_location_parsing(self, simple_nginx_config):
        """Test location block parsing."""
        analyzer = NginxAnalyzer(simple_nginx_config)
        structure = analyzer.get_structure()

        location = structure['locations'][0]
        assert location['path'] == '/'
        assert location['target'] == 'http://localhost:3000'
        assert location['server'] == 'example.com'

    def test_upstream_parsing(self, simple_nginx_config):
        """Test upstream block parsing."""
        analyzer = NginxAnalyzer(simple_nginx_config)
        structure = analyzer.get_structure()

        upstream = structure['upstreams'][0]
        assert upstream['name'] == 'backend'
        assert 'line' in upstream

    def test_complex_structure(self, complex_nginx_config):
        """Test parsing complex nginx configuration."""
        analyzer = NginxAnalyzer(complex_nginx_config)
        structure = analyzer.get_structure()

        assert len(structure['servers']) == 2
        assert len(structure['locations']) == 3
        assert len(structure['upstreams']) == 2
        assert len(structure['comments']) == 2

    def test_ssl_port_detection(self, complex_nginx_config):
        """Test SSL port detection."""
        analyzer = NginxAnalyzer(complex_nginx_config)
        structure = analyzer.get_structure()

        ssl_server = next(s for s in structure['servers'] if 'ssl' in s['port'].lower())
        assert ssl_server['port'] == '443 (SSL)'
        assert ssl_server['name'] == 'api.example.com'

    def test_multiple_locations_per_server(self, complex_nginx_config):
        """Test that multiple locations are associated with correct server."""
        analyzer = NginxAnalyzer(complex_nginx_config)
        structure = analyzer.get_structure()

        api_locations = [loc for loc in structure['locations'] if loc['server'] == 'api.example.com']
        assert len(api_locations) == 2

    def test_static_root_location(self, complex_nginx_config):
        """Test location with static root directive."""
        analyzer = NginxAnalyzer(complex_nginx_config)
        structure = analyzer.get_structure()

        static_location = next(loc for loc in structure['locations'] if 'static:' in loc.get('target', ''))
        assert static_location['target'] == 'static: /var/www/html'

    def test_comment_extraction(self, complex_nginx_config):
        """Test comment extraction from config header."""
        analyzer = NginxAnalyzer(complex_nginx_config)
        structure = analyzer.get_structure()

        assert len(structure['comments']) >= 1
        comment_texts = [c['text'] for c in structure['comments']]
        assert any('Main configuration' in text for text in comment_texts)

    def test_extract_server_element(self, simple_nginx_config):
        """Test extracting a specific server block."""
        analyzer = NginxAnalyzer(simple_nginx_config)
        result = analyzer.extract_element('server', 'example.com')

        assert result is not None
        assert result['name'] == 'example.com'
        assert 'source' in result
        assert 'server_name example.com' in result['source']

    def test_extract_location_element(self, simple_nginx_config):
        """Test extracting a specific location block."""
        analyzer = NginxAnalyzer(simple_nginx_config)
        result = analyzer.extract_element('location', '/')

        assert result is not None
        assert result['name'] == '/'
        assert 'source' in result
        assert 'location /' in result['source']
        assert 'proxy_pass' in result['source']

    def test_extract_upstream_element(self, simple_nginx_config):
        """Test extracting a specific upstream block."""
        analyzer = NginxAnalyzer(simple_nginx_config)
        result = analyzer.extract_element('upstream', 'backend')

        assert result is not None
        assert result['name'] == 'backend'
        assert 'source' in result
        assert 'upstream backend' in result['source']

    def test_extract_nonexistent_element(self, simple_nginx_config):
        """Test extracting a non-existent element returns None."""
        analyzer = NginxAnalyzer(simple_nginx_config)
        result = analyzer.extract_element('server', 'nonexistent.com')

        # Should fall back to parent's extract_element
        assert result is None

    def test_empty_config(self):
        """Test handling empty nginx configuration."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write("")
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                structure = analyzer.get_structure()

                assert len(structure['servers']) == 0
                assert len(structure['locations']) == 0
                assert len(structure['upstreams']) == 0
                assert len(structure['comments']) == 0
            finally:
                safe_unlink(f.name)

    def test_malformed_server_block(self):
        """Test handling malformed server blocks gracefully."""
        config = """
server {
    listen 80
    # Missing semicolon but should still parse structure
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                structure = analyzer.get_structure()

                # Should still detect the server block
                assert len(structure['servers']) == 1
            finally:
                safe_unlink(f.name)

    def test_nested_location_blocks(self):
        """Test handling nested location blocks."""
        config = """
server {
    listen 80;
    server_name test.com;

    location / {
        proxy_pass http://backend;
    }

    location /admin {
        root /var/www/admin;
    }

    location /api {
        proxy_pass http://api_server;
    }
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                structure = analyzer.get_structure()

                assert len(structure['locations']) == 3
                paths = [loc['path'] for loc in structure['locations']]
                assert '/' in paths
                assert '/admin' in paths
                assert '/api' in paths
            finally:
                safe_unlink(f.name)


class TestNginxSSLDomainExtraction:
    """Test extract_ssl_domains() method (Issue #18).

    Tests extracting SSL-enabled domains from nginx configuration
    for batch certificate checking.
    """

    def test_extract_ssl_domains_basic(self):
        """Basic SSL domain extraction from server blocks."""
        config = """
server {
    listen 443 ssl;
    server_name secure.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert 'secure.example.com' in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_multiple(self):
        """Extract multiple domains from server_name directive."""
        config = """
server {
    listen 443 ssl;
    server_name api.example.com www.example.com example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert len(domains) == 3
                assert 'api.example.com' in domains
                assert 'www.example.com' in domains
                assert 'example.com' in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_excludes_non_ssl(self):
        """Non-SSL server blocks should be excluded."""
        config = """
server {
    listen 80;
    server_name http-only.example.com;
}

server {
    listen 443 ssl;
    server_name secure.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert 'secure.example.com' in domains
                assert 'http-only.example.com' not in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_filters_localhost(self):
        """localhost should be filtered out."""
        config = """
server {
    listen 443 ssl;
    server_name localhost valid.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert 'valid.example.com' in domains
                assert 'localhost' not in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_filters_underscore(self):
        """Catch-all _ server should be filtered out."""
        config = """
server {
    listen 443 ssl default_server;
    server_name _;
    ssl_certificate /etc/ssl/certs/default.pem;
}

server {
    listen 443 ssl;
    server_name valid.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert 'valid.example.com' in domains
                assert '_' not in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_filters_wildcards(self):
        """Wildcard domains should be filtered out."""
        config = """
server {
    listen 443 ssl;
    server_name *.example.com specific.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert 'specific.example.com' in domains
                assert '*.example.com' not in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_filters_ips(self):
        """IP addresses should be filtered out."""
        config = """
server {
    listen 443 ssl;
    server_name 192.168.1.100 10.0.0.1 valid.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert 'valid.example.com' in domains
                assert '192.168.1.100' not in domains
                assert '10.0.0.1' not in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_filters_non_fqdn(self):
        """Non-FQDN names (no dot) should be filtered out."""
        config = """
server {
    listen 443 ssl;
    server_name intranet internal valid.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert 'valid.example.com' in domains
                assert 'intranet' not in domains
                assert 'internal' not in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_detects_ssl_keyword(self):
        """SSL detection via 'ssl' keyword in listen directive."""
        config = """
server {
    listen 8443 ssl;
    server_name custom-port.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert 'custom-port.example.com' in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_detects_ssl_certificate(self):
        """SSL detection via ssl_certificate directive."""
        config = """
server {
    listen 443;
    server_name cert-only.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert 'cert-only.example.com' in domains
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_unique(self):
        """Duplicate domains across server blocks should be deduplicated."""
        config = """
server {
    listen 443 ssl;
    server_name shared.example.com;
    ssl_certificate /etc/ssl/certs/cert1.pem;
}

server {
    listen 443 ssl;
    server_name shared.example.com;
    ssl_certificate /etc/ssl/certs/cert2.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                # Should only appear once
                assert domains.count('shared.example.com') == 1
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_sorted(self):
        """Extracted domains should be sorted."""
        config = """
server {
    listen 443 ssl;
    server_name zebra.example.com alpha.example.com beta.example.com;
    ssl_certificate /etc/ssl/certs/cert.pem;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert domains == sorted(domains)
            finally:
                safe_unlink(f.name)

    def test_extract_ssl_domains_empty_config(self):
        """Empty config should return empty list."""
        config = "# Empty config\n"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()

            try:
                analyzer = NginxAnalyzer(f.name)
                domains = analyzer.extract_ssl_domains()

                assert domains == []
            finally:
                safe_unlink(f.name)
