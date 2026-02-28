"""Nginx configuration file analyzer."""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from ..base import FileAnalyzer
from ..registry import register


# Pattern matching ACME challenge location paths
_ACME_PATH_RE = re.compile(r'^\.well-known[/\\]acme-challenge/?$')


def _check_nobody_access(path: str) -> Dict[str, Any]:
    """Check if the nobody user can read files at path.

    Checks standard Unix other-execute bits on every directory component
    and other-read on the final target.  Also tries getfacl for ACL entries
    that could grant access to nobody even without world bits.

    Returns:
        {'status': 'ok'|'denied'|'not_found'|'error',
         'message': str,
         'failing_path': str or None}
    """
    p = Path(path)
    if not p.exists():
        return {'status': 'not_found', 'message': f'Path not found: {path}',
                'failing_path': path}

    # Walk every directory component from / to target, checking execute (traverse) bit
    check = Path('/')
    for part in p.parts[1:]:
        check = check / part
        if not check.exists():
            return {'status': 'not_found',
                    'message': f'Component not found: {check}',
                    'failing_path': str(check)}
        if check.is_dir():
            mode = os.stat(check).st_mode
            can_traverse = bool(mode & 0o001)  # other-execute
            if not can_traverse:
                # Check extended ACL as fallback (Linux only)
                if not _acl_grants_nobody(str(check), 'x'):
                    return {
                        'status': 'denied',
                        'message': (
                            f'nobody cannot traverse {check} '
                            f'(mode {oct(mode)[-3:]}, no ACL entry)'
                        ),
                        'failing_path': str(check),
                    }

    # Final target: need read (+ execute for directories)
    mode = os.stat(p).st_mode
    if p.is_dir():
        can_read = bool(mode & 0o005)  # other r-x
    else:
        can_read = bool(mode & 0o004)  # other r--
    if not can_read:
        if not _acl_grants_nobody(str(p), 'r'):
            return {
                'status': 'denied',
                'message': (
                    f'nobody cannot read {p} '
                    f'(mode {oct(mode)[-3:]}, no ACL entry)'
                ),
                'failing_path': str(p),
            }

    return {'status': 'ok', 'message': 'nobody has read access', 'failing_path': None}


