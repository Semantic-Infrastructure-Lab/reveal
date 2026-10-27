"""BACK-2280: N002, N008 and N009 read "set at http{} level" as "appears anywhere in http{}".

The global lookup searched the whole text of every http{} block of nginx.conf (and of the
vhost's own file), nested server{} and location{} blocks included, and the whole text of every
file an http{} block includes. So one server{} in nginx.conf that had ``ssl_certificate``
satisfied N002 for every other vhost next to it, and in a single file with two SSL servers the
first server's certificate covered the second. Only a directive that is a direct child of
http{} (or a top-level directive of a file included there) is inherited by every server.

Each red case has a control that must keep passing: a directive really set at http{} level,
inline or through an include, still covers the vhost; a server that has its own certificate is
still clean.
"""

import os
import tempfile
import unittest

import pytest

from reveal.rules.infrastructure.N002 import N002
from reveal.rules.infrastructure.N008 import N008
from reveal.rules.infrastructure.N009 import N009

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


MISSING_BOTH = 'missing both ssl_certificate and ssl_certificate_key'

SITE_NO_CERT = """server {
    listen 443 ssl;
    server_name a.example.test;
}
"""

SITE_WITH_CERT = """server {
    listen 443 ssl;
    server_name a.example.test;
    ssl_certificate /srv/certs/a.crt;
    ssl_certificate_key /srv/certs/a.key;
}
"""

# A neighbour vhost defined inside nginx.conf's http{}: its directives are server-level.
NGINX_CONF_SERVER_HAS_ALL = """http {
    server {
        listen 443 ssl;
        server_name b.example.test;
        ssl_certificate /srv/certs/b.crt;
        ssl_certificate_key /srv/certs/b.key;
        add_header Strict-Transport-Security "max-age=31536000" always;
        server_tokens off;
    }
}
"""


class _TmpConfigDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name: str, content: str) -> str:
        path = os.path.join(self.tmpdir, name)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(content)
        return path

    def _check(self, rule, name: str, content: str):
        path = self._write(name, content)
        return rule.check(path, None, content)


