"""cPanel adapter — filesystem-based inspection of cPanel user environments.

URI scheme: cpanel://USERNAME[/element]

Elements:
    (none)          Overview: domains, SSL status summary, nginx config presence
    domains         List addon domains with docroots and home directory
    ssl             Disk cert health per domain from /var/cpanel/ssl/apache_tls/
    acl-check       nobody ACL health per domain docroot
    full-audit      Composite: ssl + acl-check + nginx ACME in one pass; exits 2 on failure

All operations are filesystem-based; no WHM API or authentication required.
Must be run as root (or with read access to /var/cpanel/userdata/).

Examples:
    reveal cpanel://USERNAME                  # Overview
    reveal cpanel://USERNAME/domains          # All domains + docroots
    reveal cpanel://USERNAME/ssl              # Disk cert health per domain
    reveal cpanel://USERNAME/acl-check        # nobody ACL on all docroots
"""

import os
import re
import socket
import sys
from typing import Dict, Any, Optional, List

# fcntl/struct/array are Unix-only; used only in _get_local_ips() for IP
# enumeration via SIOCGIFCONF ioctl. Guarded here so the module imports
# cleanly on Windows (where cPanel does not exist).
if sys.platform != 'win32':
    import array
    import fcntl
    import struct

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.query import parse_query_params
from .renderer import CpanelRenderer


# cPanel filesystem paths
CPANEL_USERDATA_DIR = "/var/cpanel/userdata"
CPANEL_SSL_DIR = "/var/cpanel/ssl/apache_tls"
NGINX_USER_CONF_DIR = "/etc/nginx/conf.d/users"

# Non-domain files that may appear in the userdata directory (cache, metadata, etc.)
_USERDATA_ARTIFACT_EXTENSIONS = ('.cache', '.yaml', '.json', '.lock', '.tmp', '.db', '.bak', '.log')


def _parse_cpanel_userdata(path: str) -> Dict[str, str]:
    """Parse a cPanel userdata file (YAML-ish key: value format).

    cPanel userdata files are a simple key: value format (not full YAML).
    Each line is either blank, a comment, or `key: value`.

    Returns:
        Dict of directive name → value.
    """
    try:
        text = open(path, 'r', encoding='utf-8', errors='replace').read()
    except OSError:
        return {}
    result: Dict[str, str] = {}
    for line in text.split('\n'):
        line = line.rstrip()
        if not line or line.startswith('#') or line.startswith('-'):
            continue
        m = re.match(r'^(\w+):\s*(.*)', line)
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result


def _list_user_domains(username: str) -> List[Dict[str, str]]:
    """Read /var/cpanel/userdata/USERNAME/ and return domain entries.

    Each file in this directory represents one domain (or subdomain).
    Files ending in `_SSL` are the SSL vhost duplicates — we skip them.
    The `main` file describes the account itself (not a domain); skipped.

    Returns:
        List of dicts with keys: domain, docroot, serveralias, type
        type is one of: main_domain | addon | subdomain | parked
    """
    userdata_dir = os.path.join(CPANEL_USERDATA_DIR, username)
    if not os.path.isdir(userdata_dir):
        return []

    entries = []
    for fname in sorted(os.listdir(userdata_dir)):
        # Skip non-domain files
        if fname in ('main', 'nobody') or fname.endswith('_SSL'):
            continue
        # Skip filesystem artifacts (.cache, .yaml, .json, etc.) — not domain entries
        if any(fname.endswith(ext) for ext in _USERDATA_ARTIFACT_EXTENSIONS):
            continue
        fpath = os.path.join(userdata_dir, fname)
        if not os.path.isfile(fpath):
            continue

        data = _parse_cpanel_userdata(fpath)
        domain = data.get('domain', fname)
        docroot = data.get('documentroot', '')
        serveralias = data.get('serveralias', '')
        # heuristic type detection
        dom_type = data.get('type', '')
        if not dom_type:
            if fname == username or '.' not in fname:
                dom_type = 'main_domain'
            elif fname.count('.') >= 2 and not fname.startswith('www.'):
                dom_type = 'subdomain'
            else:
                dom_type = 'addon'

        entries.append({
            'domain': domain,
            'docroot': docroot,
            'serveralias': serveralias,
            'type': dom_type,
        })
    return entries


