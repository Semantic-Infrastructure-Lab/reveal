"""Tests for NginxUriRenderer.

Covers all 13 static render methods using capsys to capture stdout/stderr.
"""
import sys
import pytest
from reveal.adapters.nginx.renderer import NginxUriRenderer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

R = NginxUriRenderer


# ---------------------------------------------------------------------------
# _render_nginx_sites_overview
# ---------------------------------------------------------------------------

class TestRenderNginxSitesOverview:
    def test_header_shows_count(self, capsys):
        R._render_nginx_sites_overview({'sites': [
            {'file': 'example.com', 'enabled': True, 'is_symlink': False, 'domains': ['example.com']},
        ]})
        out = capsys.readouterr().out
        assert '1 configs found' in out

    def test_enabled_site_shows_checkmark(self, capsys):
        R._render_nginx_sites_overview({'sites': [
            {'file': 'site.conf', 'enabled': True, 'is_symlink': False, 'domains': ['site.example.com']},
        ]})
        out = capsys.readouterr().out
        assert '✅' in out
        assert 'site.conf' in out

    def test_disabled_site_shows_cross(self, capsys):
        R._render_nginx_sites_overview({'sites': [
            {'file': 'disabled.conf', 'enabled': False, 'is_symlink': False, 'domains': []},
        ]})
        out = capsys.readouterr().out
        assert '❌' in out

    def test_symlink_annotated(self, capsys):
        R._render_nginx_sites_overview({'sites': [
            {'file': 'sym.conf', 'enabled': True, 'is_symlink': True, 'domains': ['x.com']},
        ]})
        out = capsys.readouterr().out
        assert 'symlink' in out

    def test_empty_sites(self, capsys):
        R._render_nginx_sites_overview({'sites': []})
        out = capsys.readouterr().out
        assert 'No nginx config files found' in out

    def test_many_domains_truncated(self, capsys):
        domains = ['a.com', 'b.com', 'c.com', 'd.com', 'e.com', 'f.com']
        R._render_nginx_sites_overview({'sites': [
            {'file': 'multi.conf', 'enabled': True, 'is_symlink': False, 'domains': domains},
        ]})
        out = capsys.readouterr().out
        assert '+2 more' in out

    def test_next_steps_printed(self, capsys):
        R._render_nginx_sites_overview({'sites': [], 'next_steps': ['Run nginx -t']})
        out = capsys.readouterr().out
        assert 'Run nginx -t' in out

    def test_no_next_steps_no_crash(self, capsys):
        R._render_nginx_sites_overview({'sites': []})
        capsys.readouterr()  # no exception


# ---------------------------------------------------------------------------
# _render_nginx_vhost_not_found
# ---------------------------------------------------------------------------

class TestRenderNginxVhostNotFound:
    def test_shows_domain(self, capsys):
        R._render_nginx_vhost_not_found({'domain': 'missing.com'})
        out = capsys.readouterr().out
        assert 'missing.com' in out
        assert '❌' in out

    def test_shows_config_file_when_present(self, capsys):
        R._render_nginx_vhost_not_found({'domain': 'x.com', 'config_file': '/etc/nginx/x.conf'})
        out = capsys.readouterr().out
        assert '/etc/nginx/x.conf' in out

    def test_shows_note(self, capsys):
        R._render_nginx_vhost_not_found({'domain': 'x.com', 'note': 'Check sites-enabled'})
        out = capsys.readouterr().out
        assert 'Check sites-enabled' in out

    def test_searched_dirs_listed(self, capsys):
        R._render_nginx_vhost_not_found({'domain': 'x.com', 'searched': ['/etc/nginx/sites-enabled']})
        out = capsys.readouterr().out
        assert '/etc/nginx/sites-enabled' in out

    def test_next_steps_printed(self, capsys):
        R._render_nginx_vhost_not_found({'domain': 'x.com', 'next_steps': ['Check DNS']})
        out = capsys.readouterr().out
        assert 'Check DNS' in out


# ---------------------------------------------------------------------------
# _print_ports
# ---------------------------------------------------------------------------

