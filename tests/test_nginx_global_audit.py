"""Tests for NginxAnalyzer.audit_global_directives() (BACK-091)."""

import json
import tempfile
import os
import sys
import unittest
from argparse import Namespace
from io import StringIO
from unittest.mock import patch

from reveal.analyzers.nginx import NginxAnalyzer


def _make_config(lines):
    """Write lines to a temp .conf file and return the path."""
    fd, path = tempfile.mkstemp(suffix='.conf')
    with os.fdopen(fd, 'w') as fh:
        fh.write('\n'.join(lines))
    return path


class TestAuditGlobalDirectivesHttpBlock(unittest.TestCase):
    """Unit tests for audit_global_directives() http{} checks."""

    def _audit(self, lines):
        path = _make_config(lines)
        analyzer = NginxAnalyzer(path)
        return {f['id']: f for f in analyzer.audit_global_directives()}

    # ── server_tokens ──────────────────────────────────────────────────

    def test_server_tokens_off_present(self):
        findings = self._audit([
            'http {',
            '    server_tokens off;',
            '}',
        ])
        self.assertTrue(findings['server_tokens']['present'])
        self.assertEqual(findings['server_tokens']['severity'], 'MEDIUM')
        self.assertEqual(findings['server_tokens']['context'], 'http{}')

    def test_server_tokens_missing(self):
        findings = self._audit(['http {', '    gzip on;', '}'])
        self.assertFalse(findings['server_tokens']['present'])

    def test_server_tokens_on_does_not_match(self):
        # "server_tokens on" is the bad state — should report missing
        findings = self._audit(['http {', '    server_tokens on;', '}'])
        self.assertFalse(findings['server_tokens']['present'])

    # ── HSTS ───────────────────────────────────────────────────────────

    def test_hsts_present(self):
        findings = self._audit([
            'http {',
            '    add_header Strict-Transport-Security "max-age=31536000";',
            '}',
        ])
        self.assertTrue(findings['hsts']['present'])
        self.assertEqual(findings['hsts']['severity'], 'HIGH')

    def test_hsts_missing(self):
        findings = self._audit(['http {', '    server_tokens off;', '}'])
        self.assertFalse(findings['hsts']['present'])

    # ── X-Content-Type-Options ─────────────────────────────────────────

    def test_xcto_present(self):
        findings = self._audit([
            'http {',
            '    add_header X-Content-Type-Options nosniff;',
            '}',
        ])
        self.assertTrue(findings['xcto']['present'])
        self.assertEqual(findings['xcto']['severity'], 'MEDIUM')

    def test_xcto_missing(self):
        findings = self._audit(['http {', '}'])
        self.assertFalse(findings['xcto']['present'])

    # ── X-Frame-Options ────────────────────────────────────────────────

    def test_xfo_present(self):
        findings = self._audit([
            'http {',
            '    add_header X-Frame-Options SAMEORIGIN;',
            '}',
        ])
        self.assertTrue(findings['xfo']['present'])
        self.assertEqual(findings['xfo']['severity'], 'MEDIUM')

    def test_xfo_missing(self):
        findings = self._audit(['http {', '}'])
        self.assertFalse(findings['xfo']['present'])

    # ── ssl_protocols ──────────────────────────────────────────────────

    def test_ssl_protocols_present(self):
        findings = self._audit([
            'http {',
            '    ssl_protocols TLSv1.2 TLSv1.3;',
            '}',
        ])
        self.assertTrue(findings['ssl_protocols']['present'])
        self.assertEqual(findings['ssl_protocols']['severity'], 'MEDIUM')

    def test_ssl_protocols_missing(self):
        findings = self._audit(['http {', '}'])
        self.assertFalse(findings['ssl_protocols']['present'])

    # ── resolver ───────────────────────────────────────────────────────

    def test_resolver_present(self):
        findings = self._audit([
            'http {',
            '    resolver 8.8.8.8 valid=300s;',
            '}',
        ])
        self.assertTrue(findings['resolver']['present'])
        self.assertEqual(findings['resolver']['severity'], 'LOW')

    def test_resolver_missing(self):
        findings = self._audit(['http {', '}'])
        self.assertFalse(findings['resolver']['present'])

    # ── limit_req_zone ─────────────────────────────────────────────────

    def test_limit_req_zone_present(self):
        findings = self._audit([
            'http {',
            '    limit_req_zone $binary_remote_addr zone=one:10m rate=1r/s;',
            '}',
        ])
        self.assertTrue(findings['limit_req_zone']['present'])
        self.assertEqual(findings['limit_req_zone']['severity'], 'LOW')

    def test_limit_req_zone_missing(self):
        findings = self._audit(['http {', '}'])
        self.assertFalse(findings['limit_req_zone']['present'])

    # ── client_max_body_size ───────────────────────────────────────────

    def test_client_max_body_size_present(self):
        findings = self._audit([
            'http {',
            '    client_max_body_size 10m;',
            '}',
        ])
        self.assertTrue(findings['client_max_body_size']['present'])
        self.assertEqual(findings['client_max_body_size']['severity'], 'LOW')

    def test_client_max_body_size_missing(self):
        findings = self._audit(['http {', '}'])
        self.assertFalse(findings['client_max_body_size']['present'])

    # ── gzip ───────────────────────────────────────────────────────────

    def test_gzip_on_present(self):
        findings = self._audit([
            'http {',
            '    gzip on;',
            '}',
        ])
        self.assertTrue(findings['gzip']['present'])
        self.assertEqual(findings['gzip']['severity'], 'INFO')

    def test_gzip_off_does_not_match(self):
        findings = self._audit(['http {', '    gzip off;', '}'])
        self.assertFalse(findings['gzip']['present'])

    def test_gzip_missing(self):
        findings = self._audit(['http {', '}'])
        self.assertFalse(findings['gzip']['present'])