def _get_disk_cert_status(domain: str) -> Dict[str, Any]:
    """Load cPanel disk cert for domain and return status dict.

    Returns dict with: status ('ok'|'missing'|'expired'|'expiring'|'error'),
    days_until_expiry, not_after (str), serial_number.
    """
    cert_path = os.path.join(CPANEL_SSL_DIR, domain, 'combined')
    if not os.path.exists(cert_path):
        return {'status': 'missing', 'cert_path': cert_path}

    try:
        from ..ssl.certificate import load_certificate_from_file
        leaf, _ = load_certificate_from_file(cert_path)
        days = leaf.days_until_expiry
        if days < 0:
            status = 'expired'
        elif days < 7:
            status = 'critical'
        elif days < 30:
            status = 'expiring'
        else:
            status = 'ok'
        return {
            'status': status,
            'cert_path': cert_path,
            'days_until_expiry': days,
            'not_after': leaf.not_after.strftime('%Y-%m-%d'),
            'serial_number': leaf.serial_number,
            'common_name': leaf.common_name,
        }
    except Exception as exc:
        return {'status': 'error', 'cert_path': cert_path, 'error': str(exc)[:80]}


def _check_docroot_acl(docroot: str) -> Dict[str, Any]:
    """Check that nobody user has read+execute access to docroot path components.

    Delegates to the nginx analyzer's _check_nobody_access utility.
    """
    from ...analyzers.nginx import _check_nobody_access
    return _check_nobody_access(docroot)


def _dns_resolves(domain: str) -> bool:
    """Return True if domain resolves in DNS, False if NXDOMAIN or lookup error."""
    try:
        socket.getaddrinfo(domain, None)
        return True
    except socket.gaierror:
        return False


def _dns_resolve_ips(domain: str) -> List[str]:
    """Return list of IPv4 addresses domain resolves to (empty list on failure)."""
    try:
        return list({info[4][0] for info in socket.getaddrinfo(domain, None, socket.AF_INET)})
    except socket.gaierror:
        return []


def _get_local_ips() -> set:
    """Return set of non-loopback IPv4 addresses bound to this host (stdlib only, Linux)."""
    if sys.platform == 'win32':
        return set()  # SIOCGIFCONF is Linux-only; caller falls back to hostname
    ips: set = set()
    try:
        max_bytes = 4096
        names = array.array('B', b'\0' * max_bytes)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            outbytes = struct.unpack('iL', fcntl.ioctl(
                s.fileno(), 0x8912,  # SIOCGIFCONF
                struct.pack('iL', max_bytes, names.buffer_info()[0])
            ))[0]
            for i in range(0, outbytes, 40):
                ip = socket.inet_ntoa(bytes(names[i + 20:i + 24]))
                if not ip.startswith('127.'):
                    ips.add(ip)
        finally:
            s.close()
    except OSError:  # ioctl unsupported or permission denied — fall back to hostname
        pass
    if not ips:
        # Fallback: resolve hostname
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith('127.'):
                    ips.add(ip)
        except OSError:  # hostname resolution failed — return empty set
            pass
    return ips


