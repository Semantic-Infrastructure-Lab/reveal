"""Infrastructure adapters catch their named failures, not every Exception (BACK-1059).

domain://, ssl://, letsencrypt://, cpanel://, mysql:// and nginx:// probe external
services (DNS, TLS, MySQL, the filesystem). A network or driver error is expected
and is reported in the result; a bug in parsing the reply (a RuntimeError here
stands for it) used to be caught by the same `except Exception` and read as one of
those failures. Each case injects an unexpected RuntimeError and asserts it
propagates, and injects the named error to show the old path is unchanged.

No test touches the network, DNS or a database: every call is patched.

Several of these adapters are NOT_RUNNABLE in the contract harness (BACK-1615), so
these tests are their only coverage of the failure paths.
"""

import http.client
import socket
import ssl
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.component

BUG = RuntimeError("bug in reply parsing")


# ---------------------------------------------------------------------------
# domain/dns.py
# ---------------------------------------------------------------------------

dns_exception = pytest.importorskip("dns.exception")
dns_resolver = pytest.importorskip("dns.resolver")

from reveal.adapters.domain import dns as dns_mod  # noqa: E402


def _resolve(side_effect):
    return patch.object(dns_mod.dns.resolver, 'resolve', side_effect=side_effect)


def test_get_dns_summary_reports_oserror_in_result():
    with patch.object(dns_mod, 'get_dns_records', side_effect=OSError("network down")):
        result = dns_mod.get_dns_summary('example.com')
    assert result['error'] == 'network down'
    assert result['nameservers'] == []


def test_get_dns_summary_does_not_swallow_a_bug():
    with patch.object(dns_mod, 'get_dns_records', side_effect=BUG):
        with pytest.raises(RuntimeError, match="bug in reply parsing"):
            dns_mod.get_dns_summary('example.com')


@pytest.mark.parametrize("error", [dns_exception.Timeout(), socket.gaierror("no such host")])
def test_nameserver_response_reports_named_failures(error):
    with _resolve(error):
        result = dns_mod.check_nameserver_response('example.com')
    assert result['status'] == 'failure'
    assert result['value'] == 'Not responding'


def test_nameserver_response_does_not_swallow_a_bug():
    with _resolve(BUG):
        with pytest.raises(RuntimeError):
            dns_mod.check_nameserver_response('example.com')


@pytest.mark.parametrize("check", ['check_mx_records', 'check_spf_record', 'check_dmarc_record'])
def test_email_checks_report_oserror_as_check_failed(check):
    with _resolve(OSError("socket closed")):
        result = getattr(dns_mod, check)('example.com')
    assert result['status'] == 'warning'
    assert result['value'] == 'Check failed'


@pytest.mark.parametrize("check", ['check_mx_records', 'check_spf_record', 'check_dmarc_record'])
def test_email_checks_still_map_dns_errors_to_missing(check):
    """Negative control: a DNSException is "no record", not "check failed"."""
    with _resolve(dns_exception.DNSException()):
        result = getattr(dns_mod, check)('example.com')
    assert result['status'] == 'failure'


@pytest.mark.parametrize("check", ['check_mx_records', 'check_spf_record', 'check_dmarc_record'])
def test_email_checks_do_not_swallow_a_bug(check):
    with _resolve(BUG):
        with pytest.raises(RuntimeError):
            getattr(dns_mod, check)('example.com')


def _ns_answers():
    return [MagicMock(__str__=lambda self: 'ns1.example.com.')]


def test_propagation_records_a_failing_nameserver_and_continues():
    """Negative control: a per-nameserver socket error is logged and recorded."""
    with _resolve(lambda *a, **k: _ns_answers()), \
            patch.object(dns_mod.socket, 'gethostbyname', side_effect=socket.gaierror("nope")):
        result = dns_mod.check_dns_propagation('example.com')
    assert result['name'] == 'dns_propagation'
    assert 'Error' in str(result['details']['responses']['ns1.example.com'])


def test_propagation_does_not_swallow_a_bug_in_a_nameserver_query():
    with _resolve(lambda *a, **k: _ns_answers()), \
            patch.object(dns_mod.socket, 'gethostbyname', side_effect=BUG):
        with pytest.raises(RuntimeError):
            dns_mod.check_dns_propagation('example.com')


def test_propagation_reports_dns_error_in_the_ns_lookup():
    with _resolve(dns_exception.Timeout()):
        result = dns_mod.check_dns_propagation('example.com')
    assert result['status'] == 'failure'
    assert result['value'] == 'Check failed'


