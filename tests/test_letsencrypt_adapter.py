"""Tests for LetsEncryptAdapter (BACK-079)."""

import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from reveal.adapters.letsencrypt.adapter import (
    LetsEncryptAdapter,
    _walk_live_dir,
    _collect_nginx_cert_paths,
    _find_orphans,
    _find_duplicates,
    _load_cert_info,
    _check_renewal_timer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cert_dir(base: Path, name: str, san: list, days: int = 90, expired: bool = False):
    """Create a fake letsencrypt live/<name>/cert.pem directory structure."""
    cert_dir = base / name
    cert_dir.mkdir(parents=True, exist_ok=True)
    (cert_dir / 'cert.pem').write_text(f'# fake cert {name}')  # not a real cert
    return cert_dir


def _fake_cert(name: str, san: list, days: int = 90, expired: bool = False) -> dict:
    """Build a cert dict as would be returned by _load_cert_info."""
    return {
        'name': name,
        'cert_path': f'/etc/letsencrypt/live/{name}/cert.pem',
        'common_name': san[0] if san else name,
        'san': sorted(san),
        'days_until_expiry': days,
        'not_after': '2026-12-31T00:00:00+00:00',
        'is_expired': expired,
        'issuer': "Let's Encrypt",
    }


# ---------------------------------------------------------------------------
# _collect_nginx_cert_paths
# ---------------------------------------------------------------------------

class TestCollectNginxCertPaths(unittest.TestCase):

    def test_extracts_ssl_certificate_path(self):
        with tempfile.TemporaryDirectory() as d:
            conf = Path(d) / 'example.conf'
            conf.write_text(
                'server {\n'
                '    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;\n'
                '    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;\n'
                '}\n'
            )
            paths = _collect_nginx_cert_paths([d])
        self.assertIn('/etc/letsencrypt/live/example.com/fullchain.pem', paths)
        self.assertNotIn('/etc/letsencrypt/live/example.com/privkey.pem', paths)

    def test_multiple_vhosts(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'a.conf').write_text(
                'ssl_certificate /etc/letsencrypt/live/a.com/fullchain.pem;\n'
            )
            (Path(d) / 'b.conf').write_text(
                'ssl_certificate /etc/letsencrypt/live/b.com/fullchain.pem;\n'
            )
            paths = _collect_nginx_cert_paths([d])
        self.assertIn('/etc/letsencrypt/live/a.com/fullchain.pem', paths)
        self.assertIn('/etc/letsencrypt/live/b.com/fullchain.pem', paths)

    def test_missing_dir_returns_empty(self):
        paths = _collect_nginx_cert_paths(['/nonexistent/dir'])
        self.assertEqual(paths, [])

    def test_no_ssl_certificate_in_config(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'plain.conf').write_text('server { listen 80; }\n')
            paths = _collect_nginx_cert_paths([d])
        self.assertEqual(paths, [])

    def test_handles_quoted_paths(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'q.conf').write_text(
                'ssl_certificate "/etc/letsencrypt/live/quoted.com/fullchain.pem";\n'
            )
            paths = _collect_nginx_cert_paths([d])
        self.assertIn('/etc/letsencrypt/live/quoted.com/fullchain.pem', paths)


# ---------------------------------------------------------------------------
# _find_orphans
# ---------------------------------------------------------------------------

class TestFindOrphans(unittest.TestCase):

    def test_cert_in_use_is_not_orphan(self):
        certs = [_fake_cert('example.com', ['example.com'])]
        nginx_paths = ['/etc/letsencrypt/live/example.com/fullchain.pem']
        orphans = _find_orphans(certs, nginx_paths)
        self.assertEqual(orphans, [])

    def test_cert_not_referenced_is_orphan(self):
        certs = [_fake_cert('old.com', ['old.com'])]
        nginx_paths = ['/etc/letsencrypt/live/example.com/fullchain.pem']
        orphans = _find_orphans(certs, nginx_paths)
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0]['name'], 'old.com')

    def test_multiple_certs_partial_orphans(self):
        certs = [
            _fake_cert('active.com', ['active.com']),
            _fake_cert('orphan.com', ['orphan.com']),
        ]
        nginx_paths = ['/etc/letsencrypt/live/active.com/cert.pem']
        orphans = _find_orphans(certs, nginx_paths)
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0]['name'], 'orphan.com')

    def test_cert_with_error_skipped(self):
        certs = [{'name': 'bad.com', 'cert_path': '/path/cert.pem', 'error': 'parse failed'}]
        orphans = _find_orphans(certs, [])
        self.assertEqual(orphans, [])

    def test_no_nginx_paths_all_are_orphans(self):
        certs = [
            _fake_cert('a.com', ['a.com']),
            _fake_cert('b.com', ['b.com']),
        ]
        orphans = _find_orphans(certs, [])
        self.assertEqual(len(orphans), 2)


