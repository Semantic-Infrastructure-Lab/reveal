"""Tests for the nginx:// URI adapter.

Covers the two bugs found during tia-proxy validation (2026-03-10):
  1. *.conf glob pattern missed extension-less sites-enabled files
  2. SERVER_BLOCK_RE only handled 1 level of brace nesting, missing SSL block
     when config had nested locations (location ~* inside location /)

Extended coverage (kilonova-throne-0311, BACK-015):
  - get_schema() completeness
  - All 5 element endpoints (ports, upstream, auth, locations, config)
  - Not-found handling
  - Helper function unit tests (ports, upstreams, auth, locations, warnings)
  - Schema via help://schemas/nginx endpoint
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
    _extract_ports,
    _extract_upstreams_referenced,
    _find_upstream_definitions,
    _extract_auth_directives,
    _extract_location_blocks,
    _detect_warnings,
    _resolve_symlink_info,
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


# ---------------------------------------------------------------------------
# Additional fixtures
# ---------------------------------------------------------------------------

_SIMPLE_VHOST = textwrap.dedent("""\
    server {
        listen 80;
        server_name example.com www.example.com;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl;
        server_name example.com www.example.com;

        ssl_certificate /etc/ssl/certs/example.pem;
        ssl_certificate_key /etc/ssl/private/example.key;

        upstream myapp {
            server 127.0.0.1:8000;
        }

        location / {
            proxy_pass http://myapp;
        }

        location /static {
            root /var/www/static;
        }
    }
