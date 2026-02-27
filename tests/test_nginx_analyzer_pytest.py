"""Tests for nginx configuration analyzer."""

import tempfile
import os
import time
from pathlib import Path
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


class TestNginxHttpDirectives:
    """Tests for Issue #21: parse global http{} directives (timeouts, buffers, proxy settings).

    Ensures that reveal surfaces http{}-level directives even when there are
    no server{} blocks, so that main nginx.conf files produce useful output.
    """

    def _write_conf(self, content):
        """Helper: write content to a temp .conf file and return path."""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(content)
        f.flush()
        f.close()
        return f.name

    def test_http_only_config_surfaces_directives(self):
        """Issue #21: config with only http{} directives should not be empty."""
        config = """
http {
    send_timeout 30s;
    proxy_read_timeout 60s;
    keepalive_timeout 15s;
    client_body_timeout 30s;
    proxy_connect_timeout 10s;
    proxy_buffering on;
    client_body_buffer_size 256k;
}
"""
        path = self._write_conf(config)
        try:
            analyzer = NginxAnalyzer(path)
            structure = analyzer.get_structure()

            assert 'directives' in structure, "Expected 'directives' key in structure"
            d = structure['directives']
            assert d['send_timeout'] == '30s'
            assert d['proxy_read_timeout'] == '60s'
            assert d['keepalive_timeout'] == '15s'
            assert d['client_body_timeout'] == '30s'
            assert d['proxy_connect_timeout'] == '10s'
            assert d['proxy_buffering'] == 'on'
            assert d['client_body_buffer_size'] == '256k'
        finally:
            safe_unlink(path)

    def test_http_directives_not_included_when_absent(self):
        """No http{} block → 'directives' key absent (not an empty dict)."""
        config = """
server {
    listen 80;
    server_name example.com;
}
"""
        path = self._write_conf(config)
        try:
            analyzer = NginxAnalyzer(path)
            structure = analyzer.get_structure()

            assert 'directives' not in structure
        finally:
            safe_unlink(path)

    def test_http_directives_excludes_nested_block_contents(self):
        """Directives inside server{} are not collected into http directives."""
        config = """
http {
    send_timeout 30s;

    server {
        listen 80;
        server_name inner.example.com;
        proxy_pass http://backend;
    }
}
"""
        path = self._write_conf(config)
        try:
            analyzer = NginxAnalyzer(path)
            structure = analyzer.get_structure()

            d = structure.get('directives', {})
            assert 'send_timeout' in d
            assert 'proxy_pass' not in d
            assert 'listen' not in d
        finally:
            safe_unlink(path)

    def test_events_directives_parsed(self):
        """events{} directives surfaced under 'events_directives'."""
        config = """
events {
    worker_connections 8192;
    use epoll;
    multi_accept on;
}
"""
        path = self._write_conf(config)
        try:
            analyzer = NginxAnalyzer(path)
            structure = analyzer.get_structure()

            assert 'events_directives' in structure
            e = structure['events_directives']
            assert e['worker_connections'] == '8192'
            assert e['use'] == 'epoll'
            assert e['multi_accept'] == 'on'
        finally:
            safe_unlink(path)

    def test_both_http_and_events_directives(self):
        """Both http{} and events{} directives are present when both blocks exist."""
        config = """
events {
    worker_connections 1024;
}

http {
    send_timeout 60s;
    keepalive_timeout 20s;
}
"""
        path = self._write_conf(config)
        try:
            analyzer = NginxAnalyzer(path)
            structure = analyzer.get_structure()

            assert 'directives' in structure
            assert 'events_directives' in structure
            assert structure['directives']['send_timeout'] == '60s'
            assert structure['events_directives']['worker_connections'] == '1024'
        finally:
            safe_unlink(path)

    def test_http_directives_with_server_blocks_still_parsed(self):
        """http{} directives are collected even when server{} blocks are also present."""
        config = """
http {
    gzip on;
    gzip_types text/plain application/json;

    server {
        listen 443 ssl;
        server_name api.example.com;
    }
}
"""
        path = self._write_conf(config)
        try:
            analyzer = NginxAnalyzer(path)
            structure = analyzer.get_structure()

            assert 'directives' in structure
            assert structure['directives']['gzip'] == 'on'
            assert len(structure['servers']) == 1
        finally:
            safe_unlink(path)

    def test_comments_inside_http_block_ignored(self):
        """Comment lines inside http{} are not parsed as directives."""
        config = """
http {
    # This is a timeout comment
    send_timeout 45s;
    # proxy_read_timeout 999s;
}
"""
        path = self._write_conf(config)
        try:
            analyzer = NginxAnalyzer(path)
            structure = analyzer.get_structure()

            d = structure.get('directives', {})
            assert 'send_timeout' in d
            assert d['send_timeout'] == '45s'
            # Commented-out directive must not appear
            assert 'proxy_read_timeout' not in d
        finally:
            safe_unlink(path)

    def test_empty_http_block_no_directives_key(self):
        """An http{} block with no directives produces no 'directives' key."""
        config = """
http {
    # nothing here
    server {
        listen 80;
    }
}
"""
        path = self._write_conf(config)
        try:
            analyzer = NginxAnalyzer(path)
            structure = analyzer.get_structure()

            # No directive key-value pairs → key should be absent
            assert 'directives' not in structure
        finally:
            safe_unlink(path)