# ---------------------------------------------------------------------------
# _find_duplicates
# ---------------------------------------------------------------------------

class TestFindDuplicates(unittest.TestCase):

    def test_no_duplicates(self):
        certs = [
            _fake_cert('a.com', ['a.com', 'www.a.com']),
            _fake_cert('b.com', ['b.com']),
        ]
        groups = _find_duplicates(certs)
        self.assertEqual(groups, [])

    def test_two_certs_same_sans(self):
        certs = [
            _fake_cert('a1.com', ['a.com', 'www.a.com']),
            _fake_cert('a2.com', ['a.com', 'www.a.com']),
        ]
        groups = _find_duplicates(certs)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 2)

    def test_three_certs_two_duplicate(self):
        certs = [
            _fake_cert('a1.com', ['a.com']),
            _fake_cert('a2.com', ['a.com']),
            _fake_cert('b.com', ['b.com']),
        ]
        groups = _find_duplicates(certs)
        self.assertEqual(len(groups), 1)
        names = {c['name'] for c in groups[0]}
        self.assertEqual(names, {'a1.com', 'a2.com'})

    def test_cert_with_error_skipped(self):
        certs = [
            _fake_cert('a.com', ['a.com']),
            {'name': 'bad.com', 'cert_path': '/path/cert.pem', 'error': 'parse failed'},
        ]
        groups = _find_duplicates(certs)
        self.assertEqual(groups, [])

    def test_empty_san_not_grouped(self):
        # Certs with no SANs should not be grouped (frozenset() is falsy key)
        cert1 = _fake_cert('a.com', [])
        cert2 = _fake_cert('b.com', [])
        groups = _find_duplicates([cert1, cert2])
        self.assertEqual(groups, [])


# ---------------------------------------------------------------------------
# _walk_live_dir
# ---------------------------------------------------------------------------

class TestWalkLiveDir(unittest.TestCase):

    def test_missing_dir_returns_empty(self):
        certs = _walk_live_dir('/nonexistent/letsencrypt/live')
        self.assertEqual(certs, [])

    def test_empty_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            certs = _walk_live_dir(d)
        self.assertEqual(certs, [])

    def test_dir_without_cert_pem_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'example.com').mkdir()
            certs = _walk_live_dir(d)
        self.assertEqual(certs, [])

    def test_dir_with_cert_pem_attempted(self):
        """walk_live_dir should attempt to load cert.pem files."""
        with tempfile.TemporaryDirectory() as d:
            cert_dir = Path(d) / 'example.com'
            cert_dir.mkdir()
            (cert_dir / 'cert.pem').write_text('# fake')

            # _load_cert_info will fail on non-real cert but should return error dict
            certs = _walk_live_dir(d)
        self.assertEqual(len(certs), 1)
        self.assertEqual(certs[0]['name'], 'example.com')


# ---------------------------------------------------------------------------
# LetsEncryptAdapter
# ---------------------------------------------------------------------------