_SCHEMA_ELEMENTS = {
    '(none)': 'Overview: domain count, SSL summary, nginx config path',
    'domains': 'All addon/subdomain domains with docroots and type',
    'ssl': 'Disk cert health per domain from /var/cpanel/ssl/apache_tls/ (supports ?domain_type= query param)',
    'acl-check': 'nobody ACL status on every domain docroot (supports --only-failures)',
    'full-audit': 'Composite: ssl + acl-check + nginx ACME in one pass; exits 2 on any failure',
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'cpanel_user',
        'description': 'Overview of a cPanel user — domain count, SSL summary, nginx config presence',
        'triggered_by': 'cpanel://USERNAME (no element)',
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'cpanel_user'},
            'username': {'type': 'string'},
            'userdata_dir': {'type': 'string'},
            'userdata_accessible': {'type': 'boolean'},
            'domain_count': {'type': 'integer'},
            'nginx_config': {'type': ['string', 'null']},
            'ssl_summary': {'type': 'object', 'description': 'Counts keyed by status: ok/expiring/critical/expired/missing/error'},
            'next_steps': {'type': 'array', 'items': {'type': 'string'}},
        }},
    },
    {
        'type': 'cpanel_domains',
        'description': 'All domains for a cPanel user with docroots and type',
        'triggered_by': 'cpanel://USERNAME/domains',
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'cpanel_domains'},
            'username': {'type': 'string'},
            'domain_count': {'type': 'integer'},
            'domains': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'domain': {'type': 'string'},
                'docroot': {'type': 'string'},
                'type': {'type': 'string', 'enum': ['main', 'addon', 'subdomain']},
            }}},
        }},
    },
    {
        'type': 'cpanel_ssl',
        'description': 'Disk cert health per domain — sorted by severity (failures first)',
        'triggered_by': 'cpanel://USERNAME/ssl',
        'flags': ['--dns-verified', '--only-failures', '--format=json'],
        'query_params': {'domain_type': 'Filter to: main_domain, addon, subdomain, parked'},
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'cpanel_ssl'},
            'username': {'type': 'string'},
            'cpanel_ssl_dir': {'type': 'string'},
            'cert_count': {'type': 'integer'},
            'dns_verified': {'type': 'boolean'},
            'only_failures': {'type': 'boolean'},
            'domain_type_filter': {'type': ['string', 'null'], 'description': 'Active ?domain_type= filter, or null'},
            'summary': {'type': 'object', 'description': 'Counts by status: ok/expiring/critical/expired/missing/error (excludes nxdomain and elsewhere when dns_verified)'},
            'dns_excluded': {'type': 'object', 'description': 'NXDOMAIN-excluded domain counts by status (only when dns_verified=true)'},
            'dns_elsewhere': {'type': 'object', 'description': 'Resolves-but-not-here domain counts by status (only when dns_verified=true)'},
            'certs': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'domain': {'type': 'string'},
                'domain_type': {'type': 'string', 'enum': ['main_domain', 'addon', 'subdomain', 'parked', 'unknown']},
                'status': {'type': 'string', 'enum': ['ok', 'expiring', 'critical', 'expired', 'missing', 'error']},
                'days_until_expiry': {'type': ['number', 'null']},
                'dns_resolves': {'type': 'boolean', 'description': 'Only present when dns_verified=true; false = NXDOMAIN'},
                'dns_points_here': {'type': ['boolean', 'null'], 'description': 'Only present when dns_verified=true and domain resolves; false = points to different server'},
            }}},
            'next_steps': {'type': 'array', 'items': {'type': 'string'}},
        }},
    },
    {
        'type': 'cpanel_acl',
        'description': 'nobody ACL status on every domain docroot — required for ACME renewal',
        'triggered_by': 'cpanel://USERNAME/acl-check',
        'flags': ['--only-failures', '--format=json'],
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'cpanel_acl'},
            'username': {'type': 'string'},
            'domain_count': {'type': 'integer'},
            'only_failures': {'type': 'boolean'},
            'has_failures': {'type': 'boolean'},
            'summary': {'type': 'object', 'description': 'Counts keyed by acl_status: ok/denied/no_docroot/unknown'},
            'domains': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'domain': {'type': 'string'},
                'docroot': {'type': 'string'},
                'acl_status': {'type': 'string', 'enum': ['ok', 'denied', 'no_docroot', 'unknown']},
                'acl_detail': {'type': 'object'},
            }}},
            'next_steps': {'type': 'array', 'items': {'type': 'string'}},
        }},
    },
    {
        'type': 'cpanel_full_audit',
        'description': 'Composite: ssl + acl-check + nginx ACME in one pass. Exits 2 if any component has failures.',
        'triggered_by': 'cpanel://USERNAME/full-audit',
        'flags': ['--only-failures', '--dns-verified', '--format=json'],
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'cpanel_full_audit'},
            'username': {'type': 'string'},
            'has_failures': {'type': 'boolean', 'description': 'True if any of ssl/acl/nginx components has failures'},
            'ssl': {'type': 'object', 'description': 'cpanel_ssl result (see cpanel_ssl schema)'},
            'acl': {'type': 'object', 'description': 'cpanel_acl result (see cpanel_acl schema)'},
            'nginx': {'type': ['object', 'null'], 'description': 'null if no nginx conf; otherwise {domain_count, has_failures, domains}'},
        }},
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'reveal cpanel://johndoe/full-audit', 'description': 'One-shot composite: ssl + ACL + nginx ACME; exits 2 on any failure', 'output_type': 'cpanel_full_audit'},
    {'uri': 'reveal cpanel://johndoe/full-audit --format=json', 'description': 'Machine-readable composite audit for scripting', 'output_type': 'cpanel_full_audit'},
    {'uri': 'reveal cpanel://johndoe', 'description': 'Overview: domain count, SSL summary, nginx config path', 'output_type': 'cpanel_user'},
    {'uri': 'reveal cpanel://johndoe/domains', 'description': 'List all domains with docroots and type (main/addon/subdomain)', 'output_type': 'cpanel_domains'},
    {'uri': 'reveal cpanel://johndoe/ssl', 'description': 'Disk cert health per domain — sorted by severity', 'output_type': 'cpanel_ssl'},
    {'uri': 'reveal cpanel://johndoe/ssl --dns-verified', 'description': 'SSL cert health: excludes NXDOMAIN and elsewhere-pointing domains from counts', 'output_type': 'cpanel_ssl'},
    {'uri': 'reveal cpanel://johndoe/ssl --only-failures', 'description': 'Show only cert failures (non-ok domains)', 'output_type': 'cpanel_ssl'},
    {'uri': 'reveal cpanel://johndoe/ssl?domain_type=main_domain', 'description': 'Disk cert health for main domain only', 'output_type': 'cpanel_ssl'},
    {'uri': 'reveal cpanel://johndoe/ssl?domain_type=subdomain --only-failures', 'description': 'Failed subdomain certs only', 'output_type': 'cpanel_ssl'},
    {'uri': 'reveal cpanel://johndoe/acl-check', 'description': 'nobody ACL status on every docroot — needed for ACME cert renewal', 'output_type': 'cpanel_acl'},
    {'uri': 'reveal cpanel://johndoe/acl-check --only-failures', 'description': 'Show only denied docroots', 'output_type': 'cpanel_acl'},
    {'uri': "reveal cpanel://johndoe/ssl --format=json | jq '.certs[] | select(.status != \"ok\")'", 'description': 'jq: all failing certs', 'output_type': 'cpanel_ssl'},
    {'uri': "reveal cpanel://johndoe/ssl --dns-verified --format=json | jq '.certs[] | select(.dns_points_here == false)'", 'description': 'jq: domains pointing to a different server', 'output_type': 'cpanel_ssl'},
]