class TestPrintPorts:
    def test_ssl_port(self, capsys):
        R._print_ports([{'port': '443', 'spec': '443 ssl', 'is_ssl': True, 'certbot_managed': False}])
        out = capsys.readouterr().out
        assert 'HTTPS' in out
        assert '443' in out

    def test_certbot_managed_noted(self, capsys):
        R._print_ports([{'port': '443', 'spec': '443 ssl', 'is_ssl': True, 'certbot_managed': True}])
        out = capsys.readouterr().out
        assert 'certbot-managed' in out

    def test_http_port(self, capsys):
        R._print_ports([{'port': '80', 'spec': '80', 'is_ssl': False, 'redirect_to_https': False}])
        out = capsys.readouterr().out
        assert 'HTTP' in out
        assert '80' in out

    def test_redirect_to_https_noted(self, capsys):
        R._print_ports([{'port': '80', 'spec': '80', 'is_ssl': False, 'redirect_to_https': True}])
        out = capsys.readouterr().out
        assert 'redirect to HTTPS' in out

    def test_empty_ports(self, capsys):
        R._print_ports([])
        out = capsys.readouterr().out
        assert 'no listen directives' in out


# ---------------------------------------------------------------------------
# _print_upstreams
# ---------------------------------------------------------------------------

class TestPrintUpstreams:
    def test_reachable_server(self, capsys):
        R._print_upstreams({'myapp': {
            'definition': {'servers': ['127.0.0.1:8080']},
            'reachability': [{'address': '127.0.0.1:8080', 'reachable': True}],
        }})
        out = capsys.readouterr().out
        assert 'myapp' in out
        assert '✅' in out

    def test_unreachable_server_with_error(self, capsys):
        R._print_upstreams({'myapp': {
            'definition': {'servers': ['127.0.0.1:9999']},
            'reachability': [{'address': '127.0.0.1:9999', 'reachable': False, 'error': 'Connection refused'}],
        }})
        out = capsys.readouterr().out
        assert '❌' in out
        assert 'Connection refused' in out

    def test_empty_upstreams(self, capsys):
        R._print_upstreams({})
        out = capsys.readouterr().out
        assert 'no proxy_pass found' in out

    def test_falls_back_to_reachability_addresses(self, capsys):
        R._print_upstreams({'app': {
            'definition': None,
            'reachability': [{'address': '10.0.0.1:80', 'reachable': True}],
        }})
        out = capsys.readouterr().out
        assert '10.0.0.1:80' in out


# ---------------------------------------------------------------------------
# _print_auth
# ---------------------------------------------------------------------------

class TestPrintAuth:
    def test_no_auth(self, capsys):
        R._print_auth({})
        out = capsys.readouterr().out
        assert 'none' in out

    def test_auth_basic(self, capsys):
        R._print_auth({'auth_basic': 'Restricted Area'})
        out = capsys.readouterr().out
        assert 'auth_basic' in out
        assert 'Restricted Area' in out

    def test_auth_request(self, capsys):
        R._print_auth({'auth_request': '/auth'})
        out = capsys.readouterr().out
        assert 'auth_request' in out
        assert '/auth' in out

    def test_per_location_auth(self, capsys):
        R._print_auth({'locations_with_auth': [
            {'path': '/admin', 'auth_basic': 'Admin'},
        ]})
        out = capsys.readouterr().out
        assert '/admin' in out
        assert 'Admin' in out

    def test_per_location_auth_request(self, capsys):
        R._print_auth({'locations_with_auth': [
            {'path': '/api', 'auth_request': '/check'},
        ]})
        out = capsys.readouterr().out
        assert '/api' in out
        assert '/check' in out


# ---------------------------------------------------------------------------
# _print_locations
# ---------------------------------------------------------------------------

class TestPrintLocations:
    def test_proxy_location(self, capsys):
        R._print_locations([{'path': '/', 'target': 'http://app', 'type': 'proxy'}])
        out = capsys.readouterr().out
        assert '/' in out
        assert 'proxy' in out
        assert 'http://app' in out

    def test_static_location(self, capsys):
        R._print_locations([{'path': '/static', 'target': '/var/www', 'type': 'static'}])
        out = capsys.readouterr().out
        assert 'static' in out

    def test_auth_basic_on_location(self, capsys):
        R._print_locations([{'path': '/secure', 'target': '', 'type': 'other', 'auth_basic': 'Zone'}])
        out = capsys.readouterr().out
        assert 'auth_basic' in out

    def test_auth_off_on_location(self, capsys):
        R._print_locations([{'path': '/open', 'target': '', 'type': 'other', 'auth_basic': None}])
        out = capsys.readouterr().out
        assert 'auth off' in out

    def test_empty_locations(self, capsys):
        R._print_locations([])
        out = capsys.readouterr().out
        assert 'no location blocks found' in out


