"""Tests for the cpanel:// adapter — CpanelAdapter + helpers."""

import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from reveal.adapters.cpanel.adapter import (
    CpanelAdapter,
    _parse_cpanel_userdata,
    _parse_main_domain_types,
    _list_user_domains,
    _get_disk_cert_status,
    CPANEL_USERDATA_DIR,
    CPANEL_SSL_DIR,
    NGINX_USER_CONF_DIR,
)
from reveal.adapters.cpanel.renderer import CpanelRenderer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cert(days: int = 90, serial: str = 'AABB'):
    from reveal.adapters.ssl.certificate import CertificateInfo
    now = datetime.now(timezone.utc)
    return CertificateInfo(
        subject={'commonName': 'example.com'},
        issuer={'organizationName': 'Test CA', 'commonName': 'Test CA Root'},
        not_before=now - timedelta(days=10),
        not_after=now + timedelta(days=days),
        serial_number=serial,
        version=3,
        san=['example.com'],
        signature_algorithm='sha256WithRSAEncryption',
    )


# ---------------------------------------------------------------------------
# _parse_cpanel_userdata
# ---------------------------------------------------------------------------

class TestParseCpanelUserdata:

    def test_parses_simple_key_value(self, tmp_path):
        f = tmp_path / "example.com"
        f.write_text("domain: example.com\ndocumentroot: /home/user/public_html\n")
        result = _parse_cpanel_userdata(str(f))
        assert result['domain'] == 'example.com'
        assert result['documentroot'] == '/home/user/public_html'

    def test_skips_blank_and_comment_lines(self, tmp_path):
        f = tmp_path / "data"
        f.write_text("# comment\n\ndomain: test.com\n")
        result = _parse_cpanel_userdata(str(f))
        assert result == {'domain': 'test.com'}

    def test_missing_file_returns_empty_dict(self):
        result = _parse_cpanel_userdata('/nonexistent/path/file')
        assert result == {}

    def test_skips_yaml_list_lines(self, tmp_path):
        f = tmp_path / "data"
        f.write_text("domain: site.com\n- list_item\ntype: addon\n")
        result = _parse_cpanel_userdata(str(f))
        assert result['domain'] == 'site.com'
        assert result['type'] == 'addon'
        assert '-' not in result


# ---------------------------------------------------------------------------
# _parse_main_domain_types (BACK-128)
# ---------------------------------------------------------------------------

class TestParseMainDomainTypes:

    def test_returns_empty_when_no_main_file(self, tmp_path):
        """Missing main file returns empty dict."""
        assert _parse_main_domain_types(str(tmp_path)) == {}

    def test_parses_main_domain(self, tmp_path):
        """main_domain scalar is detected."""
        (tmp_path / "main").write_text("main_domain: example.com\n")
        result = _parse_main_domain_types(str(tmp_path))
        assert result['example.com'] == 'main_domain'

    def test_parses_addon_domains(self, tmp_path):
        """addon_domains list items are detected."""
        (tmp_path / "main").write_text(
            "main_domain: example.com\n"
            "addon_domains:\n"
            "  - addon.io\n"
            "  - extra.net\n"
        )
        result = _parse_main_domain_types(str(tmp_path))
        assert result['addon.io'] == 'addon'
        assert result['extra.net'] == 'addon'

    def test_parses_parked_domains(self, tmp_path):
        """parked_domains list items are detected."""
        (tmp_path / "main").write_text(
            "main_domain: example.com\n"
            "parked_domains:\n"
            "  - alias.io\n"
        )
        result = _parse_main_domain_types(str(tmp_path))
        assert result['alias.io'] == 'parked'

    def test_parses_sub_domains(self, tmp_path):
        """sub_domains list items are detected."""
        (tmp_path / "main").write_text(
            "main_domain: example.com\n"
            "sub_domains:\n"
            "  - blog.example.com\n"
            "  - shop.example.com\n"
        )
        result = _parse_main_domain_types(str(tmp_path))
        assert result['blog.example.com'] == 'subdomain'
        assert result['shop.example.com'] == 'subdomain'

    def test_full_main_file(self, tmp_path):
        """A realistic main file with all domain types."""
        (tmp_path / "main").write_text(
            "main_domain: example.com\n"
            "addon_domains:\n"
            "  - addon.io\n"
            "sub_domains:\n"
            "  - blog.example.com\n"
            "  - shop.addon.io\n"
            "parked_domains:\n"
            "  - alias.com\n"
        )
        result = _parse_main_domain_types(str(tmp_path))
        assert result == {
            'example.com': 'main_domain',
            'addon.io': 'addon',
            'blog.example.com': 'subdomain',
            'shop.addon.io': 'subdomain',
            'alias.com': 'parked',
        }

    def test_empty_lists_handled(self, tmp_path):
        """main file with empty domain lists returns only main_domain."""
        (tmp_path / "main").write_text(
            "main_domain: example.com\n"
            "addon_domains:\n"
            "sub_domains:\n"
            "parked_domains:\n"
        )
        result = _parse_main_domain_types(str(tmp_path))
        assert result == {'example.com': 'main_domain'}

    def test_unknown_keys_ignored(self, tmp_path):
        """List items under unknown keys are not included."""
        (tmp_path / "main").write_text(
            "main_domain: example.com\n"
            "random_stuff:\n"
            "  - junk.io\n"
        )
        result = _parse_main_domain_types(str(tmp_path))
        assert 'junk.io' not in result


# ---------------------------------------------------------------------------
# _list_user_domains
# ---------------------------------------------------------------------------