def test_propagation_does_not_swallow_a_bug_in_the_ns_lookup():
    with _resolve(BUG):
        with pytest.raises(RuntimeError):
            dns_mod.check_dns_propagation('example.com')


def _patched_ns_resolver(effect):
    resolver = MagicMock()
    resolver.return_value.resolve.side_effect = effect
    return patch.object(dns_mod.dns.resolver, 'Resolver', resolver)


def test_query_ns_reports_dns_error_as_query_failed():
    with patch.object(dns_mod.socket, 'gethostbyname', return_value='192.0.2.1'), \
            _patched_ns_resolver(dns_exception.DNSException("refused")):
        result = dns_mod._query_ns_for_ns_records('ns1.example.com', 'example.com')
    assert result['status'] == 'query_failed'


def test_query_ns_keeps_timeout_distinct():
    """Negative control: Timeout is still 'no_response'."""
    with patch.object(dns_mod.socket, 'gethostbyname', return_value='192.0.2.1'), \
            _patched_ns_resolver(dns_exception.Timeout()):
        result = dns_mod._query_ns_for_ns_records('ns1.example.com', 'example.com')
    assert result['status'] == 'no_response'


def test_query_ns_does_not_swallow_a_bug():
    with patch.object(dns_mod.socket, 'gethostbyname', return_value='192.0.2.1'), \
            _patched_ns_resolver(BUG):
        with pytest.raises(RuntimeError):
            dns_mod._query_ns_for_ns_records('ns1.example.com', 'example.com')


def test_ns_authority_reports_dns_error():
    with _resolve(dns_exception.DNSException("servfail")):
        result = dns_mod.check_ns_authority('example.com')
    assert result['status'] == 'error'
    assert 'Failed to resolve NS records' in result['message']


def test_ns_authority_does_not_swallow_a_bug():
    with _resolve(BUG):
        with pytest.raises(RuntimeError):
            dns_mod.check_ns_authority('example.com')


# ---------------------------------------------------------------------------
# domain/adapter.py
# ---------------------------------------------------------------------------

from reveal.adapters.domain import adapter as domain_mod  # noqa: E402


def test_domain_ssl_check_reports_oserror():
    with patch.object(domain_mod, 'check_ssl_health', side_effect=socket.timeout("timed out")):
        result = domain_mod._check_ssl_certificate('example.com')
    assert result['status'] == 'failure'
    assert 'SSL check failed' in result['message']


def test_domain_ssl_check_does_not_swallow_a_bug():
    with patch.object(domain_mod, 'check_ssl_health', side_effect=BUG):
        with pytest.raises(RuntimeError):
            domain_mod._check_ssl_certificate('example.com')


@pytest.mark.parametrize("error", [
    OSError("connection reset"),
    ValueError("invalid URL"),
    http.client.BadStatusLine("garbage"),
])
def test_redirect_chain_reports_named_failures(error):
    with patch.object(domain_mod, '_handle_redirect_step', side_effect=error):
        result = domain_mod._follow_redirect_chain('https://example.com/')
    assert result['status'] is None
    assert result['error']


def test_redirect_chain_does_not_swallow_a_bug():
    with patch.object(domain_mod, '_handle_redirect_step', side_effect=BUG):
        with pytest.raises(RuntimeError):
            domain_mod._follow_redirect_chain('https://example.com/')


def test_domain_ssl_status_reports_oserror():
    adapter = domain_mod.DomainAdapter("domain://example.com")
    with patch.object(domain_mod, 'check_ssl_health', side_effect=OSError("unreachable")):
        result = adapter._get_ssl_status()
    assert result['error'] == 'unreachable'


def test_domain_ssl_status_does_not_swallow_a_bug():
    adapter = domain_mod.DomainAdapter("domain://example.com")
    with patch.object(domain_mod, 'check_ssl_health', side_effect=BUG):
        with pytest.raises(RuntimeError):
            adapter._get_ssl_status()


def test_domain_ssl_summary_reports_oserror():
    adapter = domain_mod.DomainAdapter("domain://example.com")
    with patch.object(domain_mod, 'check_ssl_health', side_effect=OSError("unreachable")):
        result = adapter._get_ssl_summary()
    assert result['health_status'] == 'error'
    assert result['error'] == 'unreachable'


def test_domain_ssl_summary_does_not_swallow_a_bug():
    adapter = domain_mod.DomainAdapter("domain://example.com")
    with patch.object(domain_mod, 'check_ssl_health', side_effect=BUG):
        with pytest.raises(RuntimeError):
            adapter._get_ssl_summary()


