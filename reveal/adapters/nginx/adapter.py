"""nginx:// URI adapter — domain-centric nginx vhost inspection.

Provides a domain-centric view of nginx configuration, complementing
the existing file-path analyzer (reveal /etc/nginx/conf.d/domain.conf).

Usage:
    reveal nginx://smd-ops.mytia.net           # vhost summary
    reveal nginx://smd-ops.mytia.net/ports     # listening ports
    reveal nginx://smd-ops.mytia.net/upstream  # proxy_pass targets + reachability
    reveal nginx://smd-ops.mytia.net/auth      # auth_basic / auth_request directives
    reveal nginx://smd-ops.mytia.net/locations # location blocks
    reveal nginx://smd-ops.mytia.net/config    # full compiled config for this domain
    reveal nginx://                            # overview of all enabled sites
"""

import os
import re
import socket
import glob
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from ..base import ResourceAdapter, register_adapter, register_renderer
from .renderer import NginxUriRenderer


# Common nginx config directories, in search priority order
_NGINX_SEARCH_DIRS = [
    '/etc/nginx/sites-enabled',
    '/etc/nginx/conf.d',
    '/usr/local/nginx/conf/sites-enabled',
    '/usr/local/etc/nginx/sites-enabled',
]

_NGINX_MAIN_CONFIGS = [
    '/etc/nginx/nginx.conf',
    '/usr/local/nginx/conf/nginx.conf',
    '/usr/local/etc/nginx/nginx.conf',
]

# Nginx includes all files in sites-enabled/, but only *.conf in conf.d/.
# Skip backup/temp files regardless.
_BACKUP_SUFFIXES = ('.bak', '.backup', '.old', '.disabled', '.orig', '~')
_ARTIFACT_SUFFIXES = _BACKUP_SUFFIXES + ('.tmp',)


_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'nginx_sites_overview',
        'description': 'List of all enabled nginx vhosts',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'nginx_sites_overview'},
                'sites': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'domains': {'type': 'array', 'items': {'type': 'string'}},
                            'is_symlink': {'type': 'boolean'},
                            'enabled': {'type': 'boolean'},
                        }
                    }
                },
                'next_steps': {'type': 'array'},
            }
        }
    },
    {
        'type': 'nginx_vhost_summary',
        'description': 'Full vhost summary — ports, upstreams, auth, locations, warnings',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'nginx_vhost_summary'},
                'domain': {'type': 'string'},
                'config_file': {'type': 'string'},
                'symlink': {'type': 'object'},
                'ports': {'type': 'array'},
                'upstreams': {'type': 'object'},
                'auth': {'type': 'object'},
                'locations': {'type': 'array'},
                'warnings': {'type': 'array', 'items': {'type': 'string'}},
                'next_steps': {'type': 'array'},
            }
        }
    },
    {
        'type': 'nginx_vhost_not_found',
        'description': 'Domain not found in any nginx config',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'nginx_vhost_not_found'},
                'domain': {'type': 'string'},
                'searched': {'type': 'array'},
                'next_steps': {'type': 'array'},
            }
        }
    },
    {
        'type': 'nginx_vhost_ports',
        'description': 'Listening ports for domain',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'nginx_vhost_ports'},
                'domain': {'type': 'string'},
                'config_file': {'type': 'string'},
                'ports': {'type': 'array'},
            }
        }
    },
    {
        'type': 'nginx_vhost_upstream',
        'description': 'Upstream proxy_pass targets with reachability',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'nginx_vhost_upstream'},
                'domain': {'type': 'string'},
                'config_file': {'type': 'string'},
                'upstreams': {'type': 'object'},
            }
        }
    },
    {
        'type': 'nginx_vhost_auth',
        'description': 'Auth directives (auth_basic, auth_request)',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'nginx_vhost_auth'},
                'domain': {'type': 'string'},
                'config_file': {'type': 'string'},
                'auth': {'type': 'object'},
            }
        }
    },
    {
        'type': 'nginx_vhost_locations',
        'description': 'Location blocks with routing targets',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'nginx_vhost_locations'},
                'domain': {'type': 'string'},
                'config_file': {'type': 'string'},
                'locations': {'type': 'array'},
            }
        }
    },
    {
        'type': 'nginx_vhost_config',
        'description': 'Raw server block config text',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'nginx_vhost_config'},
                'domain': {'type': 'string'},
                'config_file': {'type': 'string'},
                'server_block': {'type': 'string'},
            }
        }
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'nginx://',
        'description': 'Overview of all enabled nginx vhosts',
        'output_type': 'nginx_sites_overview',
    },
    {
        'uri': 'nginx://example.com',
        'description': 'Full vhost summary (ports, upstreams, auth, locations)',
        'output_type': 'nginx_vhost_summary',
    },
    {
        'uri': 'nginx://example.com/ports',
        'description': 'Listening ports only',
        'element': 'ports',
        'output_type': 'nginx_vhost_ports',
    },
    {
        'uri': 'nginx://example.com/upstream',
        'description': 'proxy_pass targets with TCP reachability check',
        'element': 'upstream',
        'output_type': 'nginx_vhost_upstream',
    },
    {
        'uri': 'nginx://example.com/auth',
        'description': 'Auth directives (auth_basic, auth_request)',
        'element': 'auth',
        'output_type': 'nginx_vhost_auth',
    },
    {
        'uri': 'nginx://example.com/locations',
        'description': 'Location block routing table',
        'element': 'locations',
        'output_type': 'nginx_vhost_locations',
    },
    {
        'uri': 'nginx://example.com/config',
        'description': 'Raw nginx server block text',
        'element': 'config',
        'output_type': 'nginx_vhost_config',
    },
]