def _acl_grants_nobody(path: str, perm: str) -> bool:
    """Return True if getfacl shows nobody or other has the given permission.

    perm: 'r', 'w', or 'x'
    Returns False if getfacl is unavailable or raises any error.
    """
    try:
        result = subprocess.run(
            ['getfacl', '--omit-header', path],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode != 0:
            return False
        for line in result.stdout.splitlines():
            # Lines like: user:nobody:r-x  or  other::r-x
            if line.startswith(('user:nobody:', 'other::')):
                perms = line.split(':', 2)[-1] if ':' in line else ''
                if perm in perms:
                    return True
    except Exception:
        pass
    return False


@register('.conf', name='Nginx', icon='')
class NginxAnalyzer(FileAnalyzer):
    """Nginx configuration file analyzer.

    Extracts server blocks, locations, upstreams, and key directives.
    """

    def _parse_server_block(self, line_num: int) -> Dict[str, Any]:
        """Parse server block starting at line_num."""
        server_info = {
            'line': line_num,
            'name': 'unknown',
            'port': 'unknown',
            'domains': [],  # All domains from server_name directive
            'is_ssl': False,
        }
        # Look ahead for server_name and listen
        for j in range(line_num, min(line_num + 30, len(self.lines) + 1)):
            next_line = self.lines[j-1].strip()
            if next_line.startswith('server_name '):
                match = re.match(r'server_name\s+(.*?);', next_line)
                if match:
                    # Parse all domains (space-separated)
                    domains_str = match.group(1)
                    domains = [d.strip() for d in domains_str.split() if d.strip()]
                    server_info['domains'] = domains
                    server_info['name'] = domains[0] if domains else 'unknown'
            elif next_line.startswith('listen '):
                match = re.match(r'listen\s+(\S+)', next_line)
                if match:
                    port = match.group(1).rstrip(';')
                    server_info['port'] = self._format_port(port)
                    # Check if SSL
                    if '443' in port or 'ssl' in next_line.lower():
                        server_info['is_ssl'] = True
            elif 'ssl_certificate' in next_line:
                server_info['is_ssl'] = True
            if next_line == '}' and j > line_num:
                break
        # Add signature for display (shows port after name)
        server_info['signature'] = f" [{server_info['port']}]"
        return server_info

    def _format_port(self, port: str) -> str:
        """Format port string for display."""
        if port.startswith('443'):
            return '443 (SSL)'
        if port.startswith('80'):
            return '80'
        return port

    def _parse_location_block(self, line_num: int, path: str, current_server: Optional[Dict]) -> Dict[str, Any]:
        """Parse location block starting at line_num."""
        loc_info = {
            'line': line_num,
            'name': path,
            'path': path,
            'server': current_server['name'] if current_server else 'unknown'
        }
        # Look ahead for proxy_pass or root
        for j in range(line_num, min(line_num + 15, len(self.lines) + 1)):
            next_line = self.lines[j-1].strip()
            if next_line.startswith('proxy_pass '):
                match_proxy = re.match(r'proxy_pass\s+(.*?);', next_line)
                if match_proxy:
                    loc_info['target'] = match_proxy.group(1)
                    break
            elif next_line.startswith('root '):
                match_root = re.match(r'root\s+(.*?);', next_line)
                if match_root:
                    loc_info['target'] = f"static: {match_root.group(1)}"
                    break
        return loc_info

    def _parse_block_directives(self, block_name: str) -> Dict[str, str]:
        """Parse key-value directives from a top-level named block (e.g. http, events).

        Collects only direct-child directives (depth 1 inside the block),
        skipping nested blocks like server{}, map{}, upstream{}.
        Handles multi-line directives (e.g. log_format spanning multiple lines).

        Returns:
            Dict mapping directive name -> value string (without trailing semicolon).
        """
        directives: Dict[str, str] = {}
        depth = 0
        in_block = False
        block_pattern = re.compile(r'^' + re.escape(block_name) + r'\s*\{')
        pending_key: Optional[str] = None
        pending_parts: List[str] = []

        for line in self.lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            if not in_block and depth == 0 and block_pattern.match(stripped):
                in_block = True
                depth += stripped.count('{') - stripped.count('}')
                continue

            if in_block:
                # Accumulating a multi-line directive value
                if pending_key is not None:
                    pending_parts.append(stripped.rstrip(';').rstrip())
                    if ';' in stripped:
                        directives[pending_key] = ' '.join(pending_parts)
                        pending_key = None
                        pending_parts = []
                    continue  # don't update depth for continuation lines

                opens = stripped.count('{')
                closes = stripped.count('}')

                if depth == 1 and opens == 0 and not stripped.startswith('}'):
                    match = re.match(r'^([\w_-]+)\s+(.+)', stripped)
                    if match:
                        key, rest = match.group(1), match.group(2)
                        if ';' in stripped:
                            # Single-line directive
                            directives[key] = rest.rstrip(';').rstrip()
                        else:
                            # Start of multi-line directive
                            pending_key = key
                            pending_parts = [rest.rstrip()]

                depth += opens - closes
                if depth <= 0:
                    break  # exited the block

        return directives

    def _parse_main_directives(self) -> Dict[str, str]:
        """Parse key-value directives at the main (outermost) context — depth 0.

        Captures directives like user, worker_processes, error_log, pid in
        nginx.conf, and ssl_protocols, client_max_body_size, etc. in vhost
        include files. Skips block openers (events{}, http{}, map{}, etc.)

        Returns:
            Dict mapping directive name -> value string (without trailing semicolon).
        """
        directives: Dict[str, str] = {}
        depth = 0
        pending_key: Optional[str] = None
        pending_parts: List[str] = []

        for line in self.lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            if pending_key is not None:
                # Continuation of multi-line directive
                pending_parts.append(stripped.rstrip(';').rstrip())
                depth += stripped.count('{') - stripped.count('}')
                if ';' in stripped:
                    directives[pending_key] = ' '.join(pending_parts)
                    pending_key = None
                    pending_parts = []
                continue

            opens = stripped.count('{')
            closes = stripped.count('}')

            if depth == 0 and not stripped.startswith('}'):
                if opens == 0 and ';' in stripped:
                    # Single-line top-level directive
                    match = re.match(r'^([\w_-]+)\s+(.+?)\s*;', stripped)
                    if match:
                        directives[match.group(1)] = match.group(2)
                elif opens == 0:
                    # Possible start of multi-line top-level directive
                    match = re.match(r'^([\w_-]+)\s+(.+)', stripped)
                    if match:
                        pending_key = match.group(1)
                        pending_parts = [match.group(2).rstrip()]

            depth += opens - closes

        return directives

    def _parse_upstream_servers(self, line_num: int) -> Dict[str, Any]:
        """Parse upstream block body, extracting server entries and key settings.

        Args:
            line_num: 1-based line number where the upstream block starts.

        Returns:
            Dict with 'servers' (list of dicts with 'address' + optional 'params')
            and 'settings' (dict of other directives like keepalive).
        """
        servers: List[Dict[str, str]] = []
        settings: Dict[str, str] = {}
        depth = 0

        for i in range(line_num - 1, len(self.lines)):
            line = self.lines[i]
            stripped = line.strip()
            depth += stripped.count('{') - stripped.count('}')

            if depth <= 0 and i >= line_num:
                break

            if not stripped or stripped.startswith('#') or '{' in stripped:
                continue

            if stripped.startswith('server '):
                match = re.match(r'server\s+(\S+)(.*?)\s*;', stripped)
                if match:
                    addr = match.group(1)
                    params = match.group(2).strip()
                    entry: Dict[str, str] = {'address': addr}
                    if params:
                        entry['params'] = params
                    servers.append(entry)
            elif ';' in stripped:
                m = re.match(r'^([\w_-]+)\s+(.+?)\s*;', stripped)
                if m:
                    settings[m.group(1)] = m.group(2)

        return {'servers': servers, 'settings': settings}

    def _try_parse_map_block(self, stripped: str) -> Optional[Dict[str, str]]:
        """Try to parse map block source/target variables from line."""
        match = re.match(r'map\s+(\S+)\s+(\S+)\s*\{', stripped)
        if match:
            return {'source': match.group(1), 'target': match.group(2)}
        return None

    def _is_top_level_comment(self, stripped: str, line_num: int) -> bool:
        """Check if line is a top-level comment header."""
        return stripped.startswith('#') and line_num <= 10 and len(stripped) > 3

    def _is_server_block_start(self, stripped: str) -> bool:
        """Check if line starts a server block."""
        return 'server {' in stripped or stripped.startswith('server {')

    def _try_parse_location_block(self, stripped: str) -> Optional[str]:
        """Try to parse location path from line."""
        match = re.match(r'location\s+(.+?)\s*\{', stripped)
        return match.group(1) if match else None

    def _try_parse_upstream_block(self, stripped: str) -> Optional[str]:
        """Try to parse upstream name from line."""
        match = re.match(r'upstream\s+(\S+)\s*\{', stripped)
        return match.group(1) if match else None

    def _process_comment(self, comments: List, stripped: str, line_num: int) -> None:
        """Process and add comment to list if it's a top-level header."""
        if self._is_top_level_comment(stripped, line_num):
            comments.append({'line': line_num, 'text': stripped[1:].strip()})

    def _process_server_block(self, servers: List, line_num: int) -> tuple:
        """Process server block and return (server_info, should_enter_server)."""
        server_info = self._parse_server_block(line_num)
        servers.append(server_info)
        return server_info, True

    def _process_location_block(self, locations: List, stripped: str, line_num: int,
                                 in_server: bool, brace_depth: int, current_server: Optional[Dict]) -> None:
        """Process location block if inside server context."""
        if in_server and brace_depth > 0 and 'location ' in stripped:
            location_path = self._try_parse_location_block(stripped)
            if location_path:
                loc_info = self._parse_location_block(line_num, location_path, current_server)
                locations.append(loc_info)

    def _process_upstream_block(self, upstreams: List, stripped: str, line_num: int) -> None:
        """Process upstream block if detected, extracting server entries and settings."""
        if 'upstream ' in stripped and '{' in stripped:
            upstream_name = self._try_parse_upstream_block(stripped)
            if upstream_name:
                detail = self._parse_upstream_servers(line_num)
                servers = detail['servers']
                settings = detail['settings']
                if servers:
                    first = servers[0]['address']
                    sig = f" [{first}]" if len(servers) == 1 else f" [{first}, +{len(servers)-1} more]"
                else:
                    sig = ''
                upstreams.append({
                    'line': line_num,
                    'name': upstream_name,
                    'servers': servers,
                    'settings': settings,
                    'signature': sig,
                })

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract nginx config structure."""
        servers: List[Dict[str, Any]] = []
        locations: List[Dict[str, Any]] = []
        upstreams: List[Dict[str, Any]] = []
        maps: List[Dict[str, Any]] = []
        comments: List[Dict[str, Any]] = []

        current_server = None
        in_server = False
        brace_depth = 0

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            brace_depth += stripped.count('{') - stripped.count('}')

            self._process_comment(comments, stripped, i)

            if self._is_server_block_start(stripped):
                current_server, in_server = self._process_server_block(servers, i)
            else:
                self._process_location_block(locations, stripped, i, in_server, brace_depth, current_server)
                self._process_upstream_block(upstreams, stripped, i)
                if 'map ' in stripped and '{' in stripped:
                    map_info = self._try_parse_map_block(stripped)
                    if map_info:
                        maps.append({
                            'line_start': i,
                            'line_end': i,
                            'name': f"{map_info['source']} → {map_info['target']}",
                            'source_var': map_info['source'],
                            'target_var': map_info['target'],
                        })

            # Reset server context when we exit server block
            if in_server and brace_depth == 0:
                in_server = False
                current_server = None

        main_directives = self._parse_main_directives()
        http_directives = self._parse_block_directives('http')
        events_directives = self._parse_block_directives('events')

        result: Dict[str, Any] = {
            'contract_version': '1.0',
            'type': 'nginx_structure',
            'source': str(self.path),
            'source_type': 'file',
            'comments': comments,
        }
        if main_directives:
            result['main_directives'] = main_directives
        result['servers'] = servers
        result['locations'] = locations
        result['upstreams'] = upstreams
        if maps:
            result['maps'] = maps
        if http_directives:
            result['directives'] = http_directives
        if events_directives:
            result['events_directives'] = events_directives

        # N3: filter to a single domain if requested
        domain_filter = kwargs.get('domain')
        if domain_filter:
            result = self._filter_structure_by_domain(result, domain_filter)

        return result

    def _filter_structure_by_domain(self, structure: Dict[str, Any], domain: str) -> Dict[str, Any]:
        """Return structure filtered to server blocks matching domain (N3)."""
        all_servers = structure.get('servers', [])
        matching = [
            s for s in all_servers
            if domain in s.get('domains', []) or s.get('name') == domain
        ]
        if not matching:
            filtered = dict(structure)
            filtered['servers'] = []
            filtered['locations'] = []
            filtered['_domain_filter'] = domain
            filtered['_domain_not_found'] = True
            return filtered

        matching_names = {s['name'] for s in matching}
        matching_locs = [
            loc for loc in structure.get('locations', [])
            if loc.get('server') in matching_names
        ]
        filtered = dict(structure)
        filtered['servers'] = matching
        filtered['locations'] = matching_locs
        filtered['_domain_filter'] = domain
        return filtered

    def extract_ssl_domains(self) -> List[str]:
        """Extract all SSL-enabled domains from nginx config.

        Returns:
            List of unique domain names from SSL server blocks.
            Filters out: localhost, _, wildcards (*.example.com),
            IP addresses, and non-FQDN values.
        """
        structure = self.get_structure()
        domains = set()

        for server in structure.get('servers', []):
            # Only process SSL-enabled server blocks
            if not server.get('is_ssl'):
                continue

            for domain in server.get('domains', []):
                # Skip non-domain values
                if not domain or domain == '_' or domain == 'localhost':
                    continue
                # Skip wildcards (can't SSL check *.example.com)
                if domain.startswith('*.'):
                    continue
                # Skip IP addresses
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', domain):
                    continue
                # Skip non-FQDN (no dot)
                if '.' not in domain:
                    continue
                domains.add(domain)

        return sorted(domains)

    def _parse_location_root(self, line_num: int) -> Optional[str]:
        """Return the root or alias directive value from a location block body."""
        for j in range(line_num, min(line_num + 20, len(self.lines) + 1)):
            line = self.lines[j - 1].strip()
            m = re.match(r'^(?:root|alias)\s+(.*?)\s*;', line)
            if m:
                return m.group(1).strip('"\'')
            if line == '}':
                break
        return None

    def _parse_server_root(self, server_line: int) -> Optional[str]:
        """Return the root directive value from a server block."""
        depth = 0
        for j in range(server_line - 1, min(server_line + 200, len(self.lines))):
            line = self.lines[j].strip()
            depth += line.count('{') - line.count('}')
            m = re.match(r'^root\s+(.*?)\s*;', line)
            if m and depth == 1:
                return m.group(1).strip('"\'')
            if depth <= 0 and j > server_line:
                break
        return None

    def _find_server_start_for_location(self, location_line: int) -> Tuple[int, Dict]:
        """Find the server block that contains the given location line number."""
        best_start = 0
        best_info: Dict = {}
        depth = 0
        in_server = False
        current_start = 0
        current_info: Dict = {}

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            depth += stripped.count('{') - stripped.count('}')
            if self._is_server_block_start(stripped):
                current_start = i
                current_info, _ = self._process_server_block([], i)
                in_server = True
            if in_server and i <= location_line:
                best_start = current_start
                best_info = current_info
            if in_server and depth == 0:
                in_server = False
        return best_start, best_info

    def extract_acme_roots(self) -> List[Dict[str, Any]]:
        """Find ACME challenge location blocks and check nobody ACL on each root.

        Returns a list of dicts (one per ACME location found):
            domain      – first server_name from the parent server block
            acme_path   – resolved root/alias path for the challenge location
            acl_status  – 'ok', 'denied', 'not_found', or 'unknown'
            acl_message – human-readable detail
            line        – line number in config
        """
        results: List[Dict[str, Any]] = []
        seen: set = set()

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            # Match: location [modifier] /.well-known/acme-challenge[/] {
            m = re.match(r'^location\s+(?:=\s+|~\*?\s+|^~\s+)?(.+?)\s*\{', stripped)
            if not m:
                continue
            path = m.group(1).strip().lstrip('/')
            if not _ACME_PATH_RE.match(path):
                continue

            # Find parent server block
            server_start, server_info = self._find_server_start_for_location(i)
            domain = server_info.get('name', 'unknown') if server_info else 'unknown'

            # Resolve root: location-level first, then server-level
            root = self._parse_location_root(i)
            if not root and server_start:
                root = self._parse_server_root(server_start)

            key = (domain, root)
            if key in seen:
                continue
            seen.add(key)

            if root:
                acl = _check_nobody_access(root)
            else:
                acl = {'status': 'unknown', 'message': 'no root directive found',
                       'failing_path': None}

            results.append({
                'domain': domain,
                'acme_path': root or '(not found)',
                'acl_status': acl['status'],
                'acl_message': acl['message'],
                'acl_failing_path': acl.get('failing_path'),
                'line': i,
            })

        return results

    def extract_docroot_acl(self) -> List[Dict[str, Any]]:
        """Check nobody ACL for all root directives found in the config.

        Returns a list of dicts:
            domain      – first server_name from parent server block
            root        – root path
            acl_status  – 'ok', 'denied', 'not_found', or 'error'
            acl_message – human-readable detail
            line        – line number of the root directive
        """
        results: List[Dict[str, Any]] = []
        seen: set = set()

        current_server_info: Dict = {}
        current_server_start = 0
        depth = 0
        in_server = False

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            depth += stripped.count('{') - stripped.count('}')

            if self._is_server_block_start(stripped):
                current_server_info, in_server = self._process_server_block([], i)
                current_server_start = i

            if in_server and depth == 0:
                in_server = False

            m = re.match(r'^root\s+(.*?)\s*;', stripped)
            if not m:
                continue
            root = m.group(1)
            domain = current_server_info.get('name', 'unknown') if current_server_info else 'unknown'

            if root in seen:
                continue
            seen.add(root)

            acl = _check_nobody_access(root)
            results.append({
                'domain': domain,
                'root': root,
                'acl_status': acl['status'],
                'acl_message': acl['message'],
                'acl_failing_path': acl.get('failing_path'),
                'line': i,
            })

        return results

    def detect_location_conflicts(self) -> List[Dict[str, Any]]:
        """Detect nginx location blocks where prefix-overlap could cause routing surprises (N2).

        nginx uses longest-prefix-wins for non-regex locations, and regex locations
        are evaluated in order. Conflicts arise when:
          - Two non-regex locations where one is a strict prefix of the other
            (different servers, or same server from different include files)
          - A non-regex location and a regex location match the same prefix

        Returns a list of conflict dicts:
            server      – server_name of the affected server block
            location_a  – {line, path} of first location
            location_b  – {line, path} of second location
            type        – 'prefix_overlap' or 'regex_shadows_prefix'
            severity    – 'warning' or 'info'
            note        – human-readable explanation
        """
        structure = self.get_structure()
        locations = structure.get('locations', [])
        conflicts: List[Dict[str, Any]] = []

        # Group by server
        from collections import defaultdict
        by_server: Dict[str, List[Dict]] = defaultdict(list)
        for loc in locations:
            by_server[loc.get('server', 'unknown')].append(loc)

        for server_name, locs in by_server.items():
            # Separate regex vs non-regex
            regex_locs = [l for l in locs if re.match(r'^~\*?\s+', l['path'])]
            prefix_locs = [l for l in locs if not re.match(r'^~\*?\s+', l['path'])]

            # Check prefix-prefix overlaps
            for i, loc_a in enumerate(prefix_locs):
                for loc_b in prefix_locs[i + 1:]:
                    pa = loc_a['path'].rstrip('/')
                    pb = loc_b['path'].rstrip('/')
                    shorter, longer = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
                    shorter_loc = loc_a if loc_a['path'].rstrip('/') == shorter else loc_b
                    longer_loc = loc_a if shorter_loc is loc_b else loc_b

                    if shorter and longer.startswith(shorter):
                        # Only flag if they differ (not identical paths)
                        if shorter != longer:
                            note = (
                                f'"{shorter_loc["path"]}" (line {shorter_loc["line"]}) is a '
                                f'prefix of "{longer_loc["path"]}" (line {longer_loc["line"]}) — '
                                f'nginx picks the longer match; requests to "{shorter}/" that '
                                f'don\'t match "{longer}" fall through to the shorter block'
                            )
                            conflicts.append({
                                'server': server_name,
                                'location_a': {'line': shorter_loc['line'], 'path': shorter_loc['path']},
                                'location_b': {'line': longer_loc['line'], 'path': longer_loc['path']},
                                'type': 'prefix_overlap',
                                'severity': 'info',
                                'note': note,
                            })

            # Check regex vs prefix conflicts
            for rloc in regex_locs:
                raw_pattern = re.sub(r'^~\*?\s+', '', rloc['path'])
                for ploc in prefix_locs:
                    prefix_path = ploc['path'].rstrip('/')
                    if not prefix_path:
                        continue
                    # Check if the regex pattern could match the prefix path
                    try:
                        # Test both bare path and path/ so that patterns like
                        # /static/.* match against the /static prefix location
                        test_paths = [prefix_path, prefix_path + '/']
                        if any(re.search(raw_pattern, tp, re.IGNORECASE) for tp in test_paths):
                            note = (
                                f'regex location "{rloc["path"]}" (line {rloc["line"]}) '
                                f'may match requests also handled by prefix '
                                f'"{ploc["path"]}" (line {ploc["line"]}) — '
                                f'regex locations are evaluated after longest-prefix match; '
                                f'verify intended priority'
                            )
                            conflicts.append({
                                'server': server_name,
                                'location_a': {'line': ploc['line'], 'path': ploc['path']},
                                'location_b': {'line': rloc['line'], 'path': rloc['path']},
                                'type': 'regex_shadows_prefix',
                                'severity': 'warning',
                                'note': note,
                            })
                    except re.error:
                        pass  # Skip malformed regex patterns

        return conflicts

    def _find_server_line(self, name: str) -> Optional[int]:
        """Find line number of server block with given server_name."""
        for i, line in enumerate(self.lines, 1):
            if 'server {' in line or line.strip().startswith('server {'):
                for j in range(i, min(i + 20, len(self.lines) + 1)):
                    if f'server_name {name}' in self.lines[j-1]:
                        return i
        return None

    def _find_block_line(self, pattern: str) -> Optional[int]:
        """Find line number matching given regex pattern."""
        for i, line in enumerate(self.lines, 1):
            if re.search(pattern, line):
                return i
        return None

    def _find_closing_brace(self, start_line: int) -> int:
        """Find matching closing brace for block starting at start_line."""
        brace_depth = 0
        for i in range(start_line - 1, len(self.lines)):
            line = self.lines[i]
            brace_depth += line.count('{') - line.count('}')
            if brace_depth == 0 and i >= start_line:
                return i + 1
        return start_line

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a server or location block.

        Args:
            element_type: 'server', 'location', or 'upstream'
            name: Name to find (server_name, location path, or upstream name)

        Returns:
            Dict with block content
        """
        start_line = None

        if element_type == 'server':
            start_line = self._find_server_line(name)
        elif element_type == 'location':
            pattern = rf'location\s+{re.escape(name)}\s*\{{'
            start_line = self._find_block_line(pattern)
        elif element_type == 'upstream':
            pattern = rf'upstream\s+{re.escape(name)}\s*\{{'
            start_line = self._find_block_line(pattern)

        if not start_line:
            return super().extract_element(element_type, name)

        end_line = self._find_closing_brace(start_line)
        source = '\n'.join(self.lines[start_line-1:end_line])

        return {
            'name': name,
            'line_start': start_line,
            'line_end': end_line,
            'source': source,
        }

    def get_error_log_path(self) -> Optional[str]:
        """Return the nginx error_log path from the config, or None if not specified.

        Checks main context directives first (nginx.conf).  For cPanel user
        vhost configs the error_log is not present inline; callers should fall
        back to common paths such as /var/log/nginx/error.log.
        """
        main = self._parse_main_directives()
        raw = main.get('error_log', '')
        if not raw:
            return None
        # error_log may be "path level" — strip the level token and whitespace
        parts = raw.split()
        return parts[0] if parts else None

    def diagnose_acme_errors(
        self, log_path: str, tail_lines: int = 5000
    ) -> List[Dict[str, Any]]:
        """Scan an nginx error log for ACME / SSL failure patterns per domain.

        Reads the last *tail_lines* lines of *log_path* and groups error events
        by domain and pattern type.  Only SSL domains present in this config
        file are considered.

        Pattern types detected:
            permission_denied   – open() on /.well-known/ path returned 13
            not_found           – open() on /.well-known/ path returned 2 (ENOENT)
            ssl_error           – SSL_CTX_use_certificate or handshake failures

        Returns:
            List of dicts sorted by domain then pattern:
                domain      – server_name from this config
                pattern     – 'permission_denied' | 'not_found' | 'ssl_error'
                count       – number of matching log lines
                last_seen   – raw timestamp string of most recent match
                sample      – one representative log line (first 120 chars)
        """
        import os

        domains = set(self.extract_ssl_domains())
        if not domains:
            return []

        # Patterns: (pattern_key, compiled_regex)
        PATTERNS = [
            ('permission_denied', re.compile(
                r'open\(\)\s+"[^"]*\.well-known[^"]*"\s+failed.*Permission denied',
                re.IGNORECASE,
            )),
            ('not_found', re.compile(
                r'open\(\)\s+"[^"]*\.well-known[^"]*"\s+failed.*No such file',
                re.IGNORECASE,
            )),
            ('ssl_error', re.compile(
                r'(SSL_CTX_use_certificate|SSL handshake|ssl_handshake|'
                r'no "ssl_certificate"|cannot load certificate)',
                re.IGNORECASE,
            )),
        ]

        # Read last tail_lines lines from the log
        try:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as fh:
                all_lines = fh.readlines()
        except OSError:
            return []

        recent_lines = all_lines[-tail_lines:]

        # Group results: key = (domain, pattern_key)
        hits: Dict[tuple, Dict] = {}

        for raw_line in recent_lines:
            line = raw_line.rstrip()

            # Try to extract server name from nginx error log line.
            # Format: 2026/02/15 03:21:17 [error] … server: example.com, request: …
            server_match = re.search(r'server:\s+([^\s,]+)', line)
            line_domain = server_match.group(1).lower() if server_match else None

            for pattern_key, regex in PATTERNS:
                if not regex.search(line):
                    continue

                # Which domains does this line belong to?
                matched_domains: set = set()
                if line_domain and line_domain in domains:
                    matched_domains.add(line_domain)
                else:
                    # Fallback: scan line for any known domain substring
                    for d in domains:
                        if d in line:
                            matched_domains.add(d)

                if not matched_domains:
                    continue

                # Extract timestamp (first token: YYYY/MM/DD HH:MM:SS)
                ts_match = re.match(r'^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})', line)
                timestamp = ts_match.group(1) if ts_match else ''

                for d in matched_domains:
                    key = (d, pattern_key)
                    if key not in hits:
                        hits[key] = {
                            'domain': d,
                            'pattern': pattern_key,
                            'count': 0,
                            'last_seen': timestamp,
                            'sample': line[:120],
                        }
                    hits[key]['count'] += 1
                    if timestamp > hits[key]['last_seen']:
                        hits[key]['last_seen'] = timestamp

        return sorted(hits.values(), key=lambda r: (r['domain'], r['pattern']))