# ---------------------------------------------------------------------------
# ssl/certificate.py
# ---------------------------------------------------------------------------

from reveal.adapters.ssl import certificate as cert_mod  # noqa: E402


def test_unparseable_der_is_an_error_not_an_empty_certificate():
    """An empty cert dict became "expires now"; the failure must reach the caller."""
    with pytest.raises(ValueError, match="Could not parse certificate"):
        cert_mod.SSLFetcher()._parse_binary_cert(b"not a certificate")


def test_unparseable_der_file_fails_to_load(tmp_path):
    path = tmp_path / "junk.der"
    path.write_bytes(b"not a certificate")
    with pytest.raises(ValueError, match="Failed to parse certificate file"):
        cert_mod.load_certificate_from_file(str(path))


def test_unparseable_pem_block_fails_to_load(tmp_path):
    """Negative control: a bad PEM block already raised ValueError."""
    path = tmp_path / "junk.pem"
    path.write_text(
        "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to parse PEM block"):
        cert_mod.load_certificate_from_file(str(path))


def test_pem_loader_does_not_relabel_a_bug(tmp_path):
    path = tmp_path / "ok.pem"
    path.write_text(
        "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n", encoding="utf-8")
    with patch.object(cert_mod.x509, 'load_pem_x509_certificate', side_effect=BUG):
        with pytest.raises(RuntimeError):
            cert_mod.load_certificate_from_file(str(path))


def test_der_loader_does_not_relabel_a_bug(tmp_path):
    path = tmp_path / "ok.der"
    path.write_bytes(b"\x30\x00")
    with patch.object(cert_mod.SSLFetcher, '_parse_binary_cert', side_effect=BUG):
        with pytest.raises(RuntimeError):
            cert_mod.load_certificate_from_file(str(path))


@pytest.mark.parametrize("error", [
    ssl.SSLError("handshake failure"),
    socket.gaierror("no such host"),
    ValueError("embedded null"),
    http.client.BadStatusLine("garbage"),
])
def test_ssl_health_reports_named_failures(error):
    with patch.object(cert_mod.SSLFetcher, 'fetch_certificate_with_verification',
                      side_effect=error):
        result = cert_mod.check_ssl_health('example.com')
    assert result['status'] == 'failure'
    assert result['exit_code'] == 2
    assert result['error'] == str(error)


def test_ssl_health_reports_an_unparseable_certificate_as_failure():
    """The new ValueError from _parse_binary_cert surfaces as a failed check."""
    with patch.object(cert_mod.SSLFetcher, 'fetch_certificate_with_verification',
                      side_effect=ValueError("Could not parse certificate: junk")):
        result = cert_mod.check_ssl_health('example.com')
    assert result['status'] == 'failure'
    assert 'Could not parse certificate' in result['error']


def test_ssl_health_does_not_swallow_a_bug():
    with patch.object(cert_mod.SSLFetcher, 'fetch_certificate_with_verification',
                      side_effect=BUG):
        with pytest.raises(RuntimeError):
            cert_mod.check_ssl_health('example.com')


@pytest.mark.parametrize("error", [socket.timeout("timed out"), ssl.SSLError("bad"), ValueError("host")])
def test_tls_version_check_reports_named_failures(error):
    with patch.object(cert_mod.socket, 'create_connection', side_effect=error):
        check, failed = cert_mod._check_tls_version('example.com', 443, 1.0)
    assert check['status'] == 'warning'
    assert check['value'] == 'Unknown'
    assert failed is False


def test_tls_version_check_does_not_swallow_a_bug():
    with patch.object(cert_mod.socket, 'create_connection', side_effect=BUG):
        with pytest.raises(RuntimeError):
            cert_mod._check_tls_version('example.com', 443, 1.0)


# ---------------------------------------------------------------------------
# ssl/adapter.py
# ---------------------------------------------------------------------------

from reveal.adapters.ssl import adapter as ssl_adapter_mod  # noqa: E402


def test_validate_single_domain_reports_oserror():
    adapter = ssl_adapter_mod.SSLAdapter("ssl://example.com")
    with patch.object(ssl_adapter_mod, 'check_ssl_health', side_effect=OSError("refused")):
        result = adapter._validate_single_domain('example.com')
    assert result['status'] == 'failure'
    assert result['issues'][0]['type'] == 'connection_error'