# ---------------------------------------------------------------------------
# _render_nginx_vhost_summary
# ---------------------------------------------------------------------------

class TestRenderNginxVhostSummary:
    def _make_result(self, **kwargs):
        base = {
            'domain': 'example.com',
            'config_file': '/etc/nginx/sites-enabled/example.com',
            'symlink': {},
            'ports': [],
            'upstreams': {},
            'auth': {},
            'locations': [],
            'warnings': [],
        }
        base.update(kwargs)
        return base

    def test_domain_in_header(self, capsys):
        R._render_nginx_vhost_summary(self._make_result())
        out = capsys.readouterr().out
        assert 'example.com' in out

    def test_symlink_info_shown(self, capsys):
        result = self._make_result(symlink={'is_symlink': True, 'target': '/etc/nginx/sites-available/x', 'exists': True})
        R._render_nginx_vhost_summary(result)
        out = capsys.readouterr().out
        assert 'Symlinked' in out

    def test_broken_symlink_shows_cross(self, capsys):
        result = self._make_result(symlink={'is_symlink': True, 'target': '/missing', 'exists': False})
        R._render_nginx_vhost_summary(result)
        out = capsys.readouterr().out
        assert '❌' in out

    def test_warnings_shown(self, capsys):
        result = self._make_result(warnings=['Missing SSL cert'])
        R._render_nginx_vhost_summary(result)
        out = capsys.readouterr().out
        assert 'Missing SSL cert' in out

    def test_next_steps_shown(self, capsys):
        result = self._make_result(next_steps=['certbot renew'])
        R._render_nginx_vhost_summary(result)
        out = capsys.readouterr().out
        assert 'certbot renew' in out


# ---------------------------------------------------------------------------
# Element sub-renderers (ports/upstream/auth/locations/config)
# ---------------------------------------------------------------------------

class TestElementRenderers:
    def test_render_vhost_ports(self, capsys):
        R._render_nginx_vhost_ports({'domain': 'x.com', 'ports': []})
        out = capsys.readouterr().out
        assert 'x.com' in out
        assert 'Ports' in out

    def test_render_vhost_upstream(self, capsys):
        R._render_nginx_vhost_upstream({'domain': 'x.com', 'upstreams': {}})
        out = capsys.readouterr().out
        assert 'x.com' in out
        assert 'Upstream' in out

    def test_render_vhost_auth(self, capsys):
        R._render_nginx_vhost_auth({'domain': 'x.com', 'auth': {}})
        out = capsys.readouterr().out
        assert 'x.com' in out
        assert 'Auth' in out

    def test_render_vhost_locations(self, capsys):
        R._render_nginx_vhost_locations({'domain': 'x.com', 'locations': []})
        out = capsys.readouterr().out
        assert 'x.com' in out
        assert 'Location' in out

    def test_render_vhost_config(self, capsys):
        R._render_nginx_vhost_config({
            'domain': 'x.com',
            'config_file': '/etc/nginx/x.conf',
            'server_block': 'server { listen 80; }',
        })
        out = capsys.readouterr().out
        assert 'x.com' in out
        assert 'server { listen 80; }' in out

    def test_element_next_steps(self, capsys):
        R._render_nginx_vhost_ports({'domain': 'x.com', 'ports': [], 'next_steps': ['reload nginx']})
        out = capsys.readouterr().out
        assert 'reload nginx' in out


# ---------------------------------------------------------------------------
# render_error
# ---------------------------------------------------------------------------

class TestRenderError:
    def test_unknown_element_error(self, capsys):
        R.render_error(ValueError("Unknown element: foo"))
        err = capsys.readouterr().err
        assert 'Unknown element' in err
        assert 'Available elements' in err

    def test_generic_error(self, capsys):
        R.render_error(RuntimeError("Something went wrong"))
        err = capsys.readouterr().err
        assert 'Something went wrong' in err
