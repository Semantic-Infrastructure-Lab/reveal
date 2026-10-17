"""DNS resolution and validation utilities."""

import logging
import socket
from typing import Dict, List, Any

try:
    import dns.resolver
    import dns.exception
    HAS_DNSPYTHON = True
    # Every named failure of a resolver call: dnspython's own errors (NoAnswer,
    # NXDOMAIN, Timeout, NoNameservers, bad names -- all DNSException) and the
    # socket errors of the plain gethostbyname() lookups made beside them.
    _DNS_ERRORS: tuple = (dns.exception.DNSException, OSError)
except ImportError:
    HAS_DNSPYTHON = False
    _DNS_ERRORS = (OSError,)


logger = logging.getLogger(__name__)


class DnsRecords(Dict[str, List[str]]):
    """Record type -> values, plus ``failed``: record type -> cause for every lookup that
    errored (timeout, SERVFAIL, bad name). Such a type maps to ``[]`` like a genuinely
    absent one, so only ``failed`` tells "none" from "could not look it up" (BACK-1862)."""

    def __init__(self) -> None:
        super().__init__()
        self.failed: Dict[str, str] = {}


def get_dns_records(domain: str) -> DnsRecords:
    """Fetch DNS records for domain (A, AAAA, MX, TXT, NS, CNAME).

    Args:
        domain: Domain name to query

    Returns:
        Dict mapping record types to lists of values; ``.failed`` names the types whose
        lookup errored rather than came back empty

    Raises:
        ImportError: If dnspython is not installed
    """
    if not HAS_DNSPYTHON:
        raise ImportError('dnspython is required for DNS operations. Install with: pip install "reveal-cli[dns]"')

    records = DnsRecords()
    record_types = ['A', 'AAAA', 'MX', 'TXT', 'NS', 'CNAME', 'SOA']

    for record_type in record_types:
        try:
            answers = dns.resolver.resolve(domain, record_type)
            if record_type == 'MX':
                # MX records have priority, format as "priority hostname"
                records[record_type.lower()] = [f"{rdata.preference} {rdata.exchange}" for rdata in answers]  # type: ignore[attr-defined]
            else:
                records[record_type.lower()] = [str(rdata) for rdata in answers]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            records[record_type.lower()] = []
        except dns.exception.DNSException as e:
            # Timeout / NoNameservers / bad name: not the absence of a record (BACK-1862)
            records[record_type.lower()] = []
            records.failed[record_type.lower()] = f'{type(e).__name__}: {e}'.rstrip(': ')

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
            'error': 'dnspython not installed (pip install "reveal-cli[dns]")',
            'nameservers': [],
            'a_records': [],
            'has_mx': False,
        }

    try:
        records = get_dns_records(domain)
        summary: Dict[str, Any] = {
            'nameservers': records.get('ns', []),
            'a_records': records.get('a', []),
            'has_mx': len(records.get('mx', [])) > 0,
            'mx_records': records.get('mx', []),
        }
        failed = getattr(records, 'failed', None)
        if failed:
            summary['lookup_failed'] = dict(failed)
        return summary
    except _DNS_ERRORS as e:
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


def _is_subdomain(domain: str) -> bool:
    """Return True if domain is a subdomain (3+ labels).

    Subdomains have no NS records of their own — NS checks should be skipped.
    Examples: stg.rfr.bz (True), rfr.bz (False), www.example.com (True).
    """
    return domain.rstrip('.').count('.') >= 2