def test_validate_single_domain_does_not_swallow_a_bug():
    adapter = ssl_adapter_mod.SSLAdapter("ssl://example.com")
    with patch.object(ssl_adapter_mod, 'check_ssl_health', side_effect=BUG):
        with pytest.raises(RuntimeError):
            adapter._validate_single_domain('example.com')


# ---------------------------------------------------------------------------
# letsencrypt, cpanel, nginx: loaders of on-disk and live certificates
# ---------------------------------------------------------------------------

_LOAD = 'reveal.adapters.ssl.certificate.load_certificate_from_file'
_HEALTH = 'reveal.adapters.ssl.certificate.check_ssl_health'


@pytest.mark.parametrize("error", [ValueError("Failed to parse"), FileNotFoundError("gone"),
                                   PermissionError("denied")])
def test_letsencrypt_cert_info_reports_named_failures(error, tmp_path):
    from reveal.adapters.letsencrypt.adapter import _load_cert_info
    cert = tmp_path / "live" / "example.com" / "cert.pem"
    with patch(_LOAD, side_effect=error):
        info = _load_cert_info(cert)
    assert info['name'] == 'example.com'
    assert info['error'] == str(error)


def test_letsencrypt_cert_info_does_not_swallow_a_bug(tmp_path):
    from reveal.adapters.letsencrypt.adapter import _load_cert_info
    with patch(_LOAD, side_effect=BUG):
        with pytest.raises(RuntimeError):
            _load_cert_info(tmp_path / "live" / "example.com" / "cert.pem")


@pytest.mark.parametrize("error", [ValueError("Bad cert"), PermissionError("denied")])
def test_cpanel_disk_cert_reports_named_failures(error):
    from reveal.adapters.cpanel.adapter import _get_disk_cert_status
    with patch('os.path.exists', return_value=True), patch(_LOAD, side_effect=error):
        result = _get_disk_cert_status('example.com')
    assert result['status'] == 'error'


def test_cpanel_disk_cert_does_not_swallow_a_bug():
    from reveal.adapters.cpanel.adapter import _get_disk_cert_status
    with patch('os.path.exists', return_value=True), patch(_LOAD, side_effect=BUG):
        with pytest.raises(RuntimeError):
            _get_disk_cert_status('example.com')


def test_cpanel_live_cert_reports_oserror():
    from reveal.adapters.cpanel.adapter import _get_live_cert_status
    with patch(_HEALTH, side_effect=ConnectionRefusedError("Connection refused")):
        result = _get_live_cert_status('example.com')
    assert result['live_status'] == 'error'
    assert 'Connection refused' in result['live_error']


def test_cpanel_live_cert_does_not_swallow_a_bug():
    from reveal.adapters.cpanel.adapter import _get_live_cert_status
    with patch(_HEALTH, side_effect=BUG):
        with pytest.raises(RuntimeError):
            _get_live_cert_status('example.com')


def _full_audit(nginx_analyzer, ssl_health):
    """Run cpanel://myuser/full-audit with one ACME row and the given fakes."""
    from reveal.adapters.cpanel.adapter import CpanelAdapter
    domains = [{'domain': 'ok.com', 'docroot': '/home/u/public_html',
                'serveralias': '', 'type': 'main_domain'}]
    disk = {'status': 'ok', 'days_until_expiry': 60, 'not_after': '2026-06-01',
            'cert_path': 'combined'}
    with patch('reveal.adapters.cpanel.adapter._list_user_domains', return_value=domains), \
            patch('reveal.adapters.cpanel.adapter._get_disk_cert_status', return_value=disk), \
            patch('reveal.adapters.cpanel.adapter._check_docroot_acl', return_value={'status': 'ok'}), \
            patch('os.path.exists', return_value=True), \
            patch('reveal.analyzers.nginx.NginxAnalyzer', nginx_analyzer), \
            patch(_HEALTH, ssl_health):
        return CpanelAdapter('cpanel://myuser/full-audit').get_structure()


def _analyzer_with_one_acme_row():
    analyzer = MagicMock()
    analyzer.return_value.extract_acme_roots.return_value = [
        {'domain': 'ok.com', 'acl_status': 'ok', 'acme_path': '/x', 'acl_message': '', 'line': 1}]
    return analyzer


def test_full_audit_records_an_unreachable_domain_in_the_nginx_section():
    result = _full_audit(_analyzer_with_one_acme_row(), MagicMock(side_effect=OSError("down")))
    row = result['nginx']['domains'][0]
    assert row['ssl_status'] == 'error'
    assert row['has_failure'] is True