_SCHEMA_NOTES = [
    'Searches /etc/nginx/sites-enabled, /etc/nginx/conf.d, and common alternatives',
    'Domain lookup: matches server_name directives (exact + wildcard)',
    'Upstream reachability: TCP socket check to each backend',
    'Complements file-path analysis: reveal /etc/nginx/conf.d/domain.conf --check',
]


def _iter_nginx_configs(search_dir: str):
    """Yield config file paths from a nginx config directory.

    Mirrors nginx's own include logic:
    - sites-enabled: all files (no extension filter)
    - conf.d and others: *.conf only (including one level of subdirectories,
      e.g. conf.d/users/ on cPanel/WHM servers)

    Skips backup/temp files in both cases.
    """
    is_sites_enabled = 'sites-enabled' in search_dir
    pattern = os.path.join(search_dir, '*')
    for path in sorted(glob.glob(pattern)):
        if os.path.isdir(path):
            # Recurse one level into subdirectories (e.g. conf.d/users/)
            for subpath in sorted(glob.glob(os.path.join(path, '*.conf'))):
                if not os.path.isfile(subpath):
                    continue
                name = os.path.basename(subpath)
                if any(name.endswith(s) or ('.backup' in name) for s in _BACKUP_SUFFIXES):
                    continue
                yield subpath
            continue
        if not os.path.isfile(path):
            continue
        name = os.path.basename(path)
        # Skip backup/temp files
        if any(name.endswith(s) or ('.backup' in name) for s in _BACKUP_SUFFIXES):
            continue
        # conf.d and other dirs: only .conf files
        if not is_sites_enabled and not name.endswith('.conf'):
            continue
        yield path