class TestListUserDomains:

    def test_returns_empty_when_no_userdata_dir(self):
        with patch('os.path.isdir', return_value=False):
            result = _list_user_domains('nobody')
        assert result == []

    def test_skips_ssl_suffix_and_main_files(self, tmp_path):
        userdata = tmp_path / "myuser"
        userdata.mkdir()
        (userdata / "main").write_text("domain: myuser\n")
        (userdata / "example.com_SSL").write_text("domain: example.com\n")
        (userdata / "example.com").write_text("domain: example.com\ndocumentroot: /home/myuser/public_html\n")

        with patch('reveal.adapters.cpanel.adapter.CPANEL_USERDATA_DIR', str(tmp_path)):
            result = _list_user_domains('myuser')

        assert len(result) == 1
        assert result[0]['domain'] == 'example.com'

    def test_domain_type_addon_heuristic(self, tmp_path):
        userdata = tmp_path / "myuser"
        userdata.mkdir()
        (userdata / "addon.io").write_text("domain: addon.io\ndocumentroot: /home/myuser/addon.io\n")

        with patch('reveal.adapters.cpanel.adapter.CPANEL_USERDATA_DIR', str(tmp_path)):
            result = _list_user_domains('myuser')

        assert result[0]['type'] in ('addon', 'subdomain', 'main_domain', '')

    def test_subdomain_heuristic(self, tmp_path):
        userdata = tmp_path / "myuser"
        userdata.mkdir()
        (userdata / "sub.example.com").write_text(
            "domain: sub.example.com\ndocumentroot: /home/myuser/sub\n"
        )

        with patch('reveal.adapters.cpanel.adapter.CPANEL_USERDATA_DIR', str(tmp_path)):
            result = _list_user_domains('myuser')

        assert result[0]['domain'] == 'sub.example.com'
        assert result[0]['type'] == 'subdomain'

    def test_skips_artifact_extensions(self, tmp_path):
        """BACK-045: .cache/.yaml/.json files in userdata dir must not be treated as domains."""
        userdata = tmp_path / "myuser"
        userdata.mkdir()
        (userdata / "example.com").write_text("domain: example.com\ndocumentroot: /home/myuser/public_html\n")
        (userdata / "example.com.cache").write_text("some cache data\n")
        (userdata / "vhosts.yaml").write_text("some: yaml\n")
        (userdata / "config.json").write_text('{"key":"value"}\n')
        (userdata / "session.lock").write_text("")
        (userdata / "debug.log").write_text("log data\n")

        with patch('reveal.adapters.cpanel.adapter.CPANEL_USERDATA_DIR', str(tmp_path)):
            result = _list_user_domains('myuser')

        domains = [r['domain'] for r in result]
        assert len(result) == 1, f"Expected 1 domain, got {len(result)}: {domains}"
        assert 'example.com' in domains

    def test_skips_bak_extension(self, tmp_path):
        """BACK-045: .bak files in userdata dir must not be treated as domains."""
        userdata = tmp_path / "myuser"
        userdata.mkdir()
        (userdata / "example.com").write_text("domain: example.com\ndocumentroot: /home/myuser/public_html\n")
        (userdata / "example.com.bak").write_text("domain: old.example.com\n")

        with patch('reveal.adapters.cpanel.adapter.CPANEL_USERDATA_DIR', str(tmp_path)):
            result = _list_user_domains('myuser')

        assert len(result) == 1
        assert result[0]['domain'] == 'example.com'

    def test_parked_domain_from_main_file(self, tmp_path):
        """BACK-128: parked domains get authoritative type from main file."""
        userdata = tmp_path / "myuser"
        userdata.mkdir()
        (userdata / "main").write_text(
            "main_domain: example.com\n"
            "parked_domains:\n"
            "  - alias.io\n"
        )
        (userdata / "example.com").write_text("domain: example.com\ndocumentroot: /home/myuser/public_html\n")
        (userdata / "alias.io").write_text("domain: alias.io\ndocumentroot: /home/myuser/public_html\n")

        with patch('reveal.adapters.cpanel.adapter.CPANEL_USERDATA_DIR', str(tmp_path)):
            result = _list_user_domains('myuser')

        types = {d['domain']: d['type'] for d in result}
        assert types['example.com'] == 'main_domain'
        assert types['alias.io'] == 'parked'

    def test_addon_domain_from_main_file(self, tmp_path):
        """BACK-128: addon domains get authoritative type from main file."""
        userdata = tmp_path / "myuser"
        userdata.mkdir()
        (userdata / "main").write_text(
            "main_domain: example.com\n"
            "addon_domains:\n"
            "  - extra.net\n"
        )
        (userdata / "example.com").write_text("domain: example.com\ndocumentroot: /home/myuser/public_html\n")
        (userdata / "extra.net").write_text("domain: extra.net\ndocumentroot: /home/myuser/extra.net\n")

        with patch('reveal.adapters.cpanel.adapter.CPANEL_USERDATA_DIR', str(tmp_path)):
            result = _list_user_domains('myuser')

        types = {d['domain']: d['type'] for d in result}
        assert types['extra.net'] == 'addon'

    def test_heuristic_fallback_when_no_main_file(self, tmp_path):
        """Without a main file, heuristic still works."""
        userdata = tmp_path / "myuser"
        userdata.mkdir()
        # No main file
        (userdata / "sub.example.com").write_text("domain: sub.example.com\n")

        with patch('reveal.adapters.cpanel.adapter.CPANEL_USERDATA_DIR', str(tmp_path)):
            result = _list_user_domains('myuser')

        assert result[0]['type'] == 'subdomain'

    def test_mixed_authoritative_and_heuristic(self, tmp_path):
        """BACK-128: domains in main file get authoritative type, others get heuristic."""
        userdata = tmp_path / "myuser"
        userdata.mkdir()
        (userdata / "main").write_text(
            "main_domain: example.com\n"
            "addon_domains:\n"
            "  - addon.io\n"
        )
        (userdata / "example.com").write_text("domain: example.com\ndocumentroot: /home/myuser/public_html\n")
        (userdata / "addon.io").write_text("domain: addon.io\ndocumentroot: /home/myuser/addon.io\n")
        (userdata / "sub.example.com").write_text("domain: sub.example.com\ndocumentroot: /home/myuser/sub\n")

        with patch('reveal.adapters.cpanel.adapter.CPANEL_USERDATA_DIR', str(tmp_path)):
            result = _list_user_domains('myuser')

        types = {d['domain']: d['type'] for d in result}
        assert types['example.com'] == 'main_domain'  # authoritative
        assert types['addon.io'] == 'addon'            # authoritative
        assert types['sub.example.com'] == 'subdomain' # heuristic fallback


# ---------------------------------------------------------------------------
# _get_disk_cert_status
# ---------------------------------------------------------------------------

class TestGetDiskCertStatus:

    def test_missing_cert_file(self):
        with patch('os.path.exists', return_value=False):
            r = _get_disk_cert_status('missing.example.com')
        assert r['status'] == 'missing'

    def test_ok_cert(self):
        cert = _make_cert(days=90)
        with patch('os.path.exists', return_value=True), \
             patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   return_value=(cert, [])):
            r = _get_disk_cert_status('ok.example.com')
        assert r['status'] == 'ok'
        assert r['days_until_expiry'] >= 89

    def test_expiring_cert(self):
        cert = _make_cert(days=15)
        with patch('os.path.exists', return_value=True), \
             patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   return_value=(cert, [])):
            r = _get_disk_cert_status('expiring.example.com')
        assert r['status'] == 'expiring'

    def test_critical_cert(self):
        cert = _make_cert(days=3)
        with patch('os.path.exists', return_value=True), \
             patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   return_value=(cert, [])):
            r = _get_disk_cert_status('critical.example.com')
        assert r['status'] == 'critical'

    def test_expired_cert(self):
        cert = _make_cert(days=-5)
        with patch('os.path.exists', return_value=True), \
             patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   return_value=(cert, [])):
            r = _get_disk_cert_status('expired.example.com')
        assert r['status'] == 'expired'

    def test_load_error_returns_error_status(self):
        with patch('os.path.exists', return_value=True), \
             patch('reveal.adapters.ssl.certificate.load_certificate_from_file',
                   side_effect=ValueError("Bad cert")):
            r = _get_disk_cert_status('bad.example.com')
        assert r['status'] == 'error'
        assert 'Bad cert' in r['error']


# ---------------------------------------------------------------------------
# CpanelAdapter — URI parsing
# ---------------------------------------------------------------------------

class TestCpanelAdapterParsing:

    def test_no_arg_raises_type_error(self):
        with pytest.raises(TypeError):
            CpanelAdapter()

    def test_empty_string_raises_type_error(self):
        with pytest.raises(TypeError):
            CpanelAdapter('')

    def test_parses_username(self):
        a = CpanelAdapter('cpanel://myuser')
        assert a.username == 'myuser'
        assert a.element is None

    def test_parses_element(self):
        a = CpanelAdapter('cpanel://myuser/ssl')
        assert a.username == 'myuser'
        assert a.element == 'ssl'

    def test_parses_acl_check_element(self):
        a = CpanelAdapter('cpanel://myuser/acl-check')
        assert a.element == 'acl-check'

    def test_parses_domains_element(self):
        a = CpanelAdapter('cpanel://myuser/domains')
        assert a.element == 'domains'

    def test_unknown_element_raises(self):
        a = CpanelAdapter('cpanel://myuser/unknown-thing')
        with pytest.raises(ValueError, match='Unknown cpanel://'):
            a.get_structure()

    def test_missing_username_raises(self):
        with pytest.raises(ValueError, match='username'):
            CpanelAdapter('cpanel://')


# ---------------------------------------------------------------------------
# CpanelAdapter — get_structure
# ---------------------------------------------------------------------------