class TestLetsEncryptAdapter(unittest.TestCase):

    def test_empty_string_is_accepted(self):
        """BUG-136: letsencrypt:// with no argument must work — docs show bare URI as valid."""
        adapter = LetsEncryptAdapter('')
        self.assertIsNotNone(adapter)

    def test_rejects_wrong_scheme(self):
        with self.assertRaises(ValueError):
            LetsEncryptAdapter('ssl://example.com')

    def test_accepts_valid_uri(self):
        adapter = LetsEncryptAdapter('letsencrypt://')
        self.assertIsNotNone(adapter)

    def test_get_structure_returns_inventory_type(self):
        adapter = LetsEncryptAdapter('letsencrypt://')
        adapter.live_dir = '/nonexistent'
        result = adapter.get_structure()
        self.assertEqual(result['type'], 'letsencrypt_inventory')
        self.assertFalse(result['live_dir_exists'])
        self.assertEqual(result['cert_count'], 0)

    def test_get_structure_includes_source_fields(self):
        """BUG-04: get_structure() must include 'source' and 'source_type' keys."""
        adapter = LetsEncryptAdapter('letsencrypt://')
        adapter.live_dir = '/etc/letsencrypt/live'
        result = adapter.get_structure()
        self.assertIn('source', result)
        self.assertIn('source_type', result)
        self.assertEqual(result['source'], '/etc/letsencrypt/live')
        self.assertEqual(result['source_type'], 'letsencrypt_directory')

    def test_source_reflects_custom_live_dir(self):
        """BUG-04: 'source' must equal the actual live_dir path, not some other value."""
        adapter = LetsEncryptAdapter('letsencrypt://')
        adapter.live_dir = '/srv/certs/live'
        result = adapter.get_structure()
        self.assertEqual(result['source'], '/srv/certs/live')

    def test_check_orphans_adds_orphan_check(self):
        adapter = LetsEncryptAdapter('letsencrypt://')
        adapter.live_dir = '/nonexistent'
        adapter.nginx_dirs = ['/nonexistent']
        result = adapter.get_structure(check_orphans=True)
        self.assertIn('orphan_check', result)
        self.assertEqual(result['orphan_check']['orphan_count'], 0)

    def test_check_duplicates_adds_duplicate_check(self):
        adapter = LetsEncryptAdapter('letsencrypt://')
        adapter.live_dir = '/nonexistent'
        result = adapter.get_structure(check_duplicates=True)
        self.assertIn('duplicate_check', result)
        self.assertEqual(result['duplicate_check']['duplicate_group_count'], 0)

    def test_structure_with_fake_certs(self):
        """Integration: adapter with mocked _walk_live_dir."""
        fake_certs = [
            _fake_cert('active.com', ['active.com']),
            _fake_cert('orphan.com', ['orphan.com']),
        ]
        nginx_paths = ['/etc/letsencrypt/live/active.com/fullchain.pem']

        adapter = LetsEncryptAdapter('letsencrypt://')

        with patch('reveal.adapters.letsencrypt.adapter._walk_live_dir', return_value=fake_certs):
            with patch('reveal.adapters.letsencrypt.adapter._collect_nginx_cert_paths',
                       return_value=nginx_paths):
                result = adapter.get_structure(check_orphans=True, check_duplicates=True)

        self.assertEqual(result['cert_count'], 2)
        self.assertEqual(result['orphan_check']['orphan_count'], 1)
        self.assertEqual(result['orphan_check']['orphans'][0]['name'], 'orphan.com')
        self.assertEqual(result['duplicate_check']['duplicate_group_count'], 0)

    def test_duplicate_detection_via_adapter(self):
        fake_certs = [
            _fake_cert('cert1.com', ['example.com', 'www.example.com']),
            _fake_cert('cert2.com', ['example.com', 'www.example.com']),
            _fake_cert('other.com', ['other.com']),
        ]

        adapter = LetsEncryptAdapter('letsencrypt://')

        with patch('reveal.adapters.letsencrypt.adapter._walk_live_dir', return_value=fake_certs):
            result = adapter.get_structure(check_duplicates=True)

        self.assertEqual(result['duplicate_check']['duplicate_group_count'], 1)

    def test_get_schema_returns_dict(self):
        schema = LetsEncryptAdapter.get_schema()
        self.assertIn('adapter', schema)
        self.assertEqual(schema['adapter'], 'letsencrypt')

    def test_get_help_returns_dict(self):
        h = LetsEncryptAdapter.get_help()
        self.assertIn('name', h)
        self.assertEqual(h['name'], 'letsencrypt')

    def test_next_steps_suggests_missing_checks(self):
        adapter = LetsEncryptAdapter('letsencrypt://')
        adapter.live_dir = '/nonexistent'
        result = adapter.get_structure()
        ns = result['next_steps']
        self.assertTrue(any('check-orphans' in s for s in ns))
        self.assertTrue(any('check-duplicates' in s for s in ns))

    def test_next_steps_no_redundant_suggestion(self):
        adapter = LetsEncryptAdapter('letsencrypt://')
        adapter.live_dir = '/nonexistent'
        adapter.nginx_dirs = ['/nonexistent']
        result = adapter.get_structure(check_orphans=True, check_duplicates=True)
        ns = result['next_steps']
        self.assertFalse(any('check-orphans' in s for s in ns))
        self.assertFalse(any('check-duplicates' in s for s in ns))