def _find_artifact_files(search_dir: str) -> List[str]:
    """Return paths of backup/temp files in a nginx config directory.

    Scans top-level and one level of subdirectories (e.g. conf.d/users/).
    These files are silently skipped by nginx but indicate housekeeping debt.
    """
    found = []
    pattern = os.path.join(search_dir, '*')
    for path in sorted(glob.glob(pattern)):
        if os.path.isdir(path):
            for subpath in sorted(glob.glob(os.path.join(path, '*'))):
                if not os.path.isfile(subpath):
                    continue
                name = os.path.basename(subpath)
                if any(name.endswith(s) for s in _ARTIFACT_SUFFIXES) or '.backup' in name:
                    found.append(subpath)
        elif os.path.isfile(path):
            name = os.path.basename(path)
            if any(name.endswith(s) for s in _ARTIFACT_SUFFIXES) or '.backup' in name:
                found.append(path)
    return found


def _config_file_has_domain(conf_file: str, domain: str) -> bool:
    """Return True if the config file has a server_name directive for domain."""
    try:
        content = Path(conf_file).read_text(errors='replace')
    except OSError:
        return False
    return any(
        domain in m.group(1).split()
        for m in re.finditer(r'server_name\s+([^;]+);', content)
    )


def _find_config_for_domain(domain: str) -> Optional[str]:
    """Scan nginx config directories for the file that handles domain.

    Returns the path to the config file, or None if not found.
    """
    for search_dir in _NGINX_SEARCH_DIRS:
        if not os.path.isdir(search_dir):
            continue
        for conf_file in _iter_nginx_configs(search_dir):
            if _config_file_has_domain(conf_file, domain):
                return conf_file
    return None


def _extract_domains_from_content(content: str) -> List[str]:
    """Extract unique domain names from nginx server_name directives in content."""
    domains: List[str] = []
    for m in re.finditer(r'server_name\s+([^;]+);', content):
        for name in m.group(1).split():
            if name not in ('_', 'localhost') and '.' in name and name not in domains:
                domains.append(name)
    return domains


def _resolve_symlink_info(path: str) -> Dict[str, Any]:
    """Return symlink information for a config file path."""
    p = Path(path)
    if p.is_symlink():
        try:
            target = os.readlink(path)
            resolved = str(p.resolve())
            return {'is_symlink': True, 'target': target, 'resolved': resolved, 'exists': p.exists()}
        except OSError:
            return {'is_symlink': True, 'target': '(unresolvable)', 'resolved': None, 'exists': False}
    return {'is_symlink': False, 'target': None, 'resolved': path, 'exists': p.exists()}


def _parse_server_block_for_domain(content: str, domain: str) -> Optional[str]:
    """Extract the server block(s) relevant to domain from nginx config content."""
    # Match all server blocks; handles 3 levels of brace nesting to cover
    # nested location blocks (server → location → location ~* inside location /).
    SERVER_BLOCK_RE = re.compile(
        r'(server\s*\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})',
        re.MULTILINE | re.DOTALL
    )
    matching = []
    for m in SERVER_BLOCK_RE.finditer(content):
        block = m.group(1)
        sn_match = re.search(r'server_name\s+([^;]+);', block)
        if sn_match and domain in sn_match.group(1).split():
            matching.append(block)
    return '\n\n'.join(matching) if matching else None


def _extract_ports(server_block: str) -> List[Dict[str, Any]]:
    """Extract listening ports from a server block."""
    ports = []
    for m in re.finditer(r'listen\s+([^;]+);', server_block):
        spec = m.group(1).strip()
        is_ssl = 'ssl' in spec or '443' in spec
        port_match = re.match(r'(?:[\d.]+:)?(\d+)', spec)
        port = port_match.group(1) if port_match else spec
        entry: Dict[str, Any] = {
            'spec': spec,
            'port': port,
            'is_ssl': is_ssl,
        }
        # Detect HTTPS redirect pattern
        if not is_ssl and re.search(r'return\s+3\d\d\s+https://', server_block):
            entry['redirect_to_https'] = True
        # Detect certbot-managed SSL
        if is_ssl and re.search(r'letsencrypt', server_block):
            entry['certbot_managed'] = True
        ports.append(entry)
    return ports