class TestAuditGlobalDirectivesMainContext(unittest.TestCase):
    """Unit tests for audit_global_directives() main-context checks."""

    def _audit(self, lines):
        path = _make_config(lines)
        analyzer = NginxAnalyzer(path)
        return {f['id']: f for f in analyzer.audit_global_directives()}

    def test_worker_processes_present(self):
        findings = self._audit([
            'worker_processes auto;',
            'http {',
            '}',
        ])
        self.assertTrue(findings['worker_processes']['present'])
        self.assertEqual(findings['worker_processes']['severity'], 'INFO')
        self.assertEqual(findings['worker_processes']['context'], 'main')

    def test_worker_processes_missing(self):
        findings = self._audit(['http {', '}'])
        self.assertFalse(findings['worker_processes']['present'])

    def test_worker_processes_not_matched_inside_http(self):
        # worker_processes inside http{} should NOT count — it belongs in main
        findings = self._audit([
            'http {',
            '    worker_processes auto;',
            '}',
        ])
        self.assertFalse(findings['worker_processes']['present'])


class TestAuditGlobalDirectivesScopeIsolation(unittest.TestCase):
    """Directives in nested blocks (server{}) should not be detected."""

    def _audit(self, lines):
        path = _make_config(lines)
        analyzer = NginxAnalyzer(path)
        return {f['id']: f for f in analyzer.audit_global_directives()}

    def test_server_tokens_in_server_block_not_counted(self):
        findings = self._audit([
            'http {',
            '    server {',
            '        server_tokens off;',
            '    }',
            '}',
        ])
        self.assertFalse(findings['server_tokens']['present'])

    def test_hsts_in_server_block_not_counted(self):
        findings = self._audit([
            'http {',
            '    server {',
            '        add_header Strict-Transport-Security "max-age=31536000";',
            '    }',
            '}',
        ])
        self.assertFalse(findings['hsts']['present'])


class TestAuditGlobalDirectivesFullConfig(unittest.TestCase):
    """Integration: realistic nginx.conf with all directives present."""

    def _audit(self, lines):
        path = _make_config(lines)
        analyzer = NginxAnalyzer(path)
        return {f['id']: f for f in analyzer.audit_global_directives()}

    def test_all_present(self):
        lines = [
            'worker_processes auto;',
            'http {',
            '    server_tokens off;',
            '    add_header Strict-Transport-Security "max-age=31536000" always;',
            '    add_header X-Content-Type-Options nosniff;',
            '    add_header X-Frame-Options SAMEORIGIN;',
            '    ssl_protocols TLSv1.2 TLSv1.3;',
            '    resolver 8.8.8.8;',
            '    limit_req_zone $binary_remote_addr zone=main:10m rate=10r/s;',
            '    client_max_body_size 20m;',
            '    gzip on;',
            '}',
        ]
        findings = self._audit(lines)
        for check_id, f in findings.items():
            self.assertTrue(f['present'], f"{check_id} should be present")

    def test_all_missing_when_http_block_empty(self):
        findings = self._audit(['http {', '}'])
        http_checks = [f for f in findings.values() if f['context'] == 'http{}']
        for f in http_checks:
            self.assertFalse(f['present'], f"{f['id']} should be missing")

    def test_returns_all_check_ids(self):
        findings = self._audit(['http {', '}'])
        expected = {
            'server_tokens', 'hsts', 'xcto', 'xfo', 'ssl_protocols',
            'resolver', 'limit_req_zone', 'client_max_body_size', 'gzip',
            'worker_processes',
        }
        self.assertEqual(set(findings.keys()), expected)