# ---------------------------------------------------------------------------
# Renewal timer detection (BACK-079)
# ---------------------------------------------------------------------------

class TestCheckRenewalTimer(unittest.TestCase):

    def test_returns_unconfigured_when_no_paths_exist(self):
        """Should report not configured when no timer/cron paths are found."""
        with patch('reveal.adapters.letsencrypt.adapter.Path') as MockPath:
            MockPath.return_value.exists.return_value = False
            result = _check_renewal_timer()
        self.assertFalse(result['configured'])
        self.assertEqual(result['mechanisms'], [])
        self.assertIsNotNone(result['warning'])
        self.assertIn('renewal timer', result['warning'])

    def test_detects_systemd_timer(self):
        """Should report configured when a systemd certbot.timer file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            timer_path = os.path.join(tmpdir, 'certbot.timer')
            Path(timer_path).touch()

            from reveal.adapters.letsencrypt import adapter as le_mod
            original_paths = le_mod._RENEWAL_TIMER_PATHS
            le_mod._RENEWAL_TIMER_PATHS = [timer_path]
            try:
                result = _check_renewal_timer()
            finally:
                le_mod._RENEWAL_TIMER_PATHS = original_paths

        self.assertTrue(result['configured'])
        self.assertEqual(len(result['mechanisms']), 1)
        self.assertIsNone(result['warning'])

    def test_detects_cron_timer(self):
        """Should detect cron-based renewal and label kind as 'cron'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cron_path = os.path.join(tmpdir, 'certbot')
            Path(cron_path).touch()

            from reveal.adapters.letsencrypt import adapter as le_mod
            original_paths = le_mod._RENEWAL_TIMER_PATHS
            le_mod._RENEWAL_TIMER_PATHS = [cron_path]
            try:
                result = _check_renewal_timer()
            finally:
                le_mod._RENEWAL_TIMER_PATHS = original_paths

        self.assertTrue(result['configured'])
        self.assertEqual(result['mechanisms'][0]['kind'], 'cron')

    def test_renewal_timer_included_in_get_structure(self):
        """get_structure() should always include renewal_timer key."""
        adapter = LetsEncryptAdapter('letsencrypt://')
        with patch.object(adapter, 'live_dir', '/nonexistent'), \
             patch('reveal.adapters.letsencrypt.adapter._check_renewal_timer',
                   return_value={'configured': False, 'mechanisms': [], 'warning': 'none'}), \
             patch('reveal.adapters.letsencrypt.adapter._walk_live_dir', return_value=[]):
            result = adapter.get_structure()
        self.assertIn('renewal_timer', result)
        self.assertEqual(result['renewal_timer']['configured'], False)


# ---------------------------------------------------------------------------
# Renderer smoke test
# ---------------------------------------------------------------------------

class TestLetsEncryptRenderer(unittest.TestCase):

    def setUp(self):
        from reveal.adapters.letsencrypt.renderer import LetsEncryptRenderer
        self.renderer = LetsEncryptRenderer

    def test_renders_missing_live_dir(self):
        import io
        from unittest.mock import patch
        buf = io.StringIO()
        with patch('builtins.print', side_effect=lambda *a, **kw: buf.write(str(a[0]) + '\n')):
            self.renderer.render_structure({
                'live_dir': '/etc/letsencrypt/live',
                'live_dir_exists': False,
                'certs': [],
            })
        self.assertIn('not found', buf.getvalue())

    def test_renders_json(self):
        import io, json
        buf = io.StringIO()
        data = {'type': 'letsencrypt_inventory', 'cert_count': 0, 'certs': []}
        with patch('builtins.print', side_effect=lambda *a, **kw: buf.write(str(a[0]) + '\n')):
            self.renderer.render_structure(data, format='json')
        parsed = json.loads(buf.getvalue().strip())
        self.assertEqual(parsed['type'], 'letsencrypt_inventory')

    def test_render_error_accepts_exception(self):
        """BACK-168: render_error must accept Exception, not just str."""
        import io
        buf = io.StringIO()
        err = ImportError("missing dependency")
        with patch('builtins.print', side_effect=lambda *a, **kw: buf.write(str(a[0]) + '\n')):
            self.renderer.render_error(err)
        self.assertIn('missing dependency', buf.getvalue())

    def test_render_structure_format_kwarg(self):
        """BACK-169: render_structure parameter must be named 'format', not 'output_format'."""
        import io, json, inspect
        sig = inspect.signature(self.renderer.render_structure)
        assert 'format' in sig.parameters, "render_structure must have 'format' parameter"
        assert 'output_format' not in sig.parameters, "render_structure must not use 'output_format'"


