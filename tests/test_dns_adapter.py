"""Tests for reveal.adapters.domain.dns module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import socket


class TestGetDnsRecords:
    """Tests for get_dns_records function."""

    def test_get_dns_records_no_dnspython(self):
        """Test get_dns_records raises ImportError when dnspython not installed."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', False):
            from reveal.adapters.domain.dns import get_dns_records

            with pytest.raises(ImportError, match="dnspython is required"):
                get_dns_records('example.com')

    def test_get_dns_records_success(self):
        """Test get_dns_records returns all record types."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import get_dns_records
            import reveal.adapters.domain.dns

            # Mock dns.resolver.resolve
            mock_resolve = Mock()

            def resolve_side_effect(domain, record_type):
                if record_type == 'A':
                    return [Mock(__str__=lambda _: '1.2.3.4')]
                elif record_type == 'AAAA':
                    return [Mock(__str__=lambda _: '2001:db8::1')]
                elif record_type == 'MX':
                    mock_mx = Mock()
                    mock_mx.preference = 10
                    mock_mx.exchange = 'mail.example.com'
                    return [mock_mx]
                elif record_type == 'TXT':
                    return [Mock(__str__=lambda _: 'v=spf1 include:example.com')]
                elif record_type == 'NS':
                    return [Mock(__str__=lambda _: 'ns1.example.com')]
                elif record_type == 'CNAME':
                    return [Mock(__str__=lambda _: 'www.example.com')]
                elif record_type == 'SOA':
                    return [Mock(__str__=lambda _: 'ns1.example.com admin.example.com 1 3600 600 604800 86400')]
                return []

            mock_resolve.side_effect = resolve_side_effect

            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', mock_resolve):
                records = get_dns_records('example.com')

                assert 'a' in records
                assert '1.2.3.4' in records['a']
                assert 'aaaa' in records
                assert 'mx' in records
                assert '10 mail.example.com' in records['mx']
                assert 'txt' in records
                assert 'ns' in records
                assert 'cname' in records
                assert 'soa' in records

    def test_get_dns_records_no_answer(self):
        """Test get_dns_records handles NoAnswer exception."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import get_dns_records
            import reveal.adapters.domain.dns

            # Mock dns.resolver.resolve to raise NoAnswer
            def resolve_side_effect(domain, record_type):
                import dns.resolver
                raise dns.resolver.NoAnswer()

            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', side_effect=resolve_side_effect):
                records = get_dns_records('example.com')

                # All records should be empty lists
                for record_type in ['a', 'aaaa', 'mx', 'txt', 'ns', 'cname', 'soa']:
                    assert records[record_type] == []

    def test_get_dns_records_nxdomain(self):
        """Test get_dns_records handles NXDOMAIN exception."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import get_dns_records
            import reveal.adapters.domain.dns

            # Mock dns.resolver.resolve to raise NXDOMAIN
            def resolve_side_effect(domain, record_type):
                import dns.resolver
                raise dns.resolver.NXDOMAIN()

            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', side_effect=resolve_side_effect):
                records = get_dns_records('nonexistent.example.com')

                # All records should be empty lists
                for record_type in ['a', 'aaaa', 'mx', 'txt', 'ns', 'cname', 'soa']:
                    assert records[record_type] == []

    def test_get_dns_records_dns_exception(self):
        """Test get_dns_records handles generic DNSException."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import get_dns_records
            import reveal.adapters.domain.dns

            # Mock dns.resolver.resolve to raise DNSException
            def resolve_side_effect(domain, record_type):
                import dns.exception
                raise dns.exception.DNSException()

            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', side_effect=resolve_side_effect):
                records = get_dns_records('example.com')

                # All records should be empty lists
                for record_type in ['a', 'aaaa', 'mx', 'txt', 'ns', 'cname', 'soa']:
                    assert records[record_type] == []