class TestExtractBlockLines(unittest.TestCase):
    """Unit tests for NginxAnalyzer._extract_block_lines()."""

    def _analyzer(self, lines):
        path = _make_config(lines)
        return NginxAnalyzer(path)

    def test_returns_only_http_children(self):
        analyzer = self._analyzer([
            'events { worker_connections 1024; }',
            'http {',
            '    gzip on;',
            '    server { listen 80; }',
            '}',
        ])
        http_lines = analyzer._extract_block_lines('http')
        joined = ''.join(http_lines)
        self.assertIn('gzip', joined)
        self.assertNotIn('worker_connections', joined)

    def test_empty_block_returns_nothing(self):
        analyzer = self._analyzer(['http {', '}'])
        self.assertEqual(analyzer._extract_block_lines('http'), [])

    def test_missing_block_returns_nothing(self):
        analyzer = self._analyzer(['events {', '}'])
        self.assertEqual(analyzer._extract_block_lines('http'), [])


class TestHandleGlobalAudit(unittest.TestCase):
    """Integration tests for _handle_global_audit() via file_handler."""

    def _run(self, lines, only_failures=False, fmt='text'):
        from reveal.file_handler import _handle_global_audit
        path = _make_config(lines)
        analyzer = NginxAnalyzer(path)
        args = Namespace(only_failures=only_failures, format=fmt)
        buf = StringIO()
        with patch('sys.stdout', buf):
            try:
                _handle_global_audit(analyzer, args)
            except SystemExit:
                pass
        return buf.getvalue()

    def _run_json(self, lines, only_failures=False):
        from reveal.file_handler import _handle_global_audit
        path = _make_config(lines)
        analyzer = NginxAnalyzer(path)
        args = Namespace(only_failures=only_failures, format='json')
        buf = StringIO()
        with patch('sys.stdout', buf):
            try:
                _handle_global_audit(analyzer, args)
            except SystemExit:
                pass
        return json.loads(buf.getvalue())

    def test_text_output_contains_all_directives(self):
        out = self._run(['http {', '}'])
        self.assertIn('server_tokens', out)
        self.assertIn('Strict-Transport-Security', out)
        self.assertIn('gzip', out)
        self.assertIn('worker_processes', out)

    def test_text_output_shows_missing_symbol(self):
        out = self._run(['http {', '}'])
        self.assertIn('❌', out)

    def test_text_output_shows_present_symbol(self):
        out = self._run([
            'worker_processes auto;',
            'http {',
            '    gzip on;',
            '}',
        ])
        self.assertIn('✅', out)

    def test_only_failures_hides_present(self):
        out = self._run(
            ['http {', '    gzip on;', '}'],
            only_failures=True,
        )
        self.assertNotIn('gzip on', out)

    def test_only_failures_shows_missing(self):
        out = self._run(['http {', '}'], only_failures=True)
        self.assertIn('❌', out)

    def test_only_failures_no_missing_prints_ok(self):
        lines = [
            'worker_processes auto;',
            'http {',
            '    server_tokens off;',
            '    add_header Strict-Transport-Security "max-age=31536000" always;',
            '    add_header X-Content-Type-Options nosniff;',
            '    add_header X-Frame-Options SAMEORIGIN;',
            '    ssl_protocols TLSv1.2 TLSv1.3;',
            '    resolver 8.8.8.8;',
            '    limit_req_zone $binary_remote_addr zone=x:10m rate=1r/s;',
            '    client_max_body_size 10m;',
            '    gzip on;',
            '}',
        ]
        out = self._run(lines, only_failures=True)
        self.assertIn('No missing', out)

    def test_json_output_structure(self):
        data = self._run_json(['http {', '}'])
        self.assertEqual(data['type'], 'nginx_global_audit')
        self.assertIn('has_failures', data)
        self.assertIn('findings', data)
        self.assertIsInstance(data['findings'], list)

    def test_json_has_failures_true_when_missing(self):
        data = self._run_json(['http {', '}'])
        self.assertTrue(data['has_failures'])

    def test_json_has_failures_false_when_all_present(self):
        lines = [
            'worker_processes auto;',
            'http {',
            '    server_tokens off;',
            '    add_header Strict-Transport-Security "max-age=31536000" always;',
            '    add_header X-Content-Type-Options nosniff;',
            '    add_header X-Frame-Options SAMEORIGIN;',
            '    ssl_protocols TLSv1.2 TLSv1.3;',
            '    resolver 8.8.8.8;',
            '    limit_req_zone $binary_remote_addr zone=x:10m rate=1r/s;',
            '    client_max_body_size 10m;',
            '    gzip on;',
            '}',
        ]
        data = self._run_json(lines)
        self.assertFalse(data['has_failures'])

    def test_json_only_failures_filters(self):
        lines = ['http {', '    gzip on;', '}']
        data = self._run_json(lines, only_failures=True)
        for f in data['findings']:
            self.assertFalse(f['present'])

    def test_non_nginx_analyzer_exits(self):
        from reveal.file_handler import _handle_global_audit

        class FakeAnalyzer:
            pass

        args = Namespace(only_failures=False, format='text')
        with self.assertRaises(SystemExit):
            _handle_global_audit(FakeAnalyzer(), args)


if __name__ == '__main__':
    unittest.main()
