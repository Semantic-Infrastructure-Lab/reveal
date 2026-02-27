"""cPanel adapter — filesystem-based inspection of cPanel user environments.

URI scheme: cpanel://USERNAME[/element]

Elements:
    (none)          Overview: domains, SSL status summary, nginx config presence
    domains         List addon domains with docroots and home directory
    ssl             S2 disk-cert health per domain from /var/cpanel/ssl/apache_tls/
    acl-check       N1 nobody ACL health per domain docroot

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
from typing import Dict, Any, Optional, List

from ..base import ResourceAdapter, register_adapter, register_renderer
from .renderer import CpanelRenderer


# cPanel filesystem paths
CPANEL_USERDATA_DIR = "/var/cpanel/userdata"
CPANEL_SSL_DIR = "/var/cpanel/ssl/apache_tls"
NGINX_USER_CONF_DIR = "/etc/nginx/conf.d/users"


def _parse_cpanel_userdata(path: str) -> Dict[str, str]:
    """Parse a cPanel userdata file (YAML-ish key: value format).

    cPanel userdata files are a simple key: value format (not full YAML).
    Each line is either blank, a comment, or `key: value`.

    Returns:
        Dict of directive name → value.
    """
    result: Dict[str, str] = {}
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.rstrip()
                if not line or line.startswith('#') or line.startswith('-'):
                    continue
                m = re.match(r'^(\w+):\s*(.*)', line)
                if m:
                    result[m.group(1)] = m.group(2).strip()
    except OSError:
        pass
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

        self._parse_connection_string(connection_string)

    def _parse_connection_string(self, uri: str) -> None:
        """Parse cpanel://USERNAME[/element] URI."""
        if not uri.startswith('cpanel://'):
            raise ValueError(f"Invalid cpanel:// URI: {uri}")

        rest = uri[len('cpanel://'):]
        parts = rest.split('/', 1)
        self.username = parts[0]
        self.element = parts[1].rstrip('/') if len(parts) > 1 else None

        if not self.username:
            raise ValueError("cpanel:// URI requires a username: cpanel://USERNAME")

    def _get_domains(self) -> List[Dict[str, str]]:
        return _list_user_domains(self.username)

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get cPanel user overview or element data."""
        if self.element:
            if self.element == 'domains':
                return self._get_domains_structure()
            elif self.element == 'ssl':
                return self._get_ssl_structure()
            elif self.element == 'acl-check':
                return self._get_acl_structure()
            else:
                raise ValueError(
                    f"Unknown cpanel:// element '{self.element}'. "
                    f"Valid: domains, ssl, acl-check"
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
            f"reveal cpanel://{self.username}/domains    # All domains + docroots",
            f"reveal cpanel://{self.username}/ssl        # Cert health per domain",
            f"reveal cpanel://{self.username}/acl-check  # nobody ACL on docroots",
        ]
        if nginx_present:
            next_steps.append(
                f"reveal nginx:///{nginx_conf} --validate-nginx-acme"
                f"  # Full ACME audit"
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

    def _get_ssl_structure(self) -> Dict[str, Any]:
        """Disk cert health per domain."""
        domains = self._get_domains()
        certs = []
        for d in domains:
            status = _get_disk_cert_status(d['domain'])
            certs.append({
                'domain': d['domain'],
                **status,
            })
        # Sort: failures first, then expiring, then ok
        _ORDER = {'expired': 0, 'critical': 1, 'error': 2, 'expiring': 3,
                  'missing': 4, 'ok': 5}
        certs.sort(key=lambda r: (_ORDER.get(r['status'], 9), r['domain']))

        summary = {}
        for c in certs:
            s = c['status']
            summary[s] = summary.get(s, 0) + 1

        return {
            'contract_version': '1.0',
            'type': 'cpanel_ssl',
            'username': self.username,
            'cpanel_ssl_dir': CPANEL_SSL_DIR,
            'cert_count': len(certs),
            'summary': summary,
            'certs': certs,
            'next_steps': [
                f"reveal cpanel://{self.username}/acl-check  # Check docroot ACL",
                f"reveal nginx:///{os.path.join(NGINX_USER_CONF_DIR, self.username + '.conf')}"
                f" --cpanel-certs  # Compare disk vs live",
            ],
        }

    def _get_acl_structure(self) -> Dict[str, Any]:
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

        summary = {}
        for r in acl_results:
            s = r['acl_status']
            summary[s] = summary.get(s, 0) + 1

        has_failures = any(r['acl_status'] == 'denied' for r in acl_results)

        return {
            'contract_version': '1.0',
            'type': 'cpanel_acl',
            'username': self.username,
            'domain_count': len(acl_results),
            'summary': summary,
            'has_failures': has_failures,
            'domains': acl_results,
            'next_steps': [
                f"reveal cpanel://{self.username}/ssl  # Check cert status",
                f"reveal nginx:///{os.path.join(NGINX_USER_CONF_DIR, self.username + '.conf')}"
                f" --check-acl  # Full nginx ACL check",
            ],
        }

    def get_element(self, element_type: str, name: str = '') -> Optional[Dict[str, Any]]:
        """Not used — element routing handled in get_structure."""
        return None