class TestN005TimeoutRule:
    """Tests for N005: dangerous nginx timeout/buffer values."""

    def _write_conf(self, content):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(content)
        f.flush()
        f.close()
        return f.name

    def _run_n005(self, config_content):
        from reveal.rules.infrastructure.N005 import N005
        path = self._write_conf(config_content)
        try:
            analyzer = NginxAnalyzer(path)
            structure = analyzer.get_structure()
            rule = N005()
            return rule.check(path, structure, config_content)
        finally:
            safe_unlink(path)

    def test_safe_timeouts_no_detections(self):
        """Timeouts within safe bounds generate no detections."""
        config = """
http {
    send_timeout 60s;
    proxy_read_timeout 120s;
    keepalive_timeout 30s;
}
"""
        detections = self._run_n005(config)
        assert detections == []

    def test_send_timeout_too_short(self):
        """send_timeout below minimum triggers N005."""
        config = """
http {
    send_timeout 3s;
}
"""
        detections = self._run_n005(config)
        assert len(detections) == 1
        assert 'send_timeout' in detections[0].message or 'send timeout' in detections[0].message
        assert 'below' in detections[0].message

    def test_proxy_read_timeout_too_long(self):
        """proxy_read_timeout above maximum triggers N005."""
        config = """
http {
    proxy_read_timeout 600s;
}
"""
        detections = self._run_n005(config)
        assert len(detections) == 1
        assert 'proxy read timeout' in detections[0].message
        assert 'exceeds' in detections[0].message

    def test_buffer_size_too_large(self):
        """client_body_buffer_size above maximum triggers N005."""
        config = """
http {
    client_body_buffer_size 512m;
}
"""
        detections = self._run_n005(config)
        assert len(detections) == 1
        assert 'client body buffer size' in detections[0].message
        assert 'exceeds' in detections[0].message

    def test_multiple_violations(self):
        """Multiple bad directives produce multiple detections."""
        config = """
http {
    send_timeout 2s;
    proxy_read_timeout 900s;
    client_body_buffer_size 256m;
}
"""
        detections = self._run_n005(config)
        assert len(detections) == 3

    def test_no_http_block_no_detections(self):
        """Config without http{} block produces no detections."""
        config = """
server {
    listen 80;
    server_name example.com;
}
"""
        detections = self._run_n005(config)
        assert detections == []


# ─────────────────────────────────────────────────────────────────────────────
# Issue improvements: main directives, multi-line, upstream detail, map blocks
# ─────────────────────────────────────────────────────────────────────────────

class TestNginxMainDirectives:
    """Tests for _parse_main_directives — depth-0 directive extraction."""

    def _make_analyzer(self, config: str):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()
            name = f.name
        analyzer = NginxAnalyzer(name)
        os.unlink(name)
        return analyzer

    def test_basic_main_directives(self):
        """worker_processes, user, pid captured from main context."""
        config = """
user nobody;
worker_processes auto;
worker_rlimit_nofile 200000;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}
"""
        a = self._make_analyzer(config)
        d = a._parse_main_directives()
        assert d['user'] == 'nobody'
        assert d['worker_processes'] == 'auto'
        assert d['worker_rlimit_nofile'] == '200000'
        assert d['pid'] == '/var/run/nginx.pid'

    def test_directives_inside_blocks_not_captured(self):
        """Directives inside events{} or http{} are NOT included."""
        config = """
worker_processes 4;

events {
    worker_connections 1024;
}

http {
    keepalive_timeout 15s;
}
"""
        a = self._make_analyzer(config)
        d = a._parse_main_directives()
        assert d == {'worker_processes': '4'}
        assert 'worker_connections' not in d
        assert 'keepalive_timeout' not in d

    def test_vhost_top_level_ssl_directives(self):
        """ssl_protocols, client_max_body_size at top of vhost file captured."""
        config = """
ssl_protocols TLSv1.2 TLSv1.3;
ssl_prefer_server_ciphers on;
client_max_body_size 200m;
server_names_hash_bucket_size 256;

server {
    listen 443 ssl;
    server_name example.com;
}
"""
        a = self._make_analyzer(config)
        d = a._parse_main_directives()
        assert d['ssl_protocols'] == 'TLSv1.2 TLSv1.3'
        assert d['ssl_prefer_server_ciphers'] == 'on'
        assert d['client_max_body_size'] == '200m'
        assert d['server_names_hash_bucket_size'] == '256'

    def test_include_directive_captured(self):
        """include directives at top level are captured."""
        config = """
include /etc/nginx/conf.d/modules/*.conf;
user nobody;
"""
        a = self._make_analyzer(config)
        d = a._parse_main_directives()
        assert d['include'] == '/etc/nginx/conf.d/modules/*.conf'
        assert d['user'] == 'nobody'

    def test_empty_config_no_directives(self):
        """Config with only a server block returns empty main directives."""
        config = """
server {
    listen 80;
    server_name example.com;
}
"""
        a = self._make_analyzer(config)
        d = a._parse_main_directives()
        assert d == {}

    def test_main_directives_in_get_structure(self):
        """get_structure() includes main_directives key when directives exist."""
        config = """
worker_processes auto;
worker_rlimit_nofile 200000;

events {
    worker_connections 8192;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        assert 'main_directives' in structure
        assert structure['main_directives']['worker_processes'] == 'auto'
        assert structure['main_directives']['worker_rlimit_nofile'] == '200000'

    def test_no_main_directives_key_absent(self):
        """get_structure() omits main_directives when none present."""
        config = """
