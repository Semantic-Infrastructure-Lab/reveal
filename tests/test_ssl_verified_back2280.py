"""BACK-2280, BACK-2316: ssl:// reports one verification key, and hostname_match is the name's own answer.

``verified`` is true only when the default-context handshake succeeded, which needs the chain
AND the hostname to pass, so the overview's old ``chain_valid`` named it wrongly
(wrong.host.badssl.com has a valid chain and read ``chain_valid: false``). The overview, /chain
and /full now spell it ``verified``. ``hostname_match`` used to be false on any verification
failure, because ``ssl.CertificateError`` is ``SSLCertVerificationError`` and also catches an
untrusted chain; it is now computed from the certificate that came back.
"""
import ssl
from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from reveal.adapters.ssl.adapter import SSLAdapter
from reveal.adapters.ssl.certificate import CertificateInfo, SSLFetcher

pytestmark = pytest.mark.component


def _leaf(*san):
    now = datetime(2026, 1, 1)
    return CertificateInfo(
        subject={'commonName': san[0] if san else ''}, issuer={'organizationName': 'Test CA'},
        not_before=now, not_after=now + timedelta(days=365), serial_number='01', version=3,
        san=list(san))


class _FailingContext:
    def __init__(self, error):
        self._error = error

    def wrap_socket(self, sock, server_hostname=None):
        raise self._error


def _fetch(host, error, leaf):
    with patch('reveal.adapters.ssl.certificate.ssl.create_default_context',
               return_value=_FailingContext(error)), \
            patch('reveal.adapters.ssl.certificate.socket.create_connection', return_value=nullcontext()), \
            patch.object(SSLFetcher, 'fetch_certificate', return_value=(leaf, [])):
        return SSLFetcher().fetch_certificate_with_verification(host)[2]


def _verification_error(message, verify_code):
    error = ssl.SSLCertVerificationError(1, message)
    error.verify_code, error.verify_message = verify_code, message
    return error


def test_an_untrusted_chain_does_not_say_the_hostname_is_wrong():
    """untrusted-root.badssl.com: the name is covered, the chain is not trusted."""
    error = _verification_error('self-signed certificate in certificate chain', 19)
    verification = _fetch('a.example.test', error, _leaf('a.example.test'))
    assert verification['verified'] is False
    assert verification['hostname_match'] is True
    assert 'self-signed' in verification['error']


def test_a_name_the_certificate_does_not_cover_is_a_mismatch():
    error = _verification_error("Hostname mismatch, certificate is not valid for 'a.example.test'", 62)
    verification = _fetch('a.example.test', error, _leaf('other.example.test'))
    assert verification['verified'] is False
    assert verification['hostname_match'] is False


def test_a_wildcard_covers_one_label_when_the_chain_fails():
    error = _verification_error('unable to get local issuer certificate', 20)
    assert _fetch('a.example.test', error, _leaf('*.example.test'))['hostname_match'] is True
    assert _fetch('a.b.example.test', error, _leaf('*.example.test'))['hostname_match'] is False


def test_a_non_certificate_ssl_failure_still_computes_the_name_from_the_certificate():
    verification = _fetch('a.example.test', ssl.SSLError('handshake failure'), _leaf('a.example.test'))
    assert verification['verified'] is False and verification['hostname_match'] is True


@pytest.mark.parametrize('verification, expected', [
    ({'verified': True, 'hostname_match': True, 'error': None}, True),
    ({'verified': False, 'hostname_match': True, 'error': 'self-signed'}, False),
    (None, False),
])
def test_the_overview_spells_the_handshake_result_verified(verification, expected):
    adapter = SSLAdapter.__new__(SSLAdapter)
    adapter._verification = verification
    built = adapter._build_verification()
    assert built['verified'] is expected
    assert 'chain_valid' not in built
    assert set(built) == {'verified', 'hostname_match', 'error'}


def test_the_schema_declares_the_key_the_overview_emits():
    schema = SSLAdapter.get_schema()
    overview = next(t for t in schema['output_types'] if t['type'] == 'ssl_certificate')
    declared = overview['schema']['properties']['verification']['properties']
    assert 'verified' in declared and 'chain_valid' not in declared
    assert 'verified' in overview['example']['verification']
    assert 'chain_valid' not in overview['example']['verification']
