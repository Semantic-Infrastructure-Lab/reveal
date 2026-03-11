"""Tests for the nginx:// URI adapter.

Covers the two bugs found during tia-proxy validation (2026-03-10):
  1. *.conf glob pattern missed extension-less sites-enabled files
  2. SERVER_BLOCK_RE only handled 1 level of brace nesting, missing SSL block
     when config had nested locations (location ~* inside location /)
"""
import os
import tempfile
import textwrap
import pytest
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.nginx.adapter import (
    NginxUriAdapter,
    _iter_nginx_configs,
    _parse_server_block_for_domain,
    _NGINX_SEARCH_DIRS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_SSL_VHOST = textwrap.dedent("""\
    upstream myapp {
        server 127.0.0.1:8080;
    }
    server {
        server_name example.com;
        listen 443 ssl;
        ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
        location / { proxy_pass http://myapp; }
    }
    server {
        if ($host = example.com) { return 301 https://$host$request_uri; }
        listen 80;
        server_name example.com;
        return 404;
    }
""")

# Has nested location block (location ~* inside location /) — 2 levels deep
NESTED_LOCATION_VHOST = textwrap.dedent("""\
    server {
        server_name nested.example.com;
        listen 443 ssl;
        ssl_certificate /etc/letsencrypt/live/nested.example.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/nested.example.com/privkey.pem;
        location / {
            root /var/www/html;
            try_files $uri $uri/ /index.html;
            location ~* \\.(js|css|png|jpg)$ {
                expires 1y;
                add_header Cache-Control "public, immutable";
            }
        }
    }
    server {
        if ($host = nested.example.com) { return 301 https://$host$request_uri; }
        listen 80;
        server_name nested.example.com;
        return 404;
    }
""")


# ---------------------------------------------------------------------------
# Bug 1: glob pattern — extension-less files must be found in sites-enabled
# ---------------------------------------------------------------------------

class TestIterNginxConfigs:
    """_iter_nginx_configs() must match nginx's own include logic."""

    def test_sites_enabled_includes_extension_less_files(self, tmp_path):
        """sites-enabled/ must yield files without .conf extension."""
        sites = tmp_path / "sites-enabled"
        sites.mkdir()
        (sites / "example.com").write_text(SIMPLE_SSL_VHOST)
        (sites / "other.com.conf").write_text(SIMPLE_SSL_VHOST)

        found = list(_iter_nginx_configs(str(sites)))
        names = [os.path.basename(f) for f in found]
        assert "example.com" in names, "extension-less file should be included in sites-enabled"
        assert "other.com.conf" in names

    def test_conf_d_only_includes_conf_files(self, tmp_path):
        """conf.d/ must yield only .conf files (nginx include conf.d/*.conf)."""
        confd = tmp_path / "conf.d"
        confd.mkdir()
        (confd / "upstreams.conf").write_text("upstream foo { server 127.0.0.1; }")
        (confd / "upstreams.conf.bak").write_text("# backup")
        (confd / "mysite").write_text(SIMPLE_SSL_VHOST)

        found = list(_iter_nginx_configs(str(confd)))
        names = [os.path.basename(f) for f in found]
        assert "upstreams.conf" in names
        assert "upstreams.conf.bak" not in names, ".bak should be skipped"
        assert "mysite" not in names, "extension-less file should NOT be in conf.d"

    def test_backup_files_excluded_from_sites_enabled(self, tmp_path):
        """Backup/temp files must be excluded everywhere."""
        sites = tmp_path / "sites-enabled"
        sites.mkdir()
        (sites / "example.com").write_text(SIMPLE_SSL_VHOST)
        (sites / "example.com.bak").write_text(SIMPLE_SSL_VHOST)
        (sites / "old.conf.backup-20260101").write_text(SIMPLE_SSL_VHOST)

        found = list(_iter_nginx_configs(str(sites)))
        names = [os.path.basename(f) for f in found]
        assert "example.com" in names
        assert "example.com.bak" not in names
        assert "old.conf.backup-20260101" not in names

    def test_domain_lookup_finds_extension_less_file(self, tmp_path):
        """NginxUriAdapter must find a domain in an extension-less config file."""
        sites = tmp_path / "sites-enabled"
        sites.mkdir()
        (sites / "example.com").write_text(SIMPLE_SSL_VHOST)

        with patch.object(
            __import__('reveal.adapters.nginx.adapter', fromlist=['_NGINX_SEARCH_DIRS']),
            '_NGINX_SEARCH_DIRS',
            [str(sites)],
        ):
            adapter = NginxUriAdapter('nginx://example.com')
            result = adapter.get_structure()

        assert result.get('type') == 'nginx_vhost_summary'
        assert result['domain'] == 'example.com'
        assert result['config_file'].endswith('example.com'), \
            f"Expected config_file to end with 'example.com', got: {result['config_file']}"


# ---------------------------------------------------------------------------
# Bug 2: nested location blocks — SSL block must be found
# ---------------------------------------------------------------------------

class TestParseServerBlockNesting:
    """_parse_server_block_for_domain() must handle 3 levels of brace nesting."""

    def test_simple_vhost_both_blocks_extracted(self):
        """Both HTTPS and HTTP redirect blocks must be extracted."""
        result = _parse_server_block_for_domain(SIMPLE_SSL_VHOST, 'example.com')
        assert result is not None
        assert 'listen 443' in result
        assert 'listen 80' in result

    def test_nested_location_vhost_ssl_block_extracted(self):
        """SSL server block must be found even with nested location blocks."""
        result = _parse_server_block_for_domain(NESTED_LOCATION_VHOST, 'nested.example.com')
        assert result is not None, "Server block should be found"
        assert 'listen 443' in result, \
            "SSL (443) listen directive must appear in extracted block"
        assert 'listen 80' in result

    def test_nested_location_vhost_ports_correct(self, tmp_path):
        """NginxUriAdapter must report both 443 and 80 for nested-location vhosts."""
        sites = tmp_path / "sites-enabled"
        sites.mkdir()
        (sites / "nested.example.com").write_text(NESTED_LOCATION_VHOST)

        with patch.object(
            __import__('reveal.adapters.nginx.adapter', fromlist=['_NGINX_SEARCH_DIRS']),
            '_NGINX_SEARCH_DIRS',
            [str(sites)],
        ):
            adapter = NginxUriAdapter('nginx://nested.example.com')
            result = adapter.get_structure()

        ports = result.get('ports', [])
        port_numbers = [p['port'] for p in ports]
        assert '443' in port_numbers, \
            "Port 443 must be detected even with nested location blocks"
        assert '80' in port_numbers
        ssl_ports = [p for p in ports if p.get('is_ssl')]
        assert ssl_ports, "At least one SSL port must be detected"
        assert not result.get('warnings') or \
            'No HTTPS listener' not in ' '.join(result.get('warnings', [])), \
            "Should NOT warn about missing HTTPS when 443 ssl is present"


# ---------------------------------------------------------------------------
# Overview mode
# ---------------------------------------------------------------------------

class TestNginxUriOverview:
    """nginx:// (no domain) must list all sites from sites-enabled."""

    def test_overview_lists_extension_less_files(self, tmp_path):
        sites = tmp_path / "sites-enabled"
        sites.mkdir()
        (sites / "alpha.example.com").write_text(SIMPLE_SSL_VHOST.replace('example.com', 'alpha.example.com'))
        (sites / "beta.example.com.conf").write_text(SIMPLE_SSL_VHOST.replace('example.com', 'beta.example.com'))
        (sites / "backup.conf.bak").write_text("# should be ignored")

        with patch.object(
            __import__('reveal.adapters.nginx.adapter', fromlist=['_NGINX_SEARCH_DIRS']),
            '_NGINX_SEARCH_DIRS',
            [str(sites)],
        ):
            adapter = NginxUriAdapter('nginx://')
            result = adapter.get_structure()

        sites_found = result.get('sites', [])
        all_domains = [d for s in sites_found for d in s['domains']]
        assert 'alpha.example.com' in all_domains, "Extension-less vhost must appear in overview"
        assert 'beta.example.com' in all_domains, ".conf vhost must appear in overview"
        assert len(sites_found) == 2, "Backup .bak file must not appear in overview"
