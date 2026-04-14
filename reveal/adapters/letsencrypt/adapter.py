"""Let's Encrypt certificate adapter (letsencrypt://).

Walks /etc/letsencrypt/live/ and surfaces cert inventory, orphan detection,
and duplicate SAN detection.

Usage:
    reveal letsencrypt://                    # List all certs + SANs + expiry
    reveal letsencrypt:// --check-orphans   # Certs not referenced by any nginx ssl_certificate
    reveal letsencrypt:// --check-duplicates # Certs with identical SANs
"""

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from ...utils.query import parse_query_params
from .renderer import LetsEncryptRenderer

_LIVE_DIR = '/etc/letsencrypt/live'

# Standard nginx config directories for orphan detection
_NGINX_CONFIG_DIRS = [
    '/etc/nginx/sites-enabled',
    '/etc/nginx/conf.d',
]

# Regex to extract ssl_certificate paths from nginx config lines
_SSL_CERT_RE = re.compile(r'^\s*ssl_certificate\s+([^;]+);')


def _load_cert_info(cert_path: Path) -> Optional[Dict[str, Any]]:
    """Load and parse a single cert.pem, returning a summary dict or None on error."""
    try:
        from ..ssl.certificate import load_certificate_from_file
        leaf, _ = load_certificate_from_file(str(cert_path))
        return {
            'name': cert_path.parent.name,
            'cert_path': str(cert_path),
            'common_name': leaf.common_name,
            'san': sorted(leaf.san),
            'days_until_expiry': leaf.days_until_expiry,
            'not_after': leaf.not_after.isoformat(),
            'is_expired': leaf.is_expired,
            'issuer': leaf.issuer_name,
        }
    except Exception as exc:
        return {
            'name': cert_path.parent.name,
            'cert_path': str(cert_path),
            'error': str(exc),
        }


def _walk_live_dir(live_dir: str) -> List[Dict[str, Any]]:
    """Walk /etc/letsencrypt/live/*/cert.pem and return cert summaries."""
    base = Path(live_dir)
    if not base.exists():
        return []
    certs = []
    for subdir in sorted(base.iterdir()):
        if not subdir.is_dir():
            continue
        cert_file = subdir / 'cert.pem'
        if cert_file.exists():
            info = _load_cert_info(cert_file)
            if info:
                certs.append(info)
    return certs


def _collect_nginx_cert_paths(nginx_dirs: List[str]) -> List[str]:
    """Scan standard nginx config dirs and return all ssl_certificate path values."""
    paths: List[str] = []
    for dir_str in nginx_dirs:
        d = Path(dir_str)
        if not d.exists():
            continue
        for conf_file in d.iterdir():
            if not conf_file.is_file():
                continue
            try:
                for line in conf_file.read_text(errors='replace').splitlines():
                    m = _SSL_CERT_RE.match(line)
                    if m:
                        paths.append(m.group(1).strip().strip('"\''))
            except OSError:
                continue
    return paths


def _find_orphans(certs: List[Dict], nginx_cert_paths: List[str]) -> List[Dict]:
    """Return certs whose cert_path is not referenced by any nginx ssl_certificate directive."""
    referenced = set(nginx_cert_paths)
    orphans = []
    for cert in certs:
        if 'error' in cert:
            continue
        cert_path = cert['cert_path']
        # A cert at /etc/letsencrypt/live/DOMAIN/cert.pem is in use if any nginx
        # ssl_certificate directive references it (exact match or symlink target).
        # We also check the parent directory name appearing in any referenced path,
        # since certbot often uses fullchain.pem rather than cert.pem.
        cert_dir = cert_path.rsplit('/', 1)[0]  # POSIX split — cert_path is always a server path
        in_use = any(
            p == cert_path or p.startswith(cert_dir + '/')
            for p in referenced
        )
        if not in_use:
            orphans.append(cert)
    return orphans


def _find_duplicates(certs: List[Dict]) -> List[List[Dict]]:
    """Return groups of certs sharing identical SAN sets."""
    from collections import defaultdict
    groups: Dict[Any, List[Dict]] = defaultdict(list)
    for cert in certs:
        if 'error' in cert:
            continue
        key = frozenset(cert.get('san', []))
        if key:
            groups[key].append(cert)
    return [group for group in groups.values() if len(group) > 1]


_RENEWAL_TIMER_PATHS = [
    # systemd units (distro-specific locations)
    '/etc/systemd/system/certbot.timer',
    '/lib/systemd/system/certbot.timer',
    '/usr/lib/systemd/system/certbot.timer',
    # cron-based renewal
    '/etc/cron.d/certbot',
    '/etc/cron.daily/certbot',
]


def _check_renewal_timer() -> Dict[str, Any]:
    """Return renewal automation status by probing well-known timer/cron paths.

    No subprocess execution — filesystem presence only.  A missing timer means
    certs will expire silently even though certbot is installed.
    """
    found = []
    for path in _RENEWAL_TIMER_PATHS:
        if Path(path).exists():
            kind = 'systemd' if 'systemd' in path else 'cron'
            found.append({'path': path, 'kind': kind})
    return {
        'configured': bool(found),
        'mechanisms': found,
        'warning': None if found else (
            'No certbot renewal timer or cron job found — '
            'certs will expire without automatic renewal'
        ),
    }