_SCHEMA_NOTES = [
    'Reads /var/cpanel/userdata/<username>/ directly — no WHM API or credentials required',
    'SSL cert data comes from /var/cpanel/ssl/apache_tls/ (disk-based, not live connection)',
    "acl-check validates nobody can read each docroot — required for Let's Encrypt / AutoSSL",
    '--dns-verified excludes NXDOMAIN domains AND domains resolving to a different server (dns_elsewhere)',
    'dns_points_here=false means domain resolves in DNS but IPs do not match any local interface — migrated away',
    '?domain_type= query param filters ssl certs by type: main_domain, addon, subdomain, parked',
    'full-audit is the preferred single-command for agents: ssl+acl+nginx, exits 2 on any failure',
]


@register_adapter('cpanel')
@register_renderer(CpanelRenderer)
class CpanelAdapter(ResourceAdapter):
    """Adapter for inspecting cPanel user environments via cpanel:// URIs.

    Usage:
        reveal cpanel://USERNAME              # Overview
        reveal cpanel://USERNAME/domains      # List domains + docroots
        reveal cpanel://USERNAME/ssl          # Disk cert health per domain
        reveal cpanel://USERNAME/acl-check    # nobody ACL on all docroots
    """

    def __init__(self, connection_string: str = ""):
        if not connection_string:
            raise TypeError("CpanelAdapter requires a connection string: cpanel://USERNAME")

        self.connection_string = connection_string
        self.username: str = ''
        self.element: Optional[str] = None
        self.query_params: Dict[str, str] = {}

        self._parse_connection_string(connection_string)

    def _parse_connection_string(self, uri: str) -> None:
        """Parse cpanel://USERNAME[/element[?key=val&...]] URI."""
        if not uri.startswith('cpanel://'):
            raise ValueError(f"Invalid cpanel:// URI: {uri}")

        rest = uri[len('cpanel://'):]
        parts = rest.split('/', 1)
        self.username = parts[0]
        element_raw = parts[1].rstrip('/') if len(parts) > 1 else None

        if element_raw and '?' in element_raw:
            element_part, query_string = element_raw.split('?', 1)
            self.element = element_part or None
            self.query_params = parse_query_params(query_string)
        else:
            self.element = element_raw
            self.query_params = {}

        if not self.username:
            raise ValueError("cpanel:// URI requires a username: cpanel://USERNAME")

    def _get_domains(self) -> List[Dict[str, str]]:
        return _list_user_domains(self.username)

    def get_structure(self, dns_verified: bool = False, only_failures: bool = False,
                      **kwargs) -> Dict[str, Any]:
        """Get cPanel user overview or element data."""
        if self.element:
            if self.element == 'domains':
                return self._get_domains_structure()
            elif self.element == 'ssl':
                domain_type_filter = self.query_params.get('domain_type')
                return self._get_ssl_structure(dns_verified=dns_verified,
                                                only_failures=only_failures,
                                                domain_type_filter=domain_type_filter)
            elif self.element == 'acl-check':
                return self._get_acl_structure(only_failures=only_failures)
            elif self.element == 'full-audit':
                return self._get_full_audit_structure(dns_verified=dns_verified,
                                                       only_failures=only_failures)
            else:
                raise ValueError(
                    f"Unknown cpanel:// element '{self.element}'. "
                    f"Valid: domains, ssl, acl-check, full-audit"
                )
        return self._get_overview_structure()

    def _userdata_dir_exists(self) -> bool:
        return os.path.isdir(os.path.join(CPANEL_USERDATA_DIR, self.username))

    def _get_overview_structure(self) -> Dict[str, Any]:
        """Overview: domain count, SSL summary, nginx config presence."""
        domains = self._get_domains()
        ssl_summary = {'ok': 0, 'expiring': 0, 'critical': 0, 'expired': 0,
                       'missing': 0, 'error': 0}

        for d in domains:
            status = _get_disk_cert_status(d['domain'])['status']
            ssl_summary[status] = ssl_summary.get(status, 0) + 1

        nginx_conf = os.path.join(NGINX_USER_CONF_DIR, f'{self.username}.conf')
        nginx_present = os.path.exists(nginx_conf)

        userdata_dir = os.path.join(CPANEL_USERDATA_DIR, self.username)
        userdata_ok = os.path.isdir(userdata_dir)

        next_steps = [
            f"reveal cpanel://{self.username}/full-audit  # SSL + ACL + nginx in one pass",
            f"reveal cpanel://{self.username}/domains     # All domains + docroots",
            f"reveal cpanel://{self.username}/ssl         # Cert health per domain",
            f"reveal cpanel://{self.username}/acl-check   # nobody ACL on docroots",
        ]
        if nginx_present:
            next_steps.append(
                f"reveal {nginx_conf} --validate-nginx-acme"
                f"  # nginx ACME audit only"
            )

        return {
            'contract_version': '1.0',
            'type': 'cpanel_user',
            'username': self.username,
            'userdata_dir': userdata_dir,
            'userdata_accessible': userdata_ok,
            'domain_count': len(domains),
            'nginx_config': nginx_conf if nginx_present else None,
            'ssl_summary': ssl_summary,
            'next_steps': next_steps,
        }

    def _get_domains_structure(self) -> Dict[str, Any]:
        """List all domains with docroots and type."""
        domains = self._get_domains()
        return {
            'contract_version': '1.0',
            'type': 'cpanel_domains',
            'username': self.username,
            'domain_count': len(domains),
            'domains': domains,
        }

    def _get_ssl_structure(self, dns_verified: bool = False,
                           only_failures: bool = False,
                           domain_type_filter: Optional[str] = None) -> Dict[str, Any]:
        """Disk cert health per domain."""
        domains = self._get_domains()
        local_ips = _get_local_ips() if dns_verified else set()
        certs = []
        for d in domains:
            status = _get_disk_cert_status(d['domain'])
            entry: Dict[str, Any] = {
                'domain': d['domain'],
                'domain_type': d.get('type', 'unknown'),
                **status,
            }
            if dns_verified:
                resolved_ips = _dns_resolve_ips(d['domain'])
                entry['dns_resolves'] = bool(resolved_ips)
                if resolved_ips and local_ips:
                    entry['dns_points_here'] = bool(set(resolved_ips) & local_ips)
                elif resolved_ips:
                    entry['dns_points_here'] = None  # resolved but couldn't determine local IPs
            certs.append(entry)

        # Apply domain_type filter (from URI query param ?domain_type=...)
        if domain_type_filter:
            certs = [c for c in certs if c.get('domain_type') == domain_type_filter]

        # Sort: failures first, then expiring, then ok
        _ORDER = {'expired': 0, 'critical': 1, 'error': 2, 'expiring': 3,
                  'missing': 4, 'ok': 5}
        certs.sort(key=lambda r: (_ORDER.get(r['status'], 9), r['domain']))

        # Build summary: with --dns-verified, exclude NXDOMAIN and "elsewhere" domains from counts
        summary: Dict[str, int] = {}
        dns_excluded: Dict[str, int] = {}
        dns_elsewhere: Dict[str, int] = {}
        for c in certs:
            s = c['status']
            if dns_verified and not c.get('dns_resolves', True):
                dns_excluded[s] = dns_excluded.get(s, 0) + 1
            elif dns_verified and c.get('dns_points_here') is False:
                dns_elsewhere[s] = dns_elsewhere.get(s, 0) + 1
            else:
                summary[s] = summary.get(s, 0) + 1

        return {
            'contract_version': '1.0',
            'type': 'cpanel_ssl',
            'username': self.username,
            'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': len(certs),
            'dns_verified': dns_verified,
            'only_failures': only_failures,
            'domain_type_filter': domain_type_filter,
            'summary': summary,
            'dns_excluded': dns_excluded,
            'dns_elsewhere': dns_elsewhere,
            'certs': certs,
            'next_steps': [
                f"reveal cpanel://{self.username}/acl-check  # Check docroot ACL",
                f"reveal {os.path.join(NGINX_USER_CONF_DIR, self.username + '.conf')}"
                f" --cpanel-certs  # Compare disk vs live",
            ],
        }

    def _get_acl_structure(self, only_failures: bool = False) -> Dict[str, Any]:
        """nobody ACL health per domain docroot."""
        domains = self._get_domains()
        acl_results = []
        for d in domains:
            docroot = d['docroot']
            if docroot:
                acl = _check_docroot_acl(docroot)
                acl_results.append({
                    'domain': d['domain'],
                    'docroot': docroot,
                    'acl_status': acl.get('status', 'unknown'),
                    'acl_detail': acl,
                })
            else:
                acl_results.append({
                    'domain': d['domain'],
                    'docroot': '',
                    'acl_status': 'no_docroot',
                    'acl_detail': {},
                })

        summary: dict[str, int] = {}
        for r in acl_results:
            s = r['acl_status']
            summary[s] = summary.get(s, 0) + 1

        has_failures = any(r['acl_status'] == 'denied' for r in acl_results)

        return {
            'contract_version': '1.0',
            'type': 'cpanel_acl',
            'username': self.username,
            'domain_count': len(acl_results),
            'only_failures': only_failures,
            'summary': summary,
            'has_failures': has_failures,
            'domains': acl_results,
            'next_steps': [
                f"reveal cpanel://{self.username}/ssl  # Check cert status",
                f"reveal {os.path.join(NGINX_USER_CONF_DIR, self.username + '.conf')}"
                f" --check-acl  # Full nginx ACL check",
            ],
        }

    def _get_full_audit_structure(self, dns_verified: bool = False,
                                  only_failures: bool = False) -> Dict[str, Any]:
        """Composite audit: ssl + acl-check + nginx ACME in one pass."""
        ssl_data = self._get_ssl_structure(dns_verified=dns_verified,
                                            only_failures=only_failures)
        acl_data = self._get_acl_structure(only_failures=only_failures)

        # nginx ACME audit — optional (only if conf file exists)
        nginx_conf = os.path.join(NGINX_USER_CONF_DIR, f'{self.username}.conf')
        nginx_audit: Optional[Dict[str, Any]] = None
        if os.path.exists(nginx_conf):
            try:
                from ...analyzers.nginx import NginxAnalyzer
                from ...adapters.ssl.certificate import check_ssl_health
                analyzer = NginxAnalyzer(nginx_conf)
                rows = analyzer.extract_acme_roots()
                if rows:
                    results = []
                    for row in rows:
                        try:
                            ssl_result = check_ssl_health(row['domain'], warn_days=30,
                                                          critical_days=7)
                            leaf = ssl_result.get('leaf', {})
                            enriched = {**row,
                                        'ssl_status': ssl_result.get('status', 'unknown'),
                                        'ssl_days': leaf.get('days_until_expiry'),
                                        'ssl_not_after': leaf.get('not_after', '')}
                        except Exception as exc:
                            enriched = {**row, 'ssl_status': 'error', 'ssl_days': None,
                                        'ssl_not_after': str(exc)[:60]}
                        acl_fail = enriched['acl_status'] == 'denied'
                        ssl_fail = enriched['ssl_status'] in ('expired', 'error')
                        enriched['has_failure'] = acl_fail or ssl_fail
                        results.append(enriched)
                    nginx_audit = {
                        'domain_count': len(results),
                        'has_failures': any(r['has_failure'] for r in results),
                        'domains': results,
                    }
                else:
                    nginx_audit = {'domain_count': 0, 'has_failures': False, 'domains': []}
            except Exception as exc:
                nginx_audit = {'error': str(exc), 'has_failures': False, 'domains': []}

        # Use summary (not raw certs) so --dns-verified exclusions are respected
        ssl_has_failures = any(k != 'ok' and v > 0 for k, v in ssl_data.get('summary', {}).items())
        acl_has_failures = acl_data.get('has_failures', False)
        nginx_has_failures = nginx_audit.get('has_failures', False) if nginx_audit else False
        has_failures = ssl_has_failures or acl_has_failures or nginx_has_failures

        return {
            'contract_version': '1.0',
            'type': 'cpanel_full_audit',
            'username': self.username,
            'has_failures': has_failures,
            'ssl': ssl_data,
            'acl': acl_data,
            'nginx': nginx_audit,
        }

    def get_element(self, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Not used — element routing handled in get_structure."""
        return None

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Machine-readable schema for AI agent integration."""
        return {
            'adapter': 'cpanel',
            'description': 'Inspect cPanel user environments — domains, SSL certs, ACL health, composite audit',
            'uri_syntax': 'cpanel://USERNAME[/element[?domain_type=<type>]]',
            'uri_query_params': {'domain_type': 'Filter ssl certs by type: main_domain, addon, subdomain, parked'},
            'elements': _SCHEMA_ELEMENTS,
            'cli_flags': ['--format=json', '--dns-verified', '--only-failures'],
            'supports_batch': False,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Help documentation for the cpanel:// adapter."""
        return {
            'name': 'cpanel',
            'description': 'Inspect cPanel user environments — domains, SSL certs, ACL health',
            'stability': 'beta',
            'syntax': 'cpanel://USERNAME[/element]',
            'features': [
                'Filesystem-based — no WHM API or credentials required',
                'Overview: domain count, SSL summary, nginx config path',
                'Domain listing with docroots and type (addon/subdomain/main)',
                'Disk cert health from /var/cpanel/ssl/apache_tls/ (S2)',
                'nobody ACL check on every domain docroot (N1)',
                'JSON output for scripting',
                'Composable with nginx:// commands for full operator audits',
            ],
            'examples': [
                {
                    'uri': 'cpanel://USERNAME',
                    'description': 'Overview: domain count, SSL summary, nginx config path',
                },
                {
                    'uri': 'cpanel://USERNAME/domains',
                    'description': 'All domains with docroots and type (addon/subdomain/main)',
                },
                {
                    'uri': 'cpanel://USERNAME/ssl',
                    'description': 'Disk cert health per SSL domain',
                },
                {
                    'uri': 'cpanel://USERNAME/acl-check',
                    'description': 'nobody ACL check on every domain docroot (required for ACME renewal)',
                },
                {
                    'uri': 'cpanel://USERNAME/ssl --format=json',
                    'description': 'JSON output for scripting',
                },
            ],
            'elements': {
                '(none)': 'Overview: domain count, SSL summary, nginx config path',
                'domains': 'All addon/subdomain domains with docroots and type',
                'ssl': 'Disk cert health per domain from /var/cpanel/ssl/apache_tls/',
                'acl-check': 'nobody ACL status on every domain docroot',
            },
            'workflows': [
                {
                    'name': 'Full cPanel User SSL Audit',
                    'description': 'Complete SSL and ACL health check for a user',
                    'steps': [
                        'reveal cpanel://USERNAME                    # Overview',
                        'reveal cpanel://USERNAME/acl-check          # ACL health',
                        'reveal cpanel://USERNAME/ssl                # Disk cert health',
                        'reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme  # Composed audit',
                        'reveal /etc/nginx/conf.d/users/USERNAME.conf --cpanel-certs         # Disk vs live',
                        'reveal /etc/nginx/conf.d/users/USERNAME.conf --diagnose             # Error log audit',
                    ],
                },
            ],
            'notes': [
                'Must run as root or with read access to /var/cpanel/userdata/',
                'All operations are filesystem-based — no WHM API or network access',
                'nginx commands use plain file paths (e.g. reveal /etc/nginx/conf.d/users/USERNAME.conf)',
                'Use --validate-nginx-acme for the single-command "would have caught this" audit',
                'cpanel ACL check is filesystem-based (authoritative); nginx ACME audit also verifies config routing — use both',
            ],
            'see_also': [
                'reveal help://ssl - SSL certificate inspection',
                'reveal /etc/nginx/conf.d/users/USERNAME.conf --check-acl - N1 ACL check',
                'reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme - Full ACME+ACL+SSL audit',
                'reveal /etc/nginx/conf.d/users/USERNAME.conf --cpanel-certs - Disk vs live cert compare',
                'reveal /etc/nginx/conf.d/users/USERNAME.conf --diagnose - Error log ACME/SSL audit',
            ],
        }