class TestGetDnsSummary:
    """Tests for get_dns_summary function."""

    def test_get_dns_summary_no_dnspython(self):
        """Test get_dns_summary returns error when dnspython not installed."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', False):
            from reveal.adapters.domain.dns import get_dns_summary

            result = get_dns_summary('example.com')

            assert result['error'] == 'dnspython not installed'
            assert result['nameservers'] == []
            assert result['a_records'] == []
            assert result['has_mx'] is False

    def test_get_dns_summary_success(self):
        """Test get_dns_summary returns summary info."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import get_dns_summary

            mock_records = {
                'ns': ['ns1.example.com', 'ns2.example.com'],
                'a': ['1.2.3.4'],
                'mx': ['10 mail.example.com']
            }

            with patch('reveal.adapters.domain.dns.get_dns_records', return_value=mock_records):
                result = get_dns_summary('example.com')

                assert result['nameservers'] == ['ns1.example.com', 'ns2.example.com']
                assert result['a_records'] == ['1.2.3.4']
                assert result['has_mx'] is True
                assert result['mx_records'] == ['10 mail.example.com']

    def test_get_dns_summary_no_mx(self):
        """Test get_dns_summary with no MX records."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import get_dns_summary

            mock_records = {
                'ns': ['ns1.example.com'],
                'a': ['1.2.3.4'],
                'mx': []  # No MX records
            }

            with patch('reveal.adapters.domain.dns.get_dns_records', return_value=mock_records):
                result = get_dns_summary('example.com')

                assert result['has_mx'] is False

    def test_get_dns_summary_exception(self):
        """Test get_dns_summary handles exceptions."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import get_dns_summary

            with patch('reveal.adapters.domain.dns.get_dns_records', side_effect=Exception('DNS error')):
                result = get_dns_summary('example.com')

                assert 'error' in result
                assert result['error'] == 'DNS error'
                assert result['nameservers'] == []
                assert result['a_records'] == []
                assert result['has_mx'] is False


class TestCheckDnsResolution:
    """Tests for check_dns_resolution function."""

    def test_check_dns_resolution_success(self):
        """Test check_dns_resolution returns pass when domain resolves."""
        from reveal.adapters.domain.dns import check_dns_resolution

        mock_ips = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.2.3.4', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.2.3.5', 0)),
        ]

        with patch('socket.getaddrinfo', return_value=mock_ips):
            result = check_dns_resolution('example.com')

            assert result['name'] == 'dns_resolution'
            assert result['status'] == 'pass'
            assert '2 IPs' in result['value']
            assert result['severity'] == 'high'
            assert 'details' in result
            assert len(result['details']['ips']) == 2

    def test_check_dns_resolution_single_ip(self):
        """Test check_dns_resolution with single IP."""
        from reveal.adapters.domain.dns import check_dns_resolution

        mock_ips = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.2.3.4', 0)),
        ]

        with patch('socket.getaddrinfo', return_value=mock_ips):
            result = check_dns_resolution('example.com')

            assert result['status'] == 'pass'
            assert '1 IPs' in result['value']

    def test_check_dns_resolution_failure(self):
        """Test check_dns_resolution returns failure when domain doesn't resolve."""
        from reveal.adapters.domain.dns import check_dns_resolution

        with patch('socket.getaddrinfo', side_effect=socket.gaierror('Name or service not known')):
            result = check_dns_resolution('nonexistent.example.com')

            assert result['name'] == 'dns_resolution'
            assert result['status'] == 'failure'
            assert result['value'] == 'No resolution'
            assert result['severity'] == 'critical'
            assert 'does not resolve' in result['message']


