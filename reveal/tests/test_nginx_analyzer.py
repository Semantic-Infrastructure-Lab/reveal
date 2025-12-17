"""Tests for nginx configuration analyzer."""

import tempfile
import os
import pytest
from reveal.analyzers.nginx import NginxAnalyzer


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
    os.unlink(f.name)


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
    os.unlink(f.name)


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
                os.unlink(f.name)

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
                os.unlink(f.name)

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
                os.unlink(f.name)
