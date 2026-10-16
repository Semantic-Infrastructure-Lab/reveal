"""get_dns_records: a lookup that errored is not an empty record list (BACK-1862).

Every DNSException, Timeout and NoNameservers included, became ``[]``, so a failed MX lookup
listed as "none" and get_dns_summary said ``has_mx: False``. Same class as BACK-1850.
"""
import io
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest

dns_resolver = pytest.importorskip('dns.resolver')
dns_exception = pytest.importorskip('dns.exception')

from reveal.adapters.domain import dns as dns_checks  # noqa: E402
from reveal.adapters.domain.adapter import DomainAdapter  # noqa: E402
from reveal.adapters.domain.renderer import DomainRenderer  # noqa: E402

pytestmark = pytest.mark.component


class _A:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return self.text


def _resolver(errors):
    """resolve() that raises errors[rtype] when set, NoAnswer for the rest, one A record."""
    def resolve(domain, rtype):
        if rtype in errors:
            raise errors[rtype]
        if rtype == 'A':
            return [_A('192.0.2.1')]
        raise dns_resolver.NoAnswer()
    return resolve


def _records(errors):
    with patch.object(dns_checks, 'HAS_DNSPYTHON', True), \
            patch.object(dns_checks.dns.resolver, 'resolve', side_effect=_resolver(errors)):
        return dns_checks.get_dns_records('example.com')


@pytest.mark.parametrize('error', [dns_exception.Timeout(), dns_resolver.NoNameservers(),
                                   dns_resolver.LifetimeTimeout()],
                         ids=['timeout', 'servfail', 'lifetime'])
def test_a_failed_lookup_is_recorded_not_just_empty(error):
    records = _records({'MX': error})
    assert records['mx'] == []
    assert set(records.failed) == {'mx'}
    assert type(error).__name__ in records.failed['mx']


def test_absent_records_are_not_failures():
    records = _records({'MX': dns_resolver.NXDOMAIN()})
    assert records['mx'] == []
    assert records.failed == {}
    assert records['a'] == ['192.0.2.1']


def test_summary_does_not_claim_no_mx_when_the_lookup_failed():
    with patch.object(dns_checks, 'HAS_DNSPYTHON', True), \
            patch.object(dns_checks.dns.resolver, 'resolve',
                         side_effect=_resolver({'MX': dns_exception.Timeout()})):
        summary = dns_checks.get_dns_summary('example.com')
    assert 'mx' in summary['lookup_failed']


def test_summary_without_failures_has_no_lookup_failed_key():
    with patch.object(dns_checks, 'HAS_DNSPYTHON', True), \
            patch.object(dns_checks.dns.resolver, 'resolve', side_effect=_resolver({})):
        assert 'lookup_failed' not in dns_checks.get_dns_summary('example.com')


def _render(fn, result):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(result)
    return buf.getvalue()


def test_dns_records_result_and_text_name_the_failed_lookup():
    adapter = DomainAdapter('example.com')
    with patch.object(dns_checks, 'HAS_DNSPYTHON', True), \
            patch('reveal.adapters.domain.adapter.get_dns_records',
                  return_value=_records({'MX': dns_exception.Timeout()})):
        result = adapter._get_dns_records()
    assert 'mx' in result['lookup_failed']
    assert 'MX lookup failed' in _render(DomainRenderer._render_domain_dns_records, result)


def test_overview_text_does_not_print_mx_none_for_a_failed_lookup():
    dns = {'nameservers': [], 'a_records': [], 'has_mx': False,
           'lookup_failed': {'mx': 'Timeout: The DNS operation timed out'}}
    out = _render(DomainRenderer._print_dns_section, dns)
    assert 'Lookup failed' in out and 'None' not in out.split('MX Records:')[1]