def test_full_audit_does_not_swallow_a_bug_in_the_ssl_check():
    with pytest.raises(RuntimeError):
        _full_audit(_analyzer_with_one_acme_row(), MagicMock(side_effect=BUG))


def test_full_audit_reports_an_unreadable_nginx_conf():
    analyzer = MagicMock(side_effect=PermissionError("denied"))
    result = _full_audit(analyzer, MagicMock())
    assert result['nginx']['error'] == 'denied'


def test_full_audit_does_not_swallow_a_bug_in_the_nginx_analyzer():
    with pytest.raises(RuntimeError):
        _full_audit(MagicMock(side_effect=BUG), MagicMock())


from reveal.adapters.nginx import handlers as nginx_handlers  # noqa: E402
from reveal.adapters.nginx import adapter as nginx_adapter  # noqa: E402


def test_nginx_disk_cert_reports_named_failures(tmp_path):
    cert = tmp_path / "combined"
    cert.write_text("x", encoding="utf-8")
    result = nginx_handlers._load_disk_cert(str(cert), MagicMock(side_effect=ValueError("bad")))
    assert result['status'].startswith('error: bad')


def test_nginx_disk_cert_does_not_swallow_a_bug(tmp_path):
    cert = tmp_path / "combined"
    cert.write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError):
        nginx_handlers._load_disk_cert(str(cert), MagicMock(side_effect=BUG))


def test_nginx_live_cert_reports_oserror():
    result = nginx_handlers._load_live_cert('example.com', MagicMock(side_effect=OSError("down")))
    assert result['status'] == 'error: down'


def test_nginx_live_cert_does_not_swallow_a_bug():
    with pytest.raises(RuntimeError):
        nginx_handlers._load_live_cert('example.com', MagicMock(side_effect=BUG))


def test_nginx_acme_rows_report_oserror():
    rows = nginx_handlers._fetch_acme_ssl_data(
        [{'domain': 'a.com'}], MagicMock(side_effect=OSError("down")))
    assert rows[0]['ssl_status'] == 'error'
    assert rows[0]['error'] == 'down'


def test_nginx_acme_rows_do_not_swallow_a_bug():
    with pytest.raises(RuntimeError):
        nginx_handlers._fetch_acme_ssl_data([{'domain': 'a.com'}], MagicMock(side_effect=BUG))


@pytest.mark.parametrize("error", [ConnectionRefusedError("refused"), socket.timeout("timed out"),
                                   socket.gaierror("no such host"), OverflowError("port"),
                                   UnicodeError("label too long")])
def test_upstream_reachability_reports_named_failures(error):
    with patch.object(nginx_adapter.socket, 'create_connection', side_effect=error):
        result = nginx_adapter._check_upstream_reachability({'servers': ['10.0.0.1:8080']})
    assert result[0]['reachable'] is False
    assert result[0]['error'] == str(error)


def test_upstream_reachability_does_not_swallow_a_bug():
    with patch.object(nginx_adapter.socket, 'create_connection', side_effect=BUG):
        with pytest.raises(RuntimeError):
            nginx_adapter._check_upstream_reachability({'servers': ['10.0.0.1:8080']})


# ---------------------------------------------------------------------------
# mysql
# ---------------------------------------------------------------------------

pymysql = pytest.importorskip("pymysql")

from reveal.adapters.mysql.adapter import MySQLAdapter  # noqa: E402
from reveal.adapters.mysql.connection import MySQLConnection  # noqa: E402

DRIVER_ERROR = pymysql.err.OperationalError(1045, "Access denied")


def _connection_error():
    """What get_connection() raises when the connection cannot be opened."""
    conn = MySQLConnection("mysql://u:p@db.example.com")
    with patch('reveal.adapters.mysql.connection.pymysql') as fake:
        fake.connect.side_effect = DRIVER_ERROR
        try:
            conn.get_connection()
        except Exception as e:  # noqa: BLE001 - capturing it is the point
            return e
    raise AssertionError("get_connection did not raise")


def test_connect_failure_is_a_typed_error_naming_the_host():
    conn = MySQLConnection("mysql://u:p@db.example.com:3307")
    with patch('reveal.adapters.mysql.connection.pymysql') as fake:
        fake.connect.side_effect = DRIVER_ERROR
        with pytest.raises(Exception, match=r"db\.example\.com:3307") as info:
            conn.get_connection()
    assert type(info.value).__name__ == 'MySQLConnectionError'
    assert info.value.__cause__ is DRIVER_ERROR


