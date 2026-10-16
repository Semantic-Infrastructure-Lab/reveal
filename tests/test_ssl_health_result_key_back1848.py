"""BACK-1848: callers read the certificate out of check_ssl_health()'s real result shape.

check_ssl_health() returns the parsed certificate under 'certificate'; 'leaf' is only the
key of the ssl:// chain view. Three callers read 'leaf', so ssl_days, ssl_not_after and the
serial were always empty -- and every test mock repeated the wrong key, so none noticed.
These tests build the result with the real builder instead of a hand-written dict.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from reveal.adapters.nginx import handlers as nginx_handlers
from reveal.adapters.ssl.certificate import CertificateInfo, _build_ssl_health_success_result

_NOT_AFTER = datetime.now(timezone.utc) + timedelta(days=42, hours=1)


def _real_result():
    cert = CertificateInfo(
        subject={'commonName': 'ok.com'}, issuer={'organizationName': 'CA'},
        not_before=_NOT_AFTER - timedelta(days=90), not_after=_NOT_AFTER,
        serial_number='ABC123', version=3, san=['ok.com'])
    return _build_ssl_health_success_result('ok.com', 443, 'pass', cert, [], {}, False)


def _health(*_args, **_kwargs):
    return _real_result()


def test_real_result_keeps_the_certificate_under_certificate_not_leaf():
    result = _real_result()
    assert 'leaf' not in result
    assert result['certificate']['days_until_expiry'] == 42


def test_nginx_acme_rows_carry_the_live_expiry():
    rows = nginx_handlers._fetch_acme_ssl_data([{'domain': 'ok.com'}], _health)
    assert rows[0]['ssl_days'] == 42
    assert rows[0]['ssl_not_after'] == _NOT_AFTER.isoformat()


def test_nginx_live_cert_carries_expiry_serial_and_not_after():
    live = nginx_handlers._load_live_cert('ok.com', _health)
    assert live['expiry'] == 42
    assert live['serial'] == 'ABC123'
    assert live['not_after'] is not None


def test_cpanel_full_audit_acme_rows_carry_the_live_expiry():
    from reveal.adapters.cpanel.adapter import CpanelAdapter
    analyzer = MagicMock()
    analyzer.return_value.extract_acme_roots.return_value = [
        {'domain': 'ok.com', 'acl_status': 'ok', 'acme_path': '/x', 'acl_message': '', 'line': 1}]
    domains = [{'domain': 'ok.com', 'docroot': '/home/u/public_html',
                'serveralias': '', 'type': 'main_domain'}]
    disk = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01', 'cert_path': 'combined'}
    with patch('reveal.adapters.cpanel.adapter._list_user_domains', return_value=domains), \
            patch('reveal.adapters.cpanel.adapter._get_disk_cert_status', return_value=disk), \
            patch('reveal.adapters.cpanel.adapter._check_docroot_acl', return_value={'status': 'ok'}), \
            patch('os.path.exists', return_value=True), \
            patch('reveal.analyzers.nginx.NginxAnalyzer', analyzer), \
            patch('reveal.adapters.ssl.certificate.check_ssl_health', _health):
        result = CpanelAdapter('cpanel://myuser/full-audit').get_structure()
    text = json.dumps(result, default=str)
    assert '"ssl_days": 42' in text
    assert _NOT_AFTER.isoformat() in text