def check_nameserver_response(domain: str) -> Dict[str, Any]:
    """Check if authoritative nameservers respond.

    Args:
        domain: Domain name to check

    Returns:
        Check result dict
    """
    if _is_subdomain(domain):
        return {
            'name': 'nameserver_response',
            'status': 'pass',
            'value': 'Skipped (subdomain)',
            'threshold': 'Responsive',
            'message': 'Subdomain — NS records belong to apex; check skipped',
            'severity': 'low',
        }

    if not HAS_DNSPYTHON:
        return {
            'name': 'nameserver_response',
            'status': 'warning',
            'value': 'Skipped',
            'threshold': 'Responsive',
            'message': 'dnspython not installed (pip install "reveal-cli[dns]")',
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
    except _DNS_ERRORS as e:
        return {
            'name': 'nameserver_response',
            'status': 'failure',
            'value': 'Not responding',
            'threshold': 'Responsive',
            'message': f'Nameserver query failed: {e}',
            'severity': 'high',
        }


def check_mx_records(domain: str) -> Dict[str, Any]:
    """Check that domain has MX records configured.

    Args:
        domain: Domain name to check

    Returns:
        Check result dict
    """
    if not HAS_DNSPYTHON:
        return {
            'name': 'mx_records',
            'status': 'warning',
            'value': 'Skipped',
            'threshold': 'MX configured',
            'message': 'dnspython not installed (pip install "reveal-cli[dns]")',
            'severity': 'medium',
        }
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        mx_records = [f"{r.preference} {r.exchange}" for r in answers]
        return {
            'name': 'mx_records',
            'status': 'pass',
            'value': f'{len(mx_records)} records',
            'threshold': 'MX configured',
            'message': f'MX configured ({len(mx_records)} record{"s" if len(mx_records) != 1 else ""})',
            'severity': 'medium',
            'details': {'mx_records': mx_records},
        }
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return {
            'name': 'mx_records',
            'status': 'failure',
            'value': 'None',
            'threshold': 'MX configured',
            'message': 'No MX records — domain cannot receive email',
            'severity': 'high',
        }
    except _DNS_ERRORS as e:
        # A timeout, SERVFAIL or malformed name is not "no record": say the lookup failed
        # (BACK-1850). NoAnswer/NXDOMAIN above are the genuine absence.
        return {
            'name': 'mx_records',
            'status': 'warning',
            'value': 'Check failed',
            'threshold': 'MX configured',
            'message': f'MX check failed: lookup error ({type(e).__name__}: {e}), so the record is neither confirmed present nor absent',
            'severity': 'medium',
        }


def check_spf_record(domain: str) -> Dict[str, Any]:
    """Check that domain has a valid SPF TXT record.

    Args:
        domain: Domain name to check

    Returns:
        Check result dict
    """
    if not HAS_DNSPYTHON:
        return {
            'name': 'spf_record',
            'status': 'warning',
            'value': 'Skipped',
            'threshold': 'SPF present',
            'message': 'dnspython not installed (pip install "reveal-cli[dns]")',
            'severity': 'medium',
        }
    try:
        answers = dns.resolver.resolve(domain, 'TXT')
        spf_records = [
            str(r).strip('"') for r in answers
            if str(r).strip('"').startswith('v=spf1')
        ]

        if len(spf_records) == 0:
            return {
                'name': 'spf_record',
                'status': 'failure',
                'value': 'Missing',
                'threshold': 'SPF present',
                'message': 'No SPF record — domain is open to email spoofing',
                'severity': 'high',
            }
        if len(spf_records) > 1:
            return {
                'name': 'spf_record',
                'status': 'warning',
                'value': 'Multiple',
                'threshold': '1 SPF record',
                'message': f'Multiple SPF records ({len(spf_records)}) — RFC 7208 requires exactly one',
                'severity': 'medium',
                'details': {'spf_records': spf_records},
            }
        record = spf_records[0]
        return {
            'name': 'spf_record',
            'status': 'pass',
            'value': record[:50] + ('...' if len(record) > 50 else ''),
            'threshold': 'SPF present',
            'message': 'SPF record found',
            'severity': 'medium',
            'details': {'spf_record': record},
        }
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return {
            'name': 'spf_record',
            'status': 'failure',
            'value': 'Missing',
            'threshold': 'SPF present',
            'message': 'No SPF record — domain is open to email spoofing',
            'severity': 'high',
        }
    except _DNS_ERRORS as e:
        # A timeout, SERVFAIL or malformed name is not "no record": say the lookup failed
        # (BACK-1850). NoAnswer/NXDOMAIN above are the genuine absence.
        return {
            'name': 'spf_record',
            'status': 'warning',
            'value': 'Check failed',
            'threshold': 'SPF present',
            'message': f'SPF check failed: lookup error ({type(e).__name__}: {e}), so the record is neither confirmed present nor absent',
            'severity': 'medium',
        }


def check_dmarc_record(domain: str) -> Dict[str, Any]:
    """Check that domain has a DMARC TXT record at _dmarc.DOMAIN.

    Args:
        domain: Domain name to check

    Returns:
        Check result dict
    """
    if not HAS_DNSPYTHON:
        return {
            'name': 'dmarc_record',
            'status': 'warning',
            'value': 'Skipped',
            'threshold': 'DMARC present',
            'message': 'dnspython not installed (pip install "reveal-cli[dns]")',
            'severity': 'medium',
        }
    dmarc_domain = f'_dmarc.{domain}'
    try:
        answers = dns.resolver.resolve(dmarc_domain, 'TXT')
        dmarc_records = [
            str(r).strip('"') for r in answers
            if 'v=DMARC1' in str(r)
        ]

        if not dmarc_records:
            return {
                'name': 'dmarc_record',
                'status': 'failure',
                'value': 'Missing',
                'threshold': 'DMARC present',
                'message': 'No DMARC record — spoofed emails reach inboxes undetected',
                'severity': 'medium',
            }

        record = dmarc_records[0]
        policy = 'none'
        for part in record.split(';'):
            part = part.strip()
            if part.startswith('p='):
                policy = part[2:].strip()
                break

        if policy == 'none':
            return {
                'name': 'dmarc_record',
                'status': 'warning',
                'value': 'p=none',
                'threshold': 'p=quarantine or p=reject',
                'message': 'DMARC present but p=none (monitoring only — no enforcement)',
                'severity': 'medium',
                'details': {'dmarc_record': record, 'policy': policy},
            }
        return {
            'name': 'dmarc_record',
            'status': 'pass',
            'value': f'p={policy}',
            'threshold': 'p=quarantine or p=reject',
            'message': f'DMARC enforced (p={policy})',
            'severity': 'medium',
            'details': {'dmarc_record': record, 'policy': policy},
        }
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return {
            'name': 'dmarc_record',
            'status': 'failure',
            'value': 'Missing',
            'threshold': 'DMARC present',
            'message': 'No DMARC record — spoofed emails reach inboxes undetected',
            'severity': 'medium',
        }
    except _DNS_ERRORS as e:
        # A timeout, SERVFAIL or malformed name is not "no record": say the lookup failed
        # (BACK-1850). NoAnswer/NXDOMAIN above are the genuine absence.
        return {
            'name': 'dmarc_record',
            'status': 'warning',
            'value': 'Check failed',
            'threshold': 'DMARC present',
            'message': f'DMARC check failed: lookup error ({type(e).__name__}: {e}), so the record is neither confirmed present nor absent',
            'severity': 'medium',
        }


def check_email_dns(domain: str) -> List[Dict[str, Any]]:
    """Run all email DNS health checks (MX, SPF, DMARC).

    Args:
        domain: Domain name to check

    Returns:
        List of check result dicts
    """
    return [
        check_mx_records(domain),
        check_spf_record(domain),
        check_dmarc_record(domain),
    ]


def _dns_propagation_result(nameservers: List[str], responses: Dict[str, List[str] | str]) -> Dict[str, Any]:
    """Compare complete answers while retaining failed-observation evidence."""
    # A failed lookup is not an observation of agreement or disagreement.
    values = [v for v in responses.values() if isinstance(v, list)]
    failed = len(nameservers) - len(values)
    all_agree = not failed and len(set(tuple(v) for v in values)) == 1
    if failed:
        message = (f'Incomplete DNS observation: {len(values)} of {len(nameservers)} '
                   f'nameservers responded; {failed} lookup(s) failed; '
                   'consistency could not be established')
    elif all_agree:
        message = f'All {len(nameservers)} nameservers return consistent records'
    else:
        message = f'Inconsistent records across {len(nameservers)} nameservers (propagation in progress)'

    return {
        'name': 'dns_propagation',
        'status': 'pass' if all_agree else 'warning',
        'value': 'Complete' if all_agree else 'Partial',
        'threshold': 'Consistent',
        'message': message,
        'severity': 'medium',
        'details': {
            'nameservers_checked': len(nameservers),
            'nameservers_responded': len(values),
            'nameservers_failed': failed,
            'responses': responses,
        },
    }


def check_dns_propagation(domain: str) -> Dict[str, Any]:
    """Check if all authoritative nameservers return same records.

    Args:
        domain: Domain name to check

    Returns:
        Check result dict with propagation status
    """
    if _is_subdomain(domain):
        return {
            'name': 'dns_propagation',
            'status': 'pass',
            'value': 'Skipped (subdomain)',
            'threshold': 'Consistent',
            'message': 'Subdomain — NS propagation check applies to apex only; check skipped',
            'severity': 'low',
        }

    if not HAS_DNSPYTHON:
        return {
            'name': 'dns_propagation',
            'status': 'warning',
            'value': 'Skipped',
            'threshold': 'Consistent',
            'message': 'dnspython not installed (pip install "reveal-cli[dns]")',
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
        a_record_responses: Dict[str, List[str] | str] = {}
        for nameserver in nameservers:
            try:
                resolver = dns.resolver.Resolver()
                ns_ip = socket.gethostbyname(nameserver)
                resolver.nameservers = [ns_ip]
                answers = resolver.resolve(domain, 'A')
                a_record_responses[nameserver] = sorted([str(rdata) for rdata in answers])
            except _DNS_ERRORS as e:
                logger.warning("DNS propagation check failed for %s: %s", nameserver, e)
                a_record_responses[nameserver] = f"Error: {e}"

        return _dns_propagation_result(nameservers, a_record_responses)
    except _DNS_ERRORS as e:
        return {
            'name': 'dns_propagation',
            'status': 'failure',
            'value': 'Check failed',
            'threshold': 'Consistent',
            'message': f'Propagation check failed: {e}',
            'severity': 'medium',
        }


def _query_ns_for_ns_records(ns_hostname: str, domain: str) -> Dict[str, Any]:
    """Query a specific nameserver directly for the domain's NS records.

    Args:
        ns_hostname: Nameserver to query (e.g., 'ns1.example.com')
        domain: Domain to query for (e.g., 'example.com')

    Returns:
        Dict with keys: ip (str|None), ns_records (list[str]), status (str), error (str|None)
    """
    result: Dict[str, Any] = {
        'nameserver': ns_hostname,
        'ip': None,
        'ns_records': [],
        'status': 'ok',
        'error': None,
    }
    try:
        ip = socket.gethostbyname(ns_hostname.rstrip('.'))
        result['ip'] = ip
    except socket.gaierror as e:
        result['status'] = 'unreachable'
        result['error'] = f'Cannot resolve IP: {e}'
        return result

    try:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [result['ip']]
        resolver.lifetime = 5.0
        answers = resolver.resolve(domain, 'NS')
        result['ns_records'] = sorted(str(rdata).rstrip('.').lower() for rdata in answers)
    except dns.exception.Timeout:
        result['status'] = 'no_response'
        result['error'] = 'Query timed out'
    except _DNS_ERRORS as e:
        result['status'] = 'query_failed'
        result['error'] = str(e)

    return result


def check_ns_authority(domain: str) -> Dict[str, Any]:
    """Cross-query each authoritative NS to detect stale or orphaned entries.

    Queries each registered NS server directly for the domain's NS records
    and compares results. An orphaned NS is one that cannot be reached or
    returns NS records inconsistent with the consensus.

    Real-world use case: a domain may have an NS record pointing to a host
    that is no longer authoritative — finding this manually requires multiple
    raw dig calls. This check surfaces that class of problem automatically.

    Args:
        domain: Domain name to audit

    Returns:
        Dict with type 'domain_ns_audit', full per-server results, orphaned list,
        consensus NS set, and overall status
    """
    if not HAS_DNSPYTHON:
        return {
            'type': 'domain_ns_audit',
            'domain': domain,
            'status': 'skipped',
            'message': 'dnspython not installed (pip install "reveal-cli[dns]")',
            'registered_nameservers': [],
            'servers': [],
            'consensus_ns_records': [],
            'orphaned': [],
        }

    try:
        ns_answers = dns.resolver.resolve(domain, 'NS')
        registered_nameservers = sorted(str(rr).rstrip('.').lower() for rr in ns_answers)
    except _DNS_ERRORS as e:
        return {
            'type': 'domain_ns_audit',
            'domain': domain,
            'status': 'error',
            'message': f'Failed to resolve NS records: {e}',
            'registered_nameservers': [],
            'servers': [],
            'consensus_ns_records': [],
            'orphaned': [],
        }

    if not registered_nameservers:
        return {
            'type': 'domain_ns_audit',
            'domain': domain,
            'status': 'error',
            'message': 'No NS records found for domain',
            'registered_nameservers': [],
            'servers': [],
            'consensus_ns_records': [],
            'orphaned': [],
        }

    # Query each NS server directly
    servers = [_query_ns_for_ns_records(ns, domain) for ns in registered_nameservers]

    # Build consensus: the NS set returned by the most servers that responded
    from collections import Counter
    responding = [tuple(s['ns_records']) for s in servers if s['ns_records']]
    consensus_ns_records: List[str] = []
    if responding:
        most_common = Counter(responding).most_common(1)[0][0]
        consensus_ns_records = list(most_common)

    # Determine per-server agreement with consensus
    for server in servers:
        if server['ns_records']:
            server['agrees_with_consensus'] = (
                sorted(server['ns_records']) == sorted(consensus_ns_records)
            )
        else:
            server['agrees_with_consensus'] = False

    # Find orphaned: registered NS servers not in the consensus NS set
    orphaned = [ns for ns in registered_nameservers if ns not in consensus_ns_records]

    # Determine unreachable servers
    unreachable = [s['nameserver'] for s in servers if s['status'] in ('unreachable', 'no_response')]

    # Overall status
    if orphaned:
        overall_status = 'critical'
        summary = (f'{len(orphaned)} orphaned NS record(s) detected: '
                   f'{", ".join(orphaned)}')
    elif unreachable:
        overall_status = 'warning'
        summary = (f'{len(unreachable)} NS server(s) unreachable: '
                   f'{", ".join(unreachable)}')
    elif any(not s['agrees_with_consensus'] for s in servers):
        overall_status = 'warning'
        summary = 'NS servers return inconsistent records'
    else:
        overall_status = 'ok'
        summary = f'All {len(servers)} NS servers agree on {len(consensus_ns_records)} records'

    return {
        'type': 'domain_ns_audit',
        'domain': domain,
        'status': overall_status,
        'summary': summary,
        'registered_nameservers': registered_nameservers,
        'servers': servers,
        'consensus_ns_records': consensus_ns_records,
        'orphaned': orphaned,
        'unreachable': unreachable,
    }