class TestCpanelAdapterGetStructure:

    def _make_domains(self):
        return [
            {'domain': 'alpha.com', 'docroot': '/home/u/public_html', 'serveralias': '', 'type': 'main_domain'},
            {'domain': 'beta.com', 'docroot': '/home/u/beta', 'serveralias': '', 'type': 'addon'},
        ]

    def test_overview_returns_cpanel_user_type(self):
        adapter = CpanelAdapter('cpanel://testuser')
        with patch.object(adapter, '_get_domains', return_value=self._make_domains()), \
             patch('os.path.exists', return_value=False), \
             patch('os.path.isdir', return_value=True), \
             patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                   return_value={'status': 'ok'}):
            r = adapter.get_structure()
        assert r['type'] == 'cpanel_user'
        assert r['username'] == 'testuser'
        assert r['domain_count'] == 2

    def test_domains_element_returns_cpanel_domains_type(self):
        adapter = CpanelAdapter('cpanel://testuser/domains')
        with patch.object(adapter, '_get_domains', return_value=self._make_domains()):
            r = adapter.get_structure()
        assert r['type'] == 'cpanel_domains'
        assert len(r['domains']) == 2

    def test_ssl_element_returns_cpanel_ssl_type(self):
        adapter = CpanelAdapter('cpanel://testuser/ssl')
        cert = _make_cert(days=60)
        disk_status = {'status': 'ok', 'days_until_expiry': 60,
                       'not_after': '2026-04-30', 'serial_number': 'S1', 'common_name': 'alpha.com'}
        with patch.object(adapter, '_get_domains', return_value=self._make_domains()), \
             patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                   return_value=disk_status):
            r = adapter.get_structure()
        assert r['type'] == 'cpanel_ssl'
        assert r['cert_count'] == 2

    def test_acl_element_returns_cpanel_acl_type(self):
        adapter = CpanelAdapter('cpanel://testuser/acl-check')
        acl_ok = {'status': 'ok', 'path': '/home/u/public_html', 'checks': []}
        with patch.object(adapter, '_get_domains', return_value=self._make_domains()), \
             patch('reveal.adapters.cpanel.adapter._check_docroot_acl', return_value=acl_ok):
            r = adapter.get_structure()
        assert r['type'] == 'cpanel_acl'
        assert r['domain_count'] == 2

    def test_acl_has_failures_when_denied(self):
        adapter = CpanelAdapter('cpanel://testuser/acl-check')
        acl_denied = {'status': 'denied', 'path': '/home/u/beta'}
        with patch.object(adapter, '_get_domains', return_value=[
            {'domain': 'beta.com', 'docroot': '/home/u/beta', 'serveralias': '', 'type': 'addon'}
        ]), patch('reveal.adapters.cpanel.adapter._check_docroot_acl', return_value=acl_denied):
            r = adapter.get_structure()
        assert r['has_failures'] is True

    def test_ssl_sorted_failures_first(self):
        adapter = CpanelAdapter('cpanel://testuser/ssl')
        domains = [
            {'domain': 'ok.com', 'docroot': '/h/ok', 'serveralias': '', 'type': 'addon'},
            {'domain': 'expired.com', 'docroot': '/h/ex', 'serveralias': '', 'type': 'addon'},
        ]

        def fake_disk_status(domain):
            if domain == 'expired.com':
                return {'status': 'expired', 'days_until_expiry': -10, 'not_after': '2026-01-01',
                        'serial_number': 'OLD', 'common_name': 'expired.com'}
            return {'status': 'ok', 'days_until_expiry': 80, 'not_after': '2026-05-01',
                    'serial_number': 'NEW', 'common_name': 'ok.com'}

        with patch.object(adapter, '_get_domains', return_value=domains), \
             patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                   side_effect=lambda d: fake_disk_status(d)):
            r = adapter.get_structure()
        # expired should sort first
        assert r['certs'][0]['domain'] == 'expired.com'

    def test_ssl_cert_entries_include_domain_type(self):
        adapter = CpanelAdapter('cpanel://testuser/ssl')
        domains = [
            {'domain': 'main.com', 'docroot': '/h/m', 'serveralias': '', 'type': 'main_domain'},
            {'domain': 'sub.main.com', 'docroot': '/h/s', 'serveralias': '', 'type': 'subdomain'},
        ]
        disk_status = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-04-30',
                       'serial_number': 'S1', 'common_name': 'main.com'}
        with patch.object(adapter, '_get_domains', return_value=domains), \
             patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                   return_value=disk_status):
            r = adapter.get_structure()
        domain_types = {c['domain']: c['domain_type'] for c in r['certs']}
        assert domain_types['main.com'] == 'main_domain'
        assert domain_types['sub.main.com'] == 'subdomain'


# ---------------------------------------------------------------------------
# CpanelRenderer
# ---------------------------------------------------------------------------

class TestCpanelRenderer:

    def test_render_overview_prints_username(self, capsys):
        result = {
            'type': 'cpanel_user', 'username': 'myuser',
            'userdata_dir': '/var/cpanel/userdata/myuser',
            'userdata_accessible': True,
            'domain_count': 3,
            'nginx_config': '/etc/nginx/conf.d/users/myuser.conf',
            'ssl_summary': {'ok': 2, 'expired': 1},
            'next_steps': ['reveal cpanel://myuser/ssl'],
        }
        CpanelRenderer.render_structure(result, format='text')
        out = capsys.readouterr().out
        assert 'myuser' in out
        assert 'domains: 3' in out

    def test_render_ssl_shows_cert_status(self, capsys):
        result = {
            'type': 'cpanel_ssl', 'username': 'myuser',
            'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': 1,
            'summary': {'ok': 1},
            'certs': [{'domain': 'alpha.com', 'status': 'ok',
                       'days_until_expiry': 60, 'not_after': '2026-04-30',
                       'serial_number': 'S1'}],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, format='text')
        out = capsys.readouterr().out
        assert 'alpha.com' in out
        assert '60' in out

    def test_render_ssl_expired_subdomain_breakdown(self, capsys):
        result = {
            'type': 'cpanel_ssl', 'username': 'myuser',
            'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': 3,
            'summary': {'expired': 3},
            'dns_verified': False,
            'dns_excluded': {},
            'certs': [
                {'domain': 'old.com', 'status': 'expired', 'domain_type': 'main_domain',
                 'days_until_expiry': -10, 'not_after': '2026-01-01'},
                {'domain': 'sub1.old.com', 'status': 'expired', 'domain_type': 'subdomain',
                 'days_until_expiry': -5, 'not_after': '2026-01-01'},
                {'domain': 'sub2.old.com', 'status': 'expired', 'domain_type': 'parked',
                 'days_until_expiry': -3, 'not_after': '2026-01-01'},
            ],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, format='text')
        out = capsys.readouterr().out
        assert '3 expired (2 subdomain/parked)' in out

    def test_render_acl_shows_denied(self, capsys):
        result = {
            'type': 'cpanel_acl', 'username': 'myuser',
            'domain_count': 1,
            'summary': {'denied': 1},
            'has_failures': True,
            'domains': [{'domain': 'bad.com', 'docroot': '/home/u/bad',
                         'acl_status': 'denied', 'acl_detail': {}}],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, format='text')
        out = capsys.readouterr().out
        assert 'bad.com' in out
        assert 'denied' in out.lower()
        assert 'ACL failures' in out

    def test_render_json_format_produces_valid_json(self, capsys):
        result = {'type': 'cpanel_user', 'username': 'u', 'domain_count': 0}
        CpanelRenderer.render_structure(result, format='json')
        out = capsys.readouterr().out
        import json
        parsed = json.loads(out)
        assert parsed['username'] == 'u'


