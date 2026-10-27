"""nginx: a location block written on one line keeps its own root and proxy target (BACK-2246).

The line reader matched `^root` / `^proxy_pass` on each stripped line, so
`location /.well-known/acme-challenge/ { root /srv/a; }` never matched: the location borrowed
the next block's root, `--check-acl` printed "No root directives found." (rc 0) for a config
written that way, and `--extract acme-roots` showed "(not found)". Fixture domains are fake.
"""
import pytest

from reveal.analyzers import nginx
from reveal.analyzers.nginx import NginxAnalyzer

from conftest import _run_reveal_direct

ONE_LINE = """\
server {
    listen 80;
    server_name alpha.example.test;
    location /.well-known/acme-challenge/ { root /srv/acme/alpha; }
    location /api/ { proxy_pass http://127.0.0.1:9000; }
    location /gone/ { return 404; }
    location / {
        root /srv/www/alpha;
    }
}
"""

MULTI_LINE = """\
server {
    listen 80;
    server_name alpha.example.test;
    location /.well-known/acme-challenge/ {
        root /srv/acme/alpha;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:9000;
    }
    location /gone/ {
        return 404;
    }
    location / {
        root /srv/www/alpha;
    }
}
"""

# verify_bd V26: every root sits in a one-line location, nothing else to borrow.
ONLY_ONE_LINERS = """\
server {
    listen 80;
    server_name alpha.example.test;
    location /.well-known/acme-challenge/ { root /srv/acme/alpha; }
}
server {
    listen 80;
    server_name beta.example.test;
    location /.well-known/acme-challenge/ { root /srv/acme/beta; }  # root /srv/commented;
}
"""


@pytest.fixture(autouse=True)
def _acl_ok(monkeypatch):
    # The ACL probe walks the real filesystem; these tests are about which roots are found.
    monkeypatch.setattr(nginx, '_check_nobody_access',
                        lambda path: {'status': 'ok', 'message': 'ok', 'failing_path': None})


def _analyzer(tmp_path, text, name='site.conf'):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return NginxAnalyzer(str(path))


def _targets(analyzer):
    return {loc['path']: loc.get('target') for loc in analyzer.get_structure()['locations']}


def test_one_line_location_keeps_its_own_root_and_proxy(tmp_path):
    assert _targets(_analyzer(tmp_path, ONE_LINE)) == {
        '/.well-known/acme-challenge/': 'static: /srv/acme/alpha',
        '/api/': 'http://127.0.0.1:9000',
        '/gone/': None,          # no root or proxy: it used to borrow the next block's root
        '/': 'static: /srv/www/alpha',
    }


def test_multi_line_config_gives_the_same_targets(tmp_path):
    # Control: the same config written over several lines.
    assert _targets(_analyzer(tmp_path, MULTI_LINE)) == _targets(_analyzer(tmp_path, ONE_LINE))


def test_check_acl_rows_include_one_line_roots(tmp_path):
    rows = _analyzer(tmp_path, ONE_LINE).extract_docroot_acl()
    assert [(r['root'], r['line']) for r in rows] == [('/srv/acme/alpha', 4), ('/srv/www/alpha', 8)]
    multi = _analyzer(tmp_path, MULTI_LINE).extract_docroot_acl()
    assert [r['root'] for r in multi] == ['/srv/acme/alpha', '/srv/www/alpha']


def test_acme_roots_resolve_one_line_roots(tmp_path):
    rows = _analyzer(tmp_path, ONLY_ONE_LINERS).extract_acme_roots()
    assert [(r['domain'], r['acme_path']) for r in rows] == [
        ('alpha.example.test', '/srv/acme/alpha'), ('beta.example.test', '/srv/acme/beta')]


def test_acme_location_without_root_still_falls_back_to_the_server_root(tmp_path):
    # Control: the server-level root after a one-line location is still the fallback.
    config = ("server {\n    server_name gamma.example.test;\n"
              "    location /.well-known/acme-challenge/ { default_type text/plain; }\n"
              "    location /x/ { root /srv/other; }\n"
              "    root /srv/www/gamma;\n}\n")
    rows = _analyzer(tmp_path, config).extract_acme_roots()
    assert [(r['domain'], r['acme_path']) for r in rows] == [('gamma.example.test', '/srv/www/gamma')]


def test_cli_check_acl_and_acme_roots_on_one_line_config(tmp_path):
    path = tmp_path / 'compact.conf'
    path.write_text(ONLY_ONE_LINERS, encoding='utf-8')
    acl = _run_reveal_direct(str(path), '--check-acl')
    assert 'No root directives found' not in acl.stdout
    assert '/srv/acme/alpha' in acl.stdout and '/srv/acme/beta' in acl.stdout
    assert '/srv/commented' not in acl.stdout
    acme = _run_reveal_direct(str(path), '--extract', 'acme-roots')
    assert '(not found)' not in acme.stdout
    assert '/srv/acme/beta' in acme.stdout