@register_adapter('letsencrypt')
@register_renderer(LetsEncryptRenderer)
class LetsEncryptAdapter(ResourceAdapter):
    """Adapter for Let's Encrypt certificate inventory via letsencrypt:// URIs.

    Usage:
        reveal letsencrypt://                    # List all certs + SANs + expiry
        reveal letsencrypt:// --check-orphans   # Certs not used by any nginx vhost
        reveal letsencrypt:// --check-duplicates # Certs with identical SANs
    """

    ELEMENT_NAMESPACE_ADAPTER: bool = False

    def __init__(self, connection_string: str = ''):
        if connection_string and not connection_string.startswith('letsencrypt://'):
            raise ValueError(f"Invalid letsencrypt:// URI: {connection_string}")
        self.live_dir = _LIVE_DIR
        self.nginx_dirs = list(_NGINX_CONFIG_DIRS)
        self.query_params: Dict[str, Any] = {}
        if connection_string and '?' in connection_string:
            _, query_string = connection_string.split('?', 1)
            self.query_params = parse_query_params(query_string)

    def get_structure(
        self,
        check_orphans: bool = False,
        check_duplicates: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        check_orphans = check_orphans or bool(self.query_params.get('check-orphans'))
        check_duplicates = check_duplicates or bool(self.query_params.get('check-duplicates'))
        """Return cert inventory, optionally with orphan/duplicate analysis.

        Args:
            check_orphans: When True, cross-reference against nginx ssl_certificate
                           directives and surface unreferenced certs.
            check_duplicates: When True, find certs sharing identical SANs.
        """
        certs = _walk_live_dir(self.live_dir)
        # Sort by days_until_expiry ascending — imminent expirations first.
        # Error certs (no days_until_expiry field) sort to the end.
        certs.sort(key=lambda c: c.get('days_until_expiry', 99999))
        live_dir_exists = Path(self.live_dir).exists()

        result: Dict[str, Any] = {
            'contract_version': '1.0',
            'type': 'letsencrypt_inventory',
            'source': self.live_dir,
            'source_type': 'letsencrypt_directory',
            'live_dir': self.live_dir,
            'live_dir_exists': live_dir_exists,
            'cert_count': len(certs),
            'certs': certs,
            'renewal_timer': _check_renewal_timer(),
        }

        if check_orphans:
            nginx_paths = _collect_nginx_cert_paths(self.nginx_dirs)
            orphans = _find_orphans(certs, nginx_paths)
            result['orphan_check'] = {
                'nginx_dirs_scanned': self.nginx_dirs,
                'nginx_cert_paths_found': len(nginx_paths),
                'orphan_count': len(orphans),
                'orphans': orphans,
            }

        if check_duplicates:
            dup_groups = _find_duplicates(certs)
            result['duplicate_check'] = {
                'duplicate_group_count': len(dup_groups),
                'groups': dup_groups,
            }

        result['next_steps'] = _build_next_steps(certs, check_orphans, check_duplicates)
        return result

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'letsencrypt',
            'description': "Let's Encrypt certificate inventory — orphan and duplicate SAN detection",
            'uri_syntax': 'letsencrypt://',
            'query_params': {
                'check-orphans': 'Find certs not referenced by any nginx ssl_certificate (also: --check-orphans)',
                'check-duplicates': 'Find certs with identical SANs (also: --check-duplicates)',
            },
            'elements': {},
            'cli_flags': ['--check-orphans', '--check-duplicates', '--format=json'],
            'supports_batch': False,
            'output_types': [
                {
                    'type': 'letsencrypt_inventory',
                    'description': "Cert inventory from /etc/letsencrypt/live/",
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'letsencrypt_inventory'},
                            'cert_count': {'type': 'integer'},
                            'certs': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'name': {'type': 'string'},
                                        'cert_path': {'type': 'string'},
                                        'common_name': {'type': 'string'},
                                        'issuer': {'type': 'string'},
                                        'san': {'type': 'array', 'items': {'type': 'string'}},
                                        'days_until_expiry': {'type': 'integer'},
                                        'not_after': {'type': 'string'},
                                        'is_expired': {'type': 'boolean'},
                                    },
                                },
                            },
                            'renewal_timer': {
                                'type': 'object',
                                'description': 'Renewal automation status (systemd timer or cron)',
                                'properties': {
                                    'configured': {'type': 'boolean'},
                                    'mechanisms': {'type': 'array'},
                                    'warning': {'type': ['string', 'null']},
                                },
                            },
                        },
                    },
                },
            ],
            'example_queries': [
                {
                    'uri': 'reveal letsencrypt://',
                    'description': 'List all certs with SANs and expiry',
                },
                {
                    'uri': 'reveal letsencrypt:// --check-orphans',
                    'description': 'Find certs not referenced by any nginx ssl_certificate',
                },
                {
                    'uri': 'reveal letsencrypt:// --check-duplicates',
                    'description': 'Find certs with identical SANs (renewal candidates)',
                },
                {
                    'uri': 'reveal letsencrypt:// --format json',
                    'description': 'Machine-readable cert inventory',
                },
            ],
            'notes': [
                'Reads /etc/letsencrypt/live/*/cert.pem — requires read access',
                '--check-orphans scans /etc/nginx/sites-enabled/ and /etc/nginx/conf.d/',
                'certbot renew --dry-run is out of scope — no command execution',
            ],
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return load_help_data('letsencrypt') or {}


def _build_next_steps(certs: List[Dict], check_orphans: bool, check_duplicates: bool) -> List[str]:
    steps = []
    if not check_orphans:
        steps.append('reveal letsencrypt:// --check-orphans    # find unreferenced certs')
    if not check_duplicates:
        steps.append('reveal letsencrypt:// --check-duplicates # find duplicate-SAN certs')
    expired = [c for c in certs if c.get('is_expired')]
    if expired:
        steps.append(f'# {len(expired)} cert(s) are EXPIRED — renew with: certbot renew')
    return steps