class TestCpanelSslDnsVerified:
    """U6 — cpanel://USERNAME/ssl --dns-verified excludes NXDOMAIN domains from summary counts."""

    def _make_adapter(self):
        return CpanelAdapter('cpanel://testuser/ssl')

    def _disk_status_ok(self, domain):
        from datetime import datetime, timezone, timedelta
        return {
            'status': 'ok',
            'days_until_expiry': 60,
            'not_after': (datetime.now(timezone.utc) + timedelta(days=60)).strftime('%Y-%m-%d'),
            'serial_number': 'AA',
            'cert_path': f'/var/cpanel/ssl/apache_tls/{domain}/combined',
        }

    def _disk_status_critical(self, domain):
        from datetime import datetime, timezone, timedelta
        return {
            'status': 'critical',
            'days_until_expiry': 5,
            'not_after': (datetime.now(timezone.utc) + timedelta(days=5)).strftime('%Y-%m-%d'),
            'serial_number': 'BB',
            'cert_path': f'/var/cpanel/ssl/apache_tls/{domain}/combined',
        }

    def test_without_dns_verified_no_dns_status_field(self):
        """Without --dns-verified, certs have no dns_resolves field."""
        adapter = self._make_adapter()
        domains = [{'domain': 'active.example.com', 'docroot': '/home/u/public_html'}]
        with patch('reveal.adapters.cpanel.adapter._list_user_domains', return_value=domains), \
             patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                   side_effect=self._disk_status_ok):
            result = adapter.get_structure(dns_verified=False)
        assert result['dns_verified'] is False
        assert 'dns_resolves' not in result['certs'][0]

    def test_dns_verified_resolving_domain_in_summary(self):
        """Domains that resolve to local IPs are counted normally in summary."""
        adapter = self._make_adapter()
        domains = [{'domain': 'live.example.com', 'docroot': '/home/u/public_html'}]
        with patch('reveal.adapters.cpanel.adapter._list_user_domains', return_value=domains), \
             patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                   side_effect=self._disk_status_critical), \
             patch('reveal.adapters.cpanel.adapter._dns_resolve_ips', return_value=['1.2.3.4']), \
             patch('reveal.adapters.cpanel.adapter._get_local_ips', return_value={'1.2.3.4'}):
            result = adapter.get_structure(dns_verified=True)
        assert result['summary'].get('critical', 0) == 1
        assert sum(result['dns_excluded'].values()) == 0
        assert result['certs'][0]['dns_resolves'] is True
        assert result['certs'][0]['dns_points_here'] is True

    def test_dns_verified_nxdomain_excluded_from_summary(self):
        """NXDOMAIN domains are excluded from critical/expiring summary counts."""
        adapter = self._make_adapter()
        domains = [
            {'domain': 'dead.example.com', 'docroot': '/home/u/dead'},
            {'domain': 'live.example.com', 'docroot': '/home/u/live'},
        ]

        def disk_status(domain):
            return self._disk_status_critical(domain)

        def resolve_ips(domain):
            return ['1.2.3.4'] if domain == 'live.example.com' else []

        with patch('reveal.adapters.cpanel.adapter._list_user_domains', return_value=domains), \
             patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                   side_effect=disk_status), \
             patch('reveal.adapters.cpanel.adapter._dns_resolve_ips', side_effect=resolve_ips), \
             patch('reveal.adapters.cpanel.adapter._get_local_ips', return_value={'1.2.3.4'}):
            result = adapter.get_structure(dns_verified=True)

        # live domain is critical and resolves to this server → in summary
        assert result['summary'].get('critical', 0) == 1
        # dead domain is critical but NXDOMAIN → in dns_excluded, not summary
        assert result['dns_excluded'].get('critical', 0) == 1
        # certs show dns_resolves field
        cert_map = {c['domain']: c for c in result['certs']}
        assert cert_map['dead.example.com']['dns_resolves'] is False
        assert cert_map['live.example.com']['dns_resolves'] is True

    def test_dns_excluded_shown_in_renderer_output(self, capsys):
        """Renderer shows nxdomain-excluded count in summary line."""
        from reveal.adapters.cpanel.renderer import CpanelRenderer
        from datetime import datetime, timezone, timedelta
        result = {
            'type': 'cpanel_ssl',
            'username': 'testuser',
            'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': 2,
            'dns_verified': True,
            'only_failures': False,
            'domain_type_filter': None,
            'summary': {'critical': 1},
            'dns_excluded': {'critical': 2},
            'dns_elsewhere': {},
            'certs': [
                {
                    'domain': 'live.example.com',
                    'status': 'critical',
                    'days_until_expiry': 5,
                    'not_after': '2026-03-04',
                    'dns_resolves': True,
                    'dns_points_here': True,
                },
                {
                    'domain': 'dead1.example.com',
                    'status': 'critical',
                    'days_until_expiry': 3,
                    'not_after': '2026-03-02',
                    'dns_resolves': False,
                },
            ],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, format='text')
        out = capsys.readouterr().out
        assert 'nxdomain-excluded' in out
        assert '2 critical' in out or 'critical: 2' in out or '2' in out
        assert '[nxdomain]' in out
        assert 'dead1.example.com' in out
        assert 'live.example.com' in out


class TestCpanelSslOnlyFailures:
    """--only-failures for cpanel://user/ssl hides ok certs."""

    def _make_adapter(self):
        return CpanelAdapter('cpanel://testuser/ssl')

    def _domains(self):
        return [
            {'domain': 'ok.com', 'docroot': '/h/ok', 'serveralias': '', 'type': 'addon'},
            {'domain': 'expired.com', 'docroot': '/h/ex', 'serveralias': '', 'type': 'main_domain'},
        ]

    def _disk_status(self, domain):
        if domain == 'expired.com':
            return {'status': 'expired', 'days_until_expiry': -5, 'not_after': '2026-01-01',
                    'serial_number': 'OLD', 'common_name': 'expired.com'}
        return {'status': 'ok', 'days_until_expiry': 80, 'not_after': '2026-06-01',
                'serial_number': 'NEW', 'common_name': 'ok.com'}

    def test_only_failures_true_sets_flag_in_result(self):
        adapter = self._make_adapter()
        with patch.object(adapter, '_get_domains', return_value=self._domains()), \
             patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                   side_effect=self._disk_status):
            r = adapter.get_structure(only_failures=True)
        assert r['only_failures'] is True

    def test_only_failures_false_sets_flag_in_result(self):
        adapter = self._make_adapter()
        with patch.object(adapter, '_get_domains', return_value=self._domains()), \
             patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                   side_effect=self._disk_status):
            r = adapter.get_structure(only_failures=False)
        assert r['only_failures'] is False

    def test_renderer_hides_ok_certs_when_only_failures(self, capsys):
        result = {
            'type': 'cpanel_ssl', 'username': 'testuser',
            'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': 2,
            'only_failures': True,
            'dns_verified': False,
            'dns_excluded': {},
            'summary': {'ok': 1, 'expired': 1},
            'certs': [
                {'domain': 'expired.com', 'status': 'expired', 'domain_type': 'main_domain',
                 'days_until_expiry': -5, 'not_after': '2026-01-01'},
                {'domain': 'ok.com', 'status': 'ok', 'domain_type': 'addon',
                 'days_until_expiry': 80, 'not_after': '2026-06-01'},
            ],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, format='text')
        out = capsys.readouterr().out
        assert 'expired.com' in out
        assert 'ok.com' not in out

    def test_renderer_shows_all_certs_without_only_failures(self, capsys):
        result = {
            'type': 'cpanel_ssl', 'username': 'testuser',
            'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': 2,
            'only_failures': False,
            'dns_verified': False,
            'dns_excluded': {},
            'summary': {'ok': 1, 'expired': 1},
            'certs': [
                {'domain': 'expired.com', 'status': 'expired', 'domain_type': 'main_domain',
                 'days_until_expiry': -5, 'not_after': '2026-01-01'},
                {'domain': 'ok.com', 'status': 'ok', 'domain_type': 'addon',
                 'days_until_expiry': 80, 'not_after': '2026-06-01'},
            ],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, format='text')
        out = capsys.readouterr().out
        assert 'expired.com' in out
        assert 'ok.com' in out

    def test_renderer_prints_clean_message_when_all_pass(self, capsys):
        result = {
            'type': 'cpanel_ssl', 'username': 'testuser',
            'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': 1,
            'only_failures': True,
            'dns_verified': False,
            'dns_excluded': {},
            'summary': {'ok': 1},
            'certs': [
                {'domain': 'ok.com', 'status': 'ok', 'domain_type': 'addon',
                 'days_until_expiry': 80, 'not_after': '2026-06-01'},
            ],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, format='text')
        out = capsys.readouterr().out
        assert '✅' in out or 'No failures' in out
        assert 'ok.com' not in out


# ---------------------------------------------------------------------------
# acl-check --only-failures
# ---------------------------------------------------------------------------

