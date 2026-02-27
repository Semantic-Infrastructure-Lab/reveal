"""Tests for the cpanel:// adapter — CpanelAdapter + helpers."""

import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from reveal.adapters.cpanel.adapter import (
    CpanelAdapter,
    _parse_cpanel_userdata,
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
