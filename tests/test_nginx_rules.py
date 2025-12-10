"""Tests for nginx configuration rules (N001, N002, N003).

Tests pattern detection for common nginx misconfigurations.
"""

import unittest
from reveal.rules.infrastructure.N001 import N001
from reveal.rules.infrastructure.N002 import N002
from reveal.rules.infrastructure.N003 import N003


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

    def test_rules_in_i_category(self):
        """Nginx rules should be in Infrastructure (I) category."""
        from reveal.rules import RuleRegistry
        RuleRegistry.discover(force=True)

        for code in ['N001', 'N002', 'N003']:
            rule_class = RuleRegistry.get_rule(code)
            self.assertIsNotNone(rule_class, f"Rule {code} not found")
            from reveal.rules.base import RulePrefix
            self.assertEqual(rule_class.category, RulePrefix.I)

    def test_select_nginx_rules(self):
        """Should be able to select nginx rules by prefix."""
        from reveal.rules import RuleRegistry
        RuleRegistry.discover(force=True)

        # Select by N prefix
        rules = RuleRegistry.get_rules(select=['N'])
        rule_codes = [r.code for r in rules]

        self.assertEqual(len(rules), 3)
        self.assertIn('N001', rule_codes)
        self.assertIn('N002', rule_codes)
        self.assertIn('N003', rule_codes)


if __name__ == '__main__':
    unittest.main()
