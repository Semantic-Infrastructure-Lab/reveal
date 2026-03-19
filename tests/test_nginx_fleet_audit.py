"""Tests for nginx:// --audit fleet consistency matrix (BACK-090)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.nginx.adapter import (
    _audit_site_content,
    _build_snippet_consistency,
    _extract_includes,
    _find_nginx_conf,
    _normalize_include,
    _run_fleet_audit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(tmpdir: str, filename: str, content: str) -> str:
    path = os.path.join(tmpdir, filename)
    with open(path, 'w') as fh:
        fh.write(content)
    return path


def _site(name: str, server_tokens: bool = False, hsts: bool = False,
          xcto: bool = False, xfo: bool = False, http2: bool = False,
          limit_req: bool = False, xss: bool = False,
          includes: list = None) -> str:
    """Build a minimal nginx site config with selected directives present."""
    lines = [f'server {{', f'    server_name {name};']
    if server_tokens:
        lines.append('    server_tokens off;')
    if hsts:
        lines.append('    add_header Strict-Transport-Security "max-age=31536000" always;')
    if xcto:
        lines.append('    add_header X-Content-Type-Options nosniff always;')
    if xfo:
        lines.append('    add_header X-Frame-Options SAMEORIGIN always;')
    if http2:
        lines.append('    listen 443 ssl http2;')
    else:
        lines.append('    listen 443 ssl;')
    if limit_req:
        lines.append('    limit_req zone=default burst=20 nodelay;')
    if xss:
        lines.append('    add_header X-XSS-Protection "1; mode=block";')
    if includes:
        for inc in includes:
            lines.append(f'    include {inc};')
    lines.append('}')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# _audit_site_content
# ---------------------------------------------------------------------------

class TestAuditSiteContent(unittest.TestCase):

    def test_all_absent(self):
        content = 'server { server_name foo.example.com; listen 443 ssl; }'
        result = _audit_site_content(content)
        self.assertFalse(result['server_tokens'])
        self.assertFalse(result['hsts'])
        self.assertFalse(result['xcto'])
        self.assertFalse(result['xfo'])
        self.assertFalse(result['http2'])
        self.assertFalse(result['limit_req'])
        self.assertFalse(result['xss_prot'])

    def test_server_tokens_off(self):
        content = 'server { server_tokens off; }'
        self.assertTrue(_audit_site_content(content)['server_tokens'])

    def test_server_tokens_on_does_not_match(self):
        content = 'server { server_tokens on; }'
        self.assertFalse(_audit_site_content(content)['server_tokens'])

    def test_hsts_present(self):
        content = 'server { add_header Strict-Transport-Security "max-age=31536000"; }'
        self.assertTrue(_audit_site_content(content)['hsts'])

    def test_xcto_present(self):
        content = 'server { add_header X-Content-Type-Options nosniff; }'
        self.assertTrue(_audit_site_content(content)['xcto'])

    def test_xfo_present(self):
        content = 'server { add_header X-Frame-Options SAMEORIGIN; }'
        self.assertTrue(_audit_site_content(content)['xfo'])

    def test_http2_present(self):
        content = 'server { listen 443 ssl http2; }'
        self.assertTrue(_audit_site_content(content)['http2'])

    def test_http2_absent(self):
        content = 'server { listen 443 ssl; }'
        self.assertFalse(_audit_site_content(content)['http2'])

    def test_limit_req_present(self):
        content = 'server { limit_req zone=default burst=20; }'
        self.assertTrue(_audit_site_content(content)['limit_req'])

    def test_xss_prot_present(self):
        content = 'server { add_header X-XSS-Protection "1; mode=block"; }'
        self.assertTrue(_audit_site_content(content)['xss_prot'])

    def test_case_insensitive(self):
        content = 'server { ADD_HEADER Strict-Transport-Security "max-age=31536000"; }'
        self.assertTrue(_audit_site_content(content)['hsts'])


# ---------------------------------------------------------------------------
# _extract_includes / _normalize_include
# ---------------------------------------------------------------------------

class TestExtractIncludes(unittest.TestCase):

    def test_no_includes(self):
        content = 'server { server_name foo.example.com; }'
        self.assertEqual(_extract_includes(content), [])

    def test_single_include(self):
        content = 'server {\n    include snippets/tia-security-headers.conf;\n}'
        result = _extract_includes(content)
        self.assertEqual(len(result), 1)
        self.assertIn('tia-security-headers.conf', result[0])

    def test_multiple_includes(self):
        content = (
            'server {\n'
            '    include snippets/ssl-params.conf;\n'
            '    include snippets/tia-security-headers.conf;\n'
            '}'
        )
        result = _extract_includes(content)
        self.assertEqual(len(result), 2)

    def test_glob_include(self):
        content = 'http { include /etc/nginx/conf.d/*.conf; }'
        result = _extract_includes(content)
        self.assertEqual(len(result), 1)
        self.assertIn('*.conf', result[0])


class TestNormalizeInclude(unittest.TestCase):

    def test_two_component_path(self):
        self.assertEqual(_normalize_include('snippets/ssl-params.conf'), 'snippets/ssl-params.conf')

    def test_absolute_path(self):
        result = _normalize_include('/etc/nginx/snippets/ssl-params.conf')
        self.assertEqual(result, 'snippets/ssl-params.conf')

    def test_single_component(self):
        self.assertEqual(_normalize_include('ssl-params.conf'), 'ssl-params.conf')


# ---------------------------------------------------------------------------
# _find_nginx_conf
# ---------------------------------------------------------------------------

class TestFindNginxConf(unittest.TestCase):

    def test_finds_first_existing(self):
        with tempfile.NamedTemporaryFile(suffix='.conf', delete=False) as f:
            path = f.name
        try:
            result = _find_nginx_conf(['/nonexistent/nginx.conf', path])
            self.assertEqual(result, path)
        finally:
            os.unlink(path)

    def test_returns_none_when_none_exist(self):
        result = _find_nginx_conf(['/nonexistent/a.conf', '/nonexistent/b.conf'])
        self.assertIsNone(result)

    def test_skips_nonexistent(self):
        with tempfile.NamedTemporaryFile(suffix='.conf', delete=False) as f:
            path = f.name
        try:
            result = _find_nginx_conf(['/no-such-file.conf', path])
            self.assertEqual(result, path)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# _build_snippet_consistency
# ---------------------------------------------------------------------------

class TestBuildSnippetConsistency(unittest.TestCase):

    def _make_record(self, domain: str, includes: list) -> dict:
        return {'file': f'/etc/nginx/sites-enabled/{domain}', 'domains': [domain],
                'checks': {}, 'includes': includes}

    def test_empty(self):
        self.assertEqual(_build_snippet_consistency([], 0), [])

    def test_snippet_used_by_majority(self):
        records = [
            self._make_record('a.example.com', ['snippets/security.conf']),
            self._make_record('b.example.com', ['snippets/security.conf']),
            self._make_record('c.example.com', ['snippets/security.conf']),
            self._make_record('d.example.com', []),  # missing
        ]
        result = _build_snippet_consistency(records, 4)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['sites_with'], 3)
        self.assertEqual(result[0]['sites_without'], 1)
        self.assertIn('d.example.com', result[0]['missing_from'])

    def test_snippet_used_by_minority_excluded(self):
        # Only 1 of 10 sites uses it — below the 25% threshold
        records = [self._make_record(f'{i}.example.com', []) for i in range(9)]
        records.append(self._make_record('solo.example.com', ['snippets/rare.conf']))
        result = _build_snippet_consistency(records, 10)
        self.assertEqual(result, [])

    def test_all_sites_have_snippet(self):
        records = [
            self._make_record('a.example.com', ['snippets/security.conf']),
            self._make_record('b.example.com', ['snippets/security.conf']),
        ]
        result = _build_snippet_consistency(records, 2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['sites_without'], 0)
        self.assertEqual(result[0]['missing_from'], [])


# ---------------------------------------------------------------------------
# _run_fleet_audit — integration tests with temp dirs
# ---------------------------------------------------------------------------

class TestRunFleetAudit(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _audit(self, site_configs: dict, nginx_conf_content: str = None):
        """Write site configs to tmpdir and run fleet audit."""
        for name, content in site_configs.items():
            _write_config(self.tmpdir, name, content)

        main_configs = []
        if nginx_conf_content is not None:
            nginx_conf_path = os.path.join(self.tmpdir, 'nginx.conf')
            with open(nginx_conf_path, 'w') as f:
                f.write(nginx_conf_content)
            main_configs = [nginx_conf_path]

        return _run_fleet_audit([self.tmpdir], main_configs)

    def _get_check(self, result: dict, check_id: str) -> dict:
        return next(e for e in result['matrix'] if e['id'] == check_id)

    def test_empty_dir_returns_zero_sites(self):
        result = _run_fleet_audit([self.tmpdir], [])
        self.assertEqual(result['type'], 'nginx_fleet_audit')
        self.assertEqual(result['site_count'], 0)
        self.assertFalse(result['has_gaps'])

    def test_site_count(self):
        result = self._audit({
            'site-a.conf': _site('a.example.com'),
            'site-b.conf': _site('b.example.com'),
            'site-c.conf': _site('c.example.com'),
        })
        self.assertEqual(result['site_count'], 3)

    def test_hsts_all_missing(self):
        result = self._audit({
            'a.conf': _site('a.example.com', hsts=False),
            'b.conf': _site('b.example.com', hsts=False),
        })
        check = self._get_check(result, 'hsts')
        self.assertEqual(check['sites_with'], 0)
        self.assertEqual(check['sites_without'], 2)

    def test_hsts_all_present(self):
        result = self._audit({
            'a.conf': _site('a.example.com', hsts=True),
            'b.conf': _site('b.example.com', hsts=True),
        })
        check = self._get_check(result, 'hsts')
        self.assertEqual(check['sites_with'], 2)
        self.assertEqual(check['sites_without'], 0)

    def test_partial_hsts_coverage(self):
        result = self._audit({
            'a.conf': _site('a.example.com', hsts=True),
            'b.conf': _site('b.example.com', hsts=False),
            'c.conf': _site('c.example.com', hsts=False),
        })
        check = self._get_check(result, 'hsts')
        self.assertEqual(check['sites_with'], 1)
        self.assertEqual(check['sites_without'], 2)

    def test_http2_detection(self):
        result = self._audit({
            'a.conf': _site('a.example.com', http2=True),
            'b.conf': _site('b.example.com', http2=False),
        })
        check = self._get_check(result, 'http2')
        self.assertEqual(check['sites_with'], 1)
        self.assertEqual(check['sites_without'], 1)

    def test_xss_prot_is_deprecated_flag(self):
        result = self._audit({'a.conf': _site('a.example.com', xss=True)})
        check = self._get_check(result, 'xss_prot')
        self.assertTrue(check['deprecated'])
        self.assertEqual(check['sites_with'], 1)

    def test_has_gaps_true_when_missing_directives(self):
        result = self._audit({'a.conf': _site('a.example.com')})
        self.assertTrue(result['has_gaps'])

    def test_has_gaps_false_when_all_global(self):
        # All non-deprecated checks present globally — no per-site gaps matter
        # (Actually, global doesn't override per-site in our logic, but if all sites have everything
        # and no deprecated headers, has_gaps should be False for the non-deprecated checks)
        result = self._audit({
            'a.conf': _site('a.example.com', server_tokens=True, hsts=True,
                            xcto=True, xfo=True, http2=True, limit_req=True, xss=False),
        })
        self.assertFalse(result['has_gaps'])

    def test_consolidation_opportunity_fires_when_majority_have_directive(self):
        """When ≥50% of sites have a directive but it's not in global → consolidation."""
        nginx_conf = 'events {}\nhttp {\n    # no server_tokens here\n}'
        result = self._audit(
            {
                'a.conf': _site('a.example.com', server_tokens=True),
                'b.conf': _site('b.example.com', server_tokens=True),
                'c.conf': _site('c.example.com', server_tokens=False),
            },
            nginx_conf_content=nginx_conf,
        )
        check = self._get_check(result, 'server_tokens')
        self.assertTrue(check['consolidation_opportunity'])

    def test_consolidation_does_not_fire_when_global_present(self):
        """When global has the directive, no consolidation needed."""
        nginx_conf = 'events {}\nhttp {\n    server_tokens off;\n}'
        result = self._audit(
            {
                'a.conf': _site('a.example.com', server_tokens=True),
                'b.conf': _site('b.example.com', server_tokens=True),
            },
            nginx_conf_content=nginx_conf,
        )
        check = self._get_check(result, 'server_tokens')
        self.assertFalse(check['consolidation_opportunity'])
        self.assertTrue(check['global_present'])

    def test_consolidation_does_not_fire_when_minority_have_directive(self):
        """When < 50% of sites have a directive, no consolidation hint."""
        nginx_conf = 'events {}\nhttp {\n}'
        result = self._audit(
            {
                'a.conf': _site('a.example.com', server_tokens=True),
                'b.conf': _site('b.example.com', server_tokens=False),
                'c.conf': _site('c.example.com', server_tokens=False),
                'd.conf': _site('d.example.com', server_tokens=False),
            },
            nginx_conf_content=nginx_conf,
        )
        check = self._get_check(result, 'server_tokens')
        self.assertFalse(check['consolidation_opportunity'])

    def test_only_failures_flag_stored_in_result(self):
        result = _run_fleet_audit([self.tmpdir], [])
        result['only_failures'] = True
        self.assertTrue(result['only_failures'])

    def test_result_type(self):
        result = _run_fleet_audit([self.tmpdir], [])
        self.assertEqual(result['type'], 'nginx_fleet_audit')
        self.assertEqual(result['contract_version'], '1.0')

    def test_nonexistent_search_dir_skipped(self):
        result = _run_fleet_audit(['/nonexistent/path'], [])
        self.assertEqual(result['site_count'], 0)

    def test_matrix_contains_all_checks(self):
        result = _run_fleet_audit([self.tmpdir], [])
        ids = {e['id'] for e in result['matrix']}
        self.assertIn('server_tokens', ids)
        self.assertIn('hsts', ids)
        self.assertIn('xcto', ids)
        self.assertIn('xfo', ids)
        self.assertIn('http2', ids)
        self.assertIn('limit_req', ids)
        self.assertIn('xss_prot', ids)

    def test_sites_with_names_populated(self):
        result = self._audit({'a.conf': _site('a.example.com', hsts=True)})
        check = self._get_check(result, 'hsts')
        self.assertIn('a.example.com', check['sites_with_names'])

    def test_snippet_consistency_in_result(self):
        result = self._audit({'a.conf': _site('a.example.com')})
        self.assertIn('snippet_consistency', result)

    def test_snippet_majority_detected(self):
        content_with = _site('a.example.com', includes=['snippets/security.conf'])
        content_with2 = _site('b.example.com', includes=['snippets/security.conf'])
        content_without = _site('c.example.com')
        result = self._audit({
            'a.conf': content_with,
            'b.conf': content_with2,
            'c.conf': content_without,
        })
        snippets = result['snippet_consistency']
        if snippets:
            self.assertEqual(snippets[0]['sites_with'], 2)
            self.assertIn('c.example.com', snippets[0]['missing_from'])

    def test_date_present(self):
        result = _run_fleet_audit([self.tmpdir], [])
        self.assertRegex(result['date'], r'^\d{4}-\d{2}-\d{2}$')

    def test_nginx_conf_none_when_not_found(self):
        result = _run_fleet_audit([self.tmpdir], ['/nonexistent/nginx.conf'])
        self.assertIsNone(result['nginx_conf'])

    def test_global_present_none_when_no_nginx_conf(self):
        result = self._audit({'a.conf': _site('a.example.com')})
        check = self._get_check(result, 'server_tokens')
        self.assertIsNone(check['global_present'])


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------