""")


# ---------------------------------------------------------------------------
# Adapter init / URI parsing
# ---------------------------------------------------------------------------

class TestNginxUriAdapterInit:
    def test_overview_mode(self):
        adapter = NginxUriAdapter("nginx://")
        assert adapter.domain is None
        assert adapter.element is None

    def test_domain_only(self):
        adapter = NginxUriAdapter("nginx://example.com")
        assert adapter.domain == "example.com"
        assert adapter.element is None

    def test_domain_with_element(self):
        adapter = NginxUriAdapter("nginx://example.com/ports")
        assert adapter.domain == "example.com"
        assert adapter.element == "ports"

    def test_all_five_elements(self):
        for elem in ("ports", "upstream", "auth", "locations", "config"):
            adapter = NginxUriAdapter(f"nginx://example.com/{elem}")
            assert adapter.element == elem

    def test_subdomain(self):
        adapter = NginxUriAdapter("nginx://api.staging.example.com")
        assert adapter.domain == "api.staging.example.com"

    def test_empty_raises(self):
        with pytest.raises(TypeError):
            NginxUriAdapter("")

    def test_bare_slash_is_overview(self):
        adapter = NginxUriAdapter("nginx:///")
        assert adapter.domain is None


# ---------------------------------------------------------------------------
# get_schema()
# ---------------------------------------------------------------------------

class TestNginxUriAdapterSchema:
    def test_required_keys(self):
        schema = NginxUriAdapter.get_schema()
        for key in ('adapter', 'description', 'uri_syntax', 'query_params',
                    'elements', 'output_types', 'example_queries', 'notes'):
            assert key in schema, f"Missing key: {key}"

    def test_adapter_name(self):
        assert NginxUriAdapter.get_schema()['adapter'] == 'nginx'

    def test_all_elements_listed(self):
        elements = set(NginxUriAdapter.get_schema()['elements'].keys())
        assert elements == {'ports', 'upstream', 'auth', 'locations', 'config'}

    def test_output_types_cover_all_result_types(self):
        types = {ot['type'] for ot in NginxUriAdapter.get_schema()['output_types']}
        expected = {
            'nginx_sites_overview', 'nginx_vhost_summary', 'nginx_vhost_not_found',
            'nginx_vhost_ports', 'nginx_vhost_upstream', 'nginx_vhost_auth',
            'nginx_vhost_locations', 'nginx_vhost_config',
        }
        assert types == expected

    def test_example_queries_have_required_fields(self):
        for ex in NginxUriAdapter.get_schema()['example_queries']:
            assert 'uri' in ex
            assert 'description' in ex
            assert 'output_type' in ex

    def test_no_query_params(self):
        assert NginxUriAdapter.get_schema()['query_params'] == {}


# ---------------------------------------------------------------------------
# Vhost not-found
# ---------------------------------------------------------------------------

class TestNginxVhostNotFound:
    def test_type_when_no_dirs(self):
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', []):
            adapter = NginxUriAdapter("nginx://missing.example.com")
            result = adapter.get_structure()
        assert result['type'] == 'nginx_vhost_not_found'
        assert result['domain'] == 'missing.example.com'
        assert 'next_steps' in result

    def test_includes_searched_dirs(self):
        fake = ['/fake/sites-enabled']
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', fake):
            adapter = NginxUriAdapter("nginx://missing.example.com")
            result = adapter.get_structure()
        assert 'searched' in result


# ---------------------------------------------------------------------------
# Vhost summary (main endpoint)
# ---------------------------------------------------------------------------

class TestNginxVhostSummary:
    def test_type(self, tmp_path):
        (tmp_path / "example.conf").write_text(_SIMPLE_VHOST)
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', [str(tmp_path)]):
            result = NginxUriAdapter("nginx://example.com").get_structure()
        assert result['type'] == 'nginx_vhost_summary'

    def test_domain_set(self, tmp_path):
        (tmp_path / "example.conf").write_text(_SIMPLE_VHOST)
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', [str(tmp_path)]):
            result = NginxUriAdapter("nginx://example.com").get_structure()
        assert result['domain'] == 'example.com'

    def test_has_ports(self, tmp_path):
        (tmp_path / "example.conf").write_text(_SIMPLE_VHOST)
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', [str(tmp_path)]):
            result = NginxUriAdapter("nginx://example.com").get_structure()
        assert isinstance(result['ports'], list)
        assert len(result['ports']) > 0

    def test_has_next_steps(self, tmp_path):
        (tmp_path / "example.conf").write_text(_SIMPLE_VHOST)
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', [str(tmp_path)]):
            result = NginxUriAdapter("nginx://example.com").get_structure()
        assert 'next_steps' in result
        assert len(result['next_steps']) > 0

    def test_has_warnings_key(self, tmp_path):
        (tmp_path / "example.conf").write_text(_SIMPLE_VHOST)
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', [str(tmp_path)]):
            result = NginxUriAdapter("nginx://example.com").get_structure()
        assert 'warnings' in result


# ---------------------------------------------------------------------------
# All 5 element endpoints
# ---------------------------------------------------------------------------

class TestNginxElements:
    def _get(self, tmp_path, element):
        (tmp_path / "example.conf").write_text(_SIMPLE_VHOST)
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', [str(tmp_path)]):
            return NginxUriAdapter(f"nginx://example.com/{element}").get_structure()

    def test_ports(self, tmp_path):
        r = self._get(tmp_path, 'ports')
        assert r['type'] == 'nginx_vhost_ports'
        assert isinstance(r['ports'], list)

    def test_upstream(self, tmp_path):
        r = self._get(tmp_path, 'upstream')
        assert r['type'] == 'nginx_vhost_upstream'
        assert 'upstreams' in r

    def test_auth(self, tmp_path):
        r = self._get(tmp_path, 'auth')
        assert r['type'] == 'nginx_vhost_auth'
        assert 'auth' in r

    def test_locations(self, tmp_path):
        r = self._get(tmp_path, 'locations')
        assert r['type'] == 'nginx_vhost_locations'
        assert isinstance(r['locations'], list)

    def test_config(self, tmp_path):
        r = self._get(tmp_path, 'config')
        assert r['type'] == 'nginx_vhost_config'
        assert 'server_block' in r
        assert 'example.com' in r['server_block']

    def test_unknown_element_raises(self, tmp_path):
        (tmp_path / "example.conf").write_text(_SIMPLE_VHOST)
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', [str(tmp_path)]):
            adapter = NginxUriAdapter("nginx://example.com")
            adapter.element = 'nonexistent'
            with pytest.raises(ValueError, match='nonexistent'):
                adapter.get_structure()

    def test_element_on_missing_domain(self):
        with patch('reveal.adapters.nginx.adapter._NGINX_SEARCH_DIRS', []):
            result = NginxUriAdapter("nginx://missing.example.com/ports").get_structure()
        assert result['type'] == 'nginx_vhost_not_found'


# ---------------------------------------------------------------------------
# get_available_elements()
# ---------------------------------------------------------------------------

class TestNginxAvailableElements:
    def test_returns_all_five(self):
        adapter = NginxUriAdapter("nginx://example.com")
        names = {e['name'] for e in adapter.get_available_elements()}
        assert names == {'ports', 'upstream', 'auth', 'locations', 'config'}

    def test_each_has_name_description_example(self):
        for e in NginxUriAdapter("nginx://example.com").get_available_elements():
            assert 'name' in e and 'description' in e and 'example' in e

    def test_examples_include_domain(self):
        for e in NginxUriAdapter("nginx://mysite.com").get_available_elements():
            assert 'mysite.com' in e['example']

    def test_overview_mode_placeholder(self):
        elements = NginxUriAdapter("nginx://").get_available_elements()
        assert len(elements) == 5


# ---------------------------------------------------------------------------
# Helper: _extract_ports
# ---------------------------------------------------------------------------

class TestExtractPorts:
    def test_http_port(self):
        ports = _extract_ports("server { listen 80; server_name x.com; }")
        assert len(ports) == 1
        assert ports[0]['port'] == '80'
        assert not ports[0]['is_ssl']

    def test_https_port(self):
        ports = _extract_ports("server { listen 443 ssl; server_name x.com; }")
        assert ports[0]['is_ssl']

    def test_redirect_to_https_detected(self):
        block = "server { listen 80; return 301 https://$host$request_uri; }"
        assert _extract_ports(block)[0].get('redirect_to_https')

    def test_certbot_detected(self):
        block = "server { listen 443 ssl; # managed by letsencrypt\nserver_name x.com; }"
        ssl_port = next(p for p in _extract_ports(block) if p['is_ssl'])
        assert ssl_port.get('certbot_managed')

    def test_no_listen_directives(self):
        assert _extract_ports("server { server_name x.com; }") == []

    def test_multiple_listen(self):
        ports = _extract_ports("server { listen 80; listen 443 ssl; server_name x.com; }")
        assert len(ports) == 2


# ---------------------------------------------------------------------------
# Helper: _extract_upstreams_referenced
# ---------------------------------------------------------------------------

class TestExtractUpstreams:
    def test_proxy_pass_http(self):
        names = _extract_upstreams_referenced(
            "server { location / { proxy_pass http://myapp; } }")
        assert 'myapp' in names

    def test_no_proxy_pass(self):
        assert _extract_upstreams_referenced(
            "server { location / { root /var/www; } }") == []

    def test_no_duplicates(self):
        block = ("server { location / { proxy_pass http://myapp; } "
                 "location /api { proxy_pass http://myapp; } }")
        assert _extract_upstreams_referenced(block).count('myapp') == 1


# ---------------------------------------------------------------------------
# Helper: _find_upstream_definitions
# ---------------------------------------------------------------------------

class TestFindUpstreamDefs:
    def test_finds_upstream_block(self):
        content = "upstream myapp { server 127.0.0.1:8000; }\nserver {}"
        defs = _find_upstream_definitions(content, ['myapp'])
        assert 'myapp' in defs
        assert 'servers' in defs['myapp']

    def test_referenced_but_undefined_is_stub(self):
        """Upstream referenced by proxy_pass but not defined → stub entry."""
        content = "server { location / { proxy_pass http://backend; } }"
        defs = _find_upstream_definitions(content, ['backend'])
        assert 'backend' in defs
        assert defs['backend']['servers'] == []

    def test_multiple_servers(self):
        content = "upstream app { server 127.0.0.1:3000; server 127.0.0.1:3001; }"
        defs = _find_upstream_definitions(content, ['app'])
        assert len(defs['app']['servers']) == 2


# ---------------------------------------------------------------------------
# Helper: _extract_auth_directives
# ---------------------------------------------------------------------------

class TestExtractAuth:
    def test_auth_basic_detected(self):
        # auth_basic regex uses ^ so must be at start of line
        block = 'server {\n    auth_basic "Restricted Area";\n    auth_basic_user_file /etc/.htpasswd;\n}'
        auth = _extract_auth_directives(block)
        assert auth.get('auth_basic') == 'Restricted Area'

    def test_auth_request_detected(self):
        block = 'server {\n    auth_request /auth;\n}'
        auth = _extract_auth_directives(block)
        assert auth.get('auth_request') == '/auth'

    def test_no_auth(self):
        block = 'server {\n    location / { root /var/www; }\n}'
        auth = _extract_auth_directives(block)
        assert auth.get('auth_basic') is None
        assert auth.get('auth_request') is None


# ---------------------------------------------------------------------------
# Helper: _extract_location_blocks
# ---------------------------------------------------------------------------

class TestExtractLocations:
    def test_basic_location(self):
        locs = _extract_location_blocks("server { location / { root /var/www; } }")
        assert len(locs) == 1
        assert locs[0]['path'] == '/'

    def test_multiple_locations(self):
        block = ("server { location / { root /var/www; } "
                 "location /api { proxy_pass http://backend; } }")
        paths = [l['path'] for l in _extract_location_blocks(block)]
        assert '/' in paths and '/api' in paths

    def test_proxy_pass_gives_proxy_type(self):
        locs = _extract_location_blocks("server { location / { proxy_pass http://myapp; } }")
        assert locs[0].get('type') == 'proxy'
        assert 'myapp' in locs[0].get('target', '')

    def test_no_locations(self):
        assert _extract_location_blocks("server { server_name x.com; }") == []


# ---------------------------------------------------------------------------
# Helper: _detect_warnings
# ---------------------------------------------------------------------------

class TestDetectWarnings:
    def test_no_ssl_generates_warning(self):
        warnings = _detect_warnings([{'port': '80', 'is_ssl': False}], {}, {}, {})
        assert any('HTTPS' in w or 'ssl' in w.lower() or '443' in w for w in warnings)

    def test_ssl_present_no_https_warning(self):
        ports = [{'port': '80', 'is_ssl': False}, {'port': '443', 'is_ssl': True}]
        warnings = _detect_warnings(ports, {}, {}, {})
        https_warnings = [w for w in warnings if 'No HTTPS' in w]
        assert https_warnings == []


# ---------------------------------------------------------------------------
# Helper: _resolve_symlink_info
# ---------------------------------------------------------------------------

class TestResolveSymlink:
    def test_regular_file(self, tmp_path):
        f = tmp_path / "test.conf"
        f.write_text("")
        info = _resolve_symlink_info(str(f))
        assert not info['is_symlink']
        assert info['target'] is None

    def test_symlink(self, tmp_path):
        target = tmp_path / "target.conf"
        link = tmp_path / "link.conf"
        target.write_text("server {}")
        link.symlink_to(target)
        info = _resolve_symlink_info(str(link))
        assert info['is_symlink']
        assert info['target'] is not None


# ---------------------------------------------------------------------------
# Schema via help://schemas/nginx (integration)
# ---------------------------------------------------------------------------

class TestSchemaViaHelpEndpoint:
    def test_returns_nginx_adapter_name(self):
        from reveal.adapters.help import HelpAdapter
        result = HelpAdapter("help://").get_element("schemas/nginx")
        assert result.get('adapter') == 'nginx'

    def test_output_types_present(self):
        from reveal.adapters.help import HelpAdapter
        result = HelpAdapter("help://").get_element("schemas/nginx")
        assert 'output_types' in result
        assert len(result['output_types']) > 0
