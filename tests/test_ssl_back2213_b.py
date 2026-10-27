"""BACK-2213 lane b: ssl:// code fixes found by the guide review.

CB1: every `--check` mode exits 0 (pass), 1 (warning), 2 (failure). The nginx batch, the
     cert-file (`ssl://file://`) and the `--local-certs` modes returned 0 on warnings, while a
     single host and `reveal --stdin --check` returned 1.
CB2: the nginx batch "Next Steps" named a command that does not exist
     (`reveal ssl:// --from-nginx <path> --validate`).
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from reveal.adapters.ssl import adapter as ssl_adapter
from reveal.adapters.ssl.adapter import SSLAdapter


def _write_cert(path, days_left, cn='file.example.com'):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=100))
            .not_valid_after(now + timedelta(days=days_left, hours=1))
            .sign(key, hashes.SHA256()))
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(path)


def _reveal(*args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-m', 'reveal', *args], capture_output=True,
                          text=True, encoding='utf-8', timeout=60, env=env)


def _fake_health(statuses):
    def fake(host, port, warn_days=30, critical_days=7, advanced=False, probe_http=False, severity=None):
        return {'type': 'ssl_check', 'host': host, 'status': statuses[host], 'checks': []}
    return fake


@pytest.mark.parametrize('statuses, expected', [
    ({'a.example.com': 'pass', 'b.example.com': 'pass'}, 0),
    ({'a.example.com': 'pass', 'b.example.com': 'warning'}, 1),
    ({'a.example.com': 'warning', 'b.example.com': 'failure'}, 2),
])
def test_nginx_batch_exit_code_is_0_1_2(statuses, expected):
    adapter = SSLAdapter.__new__(SSLAdapter)
    with patch.object(ssl_adapter, 'check_ssl_health', side_effect=_fake_health(statuses)):
        result = adapter._batch_check_domains(sorted(statuses), source='/etc/nginx/x.conf')
    assert result['exit_code'] == expected


def test_batch_check_from_nginx_summary_warning_exits_1():
    results = [{'status': 'pass'}, {'status': 'warning'}]
    assert ssl_adapter._build_batch_summary(results, '/etc/nginx/x.conf')['exit_code'] == 1


def test_cert_file_check_warning_exits_1(tmp_path):
    pem = _write_cert(tmp_path / 'soon.pem', days_left=19)
    result = SSLAdapter(f'ssl://file://{pem}')._check_cert_file(pem, warn_days=30, critical_days=7)
    assert result['status'] == 'warning'
    assert result['exit_code'] == 1


def test_local_certs_warning_exits_1(tmp_path):
    pem = _write_cert(tmp_path / 'soon.pem', days_left=19, cn='soon.example.com')
    conf = tmp_path / 'site.conf'
    conf.write_text('server {\n  listen 443 ssl;\n  server_name soon.example.com;\n'
                    f'  ssl_certificate {pem};\n  ssl_certificate_key {pem};\n}}\n', encoding='utf-8')
    result = SSLAdapter(f'ssl://nginx://{conf}')._check_nginx_cert_files()
    assert result['status'] == 'warning'
    assert result['exit_code'] == 1


def test_cli_cert_file_check_warning_process_exit_is_1(tmp_path):
    pem = _write_cert(tmp_path / 'soon.pem', days_left=19)
    r = _reveal(f'ssl://file://{pem}', '--check')
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert 'Exit code: 1' in r.stdout


def test_nginx_batch_next_steps_name_a_command_that_exists():
    adapter = SSLAdapter.__new__(SSLAdapter)
    results = [{'host': 'a.example.com', 'status': 'warning', 'checks': []}]
    steps = adapter._generate_batch_next_steps(results, 0, 1, False, False, '/etc/nginx/x.conf')
    joined = '\n'.join(steps)
    assert '--from-nginx' not in joined
    assert "reveal 'ssl://nginx:///etc/nginx/x.conf' --check --validate-nginx" in joined


def test_nginx_batch_next_steps_validate_hint_does_not_depend_on_the_path_spelling():
    adapter = SSLAdapter.__new__(SSLAdapter)
    results = [{'host': 'a.example.com', 'status': 'warning', 'checks': []}]
    steps = adapter._generate_batch_next_steps(results, 0, 1, False, False, '/srv/sites.conf')
    assert any('--validate-nginx' in s for s in steps)


class _FakeVerifiedSock:
    """A verified TLS socket: getpeercert() is the ssl module dict, which has no signatureAlgorithm."""

    def __init__(self, der):
        self._der = der

    def getpeercert(self, binary_form=False):
        if binary_form:
            return self._der
        return {'subject': ((('commonName', 'v.example.com'),),),
                'issuer': ((('organizationName', 'Example CA'),),),
                'notBefore': 'Jan  1 00:00:00 2026 GMT', 'notAfter': 'Jan  1 00:00:00 2036 GMT',
                'serialNumber': '01', 'version': 3, 'subjectAltName': (('DNS', 'v.example.com'),)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_verified_fetch_reports_the_signature_algorithm(tmp_path):
    """CB3: a certificate that verifies came back with signature_algorithm None, so the
    advanced signature_algorithm check always said 'Unknown' and the SHA-1 warning could not fire."""
    from contextlib import nullcontext
    from reveal.adapters.ssl.certificate import SSLFetcher, _check_signature_algorithm
    pem_path = _write_cert(tmp_path / 'v.pem', days_left=200, cn='v.example.com')
    der = x509.load_pem_x509_certificate((tmp_path / 'v.pem').read_bytes()).public_bytes(serialization.Encoding.DER)

    class _Ctx:
        def wrap_socket(self, sock, server_hostname=None):
            return _FakeVerifiedSock(der)

    with patch('reveal.adapters.ssl.certificate.ssl.create_default_context', return_value=_Ctx()), \
            patch('reveal.adapters.ssl.certificate.socket.create_connection', return_value=nullcontext()):
        leaf, chain, verification = SSLFetcher().fetch_certificate_with_verification('v.example.com')
    assert verification['verified'] is True
    assert leaf.signature_algorithm == 'SHA256'
    check, _failed = _check_signature_algorithm(leaf)
    assert check['status'] == 'pass'
