"""DNS resolution and validation utilities."""

import socket
from typing import Dict, List, Any

try:
    import dns.resolver
    import dns.exception
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False


def get_dns_records(domain: str) -> Dict[str, List[str]]:
    """Fetch DNS records for domain (A, AAAA, MX, TXT, NS, CNAME).

    Args:
        domain: Domain name to query

    Returns:
        Dict mapping record types to lists of values

    Raises:
        ImportError: If dnspython is not installed
    """
    if not HAS_DNSPYTHON:
        raise ImportError("dnspython is required for DNS operations. Install with: pip install dnspython")

    records = {}
    record_types = ['A', 'AAAA', 'MX', 'TXT', 'NS', 'CNAME', 'SOA']

    for record_type in record_types:
        try:
            answers = dns.resolver.resolve(domain, record_type)
            if record_type == 'MX':
                # MX records have priority, format as "priority hostname"
                records[record_type.lower()] = [f"{rdata.preference} {rdata.exchange}" for rdata in answers]
            else:
                records[record_type.lower()] = [str(rdata) for rdata in answers]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.exception.DNSException):
            records[record_type.lower()] = []

    return records


def get_dns_summary(domain: str) -> Dict[str, Any]:
    """Get summarized DNS information for domain.

    Args:
        domain: Domain name to query

    Returns:
        Dict with nameservers, a_records, has_mx
    """
    if not HAS_DNSPYTHON:
        return {
            'error': 'dnspython not installed',
            'nameservers': [],
            'a_records': [],
            'has_mx': False,
        }

    try:
        records = get_dns_records(domain)
        return {
            'nameservers': records.get('ns', []),
            'a_records': records.get('a', []),
            'has_mx': len(records.get('mx', [])) > 0,
            'mx_records': records.get('mx', []),
        }
    except Exception as e:
        return {
            'error': str(e),
            'nameservers': [],
            'a_records': [],
            'has_mx': False,
        }


def check_dns_resolution(domain: str) -> Dict[str, Any]:
    """Check if domain resolves to IP addresses.

    Args:
        domain: Domain name to check

    Returns:
        Check result dict
    """
    try:
        ips = socket.getaddrinfo(domain, None)
        ip_addresses = list(set(ip[4][0] for ip in ips))

        return {
            'name': 'dns_resolution',
            'status': 'pass',
            'value': f'{len(ip_addresses)} IPs',
            'threshold': 'Resolves',
            'message': f'Domain resolves to {len(ip_addresses)} IP(s): {", ".join(ip_addresses[:3])}',
            'severity': 'high',
            'details': {'ips': ip_addresses},
        }
    except socket.gaierror as e:
        return {
            'name': 'dns_resolution',
            'status': 'failure',
            'value': 'No resolution',
            'threshold': 'Resolves',
            'message': f'Domain does not resolve: {e}',
            'severity': 'critical',
        }


def check_nameserver_response(domain: str) -> Dict[str, Any]:
    """Check if authoritative nameservers respond.

    Args:
        domain: Domain name to check

    Returns:
        Check result dict
    """
    if not HAS_DNSPYTHON:
        return {
            'name': 'nameserver_response',
            'status': 'warning',
            'value': 'Skipped',
            'threshold': 'Responsive',
            'message': 'dnspython not installed',
            'severity': 'low',
        }

    try:
        # Get NS records
        ns_records = dns.resolver.resolve(domain, 'NS')
        nameservers = [str(ns) for ns in ns_records]

        if not nameservers:
            return {
                'name': 'nameserver_response',
                'status': 'failure',
                'value': 'No nameservers',
                'threshold': 'Responsive',
                'message': 'No nameservers found for domain',
                'severity': 'critical',
            }

        # Try to query first nameserver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [socket.gethostbyname(nameservers[0].rstrip('.'))]
        resolver.resolve(domain, 'A')

        return {
            'name': 'nameserver_response',
            'status': 'pass',
            'value': f'{len(nameservers)} nameservers',
            'threshold': 'Responsive',
            'message': f'Nameservers respond ({len(nameservers)} found)',
            'severity': 'medium',
        }
    except Exception as e:
        return {
            'name': 'nameserver_response',
            'status': 'failure',
            'value': 'Not responding',
            'threshold': 'Responsive',
            'message': f'Nameserver query failed: {e}',
            'severity': 'high',
        }


def check_dns_propagation(domain: str) -> Dict[str, Any]:
    """Check if all authoritative nameservers return same records.

    Args:
        domain: Domain name to check

    Returns:
        Check result dict with propagation status
    """
    if not HAS_DNSPYTHON:
        return {
            'name': 'dns_propagation',
            'status': 'warning',
            'value': 'Skipped',
            'threshold': 'Consistent',
            'message': 'dnspython not installed',
            'severity': 'low',
        }

    try:
        # Get authoritative nameservers
        ns_records = dns.resolver.resolve(domain, 'NS')
        nameservers = [str(ns).rstrip('.') for ns in ns_records]

        if not nameservers:
            return {
                'name': 'dns_propagation',
                'status': 'failure',
                'value': 'No nameservers',
                'threshold': 'Consistent',
                'message': 'No nameservers found',
                'severity': 'critical',
            }

        # Query each nameserver for A record
        a_record_responses = {}
        for nameserver in nameservers:
            resolver = dns.resolver.Resolver()
            try:
                ns_ip = socket.gethostbyname(nameserver)
                resolver.nameservers = [ns_ip]
                answers = resolver.resolve(domain, 'A')
                a_record_responses[nameserver] = sorted([str(rdata) for rdata in answers])
            except Exception as e:
                a_record_responses[nameserver] = f"Error: {e}"

        # Check if all agree
        values = [v for v in a_record_responses.values() if not isinstance(v, str) or not v.startswith("Error")]
        all_agree = len(set(tuple(v) if isinstance(v, list) else v for v in values)) == 1

        if all_agree:
            return {
                'name': 'dns_propagation',
                'status': 'pass',
                'value': 'Complete',
                'threshold': 'Consistent',
                'message': f'All {len(nameservers)} nameservers return consistent records',
                'severity': 'medium',
                'details': {
                    'nameservers_checked': len(nameservers),
                    'responses': a_record_responses,
                },
            }
        else:
            return {
                'name': 'dns_propagation',
                'status': 'warning',
                'value': 'Partial',
                'threshold': 'Consistent',
                'message': f'Inconsistent records across {len(nameservers)} nameservers (propagation in progress)',
                'severity': 'medium',
                'details': {
                    'nameservers_checked': len(nameservers),
                    'responses': a_record_responses,
                },
            }
    except Exception as e:
        return {
            'name': 'dns_propagation',
            'status': 'failure',
            'value': 'Check failed',
            'threshold': 'Consistent',
            'message': f'Propagation check failed: {e}',
            'severity': 'medium',
        }
