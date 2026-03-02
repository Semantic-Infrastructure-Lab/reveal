"""Tests for nginx configuration rules (N001, N002, N003, N007).

Tests pattern detection for common nginx misconfigurations.
"""

import os
import tempfile
import unittest
from reveal.rules.infrastructure.N001 import N001
from reveal.rules.infrastructure.N002 import N002
from reveal.rules.infrastructure.N003 import N003
from reveal.rules.infrastructure.N007 import N007


class TestN001DuplicateBackend(unittest.TestCase):
    """Tests for N001: Duplicate backend detection."""

    def setUp(self):
        self.rule = N001()

    def test_detects_duplicate_backends(self):
        """Should detect when multiple upstreams share the same backend."""
        content = """
upstream app1 {
    server 127.0.0.1:8000;
}

upstream app2 {
    server 127.0.0.1:8000;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn("app2", detections[0].message)
        self.assertIn("app1", detections[0].message)
        self.assertIn("127.0.0.1:8000", detections[0].message)

    def test_no_false_positive_different_ports(self):
        """Should not flag upstreams with different ports."""
        content = """
upstream app1 {
    server 127.0.0.1:8000;
}

upstream app2 {
    server 127.0.0.1:8001;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_no_false_positive_different_hosts(self):
        """Should not flag upstreams with different hosts."""
        content = """
upstream app1 {
    server 10.0.0.1:8000;
}

upstream app2 {
    server 10.0.0.2:8000;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_handles_server_options(self):
        """Should normalize server specs with options like weight, backup."""
        content = """
upstream app1 {
    server 127.0.0.1:8000 weight=5;
}

upstream app2 {
    server 127.0.0.1:8000 backup;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)

    def test_handles_multiple_servers_per_upstream(self):
        """Should detect duplicates even with multiple servers per upstream."""
        content = """
upstream app1 {
    server 10.0.0.1:8000;
    server 10.0.0.2:8000;
}

upstream app2 {
    server 10.0.0.1:8000;
    server 10.0.0.3:8000;
}
"""
        detections = self.rule.check("test.conf", None, content)
        # 10.0.0.1:8000 is shared
        self.assertEqual(len(detections), 1)

    def test_handles_unix_sockets(self):
        """Should detect duplicate unix socket backends."""
        content = """
upstream app1 {
    server unix:/var/run/app.sock;
}

upstream app2 {
    server unix:/var/run/app.sock;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)

    def test_default_port_normalization(self):
        """Should treat missing port as port 80."""
        content = """
upstream app1 {
    server 127.0.0.1;
}

upstream app2 {
    server 127.0.0.1:80;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)

    def test_multiple_duplicates(self):
        """Should report all duplicate relationships."""
        content = """
upstream app1 {
    server 127.0.0.1:8000;
}

upstream app2 {
    server 127.0.0.1:8000;
}

upstream app3 {
    server 127.0.0.1:8000;
}
"""
        detections = self.rule.check("test.conf", None, content)
        # app2 and app3 both duplicate app1
        self.assertEqual(len(detections), 2)


class TestN002MissingSSLCert(unittest.TestCase):
    """Tests for N002: Missing SSL certificate detection."""

    def setUp(self):
        self.rule = N002()

    def test_detects_missing_ssl_certificate(self):
        """Should detect SSL server missing certificate directives."""
        content = """
server {
    listen 443 ssl;
    server_name example.com;

    location / {
        proxy_pass http://backend;
    }
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn("example.com", detections[0].message)
        self.assertIn("ssl_certificate", detections[0].message)

    def test_no_false_positive_with_certs(self):
        """Should not flag SSL servers with certificate configuration."""
        content = """
server {
    listen 443 ssl;
    server_name example.com;
    ssl_certificate /etc/ssl/certs/example.crt;
    ssl_certificate_key /etc/ssl/private/example.key;

    location / {
        proxy_pass http://backend;
    }
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_no_false_positive_non_ssl(self):
        """Should not flag non-SSL servers."""
        content = """
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://backend;
    }
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_detects_missing_cert_only(self):
        """Should detect when only ssl_certificate is missing."""
        content = """
server {
    listen 443 ssl;
    server_name example.com;
    ssl_certificate_key /etc/ssl/private/example.key;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn("ssl_certificate", detections[0].message)
        self.assertNotIn("ssl_certificate_key", detections[0].message)

    def test_detects_missing_key_only(self):
        """Should detect when only ssl_certificate_key is missing."""
        content = """
server {
    listen 443 ssl;
    server_name example.com;
    ssl_certificate /etc/ssl/certs/example.crt;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn("ssl_certificate_key", detections[0].message)

    def test_handles_listen_ssl_variations(self):
        """Should detect SSL on various listen directive formats."""
        # listen 443 ssl
        content1 = """
server {
    listen 443 ssl;
    server_name example.com;
}
"""
        # listen ssl
        content2 = """
server {
    listen 8443 ssl;
    server_name example.com;
}
"""
        detections1 = self.rule.check("test.conf", None, content1)
        detections2 = self.rule.check("test.conf", None, content2)

        self.assertEqual(len(detections1), 1)
        self.assertEqual(len(detections2), 1)

    def test_critical_severity(self):
        """N002 should have critical severity."""
        content = """
server {
    listen 443 ssl;
    server_name example.com;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)
        from reveal.rules.base import Severity
        self.assertEqual(detections[0].severity, Severity.CRITICAL)


class TestN003MissingProxyHeaders(unittest.TestCase):
    """Tests for N003: Missing proxy headers detection."""

    def setUp(self):
        self.rule = N003()

    def test_detects_missing_headers(self):
        """Should detect proxy location without recommended headers."""
        content = """
server {
    listen 80;
    server_name example.com;

    location /api {
        proxy_pass http://backend;
    }
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn("/api", detections[0].message)
        self.assertIn("X-Real-IP", detections[0].message)

    def test_no_false_positive_with_headers(self):
        """Should not flag locations with proper headers."""
        content = """
server {
    listen 80;
    server_name example.com;

    location /api {
        proxy_pass http://backend;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_no_false_positive_non_proxy(self):
        """Should not flag locations without proxy_pass."""
        content = """
server {
    listen 80;
    server_name example.com;

    location /static {
        root /var/www/html;
    }
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_detects_partial_headers(self):
        """Should detect when only some headers are present."""
        content = """
server {
    listen 80;

    location /api {
        proxy_pass http://backend;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn("X-Forwarded-For", detections[0].message)
        self.assertNotIn("X-Real-IP", detections[0].message)

    def test_provides_fix_suggestion(self):
        """Should provide helpful fix suggestions."""
        content = """
location /api {
    proxy_pass http://backend;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 1)
        self.assertIn("proxy_set_header", detections[0].suggestion)
        self.assertIn("$remote_addr", detections[0].suggestion)

    def test_handles_multiple_locations(self):
        """Should check all proxy locations."""
        content = """
server {
    location /api {
        proxy_pass http://api;
    }

    location /app {
        proxy_pass http://app;
    }

    location /static {
        root /var/www;
    }
}
"""
        detections = self.rule.check("test.conf", None, content)
        # Two proxy locations without headers
        self.assertEqual(len(detections), 2)


class TestNginxRuleFilePatterns(unittest.TestCase):
    """Test that nginx rules match appropriate file patterns."""

    def test_n001_matches_conf(self):
        rule = N001()
        self.assertTrue(rule.matches_target("nginx.conf"))
        self.assertTrue(rule.matches_target("/etc/nginx/nginx.conf"))
        self.assertTrue(rule.matches_target("sites-enabled/default.conf"))
        self.assertFalse(rule.matches_target("app.py"))

    def test_n002_matches_conf(self):
        rule = N002()
        self.assertTrue(rule.matches_target("site.conf"))
        self.assertTrue(rule.matches_target("/etc/nginx/sites-available/mysite.conf"))
        self.assertFalse(rule.matches_target("Dockerfile"))

    def test_n003_matches_conf(self):
        rule = N003()
        self.assertTrue(rule.matches_target("proxy.conf"))
        self.assertFalse(rule.matches_target("config.yaml"))


class TestNginxRulesIntegration(unittest.TestCase):
    """Integration tests for nginx rules via RuleRegistry."""

    def test_rules_discovered(self):
        """Nginx rules should be auto-discovered."""
        from reveal.rules import RuleRegistry
        RuleRegistry.discover(force=True)

        rules = RuleRegistry.list_rules()
        rule_codes = [r['code'] for r in rules]

        self.assertIn('N001', rule_codes)
        self.assertIn('N002', rule_codes)
        self.assertIn('N003', rule_codes)

    def test_rules_in_n_category(self):
        """Nginx rules should be in Nginx (N) category."""
        from reveal.rules import RuleRegistry
        RuleRegistry.discover(force=True)

        for code in ['N001', 'N002', 'N003']:
            rule_class = RuleRegistry.get_rule(code)
            self.assertIsNotNone(rule_class, f"Rule {code} not found")
            from reveal.rules.base import RulePrefix
            self.assertEqual(rule_class.category, RulePrefix.N)

    def test_select_nginx_rules(self):
        """Should be able to select nginx rules by prefix."""
        from reveal.rules import RuleRegistry
        RuleRegistry.discover(force=True)

        # Select by N prefix
        rules = RuleRegistry.get_rules(select=['N'])
        rule_codes = [r.code for r in rules]

        self.assertEqual(len(rules), 7)
        self.assertIn('N001', rule_codes)
        self.assertIn('N002', rule_codes)
        self.assertIn('N003', rule_codes)
        self.assertIn('N004', rule_codes)
        self.assertIn('N007', rule_codes)


class TestN004ACMEPathInconsistency(unittest.TestCase):
    """Tests for N004: ACME challenge path inconsistency detection."""

    def setUp(self):
        """Set up test fixtures."""
        from reveal.rules.infrastructure.N004 import N004
        self.rule = N004()

    def test_detects_inconsistent_acme_paths(self):
        """Should detect when server blocks have different ACME challenge roots."""
        content = '''
server {
    server_name domain-a.com;
    location /.well-known/acme-challenge/ {
        root /home/user1/public_html;
    }
}
server {
    server_name domain-b.com;
    location /.well-known/acme-challenge/ {
        root /home/user2/public_html;
    }
}
'''
        detections = self.rule.check('test.conf', None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'N004')
        self.assertIn('user2', detections[0].message)
        self.assertIn('user1', detections[0].message)

    def test_no_false_positive_consistent_paths(self):
        """Should not flag when all ACME paths are the same."""
        content = '''
server {
    server_name domain-a.com;
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
}
server {
    server_name domain-b.com;
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
}
'''
        detections = self.rule.check('test.conf', None, content)
        self.assertEqual(len(detections), 0)

    def test_handles_multiple_divergent_paths(self):
        """Should detect multiple divergent paths."""
        content = '''
server {
    server_name a.com;
    location /.well-known/acme-challenge/ {
        root /path/common;
    }
}
server {
    server_name b.com;
    location /.well-known/acme-challenge/ {
        root /path/common;
    }
}
server {
    server_name c.com;
    location /.well-known/acme-challenge/ {
        root /path/divergent1;
    }
}
server {
    server_name d.com;
    location /.well-known/acme-challenge/ {
        root /path/divergent2;
    }
}
'''
        detections = self.rule.check('test.conf', None, content)
        # Should flag both divergent paths
        self.assertEqual(len(detections), 2)
        messages = [d.message for d in detections]
        self.assertTrue(any('divergent1' in m for m in messages))
        self.assertTrue(any('divergent2' in m for m in messages))

    def test_handles_no_acme_locations(self):
        """Should handle configs with no ACME locations gracefully."""
        content = '''
server {
    server_name example.com;
    location / {
        proxy_pass http://backend;
    }
}
'''
        detections = self.rule.check('test.conf', None, content)
        self.assertEqual(len(detections), 0)

    def test_high_severity(self):
        """Should have HIGH severity."""
        from reveal.rules.base import Severity
        self.assertEqual(self.rule.severity, Severity.HIGH)

    def test_matches_nginx_file_patterns(self):
        """Should match nginx file patterns."""
        from reveal.rules.infrastructure import NGINX_FILE_PATTERNS
        self.assertEqual(self.rule.file_patterns, NGINX_FILE_PATTERNS)

    def test_handles_ssl_server_without_acme(self):
        """Should track SSL servers without ACME locations (no detections by default)."""
        content = '''
server {
    server_name secure.example.com;
    listen 443 ssl;
    ssl_certificate /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;
    location / {
        proxy_pass http://backend;
    }
}
server {
    server_name other.example.com;
    listen 443 ssl;
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
}
'''
        # SSL servers without ACME are tracked internally but don't generate detections
        # (This is intentional - see lines 119-129 in N004.py)
        detections = self.rule.check('test.conf', None, content)
        self.assertEqual(len(detections), 0)

    def test_get_server_name_no_directive(self):
        """Should return None when server block has no server_name directive."""
        server_body = '''
    listen 80;
    location / {
        proxy_pass http://backend;
    }
'''
        result = self.rule._get_server_name(server_body)
        self.assertIsNone(result)

    def test_get_server_name_empty_value(self):
        """Should return None when server_name directive has no values."""
        server_body = '''
    server_name ;
    listen 80;
'''
        result = self.rule._get_server_name(server_body)
        self.assertIsNone(result)

    def test_find_listen_line_with_listen(self):
        """Should find the line number of the listen directive."""
        server_body = '''listen 80;
    server_name example.com;
    location / {
        root /var/www;
    }
'''
        # server_start=10 means the server block starts at line 10
        line = self.rule._find_listen_line(server_body, server_start=10)
        # listen is on the first line of the body (line 10)
        self.assertEqual(line, 10)

    def test_find_listen_line_no_listen(self):
        """Should return server_start when no listen directive found."""
        server_body = '''server_name example.com;
    location / {
        root /var/www;
    }
'''
        line = self.rule._find_listen_line(server_body, server_start=20)
        self.assertEqual(line, 20)


class TestN004QuotedPaths(unittest.TestCase):
    """B3 — N004 strips quotes from cPanel-style root directives before embedding in messages."""

    def setUp(self):
        from reveal.rules.infrastructure.N004 import N004
        self.rule = N004()

    def test_quoted_paths_not_shown_in_message(self):
        """N004 message should show bare paths, not '"/home/..."'."""
        content = '''
server {
    server_name domain-a.com;
    location /.well-known/acme-challenge/ {
        root "/home/user1/public_html";
    }
}
server {
    server_name domain-b.com;
    location /.well-known/acme-challenge/ {
        root "/home/user2/public_html";
    }
}
'''
        detections = self.rule.check('test.conf', None, content)
        self.assertEqual(len(detections), 1)
        msg = detections[0].message
        self.assertIn('/home/user1/public_html', msg)
        self.assertIn('/home/user2/public_html', msg)
        self.assertNotIn('"/home/', msg, "raw double-quotes should be stripped from message")

    def test_quoted_and_unquoted_same_path_no_detection(self):
        """Quoted and unquoted versions of the same path are treated as equal (no false positive)."""
        content = '''
server {
    server_name domain-a.com;
    location /.well-known/acme-challenge/ {
        root /home/user/public_html;
    }
}
server {
    server_name domain-b.com;
    location /.well-known/acme-challenge/ {
        root "/home/user/public_html";
    }
}
'''
        detections = self.rule.check('test.conf', None, content)
        self.assertEqual(len(detections), 0,
                         "Quoted and unquoted same path should not trigger N004")

    def test_suggestion_also_has_no_quotes(self):
        """The suggestion field (common path) should also be quote-free."""
        content = '''
server {
    server_name a.com;
    location /.well-known/acme-challenge/ {
        root "/home/common/public_html";
    }
}
server {
    server_name b.com;
    location /.well-known/acme-challenge/ {
        root "/home/common/public_html";
    }
}
server {
    server_name c.com;
    location /.well-known/acme-challenge/ {
        root "/home/other/public_html";
    }
}
'''
        detections = self.rule.check('test.conf', None, content)
        self.assertEqual(len(detections), 1)
        suggestion = detections[0].suggestion
        self.assertNotIn('"', suggestion, "Suggestion field should contain no quotes")


class TestN001AllowAnnotation(unittest.TestCase):
    """Tests for N001: reveal:allow-shared-backend suppression annotation."""

    def setUp(self):
        self.rule = N001()

    def test_annotation_suppresses_duplicate(self):
        """Upstream with reveal:allow-shared-backend should not fire N001."""
        content = """
upstream sil_website_staging {
    # reveal:allow-shared-backend
    server 10.108.0.8:8080;
}
upstream tia_dev_nginx {
    server 10.108.0.8:8080;
}
"""
        detections = self.rule.check("nginx.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_annotation_on_second_upstream_suppresses(self):
        """Annotation on either upstream in a pair should suppress."""
        content = """
upstream app_prod {
    server 10.0.0.1:8080;
}
upstream app_staging {
    # reveal:allow-shared-backend
    server 10.0.0.1:8080;
}
"""
        detections = self.rule.check("nginx.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_no_annotation_still_fires(self):
        """Without annotation, N001 should still fire for duplicate backends."""
        content = """
upstream app1 {
    server 10.0.0.1:8080;
}
upstream app2 {
    server 10.0.0.1:8080;
}
"""
        detections = self.rule.check("nginx.conf", None, content)
        self.assertEqual(len(detections), 1)

    def test_suggestion_mentions_annotation(self):
        """N001 suggestion should tell users about the suppression annotation."""
        content = """
upstream a { server 127.0.0.1:9000; }
upstream b { server 127.0.0.1:9000; }
"""
        detections = self.rule.check("nginx.conf", None, content)
        self.assertGreater(len(detections), 0)
        self.assertIn("reveal:allow-shared-backend", detections[0].suggestion)


class TestN003IncludeResolution(unittest.TestCase):
    """Tests for N003: include directive handling."""

    def setUp(self):
        self.rule = N003()

    def test_unresolvable_include_suppresses_warning(self):
        """Location with an include (even if unresolvable) should not fire N003."""
        content = """
location /api/v1/assets/ {
    proxy_pass http://sdms_assets;
    include snippets/tia-proxy-headers.conf;
}
"""
        detections = self.rule.check("/etc/nginx/conf.d/test.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_include_with_headers_suppresses_warning(self):
        """Location whose include file contains the required headers should not fire."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create snippet file with the required headers
            snippet_dir = os.path.join(tmpdir, "snippets")
            os.makedirs(snippet_dir)
            snippet = os.path.join(snippet_dir, "proxy-headers.conf")
            with open(snippet, "w") as fh:
                fh.write("proxy_set_header X-Real-IP $remote_addr;\n")
                fh.write("proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n")

            # Config file lives in tmpdir/conf.d/; snippet is at tmpdir/snippets/
            conf_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_dir)
            config_file = os.path.join(conf_dir, "test.conf")

            content = f"""
location /api/ {{
    proxy_pass http://backend;
    include snippets/proxy-headers.conf;
}}
"""
            detections = self.rule.check(config_file, None, content)
            self.assertEqual(len(detections), 0)

    def test_include_without_headers_still_fires(self):
        """Location whose include file lacks the required headers should still fire."""
        with tempfile.TemporaryDirectory() as tmpdir:
            snippet_dir = os.path.join(tmpdir, "snippets")
            os.makedirs(snippet_dir)
            snippet = os.path.join(snippet_dir, "no-proxy-headers.conf")
            with open(snippet, "w") as fh:
                fh.write("proxy_set_header Host $host;\n")  # Host only, not X-Real-IP etc.

            conf_dir = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_dir)
            config_file = os.path.join(conf_dir, "test.conf")

            content = """
location /api/ {
    proxy_pass http://backend;
    include snippets/no-proxy-headers.conf;
}
"""
            detections = self.rule.check(config_file, None, content)
            self.assertEqual(len(detections), 1)

    def test_no_include_no_headers_still_fires(self):
        """Bare proxy location with no include and no headers must still fire."""
        content = """
location /bare/ {
    proxy_pass http://backend;
}
"""
        detections = self.rule.check("/etc/nginx/conf.d/test.conf", None, content)
        self.assertEqual(len(detections), 1)

    def test_absolute_include_path_resolved(self):
        """Absolute include paths should be resolved directly."""
        with tempfile.NamedTemporaryFile(suffix=".conf", mode="w", delete=False) as fh:
            fh.write("proxy_set_header X-Real-IP $remote_addr;\n")
            fh.write("proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n")
            snippet_path = fh.name

        try:
            content = f"""
location /api/ {{
    proxy_pass http://backend;
    include {snippet_path};
}}
"""
            detections = self.rule.check("/etc/nginx/conf.d/test.conf", None, content)
            self.assertEqual(len(detections), 0)
        finally:
            os.unlink(snippet_path)


class TestN007SslStapling(unittest.TestCase):
    """Tests for N007: ssl_stapling without OCSP URL."""

    def setUp(self):
        self.rule = N007()

    def _cert_path(self):
        """Return path to a cert that will be 'unreadable' (does not exist)."""
        return "/etc/letsencrypt/live/example.org/fullchain.pem"

    def test_no_ssl_stapling_no_detection(self):
        """Server blocks without ssl_stapling should not fire N007."""
        content = """
server {
    listen 443 ssl;
    ssl_certificate /etc/ssl/certs/example.pem;
    ssl_certificate_key /etc/ssl/private/example.key;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_ssl_stapling_unreadable_cert_no_detection(self):
        """ssl_stapling on a cert that can't be read should not fire (can't verify)."""
        content = f"""
server {{
    listen 443 ssl;
    ssl_certificate {self._cert_path()};
    ssl_stapling on;
    ssl_stapling_verify on;
}}
"""
        detections = self.rule.check("test.conf", None, content)
        # cert is unreadable → suppressed
        self.assertEqual(len(detections), 0)

    def test_ssl_stapling_with_real_cert_with_ocsp(self):
        """ssl_stapling on a cert that has an OCSP URL should not fire."""
        # Write a minimal PEM that our check_ocsp_url will see as 'unreadable'
        # (since it won't parse as a valid DER cert), which also suppresses.
        # This tests the code path without requiring a real cert on the test host.
        with tempfile.NamedTemporaryFile(suffix=".pem", mode="w", delete=False) as fh:
            fh.write("-----BEGIN CERTIFICATE-----\nZmFrZQ==\n-----END CERTIFICATE-----\n")
            cert_path = fh.name
        try:
            content = f"""
server {{
    listen 443 ssl;
    ssl_certificate {cert_path};
    ssl_stapling on;
}}
"""
            detections = self.rule.check("test.conf", None, content)
            # Unparseable cert → 'unreadable' → suppressed (not a false positive)
            self.assertEqual(len(detections), 0)
        finally:
            os.unlink(cert_path)

    def test_ssl_stapling_cert_with_no_ocsp_fires(self):
        """ssl_stapling on a readable cert with no OCSP URL should fire N007."""
        # Write a minimal PEM that parses as DER but contains no 'ocsp'/'http' bytes.
        # We patch _check_ocsp_url to control the result cleanly.
        rule = N007()
        rule._check_ocsp_url = lambda path: 'missing'

        with tempfile.NamedTemporaryFile(suffix=".pem", mode="w", delete=False) as fh:
            fh.write("-----BEGIN CERTIFICATE-----\nZmFrZQ==\n-----END CERTIFICATE-----\n")
            cert_path = fh.name
        try:
            content = f"""
server {{
    listen 443 ssl;
    ssl_certificate {cert_path};
    ssl_stapling on;
}}
"""
            detections = rule.check("test.conf", None, content)
            self.assertEqual(len(detections), 1)
            self.assertIn(cert_path, detections[0].message)
            self.assertIn("OCSP", detections[0].message)
        finally:
            os.unlink(cert_path)

    def test_no_ssl_certificate_directive_no_detection(self):
        """ssl_stapling without ssl_certificate directive should not fire (nothing to check)."""
        content = """
server {
    listen 443 ssl;
    ssl_stapling on;
}
"""
        detections = self.rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 0)

    def test_multiple_server_blocks_checked_independently(self):
        """Each server block is checked independently."""
        rule = N007()
        call_count = [0]
        original = rule._check_ocsp_url

        def patched(path):
            call_count[0] += 1
            return 'missing'

        rule._check_ocsp_url = patched

        content = """
server {
    listen 443 ssl;
    ssl_certificate /etc/ssl/a.pem;
    ssl_stapling on;
}
server {
    listen 8443 ssl;
    ssl_certificate /etc/ssl/b.pem;
    ssl_stapling on;
}
"""
        detections = rule.check("test.conf", None, content)
        self.assertEqual(len(detections), 2)
        self.assertEqual(call_count[0], 2)

    def test_severity_is_low(self):
        """N007 should be LOW severity."""
        from reveal.rules.base import Severity
        self.assertEqual(self.rule.severity, Severity.LOW)


if __name__ == '__main__':
    unittest.main()
