"""A DNS lookup that failed is not "no record" (BACK-1850).

mx/spf/dmarc caught every ``DNSException`` as a missing record, so a Timeout or a
SERVFAIL (NoNameservers) reported the domain as unable to receive mail / open to spoofing.
Only NoAnswer and NXDOMAIN are the absence of a record.
"""
from unittest.mock import patch

import pytest

dns_resolver = pytest.importorskip('dns.resolver')
dns_exception = pytest.importorskip('dns.exception')

from reveal.adapters.domain import dns as dns_checks  # noqa: E402

pytestmark = pytest.mark.component

CHECKS = {
    'mx': (dns_checks.check_mx_records, 'cannot receive email'),
    'spf': (dns_checks.check_spf_record, 'open to email spoofing'),
    'dmarc': (dns_checks.check_dmarc_record, 'spoofed emails'),
}


def _run(check, error):
    with patch.object(dns_checks, 'HAS_DNSPYTHON', True), \
            patch.object(dns_checks.dns.resolver, 'resolve', side_effect=error):
        return check('example.com')


@pytest.mark.parametrize('kind', CHECKS)
@pytest.mark.parametrize('error', [dns_exception.Timeout(), dns_resolver.NoNameservers(),
                                   dns_resolver.LifetimeTimeout(), OSError('network unreachable')],
                         ids=['timeout', 'servfail', 'lifetime', 'oserror'])
def test_a_failed_lookup_is_not_a_missing_record(kind, error):
    check, absence_claim = CHECKS[kind]
    result = _run(check, error)
    assert result['status'] == 'warning' and result['value'] == 'Check failed'
    assert absence_claim not in result['message']
    assert 'neither confirmed present nor absent' in result['message']


@pytest.mark.parametrize('kind', CHECKS)
@pytest.mark.parametrize('error', [dns_resolver.NoAnswer(), dns_resolver.NXDOMAIN()],
                         ids=['noanswer', 'nxdomain'])
def test_a_genuinely_absent_record_is_still_a_failure(kind, error):
    check, absence_claim = CHECKS[kind]
    result = _run(check, error)
    assert result['status'] == 'failure'
    assert absence_claim in result['message']