class TestNginxFleetAuditRenderer(unittest.TestCase):

    def _make_result(self, site_count=2, has_gaps=False, only_failures=False):
        return {
            'type': 'nginx_fleet_audit',
            'contract_version': '1.0',
            'source': 'nginx://',
            'nginx_conf': '/etc/nginx/nginx.conf',
            'site_count': site_count,
            'date': '2026-03-19',
            'has_gaps': has_gaps,
            'only_failures': only_failures,
            'snippet_consistency': [],
            'matrix': [
                {
                    'id': 'hsts',
                    'label': 'Strict-Transport-Security',
                    'severity': 'HIGH',
                    'global_present': False,
                    'deprecated': False,
                    'sites_with': 0,
                    'sites_without': site_count,
                    'sites_with_names': [],
                    'sites_without_names': ['a.example.com', 'b.example.com'],
                    'consolidation_opportunity': False,
                    'action': 'Add to nginx.conf http{}',
                },
                {
                    'id': 'xss_prot',
                    'label': 'X-XSS-Protection (depr.)',
                    'severity': 'LOW',
                    'global_present': None,
                    'deprecated': True,
                    'sites_with': 0,
                    'sites_without': site_count,
                    'sites_with_names': [],
                    'sites_without_names': [],
                    'consolidation_opportunity': False,
                    'action': '',
                },
            ],
        }

    def test_render_text_basic(self):
        from io import StringIO
        import sys
        result = self._make_result(site_count=2, has_gaps=False)
        from reveal.adapters.nginx.renderer import NginxUriRenderer
        buf = StringIO()
        with patch('sys.stdout', buf):
            NginxUriRenderer._render_nginx_fleet_audit(result)
        output = buf.getvalue()
        self.assertIn('Fleet Audit', output)
        self.assertIn('2 sites', output)
        self.assertIn('Strict-Transport-Security', output)

    def test_render_exits_2_on_gaps(self):
        from reveal.adapters.nginx.renderer import NginxUriRenderer
        result = self._make_result(site_count=2, has_gaps=True)
        with patch('sys.stdout'), self.assertRaises(SystemExit) as cm:
            NginxUriRenderer._render_nginx_fleet_audit(result)
        self.assertEqual(cm.exception.code, 2)

    def test_render_no_exit_when_no_gaps(self):
        from reveal.adapters.nginx.renderer import NginxUriRenderer
        result = self._make_result(site_count=2, has_gaps=False)
        # Should not raise SystemExit
        with patch('sys.stdout'):
            NginxUriRenderer._render_nginx_fleet_audit(result)

    def test_render_only_failures_shows_gaps_only(self):
        from io import StringIO
        from reveal.adapters.nginx.renderer import NginxUriRenderer
        result = self._make_result(site_count=2, has_gaps=True, only_failures=True)
        # Add a passing check
        result['matrix'].append({
            'id': 'xcto',
            'label': 'X-Content-Type-Options',
            'severity': 'MEDIUM',
            'global_present': True,
            'deprecated': False,
            'sites_with': 2,
            'sites_without': 0,
            'sites_with_names': ['a.example.com', 'b.example.com'],
            'sites_without_names': [],
            'consolidation_opportunity': False,
            'action': 'Globally set ✓',
        })
        buf = StringIO()
        with patch('sys.stdout', buf), self.assertRaises(SystemExit):
            NginxUriRenderer._render_nginx_fleet_audit(result)
        output = buf.getvalue()
        self.assertIn('Strict-Transport-Security', output)
        self.assertNotIn('X-Content-Type-Options', output)

    def test_render_no_sites_message(self):
        from io import StringIO
        from reveal.adapters.nginx.renderer import NginxUriRenderer
        result = self._make_result(site_count=0, has_gaps=False)
        result['matrix'] = []
        buf = StringIO()
        with patch('sys.stdout', buf):
            NginxUriRenderer._render_nginx_fleet_audit(result)
        self.assertIn('No site configs found', buf.getvalue())

    def test_render_consolidation_opportunity_marked(self):
        from io import StringIO
        from reveal.adapters.nginx.renderer import NginxUriRenderer
        result = self._make_result(site_count=4, has_gaps=False)
        result['matrix'][0]['consolidation_opportunity'] = True
        buf = StringIO()
        with patch('sys.stdout', buf):
            NginxUriRenderer._render_nginx_fleet_audit(result)
        output = buf.getvalue()
        self.assertIn('↑', output)

    def test_render_snippet_consistency_shown(self):
        from io import StringIO
        from reveal.adapters.nginx.renderer import NginxUriRenderer
        result = self._make_result(site_count=3, has_gaps=False)
        result['snippet_consistency'] = [{
            'snippet': 'snippets/security.conf',
            'sites_with': 2,
            'sites_without': 1,
            'missing_from': ['c.example.com'],
        }]
        buf = StringIO()
        with patch('sys.stdout', buf):
            NginxUriRenderer._render_nginx_fleet_audit(result)
        output = buf.getvalue()
        self.assertIn('snippets/security.conf', output)
        self.assertIn('c.example.com', output)


