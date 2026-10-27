"""BACK-2286: ssl://file://<pem>/<element> reaches the element.

Everything after ``file://`` was taken as the path, so ``ssl://file:///x/bundle.pem/chain`` failed
with "Not a directory: .../bundle.pem/chain", and the extra certificates of a PEM bundle were only
counted (``chain_certs``). The live host element names now work on a file too.
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

ELEMENTS = ('san', 'chain', 'issuer', 'subject', 'dates', 'full')


def _cert_pem(common_name):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=10))
            .not_valid_after(now + timedelta(days=200))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM)


def _reveal(*args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-m', 'reveal', *args], capture_output=True,
                          text=True, encoding='utf-8', timeout=60, env=env)


@pytest.fixture(scope='module')
def bundle(tmp_path_factory):
    path = tmp_path_factory.mktemp('ssl') / 'bundle.pem'
    path.write_bytes(_cert_pem('leaf.example.com') + _cert_pem('Intermediate CA'))
    return path.as_posix()


def test_chain_element_of_a_bundle_lists_the_extra_certificates(bundle):
    r = _reveal(f'ssl://file://{bundle}/chain', '--format=json')
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data['type'] == 'ssl_chain'
    assert data['leaf']['common_name'] == 'leaf.example.com'
    assert [c['common_name'] for c in data['chain']] == ['Intermediate CA']
    assert data['chain_length'] == 2
    assert data['file_path'] == bundle


def test_chain_element_text_names_the_file_and_the_intermediate(bundle):
    r = _reveal(f'ssl://file://{bundle}/chain')
    assert r.returncode == 0, r.stderr
    assert 'Traceback' not in r.stderr
    assert bundle in r.stdout and 'None' not in r.stdout
    assert 'Intermediate CA' in r.stdout


@pytest.mark.parametrize('element', ELEMENTS)
def test_every_host_element_works_on_a_file(bundle, element):
    text = _reveal(f'ssl://file://{bundle}/{element}')
    assert text.returncode == 0, text.stderr
    assert 'Traceback' not in text.stderr and 'None' not in text.stdout
    data = json.loads(_reveal(f'ssl://file://{bundle}/{element}', '--format=json').stdout)
    assert data['type'] == f'ssl_{element}'
    assert data['file_path'] == bundle


def test_unknown_element_on_a_file_is_named(bundle):
    r = _reveal(f'ssl://file://{bundle}/bogus')
    assert r.returncode != 0
    assert 'Unknown element: bogus' in r.stderr
    assert 'Not a directory' not in r.stderr


def test_whole_file_overview_is_unchanged(bundle):
    """Negative control: the overview without an element still answers the certificate."""
    data = json.loads(_reveal(f'ssl://file://{bundle}', '--format=json').stdout)
    assert data['type'] == 'ssl_certificate'
    assert data['common_name'] == 'leaf.example.com'
    assert data['chain_certs'] == 1


def test_missing_file_is_still_a_missing_file(tmp_path):
    """Negative control: an element name is split off only from an existing file."""
    missing = (tmp_path / 'nope' / 'chain').as_posix()
    adapter = SSLAdapter(f'ssl://file://{missing}')
    assert adapter._cert_file_path == missing and adapter.element is None


def test_host_element_parsing_is_unchanged():
    """Negative control: the network form still splits host from element."""
    adapter = SSLAdapter('ssl://example.com:8443/chain')
    assert (adapter.host, adapter.port, adapter.element) == ('example.com', 8443, 'chain')