class TestLetsEncryptQueryParams(unittest.TestCase):
    """BACK-175: letsencrypt:// adapter query param support."""

    def test_check_orphans_via_query_param(self):
        """?check-orphans in URI triggers orphan analysis."""
        from reveal.adapters.letsencrypt.adapter import LetsEncryptAdapter
        adapter = LetsEncryptAdapter('letsencrypt://?check-orphans')
        assert adapter.query_params.get('check-orphans') is True

    def test_check_duplicates_via_query_param(self):
        """?check-duplicates in URI triggers duplicate analysis."""
        from reveal.adapters.letsencrypt.adapter import LetsEncryptAdapter
        adapter = LetsEncryptAdapter('letsencrypt://?check-duplicates')
        assert adapter.query_params.get('check-duplicates') is True

    def test_no_query_params_by_default(self):
        """Bare letsencrypt:// has empty query_params."""
        from reveal.adapters.letsencrypt.adapter import LetsEncryptAdapter
        adapter = LetsEncryptAdapter('letsencrypt://')
        assert adapter.query_params == {}

    def test_schema_documents_query_params(self):
        """BACK-175: schema query_params lists check-orphans and check-duplicates."""
        from reveal.adapters.letsencrypt.adapter import LetsEncryptAdapter
        schema = LetsEncryptAdapter.get_schema()
        qp = schema['query_params']
        assert 'check-orphans' in qp
        assert 'check-duplicates' in qp


class TestLetsEncryptGetHelp:
    """Tests for letsencrypt get_help() — loaded from help_data/letsencrypt.yaml."""

    def test_get_help_returns_dict(self):
        h = LetsEncryptAdapter.get_help()
        assert isinstance(h, dict)

    def test_get_help_required_fields(self):
        h = LetsEncryptAdapter.get_help()
        assert h['name'] == 'letsencrypt'
        assert 'description' in h
        assert 'syntax' in h
        assert 'examples' in h

    def test_get_help_has_query_params_section(self):
        """query_params key must exist and document both params."""
        h = LetsEncryptAdapter.get_help()
        assert 'query_params' in h, "help data must have query_params section"
        qp = h['query_params']
        assert 'check-orphans' in qp
        assert 'check-duplicates' in qp

    def test_get_help_examples_include_uri_param_forms(self):
        """Examples must show ?check-orphans and ?check-duplicates URI forms."""
        h = LetsEncryptAdapter.get_help()
        uris = [e['uri'] for e in h['examples']]
        all_uris = ' '.join(uris)
        assert '?check-orphans' in all_uris, "missing ?check-orphans example"
        assert '?check-duplicates' in all_uris, "missing ?check-duplicates example"

    def test_get_help_examples_include_cli_flag_forms(self):
        """Examples must still show --check-orphans and --check-duplicates CLI forms."""
        h = LetsEncryptAdapter.get_help()
        uris = [e['uri'] for e in h['examples']]
        all_uris = ' '.join(uris)
        assert '--check-orphans' in all_uris
        assert '--check-duplicates' in all_uris

    def test_get_help_has_flags_section(self):
        h = LetsEncryptAdapter.get_help()
        assert 'flags' in h
        flags = h['flags']
        assert '--check-orphans' in flags
        assert '--check-duplicates' in flags


if __name__ == '__main__':
    unittest.main()