server {
    listen 80;
    server_name example.com;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        assert 'main_directives' not in structure


class TestNginxMultiLineDirectives:
    """Tests for multi-line directive support in _parse_block_directives."""

    def _make_analyzer(self, config: str):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()
            name = f.name
        analyzer = NginxAnalyzer(name)
        os.unlink(name)
        return analyzer

    def test_multiline_log_format(self):
        """log_format spanning multiple lines is captured under its key."""
        config = """
http {
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent"';

    keepalive_timeout 15s;
}
"""
        a = self._make_analyzer(config)
        d = a._parse_block_directives('http')
        assert 'log_format' in d
        assert 'main' in d['log_format']
        assert '$remote_addr' in d['log_format']
        assert '$http_user_agent' in d['log_format']

    def test_single_line_directives_still_work(self):
        """Single-line directives are unaffected by multi-line support."""
        config = """
http {
    keepalive_timeout 15s;
    gzip on;
    worker_connections 1024;
}
"""
        a = self._make_analyzer(config)
        d = a._parse_block_directives('http')
        assert d['keepalive_timeout'] == '15s'
        assert d['gzip'] == 'on'

    def test_multiline_followed_by_normal_directive(self):
        """Directive after multi-line is still captured correctly."""
        config = """
http {
    log_format combined '$remote_addr - '
                        '$request';
    gzip on;
    sendfile on;
}
"""
        a = self._make_analyzer(config)
        d = a._parse_block_directives('http')
        assert 'log_format' in d
        assert d['gzip'] == 'on'
        assert d['sendfile'] == 'on'


class TestNginxUpstreamDetail:
    """Tests for rich upstream parsing — server entries and settings."""

    def _make_analyzer(self, config: str):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()
            name = f.name
        analyzer = NginxAnalyzer(name)
        os.unlink(name)
        return analyzer

    def test_upstream_server_entry_captured(self):
        """Server address inside upstream block is captured."""
        config = """
upstream backend {
    server localhost:5000;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        upstream = structure['upstreams'][0]
        assert upstream['name'] == 'backend'
        assert len(upstream['servers']) == 1
        assert upstream['servers'][0]['address'] == 'localhost:5000'

    def test_upstream_server_with_params(self):
        """Server with max_fails and fail_timeout params are captured."""
        config = """
upstream backend {
    server master.example.com:443 max_fails=3 fail_timeout=10s;
    keepalive 32;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        upstream = structure['upstreams'][0]
        assert upstream['servers'][0]['address'] == 'master.example.com:443'
        assert 'max_fails=3' in upstream['servers'][0]['params']
        assert upstream['settings']['keepalive'] == '32'

    def test_upstream_signature_contains_backend(self):
        """Signature field contains backend address for display."""
        config = """
upstream myapp {
    server 127.0.0.1:8080;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        upstream = structure['upstreams'][0]
        assert '127.0.0.1:8080' in upstream['signature']

    def test_upstream_multiple_servers_signature(self):
        """Multiple servers: signature shows first + count."""
        config = """
upstream pool {
    server 10.0.0.1:80;
    server 10.0.0.2:80;
    server 10.0.0.3:80;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        upstream = structure['upstreams'][0]
        assert len(upstream['servers']) == 3
        assert '10.0.0.1:80' in upstream['signature']
        assert '+2 more' in upstream['signature']

    def test_upstream_keepalive_settings(self):
        """keepalive and keepalive_timeout captured in settings."""
        config = """
upstream backend {
    server app:443;
    keepalive 32;
    keepalive_timeout 5;
    keepalive_requests 100;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        upstream = structure['upstreams'][0]
        assert upstream['settings']['keepalive'] == '32'
        assert upstream['settings']['keepalive_timeout'] == '5'
        assert upstream['settings']['keepalive_requests'] == '100'

    def test_upstream_no_servers(self):
        """Upstream with no server entries has empty servers list."""
        config = """
upstream empty_pool {
    keepalive 16;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        upstream = structure['upstreams'][0]
        assert upstream['servers'] == []
        assert upstream['signature'] == ''


class TestNginxMapBlocks:
    """Tests for map{} block detection."""

    def _make_analyzer(self, config: str):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(config)
            f.flush()
            name = f.name
        analyzer = NginxAnalyzer(name)
        os.unlink(name)
        return analyzer

    def test_single_map_detected(self):
        """Single map block is detected."""
        config = """
map $host $backend {
    default 127.0.0.1;
    example.com 10.0.0.1;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        assert 'maps' in structure
        assert len(structure['maps']) == 1
        m = structure['maps'][0]
        assert m['source_var'] == '$host'
        assert m['target_var'] == '$backend'

    def test_multiple_maps_all_detected(self):
        """All 5 map blocks in ea-nginx pattern are detected."""
        config = """
map $host $PROXY_IP {
    default 127.0.0.1;
}

map $host $PROXY_PORT {
    default 81;
}

map $host $PROXY_SSL_IP {
    default 127.0.0.1;
}

map $host $PROXY_SSL_PORT {
    default 444;
}

map $host $SERVICE_SUBDOMAIN {
    default 0;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        assert 'maps' in structure
        assert len(structure['maps']) == 5

    def test_map_name_format(self):
        """Map name uses 'source → target' arrow format."""
        config = """
map $uri $new_uri {
    default $uri;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        m = structure['maps'][0]
        assert m['name'] == '$uri → $new_uri'

    def test_no_maps_key_absent(self):
        """Configs without map blocks have no 'maps' key."""
        config = """
server {
    listen 80;
    server_name example.com;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        assert 'maps' not in structure

    def test_map_variables_preserved(self):
        """source_var and target_var fields match map declaration."""
        config = """
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}
"""
        a = self._make_analyzer(config)
        structure = a.get_structure()
        m = structure['maps'][0]
        assert m['source_var'] == '$http_upgrade'
        assert m['target_var'] == '$connection_upgrade'




# ---------------------------------------------------------------------------
# N4: extract_acme_roots()
# ---------------------------------------------------------------------------

class TestNginxAcmeRootsExtraction:
    """Tests for extract_acme_roots() — N4 (ACME pipeline extraction).

    ACL results are mocked so tests focus on config parsing, not filesystem
    traversal through pytest's restricted tmp directories.
    """

    def _make_analyzer(self, config: str):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(config)
        f.close()
        a = NginxAnalyzer(f.name)
        os.unlink(f.name)
        return a

    def _ok_acl(self, path):
        return {'status': 'ok', 'message': 'nobody has read access', 'failing_path': None}

    def _denied_acl(self, path):
        return {'status': 'denied', 'message': f'nobody cannot read {path} (mode 750, no ACL entry)',
                'failing_path': path}

    def test_finds_acme_location_with_root(self, monkeypatch):
        """ACME location with explicit root is found and root is returned."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._ok_acl)
        config = """
server {
    listen 80;
    server_name example.com;
    location /.well-known/acme-challenge/ {
        root /home/example/public_html;
    }
}
"""
        rows = self._make_analyzer(config).extract_acme_roots()
        assert len(rows) == 1
        assert rows[0]['domain'] == 'example.com'
        assert rows[0]['acme_path'] == '/home/example/public_html'

    def test_inherits_server_root_when_location_has_none(self, monkeypatch):
        """Falls back to server-level root when location has no root directive."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._ok_acl)
        config = """
server {
    listen 80;
    server_name fallback.com;
    root /home/fallback/public_html;
    location /.well-known/acme-challenge/ {
    }
}
"""
        rows = self._make_analyzer(config).extract_acme_roots()
        assert len(rows) == 1
        assert rows[0]['acme_path'] == '/home/fallback/public_html'

    def test_acl_ok_status_propagated(self, monkeypatch):
        """ok ACL result is surfaced in row."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._ok_acl)
        config = """
server {
    listen 80;
    server_name ok.com;
    location /.well-known/acme-challenge/ {
        root /home/ok/public_html;
    }
}
"""
        rows = self._make_analyzer(config).extract_acme_roots()
        assert rows[0]['acl_status'] == 'ok'

    def test_acl_denied_status_propagated(self, monkeypatch):
        """denied ACL result and failing_path are surfaced in row."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._denied_acl)
        config = """
server {
    listen 80;
    server_name denied.com;
    location /.well-known/acme-challenge/ {
        root /home/denied/public_html;
    }
}
"""
        rows = self._make_analyzer(config).extract_acme_roots()
        assert rows[0]['acl_status'] == 'denied'
        assert rows[0]['acl_failing_path'] is not None

    def test_acl_not_found_when_root_missing(self, monkeypatch):
        """not_found ACL status when path doesn't exist."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access',
                            lambda p: {'status': 'not_found',
                                       'message': f'Path not found: {p}',
                                       'failing_path': p})
        config = """
server {
    listen 80;
    server_name ghost.com;
    location /.well-known/acme-challenge/ {
        root /nonexistent/path;
    }
}
"""
        rows = self._make_analyzer(config).extract_acme_roots()
        assert rows[0]['acl_status'] == 'not_found'

    def test_no_acme_location_returns_empty(self):
        """Config with no ACME challenge location returns empty list."""
        config = """
server {
    listen 80;
    server_name example.com;
    location / {
        proxy_pass http://backend;
    }
}
"""
        assert self._make_analyzer(config).extract_acme_roots() == []

    def test_multiple_servers_produce_multiple_rows(self, monkeypatch):
        """Each server block with an ACME location produces its own row."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._ok_acl)
        config = """
server {
    listen 80;
    server_name alpha.com;
    location /.well-known/acme-challenge/ { root /home/alpha/pub; }
}
server {
    listen 80;
    server_name beta.com;
    location /.well-known/acme-challenge/ { root /home/beta/pub; }
}
"""
        rows = self._make_analyzer(config).extract_acme_roots()
        assert len(rows) == 2
        assert {r['domain'] for r in rows} == {'alpha.com', 'beta.com'}

    def test_without_trailing_slash_matches(self, monkeypatch):
        """location /.well-known/acme-challenge without trailing slash is matched."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._ok_acl)
        config = """
server {
    listen 80;
    server_name noslash.com;
    location /.well-known/acme-challenge {
        root /home/noslash/pub;
    }
}
"""
        rows = self._make_analyzer(config).extract_acme_roots()
        assert len(rows) == 1
        assert rows[0]['domain'] == 'noslash.com'

    def test_unknown_status_when_no_root_found(self, monkeypatch):
        """When no root directive exists anywhere, acl_status is 'unknown'."""
        # _check_nobody_access should not be called; status comes from else branch
        config = """
server {
    listen 80;
    server_name noroot.com;
    location /.well-known/acme-challenge/ {
        try_files $uri =404;
    }
}
"""
        rows = self._make_analyzer(config).extract_acme_roots()
        assert len(rows) == 1
        assert rows[0]['acl_status'] == 'unknown'
        assert rows[0]['acme_path'] == '(not found)'


# ---------------------------------------------------------------------------
# N1: extract_docroot_acl()
# ---------------------------------------------------------------------------

class TestNginxDocRootAcl:
    """Tests for extract_docroot_acl() — N1 (cPanel ACL awareness).

    ACL results are mocked; tests focus on which root directives are found.
    """

    def _make_analyzer(self, config: str):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(config)
        f.close()
        a = NginxAnalyzer(f.name)
        os.unlink(f.name)
        return a

    def _ok_acl(self, path):
        return {'status': 'ok', 'message': 'nobody has read access', 'failing_path': None}

    def _denied_acl(self, path):
        return {'status': 'denied', 'message': f'denied at {path}', 'failing_path': path}

    def test_finds_root_directive(self, monkeypatch):
        """root directive is found and reported."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._ok_acl)
        config = """
server {
    listen 80;
    server_name example.com;
    root /home/example/public_html;
}
"""
        rows = self._make_analyzer(config).extract_docroot_acl()
        assert len(rows) == 1
        assert rows[0]['root'] == '/home/example/public_html'
        assert rows[0]['domain'] == 'example.com'

    def test_ok_status_propagated(self, monkeypatch):
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._ok_acl)
        config = """
server {
    listen 80;
    server_name ok.com;
    root /home/ok/pub;
}
"""
        rows = self._make_analyzer(config).extract_docroot_acl()
        assert rows[0]['acl_status'] == 'ok'

    def test_denied_status_propagated(self, monkeypatch):
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._denied_acl)
        config = """
server {
    listen 80;
    server_name secret.com;
    root /home/secret/pub;
}
"""
        rows = self._make_analyzer(config).extract_docroot_acl()
        assert rows[0]['acl_status'] == 'denied'
        assert rows[0]['acl_failing_path'] is not None

    def test_no_root_directives_returns_empty(self):
        config = """
server {
    listen 80;
    server_name example.com;
    location / { proxy_pass http://backend; }
}
"""
        assert self._make_analyzer(config).extract_docroot_acl() == []

    def test_deduplicates_same_root(self, monkeypatch):
        """Same root path mentioned in two server blocks checked only once."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._ok_acl)
        config = """
server {
    listen 80;
    server_name a.com;
    root /home/shared/pub;
}
server {
    listen 80;
    server_name b.com;
    root /home/shared/pub;
}
"""
        rows = self._make_analyzer(config).extract_docroot_acl()
        assert [r['root'] for r in rows].count('/home/shared/pub') == 1

    def test_multiple_roots_reported(self, monkeypatch):
        """Different root directives across servers all appear in output."""
        monkeypatch.setattr('reveal.analyzers.nginx._check_nobody_access', self._ok_acl)
        config = """
server {
    listen 80;
    server_name a.com;
    root /home/a/pub;
}
server {
    listen 80;
    server_name b.com;
    root /home/b/pub;
}
"""
        rows = self._make_analyzer(config).extract_docroot_acl()
        roots = {r['root'] for r in rows}
        assert '/home/a/pub' in roots
        assert '/home/b/pub' in roots


# ---------------------------------------------------------------------------
# _check_nobody_access() unit tests (real filesystem, using /tmp which is 1777)
# ---------------------------------------------------------------------------

class TestCheckNobodyAccess:
    """Unit tests for the _check_nobody_access() utility.

    Uses /tmp (mode 1777, universally world-executable) as the traversable
    parent so tests don't depend on pytest's restricted tmp directory layout.
    """

    def test_world_readable_dir_is_ok(self):
        """Directory with mode 755 under /tmp returns ok."""
        from reveal.analyzers.nginx import _check_nobody_access
        import uuid
        d = Path(tempfile.gettempdir()) / f"reveal_acl_test_{uuid.uuid4().hex}"
        d.mkdir(mode=0o755)
        try:
            result = _check_nobody_access(str(d))
            assert result['status'] == 'ok'
        finally:
            d.rmdir()

    def test_nonexistent_path_returns_not_found(self):
        """Non-existent path returns not_found."""
        from reveal.analyzers.nginx import _check_nobody_access
        result = _check_nobody_access('/tmp/reveal_test_ghost_will_never_exist_xyz123')
        assert result['status'] == 'not_found'

    def test_no_other_read_returns_denied(self):
        """Directory with mode 750 (no other-r-x) under /tmp returns denied."""
        from reveal.analyzers.nginx import _check_nobody_access
        import uuid
        d = Path(tempfile.gettempdir()) / f"reveal_acl_priv_{uuid.uuid4().hex}"
        d.mkdir(mode=0o750)
        try:
            result = _check_nobody_access(str(d))
            assert result['status'] == 'denied'
            assert result['failing_path'] is not None
        finally:
            d.chmod(0o755)
            d.rmdir()

# ---------------------------------------------------------------------------
# N3: get_structure(domain=...) — server block filter
# ---------------------------------------------------------------------------

class TestNginxDomainFilter:
    """Tests for get_structure(domain=...) — N3 filter."""

    def _make_analyzer(self, config: str):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(config)
        f.close()
        a = NginxAnalyzer(f.name)
        os.unlink(f.name)
        return a

    _MULTI_SERVER = """
server {
    listen 80;
    server_name alpha.com www.alpha.com;
    location / { proxy_pass http://backend-a; }
}
server {
    listen 80;
    server_name beta.com;
    location / { proxy_pass http://backend-b; }
    location /api { proxy_pass http://api-b; }
}
server {
    listen 443 ssl;
    server_name beta.com;
    location / { proxy_pass http://backend-b-ssl; }
}
"""

    def test_domain_filter_returns_only_matching_server(self):
        """Filtering by 'alpha.com' returns only alpha server block."""
        structure = self._make_analyzer(self._MULTI_SERVER).get_structure(domain='alpha.com')
        servers = structure['servers']
        assert len(servers) == 1
        assert servers[0]['name'] == 'alpha.com'

    def test_domain_filter_returns_matching_locations(self):
        """Locations are filtered to only those in the matching server block."""
        structure = self._make_analyzer(self._MULTI_SERVER).get_structure(domain='beta.com')
        location_servers = {loc['server'] for loc in structure['locations']}
        assert 'alpha.com' not in location_servers
        assert 'beta.com' in location_servers

    def test_domain_filter_matches_alias(self):
        """Filtering by an alias in server_name (www.alpha.com) resolves correctly."""
        structure = self._make_analyzer(self._MULTI_SERVER).get_structure(domain='www.alpha.com')
        servers = structure['servers']
        assert len(servers) == 1
        assert 'www.alpha.com' in servers[0]['domains']

    def test_domain_filter_multiple_server_blocks_same_name(self):
        """Two server blocks for beta.com (80 + 443) are both returned."""
        structure = self._make_analyzer(self._MULTI_SERVER).get_structure(domain='beta.com')
        assert len(structure['servers']) == 2

    def test_domain_filter_no_match_returns_empty(self):
        """Non-existent domain returns empty servers and locations."""
        structure = self._make_analyzer(self._MULTI_SERVER).get_structure(domain='nothere.com')
        assert structure['servers'] == []
        assert structure['locations'] == []
        assert structure.get('_domain_not_found') is True

    def test_no_domain_filter_returns_all(self):
        """Without domain kwarg, all server blocks are returned."""
        structure = self._make_analyzer(self._MULTI_SERVER).get_structure()
        assert len(structure['servers']) == 3


# ---------------------------------------------------------------------------
# N2: detect_location_conflicts()
# ---------------------------------------------------------------------------

class TestNginxLocationConflicts:
    """Tests for detect_location_conflicts() — N2."""

    def _make_analyzer(self, config: str):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(config)
        f.close()
        a = NginxAnalyzer(f.name)
        os.unlink(f.name)
        return a

    def test_no_conflicts_clean_config(self):
        """Config with non-overlapping locations has no conflicts."""
        config = """
server {
    server_name example.com;
    location / { proxy_pass http://backend; }
    location /static { proxy_pass http://static; }
    location /api/v1 { proxy_pass http://api; }
}
"""
        # /static and /api/v1 are independent prefixes (neither is prefix of the other)
        # / is a prefix of both, but that's expected nginx catch-all behaviour — low severity
        conflicts = self._make_analyzer(config).detect_location_conflicts()
        # / is a prefix of /static and /api/v1 → info, not warning
        warnings = [c for c in conflicts if c['severity'] == 'warning']
        assert warnings == []

    def test_prefix_overlap_detected(self):
        """Two non-regex locations where one is a strict prefix of the other."""
        config = """
server {
    server_name example.com;
    location /.well-known/acme-challenge/ { root /home/a/pub; }
    location /.well-known { proxy_pass http://backend; }
}
"""
        conflicts = self._make_analyzer(config).detect_location_conflicts()
        assert len(conflicts) >= 1
        types = {c['type'] for c in conflicts}
        assert 'prefix_overlap' in types

    def test_regex_conflict_detected(self):
        """Regex location that could match a prefix location is flagged."""
        config = """
server {
    server_name example.com;
    location /static { root /var/www; }
    location ~ /static/.* { root /var/cache; }
}
"""
        conflicts = self._make_analyzer(config).detect_location_conflicts()
        types = {c['type'] for c in conflicts}
        assert 'regex_shadows_prefix' in types

    def test_conflict_includes_server_name(self):
        """Conflict records include the server_name for context."""
        config = """
server {
    server_name mysite.com;
    location /app { proxy_pass http://app; }
    location /app/health { proxy_pass http://health; }
}
"""
        conflicts = self._make_analyzer(config).detect_location_conflicts()
        assert any(c['server'] == 'mysite.com' for c in conflicts)

    def test_conflict_includes_line_numbers(self):
        """Conflict records include line numbers for both locations."""
        config = """
server {
    server_name example.com;
    location /foo { proxy_pass http://a; }
    location /foo/bar { proxy_pass http://b; }
}
"""
        conflicts = self._make_analyzer(config).detect_location_conflicts()
        prefix_conflicts = [c for c in conflicts if c['type'] == 'prefix_overlap']
        assert len(prefix_conflicts) >= 1
        c = prefix_conflicts[0]
        assert 'line' in c['location_a']
        assert 'line' in c['location_b']

    def test_identical_paths_not_flagged(self):
        """Two location blocks with identical paths are not flagged as prefix overlap."""
        config = """
server {
    server_name example.com;
    location /api { proxy_pass http://a; }
    location /api { proxy_pass http://b; }
}
"""
        conflicts = self._make_analyzer(config).detect_location_conflicts()
        prefix_conflicts = [c for c in conflicts if c['type'] == 'prefix_overlap']
        # identical paths stripped of / are equal → not flagged (only strict prefixes flagged)
        assert prefix_conflicts == []


class TestCpanelCerts:
    """Tests for _handle_cpanel_certs() — S4 cPanel disk-cert vs live-cert comparison."""

    CPANEL_DIR = "/var/cpanel/ssl/apache_tls"

    def _make_analyzer(self, config: str):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(config)
        f.close()
        a = NginxAnalyzer(f.name)
        os.unlink(f.name)
        return a

    def _make_args(self, **kwargs):
        import argparse
        args = argparse.Namespace(
            cpanel_certs=True,
            check_acl=False,
            validate_nginx_acme=False,
            check_conflicts=False,
            extract=None,
            meta=False,
            check=False,
            validate_schema=None,
            no_fallback=False,
            format='text',
        )
        for k, v in kwargs.items():
            setattr(args, k, v)
        return args

    SSL_CONFIG = """
server {
    listen 443 ssl;
    server_name alpha.example.com;
    ssl_certificate /etc/ssl/alpha.crt;
}
server {
    listen 443 ssl;
    server_name beta.example.com;
    ssl_certificate /etc/ssl/beta.crt;
}
"""

    def _make_cert_info(self, cn='example.com', days=90, serial='AABB'):
        from datetime import datetime, timezone, timedelta
        from reveal.adapters.ssl.certificate import CertificateInfo
        now = datetime.now(timezone.utc)
        return CertificateInfo(
            subject={'commonName': cn},
            issuer={'organizationName': 'Test CA', 'commonName': 'Test CA Root'},
            not_before=now - timedelta(days=10),
            not_after=now + timedelta(days=days),
            serial_number=serial,
            version=3,
            san=[cn],
            signature_algorithm='sha256WithRSAEncryption',
        )

    def test_missing_disk_cert_shows_not_found(self, capsys):
        """When /var/cpanel/ssl/apache_tls/DOMAIN/combined is absent, show ⚫ not found."""
        from unittest.mock import patch, MagicMock
        from reveal.file_handler import _handle_cpanel_certs

        analyzer = self._make_analyzer(self.SSL_CONFIG)
        cert = self._make_cert_info(cn='alpha.example.com', days=60, serial='LIVE01')
        live_result = {
            'status': 'healthy',
            'leaf': {
                'days_until_expiry': 60,
                'serial_number': 'LIVE01',
                'not_after': cert.not_after.isoformat(),
            },
        }

        with patch('os.path.exists', return_value=False), \
             patch('reveal.adapters.ssl.certificate.check_ssl_health', return_value=live_result):
            _handle_cpanel_certs(analyzer)

        out = capsys.readouterr().out
        assert 'not found' in out or '⚫' in out

    def test_matching_serials_shows_match(self, capsys):
        """When disk serial == live serial, show ✅ same cert."""
        from unittest.mock import patch, MagicMock
        from reveal.file_handler import _handle_cpanel_certs

        analyzer = self._make_analyzer(self.SSL_CONFIG)
        serial = 'MATCHSERIAL'
        disk_cert = self._make_cert_info(cn='alpha.example.com', days=60, serial=serial)
        live_result = {
            'status': 'healthy',
            'leaf': {
                'days_until_expiry': 60,
                'serial_number': serial,
                'not_after': disk_cert.not_after.isoformat(),
            },
        }

        with patch('os.path.exists', return_value=True), \
             patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   return_value=(disk_cert, [])), \
             patch('reveal.adapters.ssl.certificate.check_ssl_health', return_value=live_result):
            _handle_cpanel_certs(analyzer)

        out = capsys.readouterr().out
        assert 'same cert' in out or '✅' in out

    def test_mismatched_serials_shows_stale(self, capsys):
        """When disk serial != live serial, show ⚠️  STALE (reload nginx)."""
        from unittest.mock import patch
        from reveal.file_handler import _handle_cpanel_certs
        import sys

        analyzer = self._make_analyzer("""
server {
    listen 443 ssl;
    server_name alpha.example.com;
    ssl_certificate /etc/ssl/alpha.crt;
}
""")
        disk_cert = self._make_cert_info(cn='alpha.example.com', days=5, serial='OLDSERIAL')
        live_result = {
            'status': 'healthy',
            'leaf': {
                'days_until_expiry': 60,
                'serial_number': 'NEWSERIAL',
                'not_after': disk_cert.not_after.isoformat(),
            },
        }

        with patch('os.path.exists', return_value=True), \
             patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   return_value=(disk_cert, [])), \
             patch('reveal.adapters.ssl.certificate.check_ssl_health', return_value=live_result), \
             pytest.raises(SystemExit) as exc_info:
            _handle_cpanel_certs(analyzer)

        assert exc_info.value.code == 2
        out = capsys.readouterr().out
        assert 'STALE' in out

    def test_cpanel_cert_path_format(self, capsys):
        """Cert path is /var/cpanel/ssl/apache_tls/DOMAIN/combined."""
        from unittest.mock import patch, call
        from reveal.file_handler import _handle_cpanel_certs

        analyzer = self._make_analyzer("""
server {
    listen 443 ssl;
    server_name mysite.example.com;
    ssl_certificate /etc/ssl/cert.crt;
}
""")
        disk_cert = self._make_cert_info(cn='mysite.example.com', days=60, serial='S1')
        live_result = {
            'status': 'healthy',
            'leaf': {'days_until_expiry': 60, 'serial_number': 'S1', 'not_after': ''},
        }

        exists_calls = []
        def fake_exists(p):
            exists_calls.append(p)
            return True

        with patch('os.path.exists', side_effect=fake_exists), \
             patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   return_value=(disk_cert, [])), \
             patch('reveal.adapters.ssl.certificate.check_ssl_health', return_value=live_result):
            _handle_cpanel_certs(analyzer)

        expected_path = '/var/cpanel/ssl/apache_tls/mysite.example.com/combined'
        assert expected_path in exists_calls

    def test_live_cert_error_shows_error(self, capsys):
        """When live cert check fails, show ❌ error."""
        from unittest.mock import patch
        from reveal.file_handler import _handle_cpanel_certs
        import sys

        analyzer = self._make_analyzer("""
server {
    listen 443 ssl;
    server_name alpha.example.com;
    ssl_certificate /etc/ssl/alpha.crt;
}
""")
        disk_cert = self._make_cert_info(cn='alpha.example.com', days=60, serial='S1')

        def raise_err(host, **kw):
            raise ConnectionError("Connection refused")

        with patch('os.path.exists', return_value=True), \
             patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   return_value=(disk_cert, [])), \
             patch('reveal.adapters.ssl.certificate.check_ssl_health', side_effect=raise_err):
            _handle_cpanel_certs(analyzer)

        out = capsys.readouterr().out
        # Error in live check → ? match, no sys.exit(2) for connection errors treated as unknown
        assert 'alpha.example.com' in out

    def test_no_ssl_domains_prints_message(self, capsys):
        """Nginx config with no SSL server blocks prints a helpful message."""
        from reveal.file_handler import _handle_cpanel_certs

        analyzer = self._make_analyzer("""
server {
    listen 80;
    server_name plain.example.com;
}
""")
        _handle_cpanel_certs(analyzer)
        out = capsys.readouterr().out
        assert 'No SSL domains' in out

    def test_wrong_analyzer_type_exits(self, tmp_path):
        """Passing a non-nginx analyzer (e.g. Python file) exits with error."""
        from reveal.file_handler import _handle_cpanel_certs
        from reveal.analyzers.python import PythonAnalyzer

        py_file = tmp_path / "foo.py"
        py_file.write_text("x = 1\n")
        analyzer = PythonAnalyzer(str(py_file))

        with pytest.raises(SystemExit) as exc_info:
            _handle_cpanel_certs(analyzer)
        assert exc_info.value.code == 1


class TestNginxDiagnose:
    """Tests for get_error_log_path(), diagnose_acme_errors(), and _handle_diagnose() — S3."""

    def _make_analyzer(self, config: str):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(config)
        f.close()
        a = NginxAnalyzer(f.name)
        os.unlink(f.name)
        return a

    SSL_CONFIG = """
server {
    listen 443 ssl;
    server_name alpha.example.com;
    ssl_certificate /etc/ssl/alpha.crt;
}
"""

    # --- get_error_log_path ---

    def test_get_error_log_path_from_directive(self):
        """error_log directive value is returned."""
        config = """
error_log /var/log/nginx/my_error.log warn;
server {
    listen 80;
    server_name x.com;
}
"""
        a = self._make_analyzer(config)
        assert a.get_error_log_path() == '/var/log/nginx/my_error.log'

    def test_get_error_log_path_no_directive_returns_none(self):
        """When no error_log directive, return None."""
        a = self._make_analyzer(self.SSL_CONFIG)
        assert a.get_error_log_path() is None

    def test_get_error_log_path_no_level_suffix(self):
        """error_log path only (no level token) still works."""
        config = "error_log /var/log/nginx/err.log;\n"
        a = self._make_analyzer(config)
        assert a.get_error_log_path() == '/var/log/nginx/err.log'

    # --- diagnose_acme_errors ---

    def _make_log(self, lines: list, tmp_path) -> str:
        """Write lines to a temp file and return path."""
        p = tmp_path / "error.log"
        p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return str(p)

    def test_permission_denied_detected(self, tmp_path):
        """Permission denied on /.well-known/ is classified as permission_denied."""
        log = self._make_log([
            '2026/02/15 03:21:17 [error] 123#123: *1 open() '
            '"/home/user/.well-known/acme-challenge/TOKEN" failed (13: Permission denied), '
            'client: 1.1.1.1, server: alpha.example.com, request: "GET /.well-known/ HTTP/1.1"',
        ], tmp_path)
        a = self._make_analyzer(self.SSL_CONFIG)
        hits = a.diagnose_acme_errors(log)
        assert len(hits) == 1
        assert hits[0]['domain'] == 'alpha.example.com'
        assert hits[0]['pattern'] == 'permission_denied'
        assert hits[0]['count'] == 1

    def test_not_found_detected(self, tmp_path):
        """ENOENT on /.well-known/ is classified as not_found."""
        log = self._make_log([
            '2026/02/15 04:00:00 [error] 123#123: *2 open() '
            '"/home/user/.well-known/acme-challenge/XYZ" failed (2: No such file or directory), '
            'client: 2.2.2.2, server: alpha.example.com, request: "GET /.well-known/ HTTP/1.1"',
        ], tmp_path)
        a = self._make_analyzer(self.SSL_CONFIG)
        hits = a.diagnose_acme_errors(log)
        assert len(hits) == 1
        assert hits[0]['pattern'] == 'not_found'

    def test_ssl_error_detected(self, tmp_path):
        """SSL_CTX_use_certificate error is classified as ssl_error."""
        log = self._make_log([
            '2026/02/15 05:00:00 [error] 123#123: *3 SSL_CTX_use_certificate_file("/etc/ssl/cert.crt") '
            'failed, server: alpha.example.com',
        ], tmp_path)
        a = self._make_analyzer(self.SSL_CONFIG)
        hits = a.diagnose_acme_errors(log)
        assert len(hits) == 1
        assert hits[0]['pattern'] == 'ssl_error'

    def test_unrelated_domain_not_included(self, tmp_path):
        """Errors for domains not in this nginx config are ignored."""
        log = self._make_log([
            '2026/02/15 03:21:17 [error] 123#123: *1 open() '
            '"/home/user/.well-known/acme-challenge/T" failed (13: Permission denied), '
            'client: 1.1.1.1, server: other.domain.com, request: "GET /.well-known/ HTTP/1.1"',
        ], tmp_path)
        a = self._make_analyzer(self.SSL_CONFIG)
        hits = a.diagnose_acme_errors(log)
        assert hits == []

    def test_count_accumulates_per_domain_pattern(self, tmp_path):
        """Multiple matching lines increment the count."""
        lines = [
            '2026/02/15 03:00:00 [error] 123#123: *1 open() '
            '"/home/user/.well-known/acme-challenge/A" failed (13: Permission denied), '
            'server: alpha.example.com, request: "GET / HTTP/1.1"',
        ] * 5
        log = self._make_log(lines, tmp_path)
        a = self._make_analyzer(self.SSL_CONFIG)
        hits = a.diagnose_acme_errors(log)
        assert len(hits) == 1
        assert hits[0]['count'] == 5

    def test_missing_log_file_returns_empty(self):
        """Non-existent log path returns empty list rather than raising."""
        a = self._make_analyzer(self.SSL_CONFIG)
        hits = a.diagnose_acme_errors('/nonexistent/path/error.log')
        assert hits == []

    def test_no_ssl_domains_returns_empty(self, tmp_path):
        """Config with no SSL server blocks returns empty list."""
        config = """
server {
    listen 80;
    server_name plain.example.com;
}
"""
        log = self._make_log([
            '2026/02/15 03:00:00 [error] open() "/.well-known/acme-challenge/T" '
            'failed (13: Permission denied), server: plain.example.com',
        ], tmp_path)
        a = self._make_analyzer(config)
        hits = a.diagnose_acme_errors(log)
        assert hits == []

    # --- _handle_diagnose ---

    def test_handle_diagnose_no_log_found_exits(self, tmp_path):
        """When no log path resolved and default paths absent, exit 1."""
        from unittest.mock import patch
        from reveal.file_handler import _handle_diagnose
        import argparse

        a = self._make_analyzer(self.SSL_CONFIG)
        with patch('os.path.exists', return_value=False), \
             pytest.raises(SystemExit) as exc_info:
            _handle_diagnose(a, log_path=None)
        assert exc_info.value.code == 1

    def test_handle_diagnose_clean_log_prints_ok(self, tmp_path, capsys):
        """When no hits found, print clean message and no exit."""
        from reveal.file_handler import _handle_diagnose

        log = self._make_log(['2026/02/15 03:00:00 [notice] nginx started'], tmp_path)
        a = self._make_analyzer(self.SSL_CONFIG)
        _handle_diagnose(a, log_path=log)
        out = capsys.readouterr().out
        assert 'No ACME' in out or '✅' in out

    def test_handle_diagnose_permission_denied_exits_2(self, tmp_path, capsys):
        """Permission denied hits trigger exit 2."""
        from reveal.file_handler import _handle_diagnose

        lines = [
            '2026/02/15 03:00:00 [error] 123#123: *1 open() '
            '"/home/user/.well-known/acme-challenge/A" failed (13: Permission denied), '
            'server: alpha.example.com, request: "GET / HTTP/1.1"',
        ]
        log = self._make_log(lines, tmp_path)
        a = self._make_analyzer(self.SSL_CONFIG)
        with pytest.raises(SystemExit) as exc_info:
            _handle_diagnose(a, log_path=log)
        assert exc_info.value.code == 2
        out = capsys.readouterr().out
        assert 'alpha.example.com' in out
        assert 'permission_denied' in out or 'Permission Denied' in out

    def test_handle_diagnose_wrong_analyzer_exits(self, tmp_path):
        """Non-nginx analyzer exits with error code 1."""
        from reveal.file_handler import _handle_diagnose
        from reveal.analyzers.python import PythonAnalyzer

        py_file = tmp_path / "foo.py"
        py_file.write_text("x = 1\n")
        a = PythonAnalyzer(str(py_file))
        with pytest.raises(SystemExit) as exc_info:
            _handle_diagnose(a, log_path='/some/log.log')
        assert exc_info.value.code == 1