class TestCpanelAclOnlyFailures:
    """--only-failures for cpanel://user/acl-check hides ok domains."""

    def _make_domains(self):
        return [
            {'domain': 'ok.com', 'docroot': '/home/u/ok', 'serveralias': '', 'type': 'main_domain'},
            {'domain': 'bad.com', 'docroot': '/home/u/bad', 'serveralias': '', 'type': 'addon'},
        ]

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    def test_only_failures_flag_stored_in_result(self, mock_acl, mock_domains):
        mock_domains.return_value = self._make_domains()
        mock_acl.return_value = {'status': 'ok'}
        a = CpanelAdapter('cpanel://u/acl-check')
        result = a.get_structure(only_failures=True)
        assert result['only_failures'] is True

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    def test_only_failures_false_stored_in_result(self, mock_acl, mock_domains):
        mock_domains.return_value = self._make_domains()
        mock_acl.return_value = {'status': 'ok'}
        a = CpanelAdapter('cpanel://u/acl-check')
        result = a.get_structure(only_failures=False)
        assert result['only_failures'] is False

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    def test_renderer_hides_ok_domains_when_only_failures(self, mock_acl, mock_domains, capsys):
        mock_domains.return_value = self._make_domains()
        def acl(path):
            return {'status': 'denied' if 'bad' in path else 'ok'}
        mock_acl.side_effect = acl
        a = CpanelAdapter('cpanel://u/acl-check')
        result = a.get_structure(only_failures=True)
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'bad.com' in out
        assert 'ok.com' not in out

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    def test_renderer_shows_clean_message_when_no_failures(self, mock_acl, mock_domains, capsys):
        mock_domains.return_value = self._make_domains()
        mock_acl.return_value = {'status': 'ok'}
        a = CpanelAdapter('cpanel://u/acl-check')
        result = a.get_structure(only_failures=True)
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'No ACL failures' in out

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    def test_renderer_shows_all_domains_without_only_failures(self, mock_acl, mock_domains, capsys):
        mock_domains.return_value = self._make_domains()
        mock_acl.return_value = {'status': 'ok'}
        a = CpanelAdapter('cpanel://u/acl-check')
        result = a.get_structure(only_failures=False)
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'ok.com' in out
        assert 'bad.com' in out


# ---------------------------------------------------------------------------
# U6 follow-on: IP-match verification (dns_points_here)
# ---------------------------------------------------------------------------

