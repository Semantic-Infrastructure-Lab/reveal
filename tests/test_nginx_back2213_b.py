"""BACK-2213 lane b: nginx:// code fixes found by the guide review.

CB6: nginx:// next steps suggested `reveal check ssl://...`, which exits 2 ("looks like a URI,
     not a file path"); the working command is `reveal ssl://... --check`.
CB7: the fleet audit told operators to add per-site-only checks (http2 on a listener,
     limit_req) to nginx.conf http{} whenever no site had them.
CB8: --diagnose labels its sample "most recent match per type" but kept the first match.
"""
from unittest.mock import patch

from reveal.adapters.nginx import adapter as nginx_adapter
from reveal.adapters.nginx.adapter import NginxUriAdapter, _build_fleet_matrix
from reveal.analyzers.nginx import NginxAnalyzer

_SITE = """server {
    listen 443 ssl;
    server_name app.example.com;
    ssl_certificate /etc/ssl/app.pem;
    location / { root /srv/app; }
}
"""


def _steps(result):
    return [s for s in result.get('next_steps', [])]


def test_next_steps_never_suggest_reveal_check_on_an_ssl_uri(tmp_path):
    conf_dir = tmp_path / 'conf.d'
    conf_dir.mkdir()
    (conf_dir / 'app.conf').write_text(_SITE, encoding='utf-8')
    with patch.object(nginx_adapter, '_NGINX_SEARCH_DIRS', [str(conf_dir)]), \
            patch.object(nginx_adapter, '_NGINX_MAIN_CONFIGS', [str(tmp_path / 'nginx.conf')]):
        overview = NginxUriAdapter('nginx://').get_structure()
        vhost = NginxUriAdapter('nginx://app.example.com').get_structure()
        ports = NginxUriAdapter('nginx://app.example.com').get_element('ports')
    steps = _steps(overview) + _steps(vhost) + _steps(ports)
    assert steps, 'positive control: each view prints next steps'
    assert not [s for s in steps if 'reveal check ssl://' in s], steps
    assert any("reveal ssl://app.example.com --check" in s for s in _steps(vhost))
    assert any("reveal 'ssl://nginx:///etc/nginx/conf.d/*.conf' --check" in s for s in _steps(overview))


def _row(matrix, check_id):
    return next(r for r in matrix if r['id'] == check_id)


def test_fleet_audit_does_not_send_per_site_checks_to_http_block():
    sites = [{'file': f'/etc/nginx/conf.d/s{i}.conf', 'domains': [f's{i}.example.com'],
              'checks': {k: False for k in ('server_tokens', 'hsts', 'xcto', 'xfo', 'http2', 'limit_req', 'xss_prot')}}
             for i in range(2)]
    matrix = _build_fleet_matrix(sites, 2, {'server_tokens': False, 'hsts': False, 'xcto': False, 'xfo': False})
    assert _row(matrix, 'hsts')['action'] == 'Add to nginx.conf http{}'  # positive control: http{}-eligible
    assert _row(matrix, 'http2')['action'] == 'Add per-site (certbot strips http2 on renewal)'
    assert _row(matrix, 'limit_req')['action'].startswith('Add zones to nginx.conf')


def test_diagnose_sample_is_the_most_recent_match():
    hits = {}
    NginxAnalyzer._record_hit(hits, 'example.com', 'permission_denied', '2026/10/26 14:03:01', 'first line')
    NginxAnalyzer._record_hit(hits, 'example.com', 'permission_denied', '2026/10/26 14:05:01', 'second line')
    entry = hits[('example.com', 'permission_denied')]
    assert entry['count'] == 2
    assert entry['last_seen'] == '2026/10/26 14:05:01'
    assert entry['sample'] == 'second line'
