"""Tests for NginxRenderer (rendering/adapters/nginx.py).

Each `_render_<type>` returns its text body; the section helpers return lines. Failure detail
and the fleet-audit exit code are checked through the URI seam (BACK-916).
"""
import pytest
from reveal.cli.defaults import _default_args
from reveal.cli.routing import uri as router
from reveal.rendering.adapters import nginx as nginx_rendering
from reveal.rendering.adapters.nginx import NginxRenderer
from reveal.rendering.base import emit_rendered

# BACK-1149: component-layer test -- single adapter/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

R = NginxRenderer


def _lines(helper, *args):
    return '\n'.join(helper(*args))


# ---------------------------------------------------------------------------
# _render_nginx_sites_overview
# ---------------------------------------------------------------------------

class TestRenderNginxSitesOverview:
    def test_header_shows_count(self):
        out = R._render_nginx_sites_overview({'sites': [
            {'file': 'example.com', 'enabled': True, 'is_symlink': False, 'domains': ['example.com']},
        ]})
        assert '1 configs found' in out

    def test_enabled_site_shows_checkmark(self):
        out = R._render_nginx_sites_overview({'sites': [
            {'file': 'site.conf', 'enabled': True, 'is_symlink': False, 'domains': ['site.example.com']},
        ]})
        assert '✅' in out
        assert 'site.conf' in out

    def test_disabled_site_shows_cross(self):
        out = R._render_nginx_sites_overview({'sites': [
            {'file': 'disabled.conf', 'enabled': False, 'is_symlink': False, 'domains': []},
        ]})
        assert '❌' in out

    def test_symlink_annotated(self):
        out = R._render_nginx_sites_overview({'sites': [
            {'file': 'sym.conf', 'enabled': True, 'is_symlink': True, 'domains': ['x.com']},
        ]})
        assert 'symlink' in out

    def test_empty_sites(self):
        out = R._render_nginx_sites_overview({'sites': []})
        assert 'No nginx config files found' in out

    def test_many_domains_truncated(self):
        domains = ['a.com', 'b.com', 'c.com', 'd.com', 'e.com', 'f.com']
        out = R._render_nginx_sites_overview({'sites': [
            {'file': 'multi.conf', 'enabled': True, 'is_symlink': False, 'domains': domains},
        ]})
        assert '+2 more' in out

    def test_next_steps_printed(self):
        out = R._render_nginx_sites_overview({'sites': [], 'next_steps': ['Run nginx -t']})
        assert 'Run nginx -t' in out

    def test_no_next_steps_no_crash(self):
        assert 'Next Steps' not in R._render_nginx_sites_overview({'sites': []})


# ---------------------------------------------------------------------------
# _render_nginx_vhost_not_found
# ---------------------------------------------------------------------------

class TestRenderNginxVhostNotFound:
    """A miss is a failed result (BACK-1523): the router prints its error; the renderer
    adds only the detail, on stderr, and nothing on stdout (BACK-1553). The detail used to sit
    in a method the failed-result branch never called, so the text output lost it."""

    MISS = {'type': 'nginx_vhost_not_found', 'domain': 'missing.com',
            'error': "No nginx config found for 'missing.com'",
            'searched': ['/etc/nginx/sites-enabled', '/etc/nginx/conf.d'],
            'next_steps': ['Check DNS']}

    def test_text_reports_searched_dirs_on_stderr_only(self, capsys):
        emit_rendered(R.render_structure, self.MISS, 'text')
        captured = capsys.readouterr()
        assert captured.out == ''
        assert '/etc/nginx/sites-enabled' in captured.err
        assert '/etc/nginx/conf.d' in captured.err
        assert 'Check DNS' in captured.err
        assert 'missing.com' not in captured.err  # the router's error line names it

    def test_json_prints_the_envelope_and_no_detail_on_stderr(self, capsys):
        emit_rendered(R.render_structure, self.MISS, 'json')
        captured = capsys.readouterr()
        assert '"searched"' in captured.out
        assert captured.err == ''

    def test_shows_config_file_when_present(self):
        assert '/etc/nginx/x.conf' in '\n'.join(R._failure_detail({'config_file': '/etc/nginx/x.conf'}))

    def test_shows_note(self):
        assert 'Check sites-enabled' in '\n'.join(R._failure_detail({'note': 'Check sites-enabled'}))

    def test_no_detail_when_nothing_to_add(self):
        assert R._failure_detail({'domain': 'x.com'}) == []


