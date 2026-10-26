"""BACK-2243: ssl://file://PEM answered honestly in text, --check and JSON.

Text output and --check raised KeyError: 'host' (the renderers assumed a network host), the JSON
suggested elements that cannot be reached through a file path (ssl://None/san), and
`--check --format=json` said "No host specified" with exit 0, an answer-less success.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from reveal.adapters.ssl.adapter import SSLAdapter


def _write_cert(path, days_left):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'file.example.com')])
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


@pytest.fixture(scope='module')
def good_pem(tmp_path_factory):
    return _write_cert(tmp_path_factory.mktemp('ssl') / 'good.pem', days_left=200)


@pytest.fixture(scope='module')
def expired_pem(tmp_path_factory):
    return _write_cert(tmp_path_factory.mktemp('ssl') / 'old.pem', days_left=-5)


def test_text_overview_of_a_file_prints_the_certificate(good_pem):
    r = _reveal(f'ssl://file://{good_pem}')
    assert r.returncode == 0, r.stderr
    assert 'Traceback' not in r.stderr and 'KeyError' not in r.stderr
    assert 'file.example.com' in r.stdout


def test_file_overview_suggests_nothing_that_cannot_run(good_pem):
    out = json.loads(_reveal(f'ssl://file://{good_pem}', '--format=json').stdout)
    blob = json.dumps(out)
    assert 'None' not in blob, 'host-based element examples leaked into file mode'
    assert f'{good_pem}/san' not in blob, 'a file path plus /element is not a reachable URI'


def test_check_of_a_good_file_passes_in_text_and_json(good_pem):
    text = _reveal(f'ssl://file://{good_pem}', '--check')
    assert text.returncode == 0, text.stderr
    assert 'Traceback' not in text.stderr
    assert good_pem in text.stdout
    data = json.loads(_reveal(f'ssl://file://{good_pem}', '--check', '--format=json').stdout)
    assert data['type'] == 'ssl_cert_file_validation'
    assert data['status'] == 'pass' and data['certs_checked'] == 1
    assert data['results'][0]['common_name'] == 'file.example.com'


def test_check_of_an_expired_file_fails_with_exit_2(expired_pem):
    r = _reveal(f'ssl://file://{expired_pem}', '--check')
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert 'EXPIRED' in r.stdout
    j = _reveal(f'ssl://file://{expired_pem}', '--check', '--format=json')
    assert j.returncode == 2
    assert json.loads(j.stdout)['status'] == 'failure'


def test_check_of_a_missing_file_is_a_failure_not_a_pass(tmp_path):
    r = _reveal(f'ssl://file://{tmp_path / "nope.pem"}', '--check', '--format=json')
    assert r.returncode == 2, (r.stdout, r.stderr)


def test_check_without_a_host_is_a_failed_answer_with_exit_code_2():
    """The 'No host specified' dict carried no exit_code, so the run exited 0."""
    adapter = SSLAdapter.__new__(SSLAdapter)
    adapter._nginx_path = None
    adapter._cert_file_path = None
    adapter.host = None
    adapter.port = 443
    result = adapter.check()
    assert result['error'] == 'No host specified'
    assert result['exit_code'] == 2