class TestN002NeighbourCertIsNotGlobal(_TmpConfigDir):

    def test_cert_inside_a_server_of_nginx_conf_does_not_cover_the_vhost(self):
        self._write('nginx.conf', NGINX_CONF_SERVER_HAS_ALL)
        detections = self._check(N002(), 'site.conf', SITE_NO_CERT)
        self.assertEqual([d.message for d in detections],
                         [f"SSL server 'a.example.test' {MISSING_BOTH}"])

    def test_cert_in_a_vhost_file_nginx_conf_includes_does_not_cover_the_vhost(self):
        self._write('other-site.conf', SITE_WITH_CERT.replace('a.example', 'b.example'))
        self._write('nginx.conf', 'http {\n    include other-site.conf;\n}\n')
        detections = self._check(N002(), 'site.conf', SITE_NO_CERT)
        self.assertEqual(len(detections), 1)
        self.assertIn("'a.example.test' missing both", detections[0].message)

    def test_key_at_http_level_cert_only_in_a_server_reports_the_missing_cert(self):
        self._write('nginx.conf', """http {
    ssl_certificate_key /srv/certs/shared.key;
    server {
        listen 443 ssl;
        server_name b.example.test;
        ssl_certificate /srv/certs/b.crt;
    }
}
""")
        detections = self._check(N002(), 'site.conf', SITE_NO_CERT)
        self.assertEqual([d.message for d in detections],
                         ["SSL server 'a.example.test' missing ssl_certificate"])

    def test_second_server_of_one_file_is_not_covered_by_the_first(self):
        self._write('nginx.conf', 'http {\n}\n')
        content = """http {
    server {
        listen 443 ssl;
        server_name first.example.test;
        ssl_certificate /srv/certs/first.crt;
        ssl_certificate_key /srv/certs/first.key;
    }
    server {
        listen 443 ssl;
        server_name second.example.test;
    }
}
"""
        detections = self._check(N002(), 'both.conf', content)
        self.assertEqual([(d.line, d.message) for d in detections],
                         [(9, f"SSL server 'second.example.test' {MISSING_BOTH}")])

    # --- controls: what really is http{} level still covers every vhost ---

    def test_control_cert_directly_in_http_of_nginx_conf_covers_the_vhost(self):
        self._write('nginx.conf', """http {
    ssl_certificate /srv/certs/wild.crt;
    ssl_certificate_key /srv/certs/wild.key;
    server {
        listen 80;
        server_name b.example.test;
    }
}
""")
        self.assertEqual(self._check(N002(), 'site.conf', SITE_NO_CERT), [])

    def test_control_cert_from_a_snippet_included_in_http_covers_the_vhost(self):
        self._write('ssl-common.conf', 'ssl_certificate /srv/certs/wild.crt;\n'
                                       'ssl_certificate_key /srv/certs/wild.key;\n')
        self._write('nginx.conf', 'http {\n    include ssl-common.conf;\n}\n')
        self.assertEqual(self._check(N002(), 'site.conf', SITE_NO_CERT), [])

    def test_quoted_brace_does_not_end_http_before_the_http_level_cert(self):
        # A "}" inside a quoted value is text, not the end of http{} (utils/nginx_conf.py grammar);
        # the old raw brace count ended http{} there and missed the cert (a false positive).
        self._write('nginx.conf', """http {
    add_header X-Note "a } b";
    ssl_certificate /srv/certs/wild.crt;
    ssl_certificate_key /srv/certs/wild.key;
}
""")
        self.assertEqual(self._check(N002(), 'site.conf', SITE_NO_CERT), [])

    def test_control_commented_http_level_cert_does_not_cover(self):
        self._write('nginx.conf', """http {
    # ssl_certificate /srv/certs/wild.crt;
    # ssl_certificate_key /srv/certs/wild.key;
}
""")
        self.assertEqual(len(self._check(N002(), 'site.conf', SITE_NO_CERT)), 1)

    def test_control_server_with_its_own_cert_is_clean_next_to_any_nginx_conf(self):
        self._write('nginx.conf', NGINX_CONF_SERVER_HAS_ALL)
        self.assertEqual(self._check(N002(), 'site.conf', SITE_WITH_CERT), [])

    def test_control_server_include_that_pulls_a_cert_in_is_clean(self):
        self._write('nginx.conf', 'http {\n}\n')
        self._write('a-cert.conf', 'ssl_certificate /srv/certs/a.crt;\n'
                                   'ssl_certificate_key /srv/certs/a.key;\n')
        content = SITE_NO_CERT.replace('    server_name',
                                       '    include a-cert.conf;\n    server_name')
        self.assertEqual(self._check(N002(), 'site.conf', content), [])

    def test_control_both_servers_of_one_file_with_certs_are_clean(self):
        self._write('nginx.conf', 'http {\n}\n')
        second = SITE_WITH_CERT.replace('a.example', 'b.example')
        content = 'http {\n' + SITE_WITH_CERT + second + '}\n'
        self.assertEqual(self._check(N002(), 'both.conf', content), [])


class TestN008N009NeighbourDirectiveIsNotGlobal(_TmpConfigDir):

    def test_hsts_inside_a_server_of_nginx_conf_does_not_cover_the_vhost(self):
        self._write('nginx.conf', NGINX_CONF_SERVER_HAS_ALL)
        detections = self._check(N008(), 'site.conf', SITE_WITH_CERT)
        self.assertEqual(len(detections), 1)
        self.assertIn("'a.example.test'", detections[0].message)

    def test_hsts_in_a_server_of_an_included_file_does_not_cover_the_vhost(self):
        self._write('other-site.conf', 'server {\n    listen 443 ssl;\n'
                    '    add_header Strict-Transport-Security "max-age=31536000" always;\n}\n')
        self._write('nginx.conf', 'http {\n    include other-site.conf;\n}\n')
        self.assertEqual(len(self._check(N008(), 'site.conf', SITE_WITH_CERT)), 1)

    def test_server_tokens_inside_a_server_of_nginx_conf_does_not_cover_the_vhost(self):
        self._write('nginx.conf', NGINX_CONF_SERVER_HAS_ALL)
        detections = self._check(N009(), 'site.conf', SITE_WITH_CERT)
        self.assertEqual(len(detections), 1)
        self.assertIn('server_tokens not disabled', detections[0].message)

    # --- controls ---

    def test_control_http_level_hsts_and_server_tokens_cover_the_vhost(self):
        self._write('headers.conf',
                    'add_header Strict-Transport-Security "max-age=31536000" always;\n')
        self._write('nginx.conf', 'http {\n    server_tokens off;\n    include headers.conf;\n}\n')
        self.assertEqual(self._check(N008(), 'site.conf', SITE_WITH_CERT), [])
        self.assertEqual(self._check(N009(), 'site.conf', SITE_WITH_CERT), [])


if __name__ == '__main__':
    unittest.main()
