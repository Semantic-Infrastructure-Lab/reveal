"""Incomplete nameserver observations cannot establish DNS consistency."""
import socket
from unittest.mock import MagicMock, patch

import pytest

dns_resolver = pytest.importorskip('dns.resolver')
dns_exception = pytest.importorskip('dns.exception')

from reveal.adapters.domain import dns as dns_checks  # noqa: E402
from reveal.adapters.domain.adapter import _generate_domain_next_steps  # noqa: E402

pytestmark = pytest.mark.component


def _check(outcomes, *, host_error=None):
    resolvers = []
    for outcome in outcomes:
        resolver = MagicMock()
        if isinstance(outcome, BaseException):
            resolver.resolve.side_effect = outcome
        else:
            resolver.resolve.return_value = outcome
        resolvers.append(resolver)
    with patch.object(dns_checks, 'HAS_DNSPYTHON', True), \
            patch.object(dns_checks.dns.resolver, 'resolve', return_value=['ns1.example.com.', 'ns2.example.com.']), \
            patch.object(dns_checks.dns.resolver, 'Resolver', side_effect=resolvers), \
            patch.object(dns_checks.socket, 'gethostbyname', side_effect=host_error,
                         return_value='192.0.2.53'):
        return dns_checks.check_dns_propagation('example.com')


@pytest.mark.parametrize('error', [OSError('network unreachable'), socket.gaierror('host unavailable'),
                                   dns_exception.Timeout(), dns_resolver.NoNameservers(), dns_resolver.NoAnswer()],
                         ids=['oserror', 'gaierror', 'timeout', 'servfail', 'noanswer'])
@pytest.mark.parametrize('all_failed', [False, True])
def test_failed_observations_are_partial_not_consistent(error, all_failed):
    result = _check([error if all_failed else ['192.0.2.1'], error])
    assert result['status'] == 'warning' and result['value'] == 'Partial'
    assert 'Incomplete DNS observation' in result['message']
    assert 'propagation in progress' not in result['message']
    details = result['details']
    assert details['nameservers_checked'] == 2
    assert details['nameservers_responded'] == (0 if all_failed else 1)
    assert details['nameservers_failed'] == (2 if all_failed else 1)
    assert details['responses']['ns2.example.com'] == f'Error: {error}'
    if not all_failed:
        assert details['responses']['ns1.example.com'] == ['192.0.2.1']
    steps = _generate_domain_next_steps([result], 'example.com')
    assert any('failed nameserver lookups' in step for step in steps)
    assert not any('propagation in progress' in step for step in steps)


def test_nameserver_hostname_resolution_failure_is_also_incomplete():
    result = _check([[], []], host_error=socket.gaierror('no host address'))
    assert result['status'] == 'warning'
    assert result['details']['nameservers_responded'] == 0
    assert result['details']['nameservers_failed'] == 2
    assert 'no host address' in result['details']['responses']['ns1.example.com']


@pytest.mark.parametrize('second,expected_status,expected_message', [
    (['192.0.2.1'], 'pass', 'All 2 nameservers return consistent records'),
    (['192.0.2.2'], 'warning', 'Inconsistent records across 2 nameservers (propagation in progress)'),
])
def test_fully_observed_agreement_and_disagreement_keep_legacy_meaning(second, expected_status, expected_message):
    result = _check([['192.0.2.1'], second])
    assert result['status'] == expected_status
    assert result['message'] == expected_message
    if expected_status == 'warning':
        assert _generate_domain_next_steps([result], 'example.com') == [
            'DNS propagation in progress - wait and check again']


def test_subdomain_skip_remains_pass_without_resolver_calls():
    with patch.object(dns_checks.dns.resolver, 'resolve') as resolve:
        result = dns_checks.check_dns_propagation('www.example.com')
    resolve.assert_not_called()
    assert result['status'] == 'pass' and result['value'] == 'Skipped (subdomain)'


def test_missing_dependency_warning_does_not_claim_propagation():
    with patch.object(dns_checks, 'HAS_DNSPYTHON', False), \
            patch.object(dns_checks.dns.resolver, 'resolve') as resolve:
        result = dns_checks.check_dns_propagation('example.com')
    resolve.assert_not_called()
    assert result['status'] == 'warning' and result['value'] == 'Skipped'
    steps = _generate_domain_next_steps([result], 'example.com')
    assert any('reveal-cli[dns]' in step for step in steps)
    assert not any('propagation in progress' in step for step in steps)