class TestCheckNameserverResponse:
    """Tests for check_nameserver_response function."""

    def test_check_nameserver_response_no_dnspython(self):
        """Test check_nameserver_response returns warning when dnspython not installed."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', False):
            from reveal.adapters.domain.dns import check_nameserver_response

            result = check_nameserver_response('example.com')

            assert result['name'] == 'nameserver_response'
            assert result['status'] == 'warning'
            assert result['value'] == 'Skipped'
            assert 'dnspython not installed' in result['message']

    def test_check_nameserver_response_success(self):
        """Test check_nameserver_response returns pass when nameservers respond."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import check_nameserver_response
            import reveal.adapters.domain.dns

            # Mock NS records
            mock_ns_records = [Mock(__str__=lambda _: 'ns1.example.com.'), Mock(__str__=lambda _: 'ns2.example.com.')]

            # Mock resolver
            mock_resolver_instance = Mock()
            mock_resolver_class = Mock(return_value=mock_resolver_instance)

            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', return_value=mock_ns_records):
                with patch.object(reveal.adapters.domain.dns.dns.resolver, 'Resolver', mock_resolver_class):
                    with patch('socket.gethostbyname', return_value='1.2.3.4'):
                        result = check_nameserver_response('example.com')

                        assert result['name'] == 'nameserver_response'
                        assert result['status'] == 'pass'
                        assert '2 nameservers' in result['value']
                        assert 'respond' in result['message']

    def test_check_nameserver_response_no_nameservers(self):
        """Test check_nameserver_response returns failure when no nameservers found."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import check_nameserver_response
            import reveal.adapters.domain.dns

            # Mock NS records as empty
            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', return_value=[]):
                result = check_nameserver_response('example.com')

                assert result['name'] == 'nameserver_response'
                assert result['status'] == 'failure'
                assert result['value'] == 'No nameservers'
                assert 'No nameservers found' in result['message']

    def test_check_nameserver_response_query_failure(self):
        """Test check_nameserver_response returns failure when query fails."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import check_nameserver_response
            import reveal.adapters.domain.dns

            # Mock NS records
            mock_ns_records = [Mock(__str__=lambda _: 'ns1.example.com.')]

            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', return_value=mock_ns_records):
                # Mock socket.gethostbyname to raise exception
                with patch('socket.gethostbyname', side_effect=socket.gaierror('DNS lookup failed')):
                    result = check_nameserver_response('example.com')

                    assert result['name'] == 'nameserver_response'
                    assert result['status'] == 'failure'
                    assert result['value'] == 'Not responding'
                    assert 'query failed' in result['message']


