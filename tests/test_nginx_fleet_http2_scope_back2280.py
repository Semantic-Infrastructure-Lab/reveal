"""BACK-2280: the fleet audit's "http2 on 443 listener" row counted port-80-only sites as Without.

http2 is a property of a TLS listener, so a site with no TLS listener (a plain port-80
redirect file, common next to its 443 twin) has nothing to add it to. Such a site is now in
neither With nor Without for that row, and the text view says how many were left out. Rows
that apply to every site (HSTS and the other headers) keep counting every site.
"""

import os
import tempfile

import pytest

from reveal.adapters.nginx.adapter import _audit_site_content, _run_fleet_audit
from reveal.rendering.adapters.nginx import NginxRenderer

# BACK-1149: exercises internal functions/modules directly, not CLI/MCP/network surface
pytestmark = pytest.mark.component


TLS_HTTP2 = 'server {\n    listen 443 ssl http2;\n    server_name a.example.test;\n}\n'
TLS_NO_HTTP2 = 'server {\n    listen [::]:443 ssl;\n    server_name b.example.test;\n}\n'
PORT_80_ONLY = ('server {\n    listen 80;\n    server_name c.example.test;\n'
                '    return 301 https://$host$request_uri;\n}\n')


def _fleet(sites):
    with tempfile.TemporaryDirectory() as tmpdir:
        for name, content in sites.items():
            with open(os.path.join(tmpdir, name), 'w', encoding='utf-8') as fh:
                fh.write(content)
        return _run_fleet_audit([tmpdir], [])


def _row(result, check_id):
    return next(r for r in result['matrix'] if r['id'] == check_id)


def test_port_80_only_site_is_not_counted_without_http2():
    result = _fleet({'a.conf': TLS_HTTP2, 'b.conf': TLS_NO_HTTP2, 'c.conf': PORT_80_ONLY})
    row = _row(result, 'http2')
    assert (row['sites_with'], row['sites_without']) == (1, 1)
    assert row['sites_with_names'] == ['a.example.test']
    assert row['sites_without_names'] == ['b.example.test']


def test_fleet_of_port_80_only_sites_has_no_http2_gap():
    other = PORT_80_ONLY.replace('c.example', 'd.example')
    result = _fleet({'c.conf': PORT_80_ONLY, 'd.conf': other})
    row = _row(result, 'http2')
    assert (row['sites_with'], row['sites_without']) == (0, 0)


def test_text_view_says_how_many_sites_the_row_left_out():
    result = _fleet({'a.conf': TLS_HTTP2, 'b.conf': TLS_NO_HTTP2, 'c.conf': PORT_80_ONLY})
    text = NginxRenderer._render_nginx_fleet_audit(result)
    http2_line = next(line for line in text.split('\n') if 'http2 on 443 listener' in line)
    assert http2_line.endswith('(1 site not applicable)')
    hsts_line = next(line for line in text.split('\n') if 'Strict-Transport-Security' in line)
    assert 'not applicable' not in hsts_line


# --- controls ---

def test_control_rows_for_every_site_still_count_the_port_80_site():
    result = _fleet({'a.conf': TLS_HTTP2, 'b.conf': TLS_NO_HTTP2, 'c.conf': PORT_80_ONLY})
    hsts = _row(result, 'hsts')
    assert (hsts['sites_with'], hsts['sites_without']) == (0, 3)
    assert result['site_count'] == 3
    assert result['has_gaps'] is True


def test_control_site_with_80_and_443_servers_counts_for_http2():
    both = PORT_80_ONLY + TLS_NO_HTTP2
    row = _row(_fleet({'b.conf': both}), 'http2')
    assert (row['sites_with'], row['sites_without']) == (0, 1)


def test_control_ssl_listener_on_another_port_still_counts():
    site = 'server {\n    listen 8443 ssl;\n    server_name e.example.test;\n}\n'
    row = _row(_fleet({'e.conf': site}), 'http2')
    assert (row['sites_with'], row['sites_without']) == (0, 1)


def test_control_site_content_checks_stay_booleans_for_tls_sites():
    checks = _audit_site_content(TLS_NO_HTTP2)
    assert checks['http2'] is False and checks['hsts'] is False
    assert _audit_site_content(TLS_HTTP2)['http2'] is True