def _extract_upstreams_referenced(server_block: str) -> List[str]:
    """Find upstream names referenced by proxy_pass in a server block."""
    names = []
    for m in re.finditer(r'proxy_pass\s+http://(\w+)', server_block):
        name = m.group(1)
        if name not in names:
            names.append(name)
    return names


def _find_upstream_definitions(content: str, names: List[str]) -> Dict[str, Any]:
    """Find upstream block definitions for the given names."""
    upstreams = {}
    for name in names:
        pattern = re.compile(
            rf'upstream\s+{re.escape(name)}\s*\{{([^}}]+)\}}',
            re.MULTILINE | re.DOTALL
        )
        m = pattern.search(content)
        if m:
            body = m.group(1)
            servers = []
            for sm in re.finditer(r'server\s+([^;]+);', body):
                servers.append(sm.group(1).strip())
            upstreams[name] = {'servers': servers, 'raw': body.strip()}
        else:
            upstreams[name] = {'servers': [], 'raw': None}
    return upstreams


def _check_upstream_reachability(upstream_def: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check if upstream servers are TCP-reachable."""
    results = []
    for server_spec in upstream_def.get('servers', []):
        # Strip weight/backup/etc params
        addr = server_spec.split()[0]
        if ':' in addr:
            host, port_str = addr.rsplit(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                port = 80
        else:
            host, port = addr, 80

        try:
            sock = socket.create_connection((host, port), timeout=3)
            sock.close()
            reachable = True
            error = None
        except Exception as e:
            reachable = False
            error = str(e)

        results.append({
            'address': addr,
            'reachable': reachable,
            'error': error,
        })
    return results


def _extract_auth_directives(server_block: str) -> Dict[str, Any]:
    """Extract authentication directives from a server block."""
    auth: Dict[str, Any] = {
        'auth_basic': None,
        'auth_request': None,
        'locations_with_auth': [],
    }

    # Top-level auth_basic
    m = re.search(r'^[ \t]*auth_basic\s+"?([^";]+)"?\s*;', server_block, re.MULTILINE)
    if m:
        val = m.group(1).strip()
        auth['auth_basic'] = None if val.lower() == 'off' else val

    # Top-level auth_request
    m = re.search(r'^[ \t]*auth_request\s+([^;]+);', server_block, re.MULTILINE)
    if m:
        auth['auth_request'] = m.group(1).strip()

    # Location-level auth
    LOC_RE = re.compile(r'location\s+([^\{]+)\s*\{([^{}]*)\}', re.MULTILINE | re.DOTALL)
    for lm in LOC_RE.finditer(server_block):
        loc_path = lm.group(1).strip()
        loc_body = lm.group(2)
        loc_auth: Dict[str, Any] = {}
        ab = re.search(r'auth_basic\s+"?([^";]+)"?\s*;', loc_body)
        if ab:
            val = ab.group(1).strip()
            loc_auth['auth_basic'] = None if val.lower() == 'off' else val
        ar = re.search(r'auth_request\s+([^;]+);', loc_body)
        if ar:
            loc_auth['auth_request'] = ar.group(1).strip()
        if loc_auth:
            auth['locations_with_auth'].append({'path': loc_path, **loc_auth})

    return auth


def _extract_location_blocks(server_block: str) -> List[Dict[str, Any]]:
    """Extract location blocks with their targets."""
    locations = []
    LOC_RE = re.compile(r'location\s+([^\{]+)\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', re.MULTILINE | re.DOTALL)
    for m in LOC_RE.finditer(server_block):
        path = m.group(1).strip()
        body = m.group(2)

        loc: Dict[str, Any] = {'path': path}

        pp = re.search(r'proxy_pass\s+([^;]+);', body)
        if pp:
            loc['target'] = pp.group(1).strip()
            loc['type'] = 'proxy'
        else:
            root = re.search(r'root\s+([^;]+);', body)
            alias = re.search(r'alias\s+([^;]+);', body)
            ret = re.search(r'return\s+([^;]+);', body)
            if alias:
                loc['target'] = alias.group(1).strip()
                loc['type'] = 'alias'
            elif root:
                loc['target'] = root.group(1).strip()
                loc['type'] = 'static'
            elif ret:
                loc['target'] = ret.group(1).strip()
                loc['type'] = 'return'
            else:
                loc['type'] = 'other'

        # Note auth overrides
        ab = re.search(r'auth_basic\s+"?([^";]+)"?\s*;', body)
        if ab:
            val = ab.group(1).strip()
            loc['auth_basic'] = None if val.lower() == 'off' else val

        locations.append(loc)

    return locations


def _detect_warnings(
    ports: List[Dict],
    upstreams: Dict,
    reachability: Dict,
    auth: Dict,
) -> List[str]:
    """Detect potential issues and return warning messages."""
    warnings = []

    # No HTTPS port
    has_https = any(p.get('is_ssl') for p in ports)
    has_http = any(not p.get('is_ssl') for p in ports)
    if has_http and not has_https:
        warnings.append("No HTTPS listener — traffic may be unencrypted")

    # Unreachable upstreams
    for name, reach_list in reachability.items():
        for srv in reach_list:
            if not srv['reachable']:
                warnings.append(f"Upstream '{name}' server {srv['address']} is not reachable: {srv['error']}")

    # auth_basic present (informational — user should verify it's intentional)
    if auth.get('auth_basic'):
        warnings.append(f"auth_basic active: \"{auth['auth_basic']}\" — verify this is intentional")

    return warnings


@register_adapter('nginx')
@register_renderer(NginxUriRenderer)
class NginxUriAdapter(ResourceAdapter):
    """Adapter for domain-centric nginx vhost inspection (nginx://).

    Finds the nginx config file that handles a given domain and provides
    a structured summary: ports, upstreams, auth, location blocks.

    Usage:
        reveal nginx://smd-ops.mytia.net           # vhost summary
        reveal nginx://smd-ops.mytia.net/ports     # listening ports
        reveal nginx://smd-ops.mytia.net/upstream  # proxy_pass targets + reachability
        reveal nginx://smd-ops.mytia.net/auth      # auth directives
        reveal nginx://smd-ops.mytia.net/locations # location blocks
        reveal nginx://smd-ops.mytia.net/config    # raw filtered config
        reveal nginx://                            # overview of all enabled sites
    """

    @staticmethod
    def get_help() -> Dict[str, Any]:
        from ..help_data import load_help_data
        return load_help_data('nginx_uri') or {}

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Machine-readable schema for nginx:// adapter — AI agent integration."""
        return {
            'adapter': 'nginx',
            'description': 'Domain-centric nginx vhost inspection — ports, upstreams, auth, locations',
            'uri_syntax': 'nginx://[<domain>[/<element>]]',
            'query_params': {},  # No query parameters
            'elements': {
                'ports': 'Listening ports (80/443, SSL, redirect)',
                'upstream': 'proxy_pass targets and reachability checks',
                'auth': 'auth_basic / auth_request directives',
                'locations': 'Location blocks with routing targets',
                'config': 'Full raw server block(s) for this domain',
            },
            'cli_flags': [],  # nginx:// has no extra CLI flags
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    def __init__(self, connection_string: str = "", **kwargs):
        if not connection_string:
            raise TypeError("NginxUriAdapter requires a connection string")

        self.connection_string = connection_string
        self.domain: Optional[str] = None
        self.element: Optional[str] = kwargs.get('element')
        self._parse_connection_string(connection_string)

    def _parse_connection_string(self, uri: str) -> None:
        if uri.startswith('nginx://'):
            uri = uri[8:]

        # nginx:// with no domain → overview mode
        if not uri or uri == '/':
            self.domain = None
            return

        parts = uri.split('/', 1)
        self.domain = parts[0] if parts[0] else None
        if len(parts) > 1 and parts[1]:
            self.element = parts[1]

    def _load_vhost(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Find and load the nginx config for self.domain.

        Returns (config_path, content, server_block_content).
        """
        assert self.domain is not None
        config_path = _find_config_for_domain(self.domain)
        if not config_path:
            return None, None, None

        try:
            content = Path(config_path).read_text(errors='replace')
        except OSError:
            return config_path, None, None

        server_block = _parse_server_block_for_domain(content, self.domain)
        return config_path, content, server_block

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get nginx vhost summary for the domain."""
        if self.domain is None:
            return self._get_overview()

        if self.element:
            result = self.get_element(self.element)
            if result is not None:
                return result
            raise ValueError(f"Unknown element: {self.element}. Use: ports, upstream, auth, locations, config")

        return self._get_vhost_summary()

    def _get_overview(self) -> Dict[str, Any]:
        """List all enabled nginx sites."""
        sites = []
        artifact_files: List[str] = []
        for search_dir in _NGINX_SEARCH_DIRS:
            if not os.path.isdir(search_dir):
                continue
            for conf_file in _iter_nginx_configs(search_dir):
                try:
                    content = Path(conf_file).read_text(errors='replace')
                except OSError:
                    continue

                domains = _extract_domains_from_content(content)
                symlink_info = _resolve_symlink_info(conf_file)
                sites.append({
                    'file': conf_file,
                    'domains': domains,
                    'is_symlink': symlink_info['is_symlink'],
                    'enabled': symlink_info['exists'],
                })
            artifact_files.extend(_find_artifact_files(search_dir))

        next_steps = [
            "Inspect a specific domain: reveal nginx://<domain>",
            "Check SSL certs across all nginx: reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check",
        ]
        if artifact_files:
            next_steps.append(
                f"Housekeeping: {len(artifact_files)} backup/temp file(s) found — review and remove"
            )

        return {
            'type': 'nginx_sites_overview',
            'sites': sites,
            'artifact_files': artifact_files,
            'next_steps': next_steps,
        }

    def _get_vhost_summary(self) -> Dict[str, Any]:
        """Build the main vhost summary."""
        assert self.domain is not None
        config_path, content, server_block = self._load_vhost()

        if config_path is None:
            return {
                'type': 'nginx_vhost_not_found',
                'domain': self.domain,
                'searched': _NGINX_SEARCH_DIRS,
                'next_steps': [
                    f"Check if nginx is installed: which nginx",
                    f"Manually find config: grep -r 'server_name {self.domain}' /etc/nginx/",
                    f"Inspect a specific file: reveal /etc/nginx/conf.d/yourfile.conf",
                ],
            }

        if server_block is None:
            return {
                'type': 'nginx_vhost_not_found',
                'domain': self.domain,
                'config_file': config_path,
                'note': 'Config file found but no server block matched this domain',
                'next_steps': [f"Inspect the file: reveal {config_path}"],
            }

        symlink_info = _resolve_symlink_info(config_path)
        ports = _extract_ports(server_block)
        upstream_names = _extract_upstreams_referenced(server_block)
        upstream_defs = _find_upstream_definitions(content, upstream_names)
        reachability = {name: _check_upstream_reachability(defn) for name, defn in upstream_defs.items()}
        auth = _extract_auth_directives(server_block)
        locations = _extract_location_blocks(server_block)
        warnings = _detect_warnings(ports, upstream_defs, reachability, auth)

        return {
            'type': 'nginx_vhost_summary',
            'domain': self.domain,
            'config_file': config_path,
            'symlink': symlink_info,
            'ports': ports,
            'upstreams': {
                name: {
                    'definition': defn,
                    'reachability': reachability.get(name, []),
                }
                for name, defn in upstream_defs.items()
            },
            'auth': auth,
            'locations': locations,
            'warnings': warnings,
            'next_steps': [
                f"reveal nginx://{self.domain}/upstream  # upstream health detail",
                f"reveal nginx://{self.domain}/config    # full compiled config",
                f"reveal ssl://{self.domain} --check     # cert detail",
            ],
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        assert self.domain is not None
        config_path, content, server_block = self._load_vhost()

        if config_path is None or server_block is None:
            return {
                'type': 'nginx_vhost_not_found',
                'domain': self.domain,
                'element': element_name,
            }

        handlers = {
            'ports': self._element_ports,
            'upstream': self._element_upstream,
            'auth': self._element_auth,
            'locations': self._element_locations,
            'config': self._element_config,
        }

        handler = handlers.get(element_name)
        if handler:
            return handler(config_path, content, server_block)
        return None

    def _element_ports(self, config_path: str, content: str, server_block: str) -> Dict[str, Any]:
        ports = _extract_ports(server_block)
        return {
            'type': 'nginx_vhost_ports',
            'domain': self.domain,
            'config_file': config_path,
            'ports': ports,
            'next_steps': [
                f"reveal nginx://{self.domain}           # full vhost summary",
                f"reveal ssl://{self.domain} --check     # SSL cert detail",
            ],
        }

    def _element_upstream(self, config_path: str, content: str, server_block: str) -> Dict[str, Any]:
        upstream_names = _extract_upstreams_referenced(server_block)
        upstream_defs = _find_upstream_definitions(content, upstream_names)
        reachability = {name: _check_upstream_reachability(defn) for name, defn in upstream_defs.items()}
        return {
            'type': 'nginx_vhost_upstream',
            'domain': self.domain,
            'config_file': config_path,
            'upstreams': {
                name: {
                    'definition': defn,
                    'reachability': reachability.get(name, []),
                }
                for name, defn in upstream_defs.items()
            },
            'next_steps': [
                f"reveal nginx://{self.domain}  # full vhost summary",
            ],
        }

    def _element_auth(self, config_path: str, content: str, server_block: str) -> Dict[str, Any]:
        auth = _extract_auth_directives(server_block)
        return {
            'type': 'nginx_vhost_auth',
            'domain': self.domain,
            'config_file': config_path,
            'auth': auth,
            'next_steps': [
                f"reveal nginx://{self.domain}  # full vhost summary",
            ],
        }

    def _element_locations(self, config_path: str, content: str, server_block: str) -> Dict[str, Any]:
        locations = _extract_location_blocks(server_block)
        return {
            'type': 'nginx_vhost_locations',
            'domain': self.domain,
            'config_file': config_path,
            'locations': locations,
            'next_steps': [
                f"reveal nginx://{self.domain}           # full vhost summary",
                f"reveal nginx://{self.domain}/upstream  # upstream health",
            ],
        }

    def _element_config(self, config_path: str, content: str, server_block: str) -> Dict[str, Any]:
        return {
            'type': 'nginx_vhost_config',
            'domain': self.domain,
            'config_file': config_path,
            'server_block': server_block,
            'next_steps': [
                f"reveal nginx://{self.domain}  # structured summary",
                f"reveal {config_path} --check  # run N-rules on full file",
            ],
        }

    def get_available_elements(self) -> List[Dict[str, str]]:
        domain = self.domain or 'example.com'
        return [
            {'name': 'ports', 'description': 'Listening ports (80/443, SSL, redirect)',
             'example': f'reveal nginx://{domain}/ports'},
            {'name': 'upstream', 'description': 'proxy_pass targets and reachability',
             'example': f'reveal nginx://{domain}/upstream'},
            {'name': 'auth', 'description': 'auth_basic / auth_request directives',
             'example': f'reveal nginx://{domain}/auth'},
            {'name': 'locations', 'description': 'Location blocks with targets',
             'example': f'reveal nginx://{domain}/locations'},
            {'name': 'config', 'description': 'Full server block(s) for this domain',
             'example': f'reveal nginx://{domain}/config'},
        ]