class TestCheckDnsPropagation:
    """Tests for check_dns_propagation function."""

    def test_check_dns_propagation_no_dnspython(self):
        """Test check_dns_propagation returns warning when dnspython not installed."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', False):
            from reveal.adapters.domain.dns import check_dns_propagation

            result = check_dns_propagation('example.com')

            assert result['name'] == 'dns_propagation'
            assert result['status'] == 'warning'
            assert result['value'] == 'Skipped'
            assert 'dnspython not installed' in result['message']

    def test_check_dns_propagation_consistent(self):
        """Test check_dns_propagation returns pass when all nameservers agree."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import check_dns_propagation
            import reveal.adapters.domain.dns

            # Mock NS records
            mock_ns_records = [
                Mock(__str__=lambda _: 'ns1.example.com.'),
                Mock(__str__=lambda _: 'ns2.example.com.')
            ]

            # Mock A record responses (same IPs from all nameservers)
            mock_a_records = [Mock(__str__=lambda _: '1.2.3.4')]

            mock_resolver_instance = Mock()
            mock_resolver_instance.resolve.return_value = mock_a_records
            mock_resolver_class = Mock(return_value=mock_resolver_instance)

            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', return_value=mock_ns_records):
                with patch.object(reveal.adapters.domain.dns.dns.resolver, 'Resolver', mock_resolver_class):
                    with patch('socket.gethostbyname', return_value='1.2.3.4'):
                        result = check_dns_propagation('example.com')

                        assert result['name'] == 'dns_propagation'
                        assert result['status'] == 'pass'
                        assert result['value'] == 'Complete'
                        assert 'consistent' in result['message']
                        assert 'details' in result
                        assert result['details']['nameservers_checked'] == 2

    def test_check_dns_propagation_inconsistent(self):
        """Test check_dns_propagation returns warning when nameservers disagree."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import check_dns_propagation
            import reveal.adapters.domain.dns

            # Mock NS records
            mock_ns_records = [
                Mock(__str__=lambda _: 'ns1.example.com.'),
                Mock(__str__=lambda _: 'ns2.example.com.')
            ]

            # Mock different A record responses from different nameservers
            call_count = [0]

            def mock_resolve_a(domain, record_type):
                call_count[0] += 1
                if call_count[0] == 1:
                    return [Mock(__str__=lambda _: '1.2.3.4')]
                else:
                    return [Mock(__str__=lambda _: '1.2.3.5')]

            mock_resolver_instance = Mock()
            mock_resolver_instance.resolve.side_effect = mock_resolve_a
            mock_resolver_class = Mock(return_value=mock_resolver_instance)

            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', return_value=mock_ns_records):
                with patch.object(reveal.adapters.domain.dns.dns.resolver, 'Resolver', mock_resolver_class):
                    with patch('socket.gethostbyname', return_value='1.2.3.4'):
                        result = check_dns_propagation('example.com')

                        assert result['name'] == 'dns_propagation'
                        assert result['status'] == 'warning'
                        assert result['value'] == 'Partial'
                        assert 'Inconsistent' in result['message']
                        assert 'propagation in progress' in result['message']

    def test_check_dns_propagation_no_nameservers(self):
        """Test check_dns_propagation returns failure when no nameservers found."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import check_dns_propagation
            import reveal.adapters.domain.dns

            # Mock NS records as empty
            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', return_value=[]):
                result = check_dns_propagation('example.com')

                assert result['name'] == 'dns_propagation'
                assert result['status'] == 'failure'
                assert result['value'] == 'No nameservers'
                assert 'No nameservers found' in result['message']

    def test_check_dns_propagation_query_error(self):
        """Test check_dns_propagation handles individual nameserver errors."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import check_dns_propagation
            import reveal.adapters.domain.dns

            # Mock NS records
            mock_ns_records = [
                Mock(__str__=lambda _: 'ns1.example.com.'),
                Mock(__str__=lambda _: 'ns2.example.com.')
            ]

            # Mock socket.gethostbyname to fail for one nameserver
            call_count = [0]

            def mock_gethostbyname(hostname):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise socket.gaierror('DNS lookup failed')
                return '1.2.3.4'

            mock_resolver_instance = Mock()
            mock_resolver_instance.resolve.return_value = [Mock(__str__=lambda _: '1.2.3.4')]
            mock_resolver_class = Mock(return_value=mock_resolver_instance)

            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', return_value=mock_ns_records):
                with patch.object(reveal.adapters.domain.dns.dns.resolver, 'Resolver', mock_resolver_class):
                    with patch('socket.gethostbyname', side_effect=mock_gethostbyname):
                        result = check_dns_propagation('example.com')

                        # Should still succeed with partial responses
                        assert result['name'] == 'dns_propagation'
                        assert result['status'] in ['pass', 'warning']
                        assert 'details' in result

    def test_check_dns_propagation_exception(self):
        """Test check_dns_propagation returns failure when check fails."""
        with patch('reveal.adapters.domain.dns.HAS_DNSPYTHON', True):
            from reveal.adapters.domain.dns import check_dns_propagation
            import reveal.adapters.domain.dns

            # Mock dns.resolver.resolve to raise exception
            with patch.object(reveal.adapters.domain.dns.dns.resolver, 'resolve', side_effect=Exception('DNS error')):
                result = check_dns_propagation('example.com')

                assert result['name'] == 'dns_propagation'
                assert result['status'] == 'failure'
                assert result['value'] == 'Check failed'
                assert 'Propagation check failed' in result['message']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