# ---------------------------------------------------------------------------
# _print_ports
# ---------------------------------------------------------------------------

class TestPrintPorts:
    def test_ssl_port(self):
        out = _lines(nginx_rendering._ports, [{'port': '443', 'spec': '443 ssl', 'is_ssl': True, 'certbot_managed': False}])
        assert 'HTTPS' in out
        assert '443' in out

    def test_certbot_managed_noted(self):
        out = _lines(nginx_rendering._ports, [{'port': '443', 'spec': '443 ssl', 'is_ssl': True, 'certbot_managed': True}])
        assert 'certbot-managed' in out

    def test_http_port(self):
        out = _lines(nginx_rendering._ports, [{'port': '80', 'spec': '80', 'is_ssl': False, 'redirect_to_https': False}])
        assert 'HTTP' in out
        assert '80' in out

    def test_redirect_to_https_noted(self):
        out = _lines(nginx_rendering._ports, [{'port': '80', 'spec': '80', 'is_ssl': False, 'redirect_to_https': True}])
        assert 'redirect to HTTPS' in out

    def test_empty_ports(self):
        out = _lines(nginx_rendering._ports, [])
        assert 'no listen directives' in out


# ---------------------------------------------------------------------------
# _print_upstreams
# ---------------------------------------------------------------------------

class TestPrintUpstreams:
    def test_reachable_server(self):
        out = _lines(nginx_rendering._upstreams, {'myapp': {
            'definition': {'servers': ['127.0.0.1:8080']},
            'reachability': [{'address': '127.0.0.1:8080', 'reachable': True}],
        }})
        assert 'myapp' in out
        assert '✅' in out

    def test_unreachable_server_with_error(self):
        out = _lines(nginx_rendering._upstreams, {'myapp': {
            'definition': {'servers': ['127.0.0.1:9999']},
            'reachability': [{'address': '127.0.0.1:9999', 'reachable': False, 'error': 'Connection refused'}],
        }})
        assert '❌' in out
        assert 'Connection refused' in out

    def test_empty_upstreams(self):
        out = _lines(nginx_rendering._upstreams, {})
        assert 'no proxy_pass found' in out

    def test_falls_back_to_reachability_addresses(self):
        out = _lines(nginx_rendering._upstreams, {'app': {
            'definition': None,
            'reachability': [{'address': '10.0.0.1:80', 'reachable': True}],
        }})
        assert '10.0.0.1:80' in out


# ---------------------------------------------------------------------------
# _print_auth
# ---------------------------------------------------------------------------

class TestPrintAuth:
    def test_no_auth(self):
        out = _lines(nginx_rendering._auth, {})
        assert 'none' in out

    def test_auth_basic(self):
        out = _lines(nginx_rendering._auth, {'auth_basic': 'Restricted Area'})
        assert 'auth_basic' in out
        assert 'Restricted Area' in out

    def test_auth_request(self):
        out = _lines(nginx_rendering._auth, {'auth_request': '/auth'})
        assert 'auth_request' in out
        assert '/auth' in out

    def test_per_location_auth(self):
        out = _lines(nginx_rendering._auth, {'locations_with_auth': [
            {'path': '/admin', 'auth_basic': 'Admin'},
        ]})
        assert '/admin' in out
        assert 'Admin' in out

    def test_per_location_auth_request(self):
        out = _lines(nginx_rendering._auth, {'locations_with_auth': [
            {'path': '/api', 'auth_request': '/check'},
        ]})
        assert '/api' in out
        assert '/check' in out


# ---------------------------------------------------------------------------
# _print_locations
# ---------------------------------------------------------------------------