class TestCpanelDnsIpMatch:
    """--dns-verified annotates dns_points_here and excludes elsewhere domains."""

    def _make_adapter(self):
        return CpanelAdapter('cpanel://testuser/ssl')

    def _disk_status_critical(self, domain):
        return {'status': 'critical', 'days_until_expiry': 5, 'not_after': '2026-03-18',
                'cert_path': f'/var/cpanel/ssl/apache_tls/{domain}/combined'}

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._dns_resolve_ips')
    @patch('reveal.adapters.cpanel.adapter._get_local_ips')
    def test_dns_points_here_true_when_ip_matches(self, mock_local, mock_ips,
                                                    mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'here.com', 'docroot': '/home/u', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.side_effect = self._disk_status_critical
        mock_ips.return_value = ['1.2.3.4']
        mock_local.return_value = {'1.2.3.4', '5.6.7.8'}
        result = self._make_adapter().get_structure(dns_verified=True)
        assert result['certs'][0]['dns_points_here'] is True
        assert result['certs'][0]['dns_resolves'] is True

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._dns_resolve_ips')
    @patch('reveal.adapters.cpanel.adapter._get_local_ips')
    def test_dns_points_here_false_when_ip_differs(self, mock_local, mock_ips,
                                                     mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'elsewhere.com', 'docroot': '/home/u', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.side_effect = self._disk_status_critical
        mock_ips.return_value = ['9.9.9.9']
        mock_local.return_value = {'1.2.3.4'}
        result = self._make_adapter().get_structure(dns_verified=True)
        assert result['certs'][0]['dns_points_here'] is False
        assert result['certs'][0]['dns_resolves'] is True

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._dns_resolve_ips')
    @patch('reveal.adapters.cpanel.adapter._get_local_ips')
    def test_elsewhere_domain_excluded_from_summary(self, mock_local, mock_ips,
                                                      mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'here.com', 'docroot': '/home/u/here', 'serveralias': '', 'type': 'main_domain'},
            {'domain': 'there.com', 'docroot': '/home/u/there', 'serveralias': '', 'type': 'addon'},
        ]
        mock_status.side_effect = self._disk_status_critical
        def resolve(domain):
            return ['1.2.3.4'] if domain == 'here.com' else ['9.9.9.9']
        mock_ips.side_effect = resolve
        mock_local.return_value = {'1.2.3.4'}
        result = self._make_adapter().get_structure(dns_verified=True)
        # here.com points here → in summary
        assert result['summary'].get('critical', 0) == 1
        # there.com points elsewhere → in dns_elsewhere, not summary
        assert result['dns_elsewhere'].get('critical', 0) == 1

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._dns_resolve_ips')
    @patch('reveal.adapters.cpanel.adapter._get_local_ips')
    def test_nxdomain_and_elsewhere_both_excluded(self, mock_local, mock_ips,
                                                    mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'here.com', 'docroot': '/home', 'serveralias': '', 'type': 'main_domain'},
            {'domain': 'dead.com', 'docroot': '/home', 'serveralias': '', 'type': 'addon'},
            {'domain': 'there.com', 'docroot': '/home', 'serveralias': '', 'type': 'subdomain'},
        ]
        mock_status.side_effect = self._disk_status_critical
        def resolve(domain):
            if domain == 'dead.com':
                return []
            if domain == 'there.com':
                return ['9.9.9.9']
            return ['1.2.3.4']
        mock_ips.side_effect = resolve
        mock_local.return_value = {'1.2.3.4'}
        result = self._make_adapter().get_structure(dns_verified=True)
        assert result['summary'].get('critical', 0) == 1      # only here.com
        assert result['dns_excluded'].get('critical', 0) == 1  # dead.com
        assert result['dns_elsewhere'].get('critical', 0) == 1  # there.com

    def test_renderer_shows_elsewhere_tag(self, capsys):
        result = {
            'type': 'cpanel_ssl', 'username': 'u', 'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': 1, 'dns_verified': True, 'only_failures': False,
            'domain_type_filter': None,
            'summary': {}, 'dns_excluded': {}, 'dns_elsewhere': {'critical': 1},
            'certs': [{'domain': 'there.com', 'domain_type': 'main_domain',
                        'status': 'critical', 'days_until_expiry': 5,
                        'not_after': '2026-03-18', 'dns_resolves': True,
                        'dns_points_here': False}],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert '[→ elsewhere]' in out
        assert 'elsewhere-excluded' in out

    def test_renderer_no_elsewhere_tag_when_points_here(self, capsys):
        result = {
            'type': 'cpanel_ssl', 'username': 'u', 'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': 1, 'dns_verified': True, 'only_failures': False,
            'domain_type_filter': None,
            'summary': {'critical': 1}, 'dns_excluded': {}, 'dns_elsewhere': {},
            'certs': [{'domain': 'here.com', 'domain_type': 'main_domain',
                        'status': 'critical', 'days_until_expiry': 5,
                        'not_after': '2026-03-18', 'dns_resolves': True,
                        'dns_points_here': True}],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert '[→ elsewhere]' not in out
        assert '[nxdomain]' not in out


# ---------------------------------------------------------------------------
# URI query param filtering (?domain_type=...)
# ---------------------------------------------------------------------------

class TestCpanelUriQueryParams:
    """_parse_connection_string handles ?key=value query params."""

    def test_parses_query_param_domain_type(self):
        a = CpanelAdapter('cpanel://myuser/ssl?domain_type=main_domain')
        assert a.element == 'ssl'
        assert a.query_params == {'domain_type': 'main_domain'}

    def test_no_query_params_empty_dict(self):
        a = CpanelAdapter('cpanel://myuser/ssl')
        assert a.query_params == {}

    def test_query_params_multiple_keys(self):
        a = CpanelAdapter('cpanel://myuser/ssl?domain_type=addon&foo=bar')
        assert a.query_params['domain_type'] == 'addon'
        assert a.query_params['foo'] == 'bar'

    def test_element_without_query_still_parses(self):
        a = CpanelAdapter('cpanel://myuser/acl-check')
        assert a.element == 'acl-check'
        assert a.query_params == {}

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    def test_domain_type_filter_applied_in_ssl_structure(self, mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'main.com', 'docroot': '/home/u/main', 'serveralias': '', 'type': 'main_domain'},
            {'domain': 'sub.main.com', 'docroot': '/home/u/sub', 'serveralias': '', 'type': 'subdomain'},
            {'domain': 'addon.com', 'docroot': '/home/u/addon', 'serveralias': '', 'type': 'addon'},
        ]
        mock_status.return_value = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/main.com/combined'}
        a = CpanelAdapter('cpanel://myuser/ssl?domain_type=main_domain')
        result = a.get_structure()
        domains_in_result = [c['domain'] for c in result['certs']]
        assert domains_in_result == ['main.com']

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    def test_domain_type_filter_subdomain(self, mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'main.com', 'docroot': '/home/u', 'serveralias': '', 'type': 'main_domain'},
            {'domain': 'sub.main.com', 'docroot': '/home/u/sub', 'serveralias': '', 'type': 'subdomain'},
        ]
        mock_status.return_value = {'status': 'expired', 'days_until_expiry': -5, 'not_after': '2026-01-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/sub.main.com/combined'}
        a = CpanelAdapter('cpanel://myuser/ssl?domain_type=subdomain')
        result = a.get_structure()
        assert all(c['domain_type'] == 'subdomain' for c in result['certs'])
        assert result['domain_type_filter'] == 'subdomain'

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    def test_no_filter_returns_all_domains(self, mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'main.com', 'docroot': '/home/u', 'serveralias': '', 'type': 'main_domain'},
            {'domain': 'sub.main.com', 'docroot': '/home/u/sub', 'serveralias': '', 'type': 'subdomain'},
        ]
        mock_status.return_value = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/main.com/combined'}
        a = CpanelAdapter('cpanel://myuser/ssl')
        result = a.get_structure()
        assert len(result['certs']) == 2
        assert result['domain_type_filter'] is None

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    def test_domain_type_filter_unknown_type_returns_empty(self, mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'main.com', 'docroot': '/home/u', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.return_value = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/main.com/combined'}
        a = CpanelAdapter('cpanel://myuser/ssl?domain_type=parked')
        result = a.get_structure()
        assert result['certs'] == []

    def test_query_param_dns_verified_parsed(self):
        """?dns-verified in URI is stored in query_params."""
        a = CpanelAdapter('cpanel://myuser/ssl?dns-verified')
        assert a.query_params.get('dns-verified') is True

    def test_query_param_check_live_parsed(self):
        """?check-live in URI is stored in query_params."""
        a = CpanelAdapter('cpanel://myuser/ssl?check-live')
        assert a.query_params.get('check-live') is True

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._dns_resolve_ips')
    def test_dns_verified_from_uri_query_param(self, mock_resolve, mock_status, mock_domains):
        """?dns-verified in URI enables dns_verified without CLI flag."""
        mock_domains.return_value = [
            {'domain': 'main.com', 'docroot': '/home/u', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.return_value = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/main.com/combined'}
        mock_resolve.return_value = ['1.2.3.4']
        a = CpanelAdapter('cpanel://myuser/ssl?dns-verified')
        result = a.get_structure()  # no dns_verified=True arg — comes from URI
        assert result['dns_verified'] is True

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._dns_resolve_ips')
    def test_dns_verified_uri_param_activates_from_false_kwarg(self, mock_resolve, mock_status, mock_domains):
        """?dns-verified in URI activates dns_verified even when kwarg is False (OR semantics)."""
        mock_domains.return_value = [
            {'domain': 'main.com', 'docroot': '/home/u', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.return_value = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/main.com/combined'}
        mock_resolve.return_value = ['1.2.3.4']
        a = CpanelAdapter('cpanel://myuser/ssl?dns-verified')
        result = a.get_structure(dns_verified=False)  # URI param wins via OR
        assert result['dns_verified'] is True


# ---------------------------------------------------------------------------
# full-audit element
# ---------------------------------------------------------------------------

def _make_ssl_result(username='myuser', certs=None):
    certs = certs or [{'domain': 'ok.com', 'domain_type': 'main_domain',
                        'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                        'cert_path': '/etc/cpanel/ssl/installed/ok.com/combined'}]
    return {
        'contract_version': '1.0', 'type': 'cpanel_ssl', 'username': username,
        'cpanel_ssl_dir': CPANEL_SSL_DIR, 'cert_count': len(certs),
        'dns_verified': False, 'only_failures': False, 'domain_type_filter': None,
        'summary': {'ok': len(certs)}, 'dns_excluded': {}, 'dns_elsewhere': {}, 'certs': certs,
        'next_steps': [],
    }


def _make_acl_result(username='myuser', has_failures=False):
    domains = [{'domain': 'ok.com', 'docroot': '/home/u/public_html',
                'acl_status': 'ok' if not has_failures else 'denied', 'acl_detail': {}}]
    return {
        'contract_version': '1.0', 'type': 'cpanel_acl', 'username': username,
        'domain_count': 1, 'summary': {'ok': 1}, 'has_failures': has_failures,
        'domains': domains, 'next_steps': [],
    }


class TestCpanelFullAudit:

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    @patch('os.path.exists', return_value=False)
    def test_full_audit_returns_correct_type(self, mock_exists, mock_acl,
                                              mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'ok.com', 'docroot': '/home/u/public_html', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.return_value = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/ok.com/combined'}
        mock_acl.return_value = {'status': 'ok'}
        a = CpanelAdapter('cpanel://myuser/full-audit')
        result = a.get_structure()
        assert result['type'] == 'cpanel_full_audit'
        assert result['username'] == 'myuser'

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    @patch('os.path.exists', return_value=False)
    def test_full_audit_all_ok_has_failures_false(self, mock_exists, mock_acl,
                                                   mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'ok.com', 'docroot': '/home/u/public_html', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.return_value = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/ok.com/combined'}
        mock_acl.return_value = {'status': 'ok'}
        a = CpanelAdapter('cpanel://myuser/full-audit')
        result = a.get_structure()
        assert result['has_failures'] is False

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    @patch('os.path.exists', return_value=False)
    def test_full_audit_ssl_failure_sets_has_failures(self, mock_exists, mock_acl,
                                                       mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'bad.com', 'docroot': '/home/u/public_html', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.return_value = {'status': 'expired', 'days_until_expiry': -10,
                                    'not_after': '2026-01-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/bad.com/combined'}
        mock_acl.return_value = {'status': 'ok'}
        a = CpanelAdapter('cpanel://myuser/full-audit')
        result = a.get_structure()
        assert result['has_failures'] is True

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    @patch('os.path.exists', return_value=False)
    def test_full_audit_acl_failure_sets_has_failures(self, mock_exists, mock_acl,
                                                       mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'ok.com', 'docroot': '/home/u/restricted', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.return_value = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/ok.com/combined'}
        mock_acl.return_value = {'status': 'denied'}
        a = CpanelAdapter('cpanel://myuser/full-audit')
        result = a.get_structure()
        assert result['has_failures'] is True

    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    @patch('os.path.exists', return_value=False)
    def test_full_audit_nginx_none_when_no_conf(self, mock_exists, mock_acl,
                                                mock_status, mock_domains):
        mock_domains.return_value = [
            {'domain': 'ok.com', 'docroot': '/home/u/public_html', 'serveralias': '', 'type': 'main_domain'},
        ]
        mock_status.return_value = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                                    'cert_path': '/etc/cpanel/ssl/installed/ok.com/combined'}
        mock_acl.return_value = {'status': 'ok'}
        a = CpanelAdapter('cpanel://myuser/full-audit')
        result = a.get_structure()
        assert result['nginx'] is None

    def test_full_audit_renderer_all_ok(self, capsys):
        result = {
            'type': 'cpanel_full_audit', 'username': 'myuser', 'has_failures': False,
            'ssl': _make_ssl_result(),
            'acl': _make_acl_result(),
            'nginx': None,
        }
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'Full audit: myuser' in out
        assert '✅' in out
        assert 'Audit complete' in out

    def test_full_audit_renderer_exits_2_on_failures(self, capsys):
        result = {
            'type': 'cpanel_full_audit', 'username': 'myuser', 'has_failures': True,
            'ssl': _make_ssl_result(certs=[{
                'domain': 'bad.com', 'domain_type': 'main_domain',
                'status': 'expired', 'days_until_expiry': -10, 'not_after': '2026-01-01',
                'cert_path': '/etc/cpanel/ssl/installed/bad.com/combined',
            }]),
            'acl': _make_acl_result(),
            'nginx': None,
        }
        with pytest.raises(SystemExit) as exc_info:
            CpanelRenderer.render_structure(result, 'text')
        assert exc_info.value.code == 2

    def test_full_audit_renderer_json_exits_2_on_failures(self, capsys):
        result = {
            'type': 'cpanel_full_audit', 'username': 'myuser', 'has_failures': True,
            'ssl': _make_ssl_result(), 'acl': _make_acl_result(), 'nginx': None,
        }
        with pytest.raises(SystemExit) as exc_info:
            CpanelRenderer.render_structure(result, 'json')
        assert exc_info.value.code == 2

    def test_full_audit_renderer_json_no_exit_when_all_ok(self, capsys):
        result = {
            'type': 'cpanel_full_audit', 'username': 'myuser', 'has_failures': False,
            'ssl': _make_ssl_result(), 'acl': _make_acl_result(), 'nginx': None,
        }
        CpanelRenderer.render_structure(result, 'json')  # should not raise
        out = capsys.readouterr().out
        import json
        parsed = json.loads(out)
        assert parsed['type'] == 'cpanel_full_audit'

    def test_full_audit_renderer_shows_nginx_none(self, capsys):
        result = {
            'type': 'cpanel_full_audit', 'username': 'myuser', 'has_failures': False,
            'ssl': _make_ssl_result(), 'acl': _make_acl_result(), 'nginx': None,
        }
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'nginx' in out
        assert 'no config' in out

    @patch('reveal.adapters.cpanel.adapter._get_local_ips')
    @patch('reveal.adapters.cpanel.adapter._dns_resolve_ips')
    @patch('reveal.adapters.cpanel.adapter._list_user_domains')
    @patch('reveal.adapters.cpanel.adapter._get_disk_cert_status')
    @patch('reveal.adapters.cpanel.adapter._check_docroot_acl')
    @patch('os.path.exists', return_value=False)
    def test_full_audit_dns_verified_excluded_failures_do_not_set_has_failures(
            self, mock_exists, mock_acl, mock_status, mock_domains,
            mock_resolve_ips, mock_local_ips):
        """Regression: full-audit with --dns-verified should not set has_failures=True
        for NXDOMAIN or elsewhere-pointing domains, since they're excluded from summary."""
        mock_local_ips.return_value = {'10.0.0.1'}
        # domain1: ok cert, resolves to this server
        # domain2: expired cert, NXDOMAIN (dns_resolve_ips returns [])
        mock_domains.return_value = [
            {'domain': 'ok.com', 'docroot': '/home/u/public_html', 'serveralias': '',
             'type': 'main_domain'},
            {'domain': 'gone.com', 'docroot': '/home/u/gone', 'serveralias': '',
             'type': 'addon'},
        ]

        def fake_status(domain):
            if domain == 'ok.com':
                return {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
                        'cert_path': '/cpanel/ssl/ok.com/combined'}
            return {'status': 'expired', 'days_until_expiry': -5, 'not_after': '2026-01-01',
                    'cert_path': '/cpanel/ssl/gone.com/combined'}

        mock_status.side_effect = fake_status
        mock_resolve_ips.side_effect = lambda d: ['10.0.0.1'] if d == 'ok.com' else []
        mock_acl.return_value = {'status': 'ok'}

        a = CpanelAdapter('cpanel://myuser/full-audit')
        result = a.get_structure(dns_verified=True)
        # gone.com is NXDOMAIN → in dns_excluded, not summary
        # summary only has ok.com → no failures
        assert result['has_failures'] is False
        assert result['ssl']['dns_excluded'].get('expired', 0) == 1
        assert 'expired' not in result['ssl']['summary']

    def test_full_audit_renderer_shows_nginx_domains(self, capsys):
        result = {
            'type': 'cpanel_full_audit', 'username': 'myuser', 'has_failures': False,
            'ssl': _make_ssl_result(), 'acl': _make_acl_result(),
            'nginx': {
                'domain_count': 3, 'has_failures': False,
                'domains': [
                    {'domain': 'a.com', 'acme_path': '/var/www/html/.well-known/acme-challenge',
                     'acl_status': 'ok', 'ssl_status': 'healthy', 'ssl_days': 45,
                     'ssl_not_after': '2026-06-01', 'has_failure': False},
                ] * 3,
            },
        }
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'nginx ACME' in out
        assert '3 ok' in out


class TestGetLiveCertStatus:
    """Tests for _get_live_cert_status (BACK-056)."""

    def test_live_ok(self):
        """Returns live_status=ok when live cert is healthy."""
        from reveal.adapters.cpanel.adapter import _get_live_cert_status
        mock_result = {
            'status': 'pass',
            'certificate': {'days_until_expiry': 87, 'not_after': '2026-06-15T00:00:00', 'serial_number': 'AABB'},
        }
        with patch('reveal.adapters.ssl.certificate.check_ssl_health', return_value=mock_result):
            result = _get_live_cert_status('example.com')
            assert result['live_status'] == 'ok'
            assert result['live_days_until_expiry'] == 87
            assert result['live_not_after'] == '2026-06-15'

    def test_live_expired(self):
        """Returns live_status=expired when live cert has expired."""
        from reveal.adapters.cpanel.adapter import _get_live_cert_status
        mock_result = {
            'status': 'failure',
            'certificate': {'days_until_expiry': -5, 'not_after': '2026-03-10T00:00:00', 'serial_number': 'CC'},
        }
        with patch('reveal.adapters.ssl.certificate.check_ssl_health', return_value=mock_result):
            result = _get_live_cert_status('example.com')
            assert result['live_status'] == 'expired'

    def test_live_check_failure(self):
        """Returns live_status=error on network exception."""
        from reveal.adapters.cpanel.adapter import _get_live_cert_status
        with patch('reveal.adapters.ssl.certificate.check_ssl_health', side_effect=Exception('Connection refused')):
            result = _get_live_cert_status('example.com')
            assert result['live_status'] == 'error'
            assert 'Connection refused' in result['live_error']

    def test_live_no_cert_data(self):
        """Returns live_status=error when check_ssl_health returns no cert."""
        from reveal.adapters.cpanel.adapter import _get_live_cert_status
        mock_result = {'status': 'failure', 'certificate': {}, 'error': 'TLS handshake failed'}
        with patch('reveal.adapters.ssl.certificate.check_ssl_health', return_value=mock_result):
            result = _get_live_cert_status('example.com')
            assert result['live_status'] == 'error'


class TestCheckLiveIntegration:
    """Tests for cpanel://USER/ssl --check-live (BACK-056)."""

    def test_check_live_adds_live_fields_to_non_ok_certs(self):
        """--check-live fetches live status for expired/missing disk certs."""
        with patch('reveal.adapters.cpanel.adapter._list_user_domains', return_value=[
            {'domain': 'bad.com', 'type': 'main_domain', 'docroot': '/home/user/public_html'},
            {'domain': 'good.com', 'type': 'subdomain', 'docroot': '/home/user/sub'},
        ]):
            with patch('reveal.adapters.cpanel.adapter._get_disk_cert_status', side_effect=[
                {'status': 'expired', 'days_until_expiry': -3, 'not_after': '2026-03-12'},
                {'status': 'ok', 'days_until_expiry': 87, 'not_after': '2026-06-15'},
            ]):
                with patch('reveal.adapters.cpanel.adapter._get_live_cert_status',
                           return_value={'live_status': 'ok', 'live_days_until_expiry': 87,
                                         'live_not_after': '2026-06-15', 'live_serial': 'NEW'}):
                    with patch('reveal.adapters.cpanel.adapter._get_local_ips', return_value=set()):
                        adapter = CpanelAdapter('cpanel://testuser/ssl')
                        result = adapter._get_ssl_structure(check_live=True)
                        bad_cert = next(c for c in result['certs'] if c['domain'] == 'bad.com')
                        good_cert = next(c for c in result['certs'] if c['domain'] == 'good.com')
                        # Expired cert should have live data
                        assert 'live_status' in bad_cert
                        assert bad_cert['live_status'] == 'ok'
                        # OK cert should NOT have live data (no network call)
                        assert 'live_status' not in good_cert

    def test_check_live_false_no_live_fields(self):
        """Without --check-live, no live fields added."""
        with patch('reveal.adapters.cpanel.adapter._list_user_domains', return_value=[
            {'domain': 'bad.com', 'type': 'main_domain', 'docroot': '/home/user/public_html'},
        ]):
            with patch('reveal.adapters.cpanel.adapter._get_disk_cert_status',
                       return_value={'status': 'expired', 'days_until_expiry': -5}):
                with patch('reveal.adapters.cpanel.adapter._get_local_ips', return_value=set()):
                    adapter = CpanelAdapter('cpanel://testuser/ssl')
                    result = adapter._get_ssl_structure(check_live=False)
                    cert = result['certs'][0]
                    assert 'live_status' not in cert

    def test_check_live_in_result_dict(self):
        """check_live flag is stored in result dict."""
        with patch('reveal.adapters.cpanel.adapter._list_user_domains', return_value=[]):
            adapter = CpanelAdapter('cpanel://testuser/ssl')
            result = adapter._get_ssl_structure(check_live=True)
            assert result['check_live'] is True

    def test_parser_accepts_check_live_flag(self):
        """--check-live is registered in the argument parser."""
        from reveal.cli.parser import create_argument_parser
        parser = create_argument_parser('test')
        args = parser.parse_args(['cpanel://user/ssl', '--check-live'])
        assert args.check_live is True

    def test_parser_check_live_default_false(self):
        """--check-live defaults to False."""
        from reveal.cli.parser import create_argument_parser
        parser = create_argument_parser('test')
        args = parser.parse_args(['cpanel://user/ssl'])
        assert args.check_live is False

    def test_renderer_shows_live_check_header(self, capsys):
        """Renderer announces live-check mode and counts non-ok domains."""
        result = {
            'type': 'cpanel_ssl', 'username': 'myuser',
            'cpanel_ssl_dir': '/var/cpanel/ssl/apache_tls',
            'cert_count': 2, 'dns_verified': False, 'only_failures': False,
            'check_live': True, 'domain_type_filter': None,
            'summary': {'expired': 1, 'ok': 1},
            'dns_excluded': {}, 'dns_elsewhere': {},
            'certs': [
                {'domain': 'bad.com', 'domain_type': 'main_domain',
                 'status': 'expired', 'days_until_expiry': -5, 'not_after': '2026-03-10',
                 'live_status': 'ok', 'live_days_until_expiry': 87, 'live_not_after': '2026-06-15'},
                {'domain': 'good.com', 'domain_type': 'subdomain',
                 'status': 'ok', 'days_until_expiry': 87, 'not_after': '2026-06-15'},
            ],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'live-check: enabled' in out
        assert '1 non-ok' in out

    def test_renderer_shows_live_line_in_cert_row(self, capsys):
        """Renderer shows ↳ live: ... line below each non-ok cert with live data."""
        result = {
            'type': 'cpanel_ssl', 'username': 'myuser',
            'cpanel_ssl_dir': '/var/cpanel/ssl/apache_tls',
            'cert_count': 1, 'dns_verified': False, 'only_failures': False,
            'check_live': True, 'domain_type_filter': None,
            'summary': {'expired': 1},
            'dns_excluded': {}, 'dns_elsewhere': {},
            'certs': [
                {'domain': 'bad.com', 'domain_type': 'main_domain',
                 'status': 'expired', 'days_until_expiry': -5, 'not_after': '2026-03-10',
                 'live_status': 'ok', 'live_days_until_expiry': 87, 'live_not_after': '2026-06-15'},
            ],
            'next_steps': [],
        }
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert '↳' in out
        assert 'live:' in out


class TestCpanelHelpApi:
    """Tests for cpanel://help/api — BACK-131."""

    def test_help_api_returns_reference(self):
        """cpanel://help/api returns the API reference structure."""
        adapter = CpanelAdapter('cpanel://help/api')
        result = adapter.get_structure()
        assert result['type'] == 'cpanel_api_reference'
        assert 'sections' in result
        assert 'domain_types' in result
        assert 'tips' in result

    def test_help_api_has_all_sections(self):
        """API reference covers account, domain, SSL, and nginx sections."""
        adapter = CpanelAdapter('cpanel://help/api')
        result = adapter.get_structure()
        section_names = [s['name'] for s in result['sections']]
        assert 'Account Management' in section_names
        assert 'Domain Management' in section_names
        assert 'SSL / AutoSSL' in section_names

    def test_help_api_domain_types_present(self):
        """Domain types section includes all four types."""
        adapter = CpanelAdapter('cpanel://help/api')
        result = adapter.get_structure()
        types = result['domain_types']
        assert 'main' in types
        assert 'addon' in types
        assert 'parked' in types
        assert 'subdomain' in types

    def test_help_api_renders_text(self, capsys):
        """Text rendering produces readable output."""
        adapter = CpanelAdapter('cpanel://help/api')
        result = adapter.get_structure()
        CpanelRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'WHM & cPanel API Quick Reference' in out
        assert 'whmapi1 listparkeddomains' in out
        assert 'Domain Types' in out

    def test_help_api_renders_json(self, capsys):
        """JSON rendering produces valid JSON."""
        import json
        adapter = CpanelAdapter('cpanel://help/api')
        result = adapter.get_structure()
        CpanelRenderer.render_structure(result, 'json')
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed['type'] == 'cpanel_api_reference'

    def test_help_unknown_topic_raises(self):
        """cpanel://help/unknown raises ValueError."""
        adapter = CpanelAdapter('cpanel://help/unknown')
        with pytest.raises(ValueError, match="Unknown cpanel://help topic"):
            adapter.get_structure()


class TestCpanelSchema:
    """Tests for CpanelAdapter.get_schema() and get_help()."""

    def test_schema_has_required_fields(self):
        """get_schema returns adapter, description, elements, output_types."""
        adapter = CpanelAdapter('cpanel://testuser')
        schema = adapter.get_schema()
        assert schema['adapter'] == 'cpanel'
        assert 'description' in schema
        assert 'elements' in schema
        assert 'output_types' in schema

    def test_schema_elements_include_help_api(self):
        """Schema elements include help/api (BACK-131)."""
        adapter = CpanelAdapter('cpanel://testuser')
        schema = adapter.get_schema()
        assert 'help/api' in schema['elements']

    def test_schema_elements_include_core_elements(self):
        """Schema lists domains, ssl, acl-check, full-audit."""
        adapter = CpanelAdapter('cpanel://testuser')
        schema = adapter.get_schema()
        for elem in ('domains', 'ssl', 'acl-check', 'full-audit'):
            assert elem in schema['elements'], f"Missing element: {elem}"

    def test_schema_output_types_present(self):
        """Output types list is non-empty."""
        adapter = CpanelAdapter('cpanel://testuser')
        schema = adapter.get_schema()
        assert len(schema['output_types']) > 0

    def test_help_has_required_fields(self):
        """get_help returns description, examples, elements, workflows."""
        adapter = CpanelAdapter('cpanel://testuser')
        help_info = adapter.get_help()
        assert 'description' in help_info
        assert 'examples' in help_info
        assert 'elements' in help_info

    def test_help_examples_are_list(self):
        """Help examples is a non-empty list with uri and description."""
        adapter = CpanelAdapter('cpanel://testuser')
        help_info = adapter.get_help()
        assert isinstance(help_info['examples'], list)
        assert len(help_info['examples']) > 0
        for ex in help_info['examples']:
            assert 'uri' in ex
            assert 'description' in ex

    def test_help_includes_help_api_example(self):
        """Help examples include cpanel://help/api."""
        adapter = CpanelAdapter('cpanel://testuser')
        help_info = adapter.get_help()
        uris = [ex['uri'] for ex in help_info['examples']]
        assert 'cpanel://help/api' in uris

    def test_schema_uses_query_params_key_not_uri_query_params(self):
        """BACK-167: get_schema() must use 'query_params' key, not 'uri_query_params'."""
        schema = CpanelAdapter.get_schema()
        assert 'query_params' in schema, "Schema must use 'query_params' key"
        assert 'uri_query_params' not in schema, "Schema must not use 'uri_query_params' key"

    def test_schema_query_params_includes_expected_params(self):
        """BACK-167: query_params lists domain_type, dns-verified, check-live."""
        schema = CpanelAdapter.get_schema()
        qp = schema['query_params']
        assert 'domain_type' in qp
        assert 'dns-verified' in qp
        assert 'check-live' in qp


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