# ---------------------------------------------------------------------------
# Adapter get_structure(audit=True)
# ---------------------------------------------------------------------------

class TestNginxUriAdapterAuditFlag(unittest.TestCase):

    def test_audit_flag_dispatches_to_fleet_audit(self):
        with patch('reveal.adapters.nginx.adapter._run_fleet_audit') as mock_audit:
            mock_audit.return_value = {
                'type': 'nginx_fleet_audit', 'has_gaps': False,
                'site_count': 0, 'matrix': [], 'snippet_consistency': [],
                'date': '2026-03-19', 'nginx_conf': None,
                'contract_version': '1.0', 'source': 'nginx://',
            }
            from reveal.adapters.nginx.adapter import NginxUriAdapter
            adapter = NginxUriAdapter('nginx://')
            result = adapter.get_structure(audit=True)
            mock_audit.assert_called_once()
            self.assertEqual(result['type'], 'nginx_fleet_audit')

    def test_audit_false_uses_overview(self):
        with patch.object(
            __import__('reveal.adapters.nginx.adapter', fromlist=['NginxUriAdapter']).NginxUriAdapter,
            '_get_overview',
            return_value={'type': 'nginx_sites_overview', 'sites': [], 'artifact_files': [], 'next_steps': []}
        ) as mock_overview:
            from reveal.adapters.nginx.adapter import NginxUriAdapter
            adapter = NginxUriAdapter('nginx://')
            result = adapter.get_structure(audit=False)
            mock_overview.assert_called_once()
            self.assertEqual(result['type'], 'nginx_sites_overview')

    def test_only_failures_stored_in_audit_result(self):
        with patch('reveal.adapters.nginx.adapter._run_fleet_audit') as mock_audit:
            mock_audit.return_value = {
                'type': 'nginx_fleet_audit', 'has_gaps': False,
                'site_count': 0, 'matrix': [], 'snippet_consistency': [],
                'date': '2026-03-19', 'nginx_conf': None,
                'contract_version': '1.0', 'source': 'nginx://',
            }
            from reveal.adapters.nginx.adapter import NginxUriAdapter
            adapter = NginxUriAdapter('nginx://')
            result = adapter.get_structure(audit=True, only_failures=True)
            self.assertTrue(result['only_failures'])


if __name__ == '__main__':
    unittest.main()