class TestPrintLocations:
    def test_proxy_location(self):
        out = _lines(nginx_rendering._locations, [{'path': '/', 'target': 'http://app', 'type': 'proxy'}])
        assert '/' in out
        assert 'proxy' in out
        assert 'http://app' in out

    def test_static_location(self):
        out = _lines(nginx_rendering._locations, [{'path': '/static', 'target': '/var/www', 'type': 'static'}])
        assert 'static' in out

    def test_auth_basic_on_location(self):
        out = _lines(nginx_rendering._locations, [{'path': '/secure', 'target': '', 'type': 'other', 'auth_basic': 'Zone'}])
        assert 'auth_basic' in out

    def test_auth_off_on_location(self):
        out = _lines(nginx_rendering._locations, [{'path': '/open', 'target': '', 'type': 'other', 'auth_basic': None}])
        assert 'auth off' in out

    def test_empty_locations(self):
        out = _lines(nginx_rendering._locations, [])
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

    def test_domain_in_header(self):
        out = R._render_nginx_vhost_summary(self._make_result())
        assert 'example.com' in out

    def test_symlink_info_shown(self):
        result = self._make_result(symlink={'is_symlink': True, 'target': '/etc/nginx/sites-available/x', 'exists': True})
        out = R._render_nginx_vhost_summary(result)
        assert 'Symlinked' in out

    def test_broken_symlink_shows_cross(self):
        result = self._make_result(symlink={'is_symlink': True, 'target': '/missing', 'exists': False})
        out = R._render_nginx_vhost_summary(result)
        assert '❌' in out

    def test_warnings_shown(self):
        result = self._make_result(warnings=['Missing SSL cert'])
        out = R._render_nginx_vhost_summary(result)
        assert 'Missing SSL cert' in out

    def test_next_steps_shown(self):
        result = self._make_result(next_steps=['certbot renew'])
        out = R._render_nginx_vhost_summary(result)
        assert 'certbot renew' in out


# ---------------------------------------------------------------------------
# Element sub-renderers (ports/upstream/auth/locations/config)
# ---------------------------------------------------------------------------

class TestElementRenderers:
    def test_render_vhost_ports(self):
        out = R._render_nginx_vhost_ports({'domain': 'x.com', 'ports': []})
        assert 'x.com' in out
        assert 'Ports' in out

    def test_render_vhost_upstream(self):
        out = R._render_nginx_vhost_upstream({'domain': 'x.com', 'upstreams': {}})
        assert 'x.com' in out
        assert 'Upstream' in out

    def test_render_vhost_auth(self):
        out = R._render_nginx_vhost_auth({'domain': 'x.com', 'auth': {}})
        assert 'x.com' in out
        assert 'Auth' in out

    def test_render_vhost_locations(self):
        out = R._render_nginx_vhost_locations({'domain': 'x.com', 'locations': []})
        assert 'x.com' in out
        assert 'Location' in out

    def test_render_vhost_config(self):
        out = R._render_nginx_vhost_config({
            'domain': 'x.com',
            'config_file': '/etc/nginx/x.conf',
            'server_block': 'server { listen 80; }',
        })
        assert 'x.com' in out
        assert 'server { listen 80; }' in out

    def test_element_next_steps(self):
        out = R._render_nginx_vhost_ports({'domain': 'x.com', 'ports': [], 'next_steps': ['reload nginx']})
        assert 'reload nginx' in out


# ---------------------------------------------------------------------------
# Fleet audit exit code: acted on by the URI seam, not by a sys.exit in the renderer
# ---------------------------------------------------------------------------

class TestFleetAuditExitCode:
    AUDIT = {'type': 'nginx_fleet_audit', 'site_count': 1, 'date': 'd', 'matrix': [],
             'has_gaps': True}

    def test_gaps_ask_for_exit_2_in_text(self):
        assert R.exit_code(self.AUDIT, 'text') == 2

    def test_no_gaps_exit_0(self):
        assert R.exit_code(dict(self.AUDIT, has_gaps=False), 'text') == 0

    def test_json_exit_is_unchanged_by_the_migration(self):
        # BACK-1758: text exits 2, json has always exited 0
        assert R.exit_code(self.AUDIT, 'json') == 0

    def test_other_result_types_never_exit(self):
        assert R.exit_code({'type': 'nginx_vhost_ports', 'has_gaps': True}, 'text') == 0

    def test_router_exits_2_after_printing_the_audit(self, capsys):
        args = _default_args()
        args.format = 'text'
        with pytest.raises(SystemExit) as exc:
            router._emit_result(self.AUDIT, args, 'nginx', R.render_structure, exit_code=R.exit_code)
        assert exc.value.code == 2
        assert 'Fleet Audit' in capsys.readouterr().out

    def test_router_exits_0_for_json(self, capsys):
        args = _default_args()
        args.format = 'json'
        router._emit_result(self.AUDIT, args, 'nginx', R.render_structure, exit_code=R.exit_code)
        assert '"has_gaps": true' in capsys.readouterr().out