def test_connect_failure_stays_catchable_as_exception():
    """Negative control: callers that caught Exception from get_connection still do."""
    conn = MySQLConnection("mysql://u:p@db.example.com")
    with patch('reveal.adapters.mysql.connection.pymysql') as fake:
        fake.connect.side_effect = OSError("refused")
        with pytest.raises(Exception, match="Failed to connect to MySQL"):
            conn.get_connection()


def test_connect_does_not_relabel_a_bug():
    """A TypeError is what a wrong argument to pymysql.connect would raise.

    (RuntimeError is not a bug here: pymysql raises it when `cryptography` is
    missing for sha256/caching_sha2 auth, and that is reported as a connection
    failure.)
    """
    conn = MySQLConnection("mysql://u:p@db.example.com")
    with patch('reveal.adapters.mysql.connection.pymysql') as fake:
        fake.connect.side_effect = TypeError("bug in connect arguments")
        with pytest.raises(TypeError, match="bug in connect arguments"):
            conn.get_connection()


def test_performance_schema_query_failure_is_disclosed():
    conn = MySQLConnection("mysql://localhost")
    with patch.object(conn, 'execute_single', side_effect=DRIVER_ERROR):
        status = conn.get_performance_schema_status()
    assert status['enabled'] is False
    assert 'Access denied' in status['error']


def test_performance_schema_connect_failure_is_disclosed():
    conn = MySQLConnection("mysql://localhost")
    with patch.object(conn, 'execute_single', side_effect=_connection_error()):
        status = conn.get_performance_schema_status()
    assert 'Failed to connect' in status['error']


def test_performance_schema_status_does_not_swallow_a_bug():
    conn = MySQLConnection("mysql://localhost")
    with patch.object(conn, 'execute_single', side_effect=BUG):
        with pytest.raises(RuntimeError):
            conn.get_performance_schema_status()


def test_performance_schema_clean_path_has_no_error_key():
    """Negative control: a healthy answer is unchanged and carries no 'error'."""
    conn = MySQLConnection("mysql://localhost")
    with patch.object(conn, 'execute_single', return_value={'enabled': 0}):
        status = conn.get_performance_schema_status()
    assert status == {'enabled': False, 'counters_reset_detected': False,
                      'likely_reset_time': None}


def test_digest_query_failure_is_disclosed_and_a_bug_is_not_swallowed():
    conn = MySQLConnection("mysql://localhost")
    snapshot = {'snapshot_time': '2026-01-01T00:00:00+00:00', 'uptime_seconds': 100}
    answers = iter([{'enabled': 1}, DRIVER_ERROR])

    def fake(query, params=None):
        value = next(answers)
        if isinstance(value, Exception):
            raise value
        return value

    with patch.object(conn, 'execute_single', side_effect=fake), \
            patch.object(conn, 'get_snapshot_context', return_value=snapshot):
        status = conn.get_performance_schema_status()
    assert status['enabled'] is True
    assert 'Access denied' in status['error']

    answers = iter([{'enabled': 1}, BUG])
    with patch.object(conn, 'execute_single', side_effect=fake), \
            patch.object(conn, 'get_snapshot_context', return_value=snapshot):
        with pytest.raises(RuntimeError):
            conn.get_performance_schema_status()


def test_replication_info_reports_driver_error():
    adapter = MySQLAdapter("mysql://localhost")
    with patch.object(adapter.conn, 'execute_single', side_effect=DRIVER_ERROR):
        info = adapter._build_replication_info()
    assert info['role'] == 'Unknown'
    assert 'Access denied' in info['error']


def test_replication_info_does_not_swallow_a_bug():
    adapter = MySQLAdapter("mysql://localhost")
    with patch.object(adapter.conn, 'execute_single', side_effect=BUG):
        with pytest.raises(RuntimeError):
            adapter._build_replication_info()


def test_slow_queries_report_driver_error():
    adapter = MySQLAdapter("mysql://localhost")
    error = pymysql.err.ProgrammingError(1146, "Table 'mysql.slow_log' doesn't exist")
    with patch.object(adapter.conn, 'execute_query', side_effect=error):
        result = adapter._get_slow_queries()
    assert result['type'] == 'slow_queries'
    assert 'slow_log' in result['error']


def test_slow_queries_do_not_swallow_a_bug():
    adapter = MySQLAdapter("mysql://localhost")
    with patch.object(adapter.conn, 'execute_query', side_effect=BUG):
        with pytest.raises(RuntimeError):
            adapter._get_slow_queries()
